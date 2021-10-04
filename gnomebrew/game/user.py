"""
Manages User Data for the game
"""
from os.path import join
from typing import Callable

from gnomebrew import mongo, login_manager, socketio
from flask_login import UserMixin
from flask import render_template
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import re
from functools import reduce

_GAME_ID_RESOLVERS = dict()
_UPDATE_RESOLVERS = dict()
_UPDATE_LISTENERS = dict()
_USER_ASSERTIONS = list()
_FRONTEND_DATA_RESOLVERS = dict()
_HTML_DIRECT_IDS = dict()
_HTML_ID_RULES = dict()
_USR_CACHE = dict()


def get_resolver(type: str):
    """
    Registers a function to resolve a game resource identifier.
    :param type: The type of this resolver. A unique identifier for the first part of a game-id, e.g. `data`
    :return: The registration wrapper. To be used as an annotation on a function that will serve as the `get` logic.
    The function will resolve game_ids leading with `type` and is expected to have these parameters:
    * `user: User` user for which the ID is to be resolved
    * `game_id: str` full ID (incl. first part that's covered through the name)
    """
    global _GAME_ID_RESOLVERS
    assert type not in _GAME_ID_RESOLVERS

    def wrapper(fun: Callable):
        _GAME_ID_RESOLVERS[type] = fun
        return fun

    return wrapper


def update_resolver(type: str):
    """
    Used to register a function as an update resolver.
    :param type:    The leading type of the update resolver, e.g. `data`.
    :return:    The registration wrapper. Expects a function that takes:
    * `user`: The firing user.
    * `game_id`: A game id
    * `update`: Update data given via the `update` function
    * `**kwargs`
    The function is expected to **return a dict** which's keys are the updated elements.
    This marks the updates that are to be used for registered `frontend_id_resolver`s
    """
    global _UPDATE_RESOLVERS
    assert type not in _UPDATE_RESOLVERS

    def wrapper(fun: Callable):
        _UPDATE_RESOLVERS[type] = fun

    return wrapper


def update_listener(game_id: str):
    """
    Registers a listener function that fires whenever a certain game_id is updated.
    :param game_id: A game ID
    :return:        A registration wrapper. Expects a function. Whenever the given `game_id` is updated via the
                    `user.update(...)` function, all registered listeners will be informed by having their function
                    called.
                    The function should expect two parameters:

                    * `user`: The user from which the update originated.
                    * `update`: The update data
                    The function should be 'lightweight', as - depending on the game id - it might be called quite
                    often. Therefore, the function should only make time-intense calls (e.g. subsequent `get`/`update`
                    calls) when strictly necessary. The function receives the update data directly as a paramter and
                    that should be enough.
    """
    global _UPDATE_LISTENERS
    if game_id not in _UPDATE_LISTENERS:
        _UPDATE_LISTENERS[game_id] = list()

    def wrapper(fun: Callable):
        _UPDATE_LISTENERS[game_id].append(fun)

    return wrapper


def user_assertion(assertion_script: Callable):
    """
    Registers a function as an assertion script.
    :param assertion_script:    A callable that takes one `User` parameter and raises an `AssertionError` if any
                                part of the user's data is problematic for the game logic.
    """
    global _USER_ASSERTIONS
    _USER_ASSERTIONS.append(assertion_script)


def frontend_id_resolver(game_id_regex):
    """
    Registers a resolver when used as @ annotation before a function. The function must take two arguments:

    * `user`: a `User` object
    * `data`: a `dict` object containing the update data
    :param game_id_regex: A `str` that represents a regex. If the regex matches the Game-ID path of the update, this
    resolver will be called
    """

    def wrapper(fun: Callable):
        global _FRONTEND_DATA_RESOLVERS
        assert game_id_regex not in _FRONTEND_DATA_RESOLVERS
        _FRONTEND_DATA_RESOLVERS[re.compile(game_id_regex)] = fun

    return wrapper


def html_generator(base_id, is_generic=False):
    """
    Registers a resolver for HTML code.
    :param is_generic:  if this is `True`, will call for any call of `html.base_id.*` instead of only `hmtl.base_id`
    :param base_id:     The ID this html generator will generate HTML for
    :return: The wrapper for the function that will cover the `html_id`. Expects a function that has a `user: User`
            parameter and a game_id kwarg.
    """

    def wrapper(fun: Callable):
        global _HTML_DIRECT_IDS
        assert base_id not in _HTML_DIRECT_IDS
        _HTML_DIRECT_IDS[base_id] = dict()
        _HTML_DIRECT_IDS[base_id]['fun'] = fun
        _HTML_DIRECT_IDS[base_id]['generic'] = is_generic
        return fun

    return wrapper


class User(UserMixin):
    """
    User Class for Gnomebrew.
    Models all relevant data to play and modify a user's play data.
    """

    def __init__(self, username):
        """
        Init.
        :param db_data: Data stored in MongoDB database for this user.
        """
        self.username = username

    def __repr__(self):
        return f"<user {self.username}>"

    # +++++++++++++++++++++ User MGMT Methods +++++++++++++++++++++

    def check_pw(self, pw):
        """
        Tests if a given PW is correct
        :param pw: Password
        :return: True if PW matches saved hash. Otherwise false
        """
        res = mongo.db.users.find_one({"username": self.username}, {"pw_hash": 1})
        return check_password_hash(res['pw_hash'], pw)

    def update_pw(self, new_pw):
        """
        Updates the user password without any checks
        :param new_pw: new pw
        """
        mongo.db.users.update_one({"username": self.username}, {"$set": {"pw_hash": generate_password_hash(new_pw)}})

    def get_name(self):
        """
        Returns username
        :return: username
        """
        return self.get_id()

    def get_id(self):
        return self.username

    def is_operator(self):
        """
        :return: `True`, if this user is marked as operator and such has access to administrative game features.
                 Otherwise, `False`.
        """
        res = mongo.db.users.find_one({"username": self.get_id()}, {'operator': 1})
        try:
            return res['operator']
        except KeyError:
            return False

    @staticmethod
    def create_user(username: str, pw: str):
        """
        This process creates a new user entity in the Gnomebrew Game.
        :param username:    Username. Must be free.
        :param pw:          Password (unhashed). Will be stored is hashed format.
        :return:            Reference to a user object representing the generated user.
        """
        # Ensure that username does not exist already
        assert not User.user_exists(username)

        # Create Bare-Bones user data
        usr_data = dict()
        usr_data['username'] = username
        usr_data['pw_hash'] = generate_password_hash(pw)

        # Write to DB to ensure persistence
        mongo.db.users.insert_one(usr_data)

        # Create user handle
        user = User(username)
        from gnomebrew.admin import reset_game_data
        reset_game_data(user)

        return user

    @staticmethod
    def user_exists(username: str):
        """
        Checks if a given user exists.
        :param username:    a username to check
        :return:        `True` if the user exists, otherwise `False`
        """
        return mongo.db.users.find_one({"username": username})

    # +++++++++++++++++++++ Game Interface Methods +++++++++++++++++++++

    def get(self, game_id: str, **kwargs):
        """
        Universal Method to retrieve an input with Game ID
        :param game_id: The ID of a game item, e.g. `attr.well.slots` or `data.storage.content`
        :return:        The result of the query
        :return:        The result of the query
        """
        id_type = game_id.split('.')[0]
        if id_type not in _GAME_ID_RESOLVERS:
            raise Exception(f"Don't recognize game IDs starting with {id_type}: {game_id}")
        return _GAME_ID_RESOLVERS[id_type](user=self, game_id=game_id, **kwargs)

    def update(self, game_id: str, update, **kwargs):
        """
        Updates Game Data to the database *and* broadcasts the data changes to potentially listening clients.
        Calling this function is the only way a game data should be updated, since this ensures integrity from database
        to frontend.
        :param game_id:    User Data path, e.g. `data.storage.content'
        :param update:  The update data
        :param kwargs:

        * `is_bulk`: If True, the update will be split the paths in keys
        * `command`: Default '$set' - mongo_db command to use for the update
        * `suppress_frontend`: If this is set `True`, no frontend updates will be run.
        """
        id_type = game_id.split('.')[0]
        assert id_type in _UPDATE_RESOLVERS
        mongo_command, res = _UPDATE_RESOLVERS[id_type](user=self, game_id=game_id, update=update, **kwargs)

        # If any update listeners are registered for this game ID, inform update listeners of the update
        global _UPDATE_LISTENERS
        for gid in res:
            if gid in _UPDATE_LISTENERS:
                for listener in _UPDATE_LISTENERS[gid]:
                    listener(user=self,
                             update=res,
                             mongo_command=mongo_command)

        if 'suppress_frontend' in kwargs and kwargs['suppress_frontend']:
            return
        self._data_update_to_frontends(mongo_command, res)

    def _data_update_to_frontends(self, mongo_command, command_content):
        """
        Helper function.
        Takes in the MongoDB content update and defines what/how to update the frontends
        :return:
        """
        for path in command_content:
            if type(command_content[path]) is datetime:
                command_content[path] = command_content[path].strftime('%d %b %Y %H:%M:%S') + ' GMT'

            individual_data = {path: command_content[path]}

            found_match = False
            for regex in _FRONTEND_DATA_RESOLVERS:
                if regex.match(path):
                    # Found a match. Execute handler instead of default.
                    found_match = True
                    _FRONTEND_DATA_RESOLVERS[regex](user=self, data=individual_data, game_id=path, command=mongo_command)
                    break

    def frontend_update(self, update_type: str, update_data: dict):
        """
        Called to send updates from server to user frontends.
        This function wraps a `socketio` call.
        :param update_type: Type of the update (for `.on(...)`)
        :param update_data: Data to be sent to all active frontends
        """
        socketio.emit(update_type, update_data, json=True, to=self.username)

    def get_unlocked_station_list(self):
        """

        :return:
        """
        return mongo.db.users.find_one({"username": self.username},
                                       {'data': 1, '_id': 0})['data'].keys()

    def get_game_data(self):
        """
        Returns all game data of this user
        :return:    All Game data as a `dict`
        """
        return mongo.db.users.find_one({"username": self.username},
                                       {'data': 1, '_id': 0})['data']

    @staticmethod
    def game_integrity_assertions(user):
        """
        Internal utility function.
        Runs any game assertions that are registered in game on a given user.
        :raise: Raises an `AssertionError` if anything about the user's data is not functional.
        """
        for assertion in _USER_ASSERTIONS:
            assertion(user)


@login_manager.user_loader
def load_user(user_id):
    """
    user Loader Callback.
    Loads user data from MongoDB database.
    :param user_id: User ID as <b>unicode</b>. Username
    :return: None if user_id does not exist. Otherwise returns User class
    """
    usr_data = mongo.db.users.find_one({"username": user_id})
    if usr_data is None:
        return None
    return User(user_id)


# STANDARD RESOLVERS

@get_resolver('data')
def data(user: User, game_id: str, **kwargs):
    """
    Evaluates a game-data ID and returns the value
    :param user:
    :param game_id:  User Data path, e.g. `data.storage.content'
    :return:    The value of this game data (KeyError if it does not exist)
    """
    splits = game_id.split('.')
    result = mongo.db.users.find_one({"username": user.get_id()}, {game_id: 1, '_id': 0})
    assert result
    try:
        for split in splits:
            result = result[split]
    except KeyError as e:
        # A key error means the resource is not (yet) written in the user data.
        # If the 'default' kwarg is used, instead of an error, return the default value
        if 'default' in kwargs:
            return kwargs['default']
        else:
            raise e
    return result


@get_resolver('html')
def html(game_id: str, user: User, **kwargs):
    splits = game_id.split('.')
    if game_id in _HTML_DIRECT_IDS:
        # Most simple case. Direct ID is registered
        return _HTML_DIRECT_IDS[game_id]['fun'](game_id=game_id, user=user, **kwargs)
    # No direct match. Check if any generic-type rules match
    rule_matches = [html_res_data['fun']
                       for html_base, html_res_data in _HTML_DIRECT_IDS.items()
                       if html_res_data['generic'] and game_id.startswith(html_base)]
    if not rule_matches:
        raise Exception(f"ID {game_id} can not be resolved with registered resolvers.")
    else:
        # Arbitrarily execute the first match. There should only be one match in this list in any case.
        return rule_matches[0](game_id=game_id, user=user, **kwargs)



@update_resolver('data')
def game_data_update(user: User, game_id: str, update, **kwargs):
    splits = game_id.split('.')
    assert splits[0] == 'data'
    if 'is_bulk' in kwargs and kwargs['is_bulk']:
        # Update is a dict. We don't want delete the other entries in here
        # Only for ONE layer though
        command_content = dict()
        for key in update:
            command_content[game_id + '.' + key] = update[key]
    else:
        command_content = {game_id: update}
    mongo_command = kwargs['command'] if 'command' in kwargs else '$set'
    mongo.db.users.update_one({"username": user.get_id()}, {mongo_command: command_content})
    # Also update the currently attached users.
    return mongo_command, command_content
