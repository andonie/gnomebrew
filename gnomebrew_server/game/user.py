"""
Manages User Data for the game
"""
from typing import Callable

from gnomebrew_server import mongo, login_manager, socketio
from gnomebrew_server.game.static_data import Upgrade, Station, Recipe, Item
from flask_login import UserMixin
from flask import render_template
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import re
from functools import reduce

_GAME_ID_RESOLVERS = dict()
_USER_ASSERTIONS = list()
_FRONTEND_DATA_RESOLVERS = dict()
_HTML_GENERATOR_RESOLVERS = dict()
_USR_CACHE = dict()


def game_id_resolver(resolver: Callable):
    """
    Registers a function to resolve a game resource identifier
    :param resolver:    The function to be called. `resolver.__name__` resolves identifiers that start with with
                        this name. E.g. `def attr(...)` resolves `attr.<...>`. Function parameters to implement:
                        * `user: User` user for which the ID is to be resolved
                        * `game_id: str` full ID (incl. first part that's covered through the name)
    """
    global _GAME_ID_RESOLVERS
    prefix = resolver.__name__
    assert prefix not in _GAME_ID_RESOLVERS
    _GAME_ID_RESOLVERS[prefix] = resolver


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


def html_generator(html_id):
    """
    Registers a resolver for HTML code.
    :param html_id:     The ID this html generator will generate HTML for
    :return: The wrapper for the function that will cover the `html_id`. Expects a function that has a `user: User`
            parameter.
    """

    def wrapper(fun: Callable):
        global _HTML_GENERATOR_RESOLVERS
        assert html_id not in _HTML_GENERATOR_RESOLVERS
        _HTML_GENERATOR_RESOLVERS[html_id] = fun

    return wrapper


class User(UserMixin):
    STARTUP_GAMEDATA = {
        'storage': {
            'content': {
                'gold': 200,
                'wood': 10
            }
        },
        'tavern': {
            'queue': [],
            'prices': {
                'beer': 1
            },
            'patrons': 0
        },
        'brewery': {

        },
        'workshop': {
            'upgrades': []
        }
    }

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

    @staticmethod
    def create_user(username: str, pw: str, additional_data: dict):
        """
        This process creates a new user entity in the Gnomebrew Game.
        :param username:    Username. Must be free.
        :param pw:          Password (unhashed). Will be stored is hashed format.
        :param additional_data: Dict containining additional data.
        :return:            Reference to a user object representing the generated user.
        """
        # Ensure that username does not exist already
        assert not mongo.db.users.find_one({"username": username})

        # Create Bare-Bones user data
        usr_data = dict()
        usr_data['username'] = username
        usr_data['pw_hash'] = generate_password_hash(pw)
        usr_data.update(additional_data)

        # Instantiate with Starting data
        usr_data['data'] = User.STARTUP_GAMEDATA

        # Write to DB to ensure persistence
        mongo.db.users.insert_one(usr_data)

        return User(username)

    # +++++++++++++++++++++ Game Interface Methods +++++++++++++++++++++

    def get(self, game_id: str, **kwargs):
        """
        Universal Method to retrieve an input with Game ID
        :param game_id: The ID of a game item, e.g. `attr.well.slots` or `data.storage.content`
        :return:        The result of the query
        :return:        The result of the query
        """
        id_type = game_id.split('.')[0]
        assert id_type in _GAME_ID_RESOLVERS
        return _GAME_ID_RESOLVERS[id_type](user=self, game_id=game_id, **kwargs)

    def update_game_data(self, path: str, update, **kwargs):
        """
        Updates Game Data to the database *and* broadcasts the data changes to potentially listening clients.
        Calling this function is the only way a game data should be updated, since this ensures integrity from database
        to frontend.
        :param path:    User Data path, e.g. `data.storage.content'
        :param update:  The update data
        :param kwargs:

        * `is_bulk`: If True, the update will be split the paths in keys
        * `command`: Default '$set' - mongo_db command to use for the update
        """
        splits = path.split('.')
        assert splits[0] == 'data'
        if 'is_bulk' in kwargs and kwargs['is_bulk']:
            # Update is a dict. We don't want delete the other entries in here
            # Only for ONE layer though
            command_content = dict()
            for key in update:
                command_content[path + '.' + key] = update[key]
        else:
            command_content = {path: update}
        mongo_command = kwargs['command'] if 'command' in kwargs else '$set'
        mongo.db.users.update_one({"username": self.username}, {mongo_command: command_content})
        # Also update the currently attached users.
        self._data_update_to_frontends(command_content)

    def _data_update_to_frontends(self, set_content):
        """
        Helper function.
        Takes in the MongoDB content update and defines what/how to update the frontends
        :return:
        """
        for path in set_content:
            if type(set_content[path]) is datetime:
                set_content[path] = set_content[path].strftime('%d %b %Y %H:%M:%S') + ' GMT'

            individual_data = {path: set_content[path]}

            found_match = False
            for regex in _FRONTEND_DATA_RESOLVERS:
                if regex.match(path):
                    # Found a match. Execute handler instead of default.
                    found_match = True
                    _FRONTEND_DATA_RESOLVERS[regex](user=self, data=individual_data, game_id=path)
                    break
            if not found_match:
                # No Regex matched the update path. Instead do the default
                self.frontend_update('update', individual_data)

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

    def game_integrity_assetion(self):
        """
        Internal utility function.
        This script runs any game assertions that are registered.
        :raise: Raises an `AssertionError` if anything about the user's data is not functional.
        """
        for assertion in _USER_ASSERTIONS:
            assertion(self)


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


@game_id_resolver
def data(user: User, game_id: str, **kwargs):
    """
    Evaluates a game-data ID and returns the value
    :param user:
    :param game_id:  User Data path, e.g. `data.storage.content'
    :return:    The value of this game data (KeyError if it does not exist)
    """
    splits = game_id.split('.')
    # Correct first split to correspond with JSON data model
    res = mongo.db.users.find_one({"username": user.get_id()}, {game_id: 1, '_id': 0})
    assert res
    try:
        for split in splits:
            res = res[split]
    except KeyError:
        # A key error means the resource is not (yet) written in the user data.
        # If the 'default' kwarg is used, instead of an error, return the default value
        if 'default' in kwargs:
            return kwargs['default']
        else:
            raise KeyError
    return res


@game_id_resolver
def slots(game_id: id, user: User, **kwargs):
    """
    Calculates the amount of **available** slots for a station:

    `slots.well = attr.well.slots - [currently occupied slots based on event queue]`
    :param game_id:       e.g. `attr.slots.well`
    :return:              The amount of currently free slots.
    """
    splits = game_id.split('.')
    assert splits[0] == 'slots' and len(splits) == 2

    # Available Slots = Max Slots - Currently Taken Slots
    max_slots = user.get('attr.' + splits[1] + '.slots')
    currently_taken = next(mongo.db.events.aggregate([{'$match': {
        'target': user.username,
        'station': splits[1],
        'due_time': {'$gt': datetime.utcnow()}
    }}, {'$group': {'_id': '', 'slots': {'$sum': '$slots'}}}]), None)
    if currently_taken:
        # Request had a result!
        return max_slots - currently_taken['slots']
    return max_slots


@game_id_resolver
def attr(game_id: str, user: User, **kwargs):
    """
    Evaluates an attribute for this user taking into account all unlocked upgrades.
    :param user:
    :param game_id: An attribute ID, e.g. 'attr.well.slots'
    :return: The result of the evaluation:
    """

    splits = game_id.split('.')
    assert splits[0] == 'attr' and len(splits) > 2

    # Get Base Value
    station: Station = Station.from_id('station.' + splits[1])
    try:
        val = station.get_base_value('.'.join(splits[2:]))
        if type(val) is list or type(val) is dict:
            # If the value is a reference, make sure we use a copy for this operation
            val = val.copy()
    except (KeyError, AssertionError):
        # Key does not exist. --> default
        if 'default' in kwargs:
            val = kwargs['default']
        else:
            raise AttributeError(f"Station does not have a base value {'.'.join(splits[2:])} and now default was set.")

    # Get all relevant Upgrades
    upgrade_list = [Upgrade.from_id(x) for x in user.get('data.workshop.upgrades')]
    upgrades: list[Upgrade] = sorted(filter(lambda x: x.relevant_for(game_id), upgrade_list))

    # Apply upgrades in sorted order
    for upgrade in upgrades:
        val = upgrade.apply_to(val=val, game_id=game_id)
    return val


@game_id_resolver
def station(game_id: str, user: User):
    return Station.from_id(game_id)


@game_id_resolver
def recipe(game_id: str, user: User):
    return Recipe.from_id(game_id)


@game_id_resolver
def recipes(game_id: str, user: User):
    splits = game_id.split('.')
    assert len(splits) == 2
    user_ws_data = user.get('data.workshop')
    return [r for r in Recipe.get_recipes_by_station(splits[1]) if r.can_execute(user,
                                                                                 user_upgrades=user_ws_data['upgrades'],
                                                                                 user_otr=user_ws_data['finished_otr'])]


@game_id_resolver
def item(game_id: str, user: User):
    return Item.from_id(game_id)


@game_id_resolver
def html(game_id: str, user: User, **kwargs):
    splits = game_id.split('.')
    if game_id in _HTML_GENERATOR_RESOLVERS:
        return _HTML_GENERATOR_RESOLVERS[game_id](user=user)
    elif len(splits) == 2:
        # Prototypical Case: Reload the entire station
        return render_template("stations/" + splits[1] + ".html",
                               station=user.get('station.' + splits[1]).get_json(),
                               **kwargs)
    else:
        return KeyError('This HTML request type was unknown.')



@game_id_resolver
def allslots(game_id: str, user: User):
    """
    Get ALL current slot data in comprehensive dict format.
    :param game_id: 'allslots' nothing else allowed
    :param user:    Executing user
    :return:        dict styled like this:
    ```
    {
        well: [ (% eta of slot 1 %), 'free' ],
        brewery: [ (% eta of slot 1 %), (% eta of slot 2 %), 'free' ],
        (% etc. etc. %)
    }
    ```
    """

    ret = dict()
    slot_data = {x['_id']: x['etas'] for x in mongo.db.events.aggregate([{'$match': {
        'target': user.username,
        'due_time': {'$gt': datetime.utcnow()}
    }}, {'$group': {'_id': '$station', 'etas': {'$push': {
        'due': '$due_time',
        'since': '$since'
    }}}}])}

    for _station in mongo.db.users.find_one({"username": user.username},
                                            {'data': 1, '_id': 0})['data']:
        max_slots = user.get('attr.' + _station + '.slots', default=0)
        if max_slots:
            # _station is slotted. Add the necessary input to return value
            if _station in slot_data:
                ret[_station] = slot_data[_station] + (['free'] * (max_slots - len(slot_data[_station])))
            else:
                ret[_station] = ['free'] * max_slots

    return ret
