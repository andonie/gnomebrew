"""
Manages User Data for the game
"""
import copy
from os.path import join
from typing import Callable, Union, List

from gnomebrew import mongo, login_manager, socketio
from gnomebrew.game.util import is_game_id_formatted
from gnomebrew.logging import log, log_exception
from flask_login import UserMixin
from flask import render_template
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import re
from functools import reduce

_GET_RESOLVERS = dict()
_UPDATE_RESOLVERS = dict()
_UPDATE_LISTENERS = dict()
_USER_ASSERTIONS = list()
_GLOBAL_ID_UPDATE_LISTENERS = dict()
_HTML_DIRECT_IDS = dict()
_HTML_ID_RULES = dict()
_USR_CACHE = dict()


def get_resolver(type: str, dynamic_buffer=False, postfix_start: int=None, **kwargs):
    """
    Registers a function to resolve a game resource identifier.
    :param type: The type of this resolver. A unique identifier for the first part of a game-id, e.g. `data`
    :param dynamic_buffer:  If set to `True`, Gnomebrew assumes this get-result will always be JSON formatted, and thus
                            nested. (e.g. I don't need to resolve 'data.station.storage.content.gold', when I already have the
                            result of 'data.storage.content' buffered)
    :param has_postfixes:   If this is set to a number, every split starting `postfix_start` will be considered a postfix
                            and postfixes for this ID will be observed and called for via `get_postfix` functions.
    :return: The registration wrapper. To be used as an annotation on a function that will serve as the `get` logic.
    The function will resolve game_ids leading with `type` and is expected to have these parameters:
    * `user: User` user for which the ID is to be resolved
    * `game_id: str` full ID (incl. first part that's covered through the name)
    """
    global _GET_RESOLVERS
    assert type not in _GET_RESOLVERS

    def wrapper(fun: Callable):
        _GET_RESOLVERS[type] = dict()
        _GET_RESOLVERS[type]['fun'] = fun
        _GET_RESOLVERS[type]['dynamic_buffer'] = dynamic_buffer
        if postfix_start:
            # Postfix start is defined.
            _GET_RESOLVERS[type]['has_postfix'] = True
            _GET_RESOLVERS[type]['postfix_start'] = postfix_start
        else:
            _GET_RESOLVERS[type]['has_postfix'] = False
        return fun

    return wrapper


def get_postfix(type: str):
    """
    Decorator function registers a function that can resolve Postfixes for a GET-ADDR.
    The rule is:
    If a `get_resolver` is created with a given `postfix_start`, the game will execute the main GET function first on the
    specified number of '.'-splits. If the given game_id was longer, the remaining splits will be iteratively executed
    by the function that's marked with *this* decorator.
    :param type:    The type for which this call decorates a postfix-code.
    """
    if type not in _GET_RESOLVERS:
        raise Exception(f"{type} is not yet a registered get-resolver yet.")
    if 'postfix_fun' in _GET_RESOLVERS:
        raise Exception(f"{type} already has a registered postfix function.")

    def wrapper(fun: Callable):
        _GET_RESOLVERS[type]['postfix_fun'] = fun
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
                    * kwargs

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
        return fun

    return wrapper


def user_assertion(assertion_script: Callable):
    """
    Registers a function as an assertion script.
    :param assertion_script:    A callable that takes one `User` parameter and raises an `AssertionError` if any
                                part of the user's data is problematic for the game logic.
    """
    global _USER_ASSERTIONS
    _USER_ASSERTIONS.append(assertion_script)


def id_update_listener(game_id_regex):
    """
    Registers a resolver when used as @ annotation before a function. The function must take two arguments:

    * `user`: a `User` object
    * `data`: a `dict` object containing the update data
    :param game_id_regex: A `str` that represents a regex. If the regex matches the Game-ID path of the update, this
    resolver will be called
    """

    def wrapper(fun: Callable):
        global _GLOBAL_ID_UPDATE_LISTENERS
        _GLOBAL_ID_UPDATE_LISTENERS[re.compile(game_id_regex)] = fun
        return fun

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

    # Defines the data an empty user starts with
    INITIAL_DATA = {
        'special': {
            'roles': [],
            'prompts': [],
            'selection': {
                '_bool': {
                    'storage_expanded': 'false',
                    'quest_expanded': 'true'
                },
                '_id': {},
                '_str': {}
            },
            'stations': ['station.quest', 'station.storage'],
            'id_listeners': [],
            'attr': {
                'station': {
                    'quest': {
                        'slots': 3
                    },
                    'storage': {
                        'max_capacity': 100
                    }
                }
            }
        },
        'station': {
            'storage': {
                'content': {
                    'item': {
                        'gold': 0,
                        'wood': 10,
                        'iron': 3,
                        'banana': 5,
                        'watermelon': 5,
                        'kiwi': 5,
                        'coal': 5
                    },
                    'quest_data': {
                    }
                },
                'it_cat_selections': {}
            },
            'quest': {
                'active': {
                },
                'available': {}
            }
        }
    }

    def __init__(self, username):
        """
        Init.
        :param db_data: Data stored in MongoDB database for this user.
        """
        self.username = username
        self.buffer = IDBuffer()

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

    @classmethod
    def create_user(cls, username: str, pw: str):
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
        user.reset_game_data()

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
        :param game_id: The ID of a game item, e.g. `attr.station.well.slots` or `data.storage.content`
        :return:        The result of the query
        """
        if 'id_buffer' in kwargs:
            raise Exception('id_buffer is deprecated')
        if not is_game_id_formatted(game_id):
            raise Exception(f"Requested Game ID '{game_id}' is malformatted.")
        splits = game_id.split('.')
        id_type = splits[0]
        if id_type not in _GET_RESOLVERS:
            raise Exception(f"Don't recognize game IDs starting with {id_type}: {game_id}")

        log('game_id', 'received', f'id:{game_id}')

        # Always go for the Buffer!
        # Use ID Buffer if possible.
        resolver_data = _GET_RESOLVERS[id_type]
        is_dynamic = resolver_data['dynamic_buffer']

        # Check if this result is already buffered
        if self.buffer.contains_id(game_id, dynamic_id=is_dynamic):
            return self.buffer.evaluate_id(game_id, is_dynamic)

        # If this is postfixed and the critical split length has been reached, remove postfix-info for basic get-request.
        if resolver_data['has_postfix'] and len(splits) > resolver_data['postfix_start']:
            game_id = '.'.join(splits[:resolver_data['postfix_start']])

        log('game_id', f"resolving", f"id:{game_id}")
        result = resolver_data['fun'](user=self, game_id=game_id, **kwargs)
        log('game_id', f"resolved", f"id:{game_id}")

        # If this is postfixed and the critical split length has been reached, apply post-GET postfix operations.
        if resolver_data['has_postfix'] and len(splits) > resolver_data['postfix_start']:
            result = resolver_data['postfix_fun'](result, splits[resolver_data['postfix_start']:])

        # Add this result to the buffer
        self.buffer.include(game_id, result, dynamic_id=is_dynamic)
        return result

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
        """
        id_type = game_id.split('.')[0]
        if id_type not in _UPDATE_RESOLVERS:
            raise Exception(f"Unkown ID type: {id_type}")

        # Invalidate the updated ID in buffer to ensure it is reloaded next time.
        self.buffer.invalidate(game_id, dynamic_id=_GET_RESOLVERS[id_type]['dynamic_buffer'])

        # Run the actual update
        mongo_command, res = _UPDATE_RESOLVERS[id_type](user=self, game_id=game_id, update=update, **kwargs)

        # Inform global & user-local update listeners of the ID(s) changed
        # Get the *exact* list of changes this updates induced, taking into account the `is_bulk` command:
        id_update_list = list()
        if 'is_bulk' in kwargs and kwargs['is_bulk']:
            for id_append in update:
                id_update_list.append((f"{game_id}.{id_append}", update[id_append]))
        else:
            id_update_list.append((game_id, update))

        # Check GLOBAL Listeners
        for updated_id, update_value in id_update_list:
            # Prepare Data Package for listeners
            individual_data = {updated_id: update_value}

            # If the individual data is datetime, format into something that JS can read
            if type(individual_data[updated_id]) is datetime:
                individual_data[updated_id] = individual_data[updated_id].strftime('%d %b %Y %H:%M:%S') + ' GMT'

            # Check all known global listeners and invoke when necessary
            for regex in _GLOBAL_ID_UPDATE_LISTENERS:
                if regex.match(updated_id):
                    # Found a match. Execute handler instead of default.
                    _GLOBAL_ID_UPDATE_LISTENERS[regex](user=self, data=individual_data, game_id=updated_id, command=mongo_command)

        # Check USER listeners
        user_listeners = self.get('data.special.id_listeners')
        for updated_id, update_value in id_update_list:
            for listener_data in user_listeners:
                if listener_data['target_id'] == updated_id or (listener_data['starts_with'] and updated_id.startswith(listener_data['target_id'])):
                    # Hit. Interpret this listener as an Effect and execute.
                    from gnomebrew.game.objects.effect import Effect

                    Effect(listener_data).execute_on(self, updated_id=updated_id, updated_value=update_value, **kwargs)

        return mongo_command, res

    def frontend_update(self, update_type: str, update_data: dict, **kwargs):
        """
        Called to send updates from server to user frontends.
        This function wraps a `socketio` call.
        :param update_type: Type of the update (for `.on(...)`)
        :param update_data: Data to be sent to all active frontends
        """
        socketio.emit(update_type, update_data, json=True, to=self.username)

    @staticmethod
    def _generate_id_listener_dict(game_id: str, on_change: dict, starts_with: bool) -> dict:
        """
        Generates an ID listener dict from a given on-change effect.
        :param game_id      Target ID
        :param on_change:   Effect data to execute on update.
        :return:            Resulting ID listener formatted dict for storage and use during `update` calls on this user.
        """
        result = copy.deepcopy(on_change)
        result['target_id'] = game_id
        result['starts_with'] = starts_with
        return result

    def register_id_listeners(self, game_id: Union[str, list], on_change: dict, starts_with=True, **kwargs):
        """
        Registers an ID listener to this user.
        Whenever `user.update` is called, all ID listeners registered to `user` will fire.
        :param game_id:         ID to listen to updates to. If `game_id` is a list of IDs, all IDs will be registered.
        :param on_change:       Describes **Effect** data that will be executed on ID update. This effect will receive
                                a keyword argument `game_id=<updated_id>` to have the changed variable available.
        :param starts_with:     If `True`, will match any ID that starts with the given `game_id` (e.g. to include
                                `item.fruit_wine.strawberry` in `item.wine`
        """
        # Push new data in DB
        if isinstance(game_id, str):
            # Simple Case: Just push one given effect to data
            self.update("data.special.id_listeners", self._generate_id_listener_dict(game_id, on_change, starts_with),
                        mongo_command='$push', **kwargs)
        elif isinstance(game_id, list):
            # Complex case: Add multiple elements to the listener bunch.
            self.update("data.special.id_listeners", {'$each': [self._generate_id_listener_dict(gid, on_change, starts_with) for gid in game_id]},
                        mongo_command='$push', **kwargs)
        else:
            raise Exception(f"Malformatted ID Registering Input: {game_id}")

    def remove_from_id_listeners(self, filter_out: Callable):
        """
        Removes all ID listeners that fit a given pattern.
        :param filter_out:   A function that expects a `dict` input for listener raw data and returns a `bool` signifying
                            whether to remove this element (`filter_out` returns `True`) or to keep an element
                            (`filter_out` returns `False`)
        """
        id_listeners = self.get('data.special.id_listeners')
        self.update('data.special.id_listeners', list(filter(lambda id_l: not filter_out(id_l), id_listeners)))

    def get_id_listeners(self) -> List[dict]:
        """
        Returns the raw listener ID data as a list of listener data `dict`s.
        :return:    The current ID listeners of this users.
        """
        return self.get('data.special.id_listeners')

    @staticmethod
    def game_integrity_assertions(user):
        """
        Internal utility function.
        Runs any game assertions that are registered in game on a given user.
        :raise: Raises an `AssertionError` if anything about the user's data is not functional.
        """
        for assertion in _USER_ASSERTIONS:
            assertion(user)

    def reset_game_data(self):
        """
        Resets this user's game data to the **initial** state.
        :param self:    User who should be reset.
        """
        # Remove user from event database
        mongo.db.events.delete_many({'target': self.get_id()})

        # Reset all Game Data: Main Collection
        proj = {'username': self.get_id()}
        res = mongo.db.users.update_one(proj, {'$set': {
            'data': User.INITIAL_DATA}
        })

        # Reset Game Data: Statistics Collection
        res = mongo.db.player_statistics.update_one(proj, {'$set': {'stat': {}}})

        # The game is kicked off the quest `quest.welcome` by convention
        from gnomebrew.game.objects import Effect

        Effect({
            'effect_type': 'add_available_quests',
            'quest_ids': ['quest.welcome']
        }).execute_on(self)


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

@get_resolver('data', dynamic_buffer=True)
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
            raise Exception(f"Could not evaluate {game_id=} at {user=}")
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
    mongo_command = kwargs['mongo_command'] if 'mongo_command' in kwargs else '$set'
    mongo.db.users.update_one({"username": user.get_id()}, {mongo_command: command_content})
    # Also update the currently attached users.
    return mongo_command, command_content


class IDBuffer:
    """
    Buffers the results of get-requests during execution of one program step.
    """

    def __init__(self):
        """
        Initializes a clean, empty ID BUffer
        """
        self._buffer_data = dict()

    def __str__(self):
        return f"<Gnomebrew ID Buffer>\n{str(self._buffer_data)}"

    def _find_dynamic_match(self, game_id: str) -> Union[str, None]:
        """
        Tries to find the best match for a given ID.
        :param game_id      Target ID to look for.
        :return:            A valid ID within this buffer that exists and that starts with the given `game_id`.
                            If no such ID is stored in Buffer, returns `None`
        """
        return max([buffer_id for buffer_id in self._buffer_data if game_id.startswith(buffer_id)], key=len, default=None)

    def _split_at_game_id(self, game_id: str, invalidate_id: str, dynamic_id: bool):
        result = self.evaluate_id(game_id, dynamic_id)
        del self._buffer_data[game_id]
        # If this is a dict, forward the split
        if isinstance(result, dict):
            for key in result:
                sub_id = f"{game_id}.{key}"
                self.include(sub_id, result[key], dynamic_id)
                if invalidate_id.startswith(sub_id):
                    # Must split this key, too.
                    self._split_at_game_id(sub_id, invalidate_id, dynamic_id)


    def contains_id(self, game_id: str, dynamic_id: bool):
        """
        Checks if this buffer already contains the data of a given game id.
        :param game_id:         The GameID to look for.
        :param dynamic_id:      If `True`, the buffer will assume it can evaluate a finer ID with whatever ID-result it
                                has in buffer that starts with this. (e.g. if I have 'data.storage.content', I can use
                                this to evaluate 'data.storage.content.iron'.
        :return:                `True` if the given ID can be evaluated by the Buffer. Otherwise `False`
        """
        if game_id in self._buffer_data:
            return True
        elif not dynamic_id:
            return False
        # Try to find dynamic match. If such an ID exists, the buffer contains this element.
        return self._find_dynamic_match(game_id)

    def evaluate_id(self, game_id: str, dynamic_id: bool):
        """
        Evaluates a GameID in this buffer.
        :param game_id:     An ID to evaluate.
        :param dynamic_id:  If `True`, the buffer will assume it can evaluate a finer ID with whatever ID-result it
                            has in buffer that starts with this. (e.g. if I have 'data.storage.content', I can use
                            this to evaluate 'data.storage.content.iron'.
        :return:            The result of the get-request from Buffer.
        """
        if game_id in self._buffer_data:
            return self._buffer_data[game_id]
        elif not dynamic_id:
            raise Exception(f"Buffer does not contain {game_id}")
        # Try to find dynamic match and use that to create return value.from
        best_match = self._find_dynamic_match(game_id)
        if not best_match:
            raise Exception(f"Buffer does not contain {game_id}")
        result = self._buffer_data[best_match]
        evaluation_steps = game_id[len(best_match)+1:].split('.')
        for step in evaluation_steps:
            try:
                result = result[step]
            except KeyError as e:
                log_exception('game_id', e)
        return result

    def invalidate(self, game_id, dynamic_id):
        """
        Invalidates an ID in this buffer.
        :param game_id:     An ID to invalidate (e.g. because it changed)
        :param dynamic_id:  Signify dynamic ID evaluation and thus removing
        :return:
        """
        if dynamic_id:
            for buffer_id in list(self._buffer_data.keys()):
                if buffer_id == game_id:
                    # Direct Hit. Just remove this ID
                    del self._buffer_data[buffer_id]
                elif game_id.startswith(buffer_id):
                    # Indirect hit. Game ID on buffer starts with this ID.
                    # Take the buffered dict and split its' contents and add to the buffer
                    self._split_at_game_id(buffer_id, game_id, dynamic_id)
        else:
            if game_id in self._buffer_data:
                del self._buffer_data[game_id]

    def include(self, game_id, get_result, dynamic_id):
        """
        Updates this buffer with new data results.
        :param game_id:         Evaluated game_id
        :param get_result:      Evaluation result
        """
        self._buffer_data[game_id] = get_result

