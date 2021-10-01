from os.path import join
from typing import Callable
import re

from flask import render_template, render_template_string

from gnomebrew import mongo

from gnomebrew.game.objects.static_object import StaticGameObject
from gnomebrew.game.user import get_resolver, update_resolver, User, frontend_id_resolver, html_generator, \
    update_listener
from gnomebrew.game.event import Event
from gnomebrew.play import request_handler
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.static_object import load_on_startup


@load_on_startup('ingame_events')
class IngameEvent(StaticGameObject):
    """
    Represents an Ingame Event.
    Ingame events are always shown in modal dialogues.
    """

    # Stores Requirement resolvers for events to fire
    _req_resolvers = dict()
    # Stores input validators
    _input_validators = dict()
    # Stores input actions
    _input_on_submit_actions = dict()

    @staticmethod
    def req_resolver(fun: Callable):
        """
        Registers a requirement resolver for ingame events
        :param fun:     The requirement check functions.
        Parameters:
        * `requirement: dict` the dict data associated with the requirement
        The `__name__` of the callable is expected to correspond with the requirement type.
        The callable is expected to **return** a **tuple** of a function and a game-id.

        **Value 1: A function**

        *Will be called many times*

        Takes a `user` object and returns `True` or `False` depending on the outcome
        of the requirement check.
        **Important**: The returned function will be called very often. To minimize runtime, the returning
        function should check for `kwargs['value']`, which would contain the value to check against, if
        already known before the call. This minimizes `get` calls where possible.

        **Value 2: A Game-ID (`str`)**

        The Game ID associated with this requirement. Used in order to add an update listener on the given game ID for
        'just-in-time' checks of Event requirements.
        """
        assert fun.__name__ not in IngameEvent._req_resolvers
        IngameEvent._req_resolvers[fun.__name__] = fun

    def __str__(self):
        """
        String conversion function. For debugging.
        :return:    A string that contains the game ID of the ingame event object
        """
        return f"<IngameEvent {self._data['game_id']}>"

    @staticmethod
    def input_validator(fun: Callable):
        """
        Registers an input validator for user input.
        :param fun:     The validator function. its `__name__` will correspond with the validate `type`.
        The function will expect three parameters:

        * value:    A given value
        * validate_data: The corresponding validate data from the JSON
        * gr:       A GameResponse object used for logging possible errors
        """
        assert fun.__name__ not in IngameEvent._input_validators
        IngameEvent._input_validators[fun.__name__] = fun

    @staticmethod
    def input_on_submit(fun: Callable):
        """
        Registers an input action for an input field in a Game Event.
        :param fun:     The function performing the input action. Its `__name__` will correspond with the `on_submit`-
                        type. The function will have three parameters:

        * user:     a user
        * value:    the submitted input value
        * on_submit_data: the data describing the action
        """
        assert fun.__name__ not in IngameEvent._input_on_submit_actions
        IngameEvent._input_on_submit_actions[fun.__name__] = fun

    def __init__(self, mongo_data):
        self._data = mongo_data

        # On init, parse requirements JSON data to executable check functions
        # generate a check function based on json data for each requirement
        # And also add a listener for each requirement
        self._requirement_checks = list()
        for req_item in self._data['requirements']:
            # Every Requirement resolver returns a tuple of two functions:
            # Function 1: The basic check method to be used for any and all requirement checks
            # Function 2: A one-time call that registers update listeners for all requirements to make sure
            #             the necessary checks for this event happen just-in-time
            basic_check, target_game_id = IngameEvent._req_resolvers[req_item['type']](req_item)
            self._requirement_checks.append(basic_check)

            # Create an update listener that fires whenever the respective Game-ID changed
            update_listener(target_game_id)(self._generate_update_listener(basic_check=basic_check,
                                                                           target_game_id=target_game_id))

    def _generate_update_listener(self, basic_check: Callable, target_game_id: str):
        """
        Generator function to create a listener function associated with this Ingame Event.
        Wrapping the creation of a listener turned out to be necessary since local variable madness happened
        with multiple requirements during `__init__`.
        :param basic_check:        The basic check function (returning a Boolean)
        :param target_game_id:      The target game ID. This is the ID the listener will listen to.
        :return:                    The ready-to-use listener function.
        """

        def on_update(user: User, update: dict):
            if basic_check(user, value=update[target_game_id]) and self._data['game_id'] not in user.get(
                    'ingame_event.finished'):
                self._check_and_fire_if_ready(user)

        return on_update

    def _check_and_fire_if_ready(self, user: User):
        """
        This function tests if this event is appropriate to fire NOW. If it is, it fires the event now.
        :param user:    a user to test for
        """
        if self.requirements_met(user) and self._data['game_id'] not in user.get('ingame_event.queued') and \
                (not self.is_one_time() or self._data['game_id'] not in user.get('ingame_event.finished')):
            # This event is due to fire!
            self.enqueue(user)

    def has_inputs(self):
        return 'input' in self._data['content']

    def has_effects(self):
        return 'effect' in self._data

    def is_one_time(self):
        return self._data['one_time'] if 'one_time' in self._data else True

    def render_body_text(self):
        return render_template_string(self._data['content']['text'])

    def render_html(self):
        """
        Returns HTML code for a modal DIV (not shown yet) that can be used to display the event to the user.
        :return:    HTML code for a modal DIV for this event.
        """
        return render_template(join('ig_event', '_event_modal.html'),
                               event=self)

    def render_input_html(self):
        """
        Returns rendered HTML code for all inputs of this ingame event.
        This function is called from the main event modal template
        :return:    Rendered HTML code
        """
        if 'input' not in self._data['content']:
            # This event does not have inputs. This should not happen during normal operation
            return ""
        html_code = ""
        for index, input_item in enumerate(self._data['content']['input']):
            html_code += render_template(join('ig_event', 'inputs', input_item['type'] + ".html"),
                                         input_data=input_item,
                                         id=index)
        return html_code

    def render_effect_html(self):
        """
        Returns HTML code that visualizes the effect this event takes into account all effects applied by this event.
        Assumes that this event has effects, otherwise spits out a `KeyError`
        :return:    Fitting HTML code
        """
        html_code = ""
        for effect in self._data['effect']:
            html_code += render_template(join('ig_event', 'effects', f'{effect}.html'),
                                         effect_data=self._data['effect'][effect])
        return html_code

    def validate_inputs(self, input_data: dict, gr: GameResponse):
        """
        Validates input data.
        :param input_data:  Input data as posted from Frontend
        :param gr:          `GameResponse` object for the player post. Used to log input errors in human-readable way.
                            Also doubles as the indicator of this function: `gr.has_failed()` will fire after
                            the validation completed with errors.
        """
        assert 'input' in self._data['content']
        for index, input_element in enumerate(self._data['content']['input']):
            # Check if this input has validators
            if 'validate' not in input_element:
                continue
            for validation in input_element['validate']:
                kwargs = {}
                if 'placeholder' in input_element:
                    kwargs['label'] = input_element['placeholder']
                IngameEvent._input_validators[validation['type']](value=input_data[index],
                                                                  validate_data=validation,
                                                                  gr=gr,
                                                                  **kwargs)

    def close_event(self, user, input_data: dict):
        """
        Closes the event for the user.
        This function is called after the user confirmed/closed the event dialogue in the frontend.
        :param user:        a user.
        :param input_data:    a dict containing the user-response, if applicable.
        """
        # If the event has a specified effect, now is the time to execute it
        if 'effect' in self._data:
            for effect in self._data['effect']:
                Event.execute_event_effect(user=user, effect_type=effect, effect_data=self._data['effect'][effect])

        if self.has_inputs():
            # I have inputs. I assume all are validated and vetted in the input dict. I can now act accordingly.
            for index, input_element in enumerate(self._data['content']['input']):
                if 'on_submit' not in input_element:
                    continue
                for submit_element in input_element['on_submit']:
                    IngameEvent._input_on_submit_actions[submit_element['type']](user=user,
                                                                                 value=input_data[index],
                                                                                 on_submit_data=submit_element)

        # Remove the event from the event-queue
        user.update('ingame_event.queued', self._data['game_id'], mongo_command='$pull')

        # Add the event to the list of passed events
        user.update('ingame_event.finished', self._data['game_id'], mongo_command='$push')

    def requirements_met(self, user):
        """
        Tests if this event's requirements are met for a given user.
        :param user:    a user
        :return:        `True` if all requirements for this event are met
        """
        return all(map(lambda req_fun: req_fun(user), self._requirement_checks))

    def enqueue(self, user, **kwargs):
        """
        Enqueues this ingame event in the user document to be fired.
        :param user:    a user that will experience this event.
        """
        # Write to user data
        user.update('ingame_event.queued', self._data['game_id'], mongo_command='$push')
        # Make a manual frontend update
        user.frontend_update('ui', {
            'type': 'event'
        })

    @staticmethod
    def overall_check(user, **kwargs):
        """
        Performs an overall check on the user to see if any ingame events are due to be fired.
        :param user:    a user.
        """
        finished = user.get('ingame_event.finished')
        for ig_event in [ingame_event for ingame_event in ig_event_list
                         if ingame_event.get_id() not in finished and ingame_event.requirements_met(user)]:
            ig_event.enqueue(user, **kwargs)


# Some standard resolvers

# Resolvers for the different data checks
_data_resolvers = dict()


def _ig_data_check(regex):
    compiled = re.compile(regex)
    assert compiled not in _data_resolvers

    def wrapper(fun: Callable):
        _data_resolvers[compiled] = fun

    return wrapper


@_ig_data_check(r'>[-0-9]+')
def _gt(val: str):
    value = int(val[1:])

    def check(num):
        return num > value

    return check


@_ig_data_check(r'<[-0-9]+')
def _lt(val: str):
    value = int(val[1:])

    def check(num):
        return num < value

    return check


@_ig_data_check(r'=[-0-9]+')
def _eq(val: str):
    value = int(val[1:])

    def check(num):
        return num == value

    return check


@IngameEvent.req_resolver
def data(requirement: dict):
    """
    Resolves a requirement check of the `data` type.
    Checks one game data element against a criterium.
    :param requirement:     a requirement.
    :return:                Evaluation Function for this requirement
    """
    # Find a match in the lookup table
    for regex in _data_resolvers:
        if regex.match(requirement['check']):
            check_fun = _data_resolvers[regex](requirement['check'])
            break

    assert check_fun

    id_to_check = requirement['item']

    def requirement_function(user, **kwargs):
        current_value = user.get(id_to_check) if 'value' not in kwargs else kwargs['value']
        return check_fun(current_value)

    return requirement_function, id_to_check


@IngameEvent.req_resolver
def upgrade(requirement: dict):
    """
    Resolves a requirement check of the `upgrade` type.
    Checks if a specific upgrade is already acquired.
    :param requirement: Requirement data
    :return:            Respective evalauation function
    """
    id_to_check = 'data.workshop.upgrades'
    upgrade_id = requirement['upgrade']

    def requirement_function(user, **kwargs):
        current_value = user.get(id_to_check) if 'value' not in kwargs else kwargs['value']
        return upgrade_id in current_value

    return requirement_function, id_to_check


@get_resolver('ingame_event')
def event_data(user, game_id: str, **kwargs):
    """
    Resolver to retrieve user specific IG Event data.
    :param user:        a user
    :param game_id:     Fully qualified game id. Can be `event_data` + :

    * `next`: Give the next waiting ingame event that's due to occur, if applicable
    * `finished`: Returns a list with the IDs of all finished Ingame-Events
    * `queued`: Returns a list of all Ingame events that are due to occur

    :param kwargs:      kwargs
    :return:
    """
    splits = game_id.split('.')

    if splits[1] == 'finished':
        res = mongo.db.users.find_one({"username": user.get_id()}, {'ingame_event.finished': 1, '_id': 0})
        return res['ingame_event']['finished']
    elif splits[1] == 'queued':
        res = mongo.db.users.find_one({"username": user.get_id()}, {'ingame_event.queued': 1, '_id': 0})
        return res['ingame_event']['queued']
    elif splits[1] == 'next':
        res = mongo.db.users.find_one({"username": user.get_id()}, {'ingame_event.queued': 1, '_id': 0})
        queue = res['ingame_event']['queued']
        if not queue:
            return None
        else:
            return queue[0]
    else:
        raise AttributeError(f'Game ID {game_id} not recognized')


@update_resolver('ingame_event')
def update_ig_event(user: User, game_id: str, update, **kwargs):
    """
    Update function for ingame event data for a user
    :param user:    a user
    :param game_id: expects either 'ingame_event.queue` or `ingame_event.finished`
    :param update:  The update value
    :param kwargs:  kwargs
    :return:        An update dict for the frontend
    """
    mongo_command = '$set' if 'mongo_command' not in kwargs else kwargs['mongo_command']
    mongo.db.users.update_one({'username': user.get_id()}, {mongo_command: {game_id: update}})
    return {
        game_id: update
    }


@frontend_id_resolver(r'^ingame_event\.')
def match_and_ignore_any_ingame_event(user: User, data: dict, game_id: str):
    """
    Ignore any and all ingame_event frontend updates
    """
    print(f'RECEIVED {game_id=}')
    pass


@get_resolver('ig_event')
def get_ig_event(game_id: str, user):
    """
    Resolver to retrieve 'clean' Ingame Event objects.
    """
    return IngameEvent.from_id(game_id)


@html_generator('html.ingame_event.next')
def display_next_event_if_applicable(game_id: str, user: User, **kwargs) -> str:
    """
    Renders and returns HTML for the next event in the ingame-event-queue, if applicable.
    If there is no ingame-event, returns an empty string.
    :param user:    a user
    :return:        HTML for the next applicable Ingame Event or `None`
    """
    next_event = user.get('ingame_event.next')
    if not next_event:
        # No queued event. Return None
        return None

    return user.get(next_event).render_html()


@request_handler
def event(request_object: dict, user: User):
    """
    Called, when a user confirms/closes an event modal. The response type (success/fail) defines whether or not the
    modal closes.
    :param request_object:  The full request object sent from frontend.
    :param user:            The respective user
    :return:                The appropriate `GameResponse` object
    """
    response = GameResponse()

    # Get the respective Game Event object
    target_event: IngameEvent = user.get(request_object['target'])

    parsed_inputs = dict()
    if target_event.has_inputs():
        for i in range(200):
            next_key = f'input[{i}]'
            if next_key in request_object:
                parsed_inputs[i] = request_object[next_key]
            else:
                break

        target_event.validate_inputs(parsed_inputs, response)
        # If any validation failed, the response has a corresponding fail msg and we can return
        if response.has_failed():
            return response

    # Validation successful or no validation necessary. The event can be closed now.
    target_event.close_event(user, parsed_inputs)

    response.succeess()
    return response


@IngameEvent.input_validator
def longer_than(value, validate_data: dict, gr: GameResponse, **kwargs):
    if len(value) <= validate_data['value']:
        gr.add_fail_msg(f"{kwargs['label'] if 'label' in kwargs else 'Your input'} is too short. "
                        f"Must be at least {validate_data['value']}")


@IngameEvent.input_on_submit
def write_to(user: User, value, on_submit_data: dict):
    user.update(on_submit_data['target'], value)
