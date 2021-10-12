"""
Manages ingame prompts to the player.
A prompt is an object that describes the prompt.
"""
from typing import Callable
from uuid import uuid4

from gnomebrew import log
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects import PlayerRequest
from gnomebrew.game.objects.data_object import DataObject
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.game_object import GameObject, render_object
from gnomebrew.game.testing import application_test
from gnomebrew.game.user import User, get_resolver, id_update_listener, load_user
from gnomebrew.game.util import global_jinja_fun



class Prompt(GameObject):
    """
    Wraps a player prompt.
    """

    prompt_types = [ 'guild', 'main', 'server' ]

    def __init__(self, data: dict):
        GameObject.__init__(self, data, uuid='prompt_id')

    def enqueue(self, user: User, **kwargs):
        """
        Enqueues this prompt to be displayed to a given user.
        :param user:    Target user.
        """
        # Enqueue update in player data
        user.update('data.special.prompts', self._data, mongo_command='$push', **kwargs)

    def render_html(self, user: User, **kwargs) -> str:
        """
        Renders this prompt as HTML.
        :param user:    Target user.
        :return:        HTML data that displays this prompt entirely.
        """
        return render_object('render.prompt', data=self._data, **kwargs)

    def process_input(self, user: User, response_data: dict, **kwargs):
        """
        Processes a user response to the prompt. Response will be validated and next actions are taken accordingly.
        :param response_data:   Player Response data
        :param user:    Target user.
        """
        log('prompt', 'processing', f"usr:{user.get_id()}", verbose=response_data)
        response = GameResponse()
        response.set_ui_target('#gb-prompt-infos')
        input_items = PlayerRequest.parse_inputs(response_data)

        if 'input' in self._data:
            # Check Input Elements and ensure that they are all appropriate for the prompt's requirements.
            for input_obj in [PlayerInput(data) for data in self._data['input'].values()]:
                if input_obj.get_id() not in input_items:
                    response.add_fail_msg(f'Missing input ID: {input_obj.get_id()}')
                else:
                    input_obj.validate(input_items[input_obj.get_id()], response)

        if 'target_id' not in response_data:
            response.add_fail_msg('Could not find target_id data.')

        if response.has_failed():
            return response

        # Take prompt list and remove my data from it.
        prompt_list = user.get('data.special.prompts')
        pre_length = len(prompt_list)

        prompt_list = list(filter(lambda prompt_data: prompt_data['prompt_id'] != response_data['target_id'], prompt_list))
        if len(prompt_list) == pre_length:
            response.add_fail_msg(f'Did not find prompt with ID {response_data["prompt_id"]}')

        if response.has_failed():
            return response

        # Execute prompt: Process Input and update resulting prompt list.
        user.update('data.special.prompts', prompt_list)

        # Prompt Response from player is acceptable. Implement any inputs now.
        if 'input' in self._data:
            for input_obj in [PlayerInput(data) for data in self._data['input'].values()]:
                input_obj.process_input(user, input_items[input_obj.get_id()])

        # Provide an update on the prompt states for the user.
        prompt_heads = get_prompt_head_dict(user)
        response.set_value('prompt_states', {f"#{key}-prompt": bool(v) for key, v in prompt_heads.items() })

        response.succeess()
        return response


    def has_input(self) -> bool:
        """
        :return: `True` if this prompt contains any user input request. Otherwise `False`.
        """
        return any([content['content_type'] == 'input' for content in self._data['content']])


class PlayerInput(DataObject):
    """
    Wraps a prompt input.
    """

    prompt_types = dict()

    @classmethod
    def type_validation(cls, input_type: str, validation_type: str):
        """
        Annotation registers a validation function for a given prompt type.
        :param input_type:  Input type, e.g. 'text'
        :param validation_type: Validation Type, e.g. 'min_length'
        """
        if input_type not in cls.prompt_types:
            cls.prompt_types[input_type] = dict()
        type_data = cls.prompt_types[input_type]
        if 'validation_functions' not in type_data:
            type_data['validation_functions'] = dict()
        if validation_type in type_data['validation_functions']:
            raise Exception(f"Validation Type {validation_type} is already registered for {input_type}.")

        def wrapper(fun: Callable):
            type_data['validation_functions'][validation_type] = fun
            return fun

        return wrapper

    @classmethod
    def type_processing(cls, input_type):
        """
        Annotation registers a processing function for a given prompt input type.
        :param input_type:  Input type
        """
        if input_type not in cls.prompt_types:
            cls.prompt_types[input_type] = dict()
        type_data = cls.prompt_types[input_type]
        if 'processing_fun' in type_data:
            raise Exception(f"Type processing is already registered for {input_type}.")

        def wrapper(fun: Callable):
            type_data['processing_fun'] = fun
            return fun

        return wrapper

    def __init__(self, data: dict):
        DataObject.__init__(self, data)

    def get_id(self):
        return self._data['input_id']

    def validate(self, data, response: GameResponse):
        """
        Checks if given input data is valid for this input.
        :param data:    Data to check
        :param response response object to provide user feedback on validations.
        """
        input_type = self._data['input_type']
        if input_type not in PlayerInput.prompt_types:
            raise Exception(f"{input_type} is not registered.")
        if 'validation_functions' not in PlayerInput.prompt_types[input_type]:
            raise Exception(f"No validation function registered for {input_type}")
        for validation in self._data['validate_input']:
            PlayerInput.prompt_types[input_type]['validation_functions'][validation['validation_type']](validation, data, response)

    def process_input(self, user, data):
        input_type = self._data['input_type']
        if input_type not in PlayerInput.prompt_types:
            raise Exception(f"{input_type} is not registered.")
        if 'processing_fun' not in PlayerInput.prompt_types[input_type]:
            raise Exception(f"No processing function registered for {input_type}")
        return PlayerInput.prompt_types[input_type]['processing_fun'](user, self._data, data)


@get_resolver('prompt', dynamic_buffer=False)
def resolve_get_prompt(user: User, game_id: str, **kwargs):
    """
    Resolves `prompt.<cmd>` requests.
    :param user:        Target user.
    :param game_id:     Game ID to resolve starting with `prompt.`
    :param kwargs:      any kwargs
    :return:            The result of the prompt request. Knows these options:

    * `prompt.active`: Currently active prompt. Raises exception if no prompt is active currently
    """
    splits = game_id.split('.')

    print(splits)

    # Default case: `prompt.<uuid>`
    prompt_data = user.get('data.special.prompts')

    match = next(filter(lambda prompt_data: prompt_data['prompt_id'] == splits[1], prompt_data), None)
    if not match:
        if 'default' in kwargs:
            return kwargs['default']
        else:
            raise Exception(f"Cannot find prompt {game_id} in player data (username: {user.get()}).")
    return match


prompt_identifiers = ['prompt_id', 'prompt_type']

@PlayerRequest.type('give_prompt', is_buffered=False)
def resolve_give_prompt(user: User, request_object: dict, **kwargs):
    """
    Called when the user requests a prompt.
    Provides the user with the requested prompt HTML which is expected to be displayed in a modal.
    :param user:        Target user.
    :param request_object:     Request Object
    :param kwargs:      kwargs
    """
    response = GameResponse()

    if not any([identifier for identifier in prompt_identifiers if identifier in request_object]):
        response.add_fail_msg(f"Missing an identifier: {prompt_identifiers}")

    if response.has_failed():
        return response

    prompt_list = user.get('data.special.prompts')

    prompt = None
    for prompt_identifier in prompt_identifiers:
        if prompt_identifier in request_object:
            print(f"{prompt_identifier=} {request_object=}")
            result = next(filter(lambda prompt_data: prompt_data[prompt_identifier] == request_object[prompt_identifier], prompt_list), None)
            if result:
                prompt = Prompt(result)
            else:
                response.add_fail_msg(f"Cannot find prompt of type {request_object[prompt_identifier]}")

    if not prompt:
        response.add_fail_msg(f"Cannot find prompt.")

    if response.has_failed():
        return response

    user.frontend_update('ui',{
        'type': 'prompt',
        'prompt_html': prompt.render_html(user)
    })

    response.succeess()
    return response



@PlayerRequest.type('prompt', is_buffered=True)
def player_prompt_request(request_object, user: User, **kwargs):
    response = GameResponse()
    log('prompt', 'processing', f"usr:{user.get_id()}", verbose=request_object)

    if 'target_id' not in request_object:
        response.add_fail_msg('Missing Target ID')

    if response.has_failed():
        return response

    target_prompt = user.get(f'prompt.{request_object["target_id"]}', default=None, **kwargs)
    if not target_prompt:
        response.add_fail_msg(f'Prompt with ID {request_object["target_id"]} not found.')
        return response

    response = Prompt(target_prompt).process_input(user, request_object, **kwargs)

    return response


@global_jinja_fun
def prompt_data_has_input(prompt_data: dict):
    """
    Utility function for Jinja template (that does not use object reference).
    :param promt_data:  Prompt data.
    :return:            `True`, if prompt data contains an input. Otherwise `False`.
    """
    return any([content['content_type'] == 'input' for content in prompt_data['content']])


@global_jinja_fun
def get_prompt_head_dict(user: User) -> dict:
    """
    Jinja util. Creates a dict with keys of prompt types and values as the first item of each kind.
    :param user:    Target user.
    :return:        Well-Formatted prompt dict
    """
    prompt_queue = user.get('data.special.prompts')
    head_dict = {prompt_type: next(filter(lambda prompt_data:prompt_data['prompt_type'] == prompt_type, prompt_queue), None)
                  for prompt_type in Prompt.prompt_types}

    return head_dict

# Some Basic Prompt Types

@PlayerInput.type_processing('text')
@PlayerInput.type_processing('number')
@PlayerInput.type_processing('selection')
def simple_write(user: User, input_data: dict, data: str):
    """
    Processes `data` by simply writing the given input data into `data`'s `target_id`.
    Used for inputs that might be different in validation but similar in processing.
    :param user         Target User
    :param input_data:  Data of input object JSON. Expected to be well-formatted
    :param data:        Input from Player Request
    """
    user.update(input_data['target_id'], data)


@PlayerInput.type_validation('text', 'min_length')
@PlayerInput.type_validation('number', 'min_length')
def min_length(input_data: dict, data, response: GameResponse):
    """
    Validates a text input
    :param response:    Response object for user feedback.
    :param input_data:  Data of input object JSON. Expected to be well-formatted
    :param data:        Input from Player Request. Expected to have a length
    :return:            `True` if `data` passes all conditions. Otherwise `False`
    """
    if len(data) < input_data['min_length']:
        response.add_fail_msg(f"Minimum length is {input_data['min_length']}")
        response.player_info(f'Input must be longer than {input_data["min_length"]}', 'must be', 'special.greater_than', str(input_data['min_length']))



# Effect Compatibility

@Effect.type('queue_prompts')
def execute_queue_prompts(user: User, effect_data: dict, **kwargs):
    # Assert effect_data is well-formatted.

    prompt_types = list()
    for prompt_object in effect_data['prompts']:
        # Input typechecking
        if 'prompt_type' not in prompt_object:
            raise Exception(f"Malformatted effect data: {effect_data}")
        if prompt_object['prompt_type'] not in prompt_types:
            prompt_types.append(prompt_object['prompt_type'])
        if 'prompt_id' not in prompt_object:
            prompt_object['prompt_id'] = uuid4()

    # Execute Queue Prompts
    user.update('data.special.prompts', effect_data['prompts'], mongo_command='$push')

    # Ensure user has the given prompt type visible
    for prompt_type in prompt_types:
        user.frontend_update('ui', {
            'type': 'update_class',
            'action': 'remove_class',
            'target': f'#{prompt_type}-prompt',
            'class_data': 'gb-navbar-hidden'
        })

@application_test(name='Add Prompt', context='Prompt')
def add_prompt(username: str, prompt_content: str):
    response = GameResponse()
    if not User.user_exists(username):
        response.add_fail_msg(f"User {username} does not exist.")
        return response
    user = load_user(username)

    prompt_data = {
        'prompt_type': 'main',
        'prompt_id': '1236634',
        'title': 'Name your Tavern',
        'content': [
            {
                'content_type': 'plain',
                'content': prompt_content
            }
        ],
        'effects': []
    }
    effect_data = {
        'effect_type': 'queue_prompts',
        'prompts': [prompt_data]
    }

    Effect(effect_data).execute_on(user)

    return response

