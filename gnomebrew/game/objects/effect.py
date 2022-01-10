"""
This module wraps Effect objects in Gnomebrew.
"""
from collections import Callable
from typing import List, Tuple, Any

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.game_object import GameObject
from gnomebrew.game.user import User


class Effect(GameObject):
    """
    Wraps effect data.
    """

    effect_resolvers = dict()

    @classmethod
    def type(cls, effect_type: str, *validation_parameters: Tuple[str, Any]):
        """
        Registers a resolver function that can handle a specific effect type.
        Used as annotation for a function that expects a `user`, `effect_data', and `kwargs`
        :param effect_type: The effect type to handle
        :param validation_parameters:   Object field parameters that this effect type expects when validating.
                                        All parameters (e.g. `('push_target', str)`) will be included in
                                        object validation.
        """
        if effect_type not in cls.effect_resolvers:
            cls.effect_resolvers[effect_type] = dict()
        if 'execute' in cls.effect_resolvers[effect_type]:
            raise Exception(f"{effect_type} is already a registered effect type.")

        # If Validation Parameters are given, ensure they are formatted correctly
        if validation_parameters:
            extra_validation = list(validation_parameters)
        else:
            extra_validation = list()

        def wrapper(fun: Callable):
            cls.effect_resolvers[effect_type]['execute'] = fun
            cls.effect_resolvers[effect_type]['validation_parameters'] = extra_validation
            return fun

        return wrapper

    @classmethod
    def type_info(cls, effect_type):
        """
        Annotation function. Decorates a function that can resolve a request for effect visuals.
        A decorated function only expects the effect's data as a `dict` and returns a list of strings representing
        this effect's full display info.

        :param effect_type:     Target Type. There can only be one display function per type.
        """
        if effect_type not in cls.effect_resolvers:
            cls.effect_resolvers[effect_type] = dict()
        if 'info' in cls.effect_resolvers[effect_type]:
            raise Exception(f"{effect_type} already has a registered type info.")

        def wrapper(fun: Callable):
            cls.effect_resolvers[effect_type]['info'] = fun
            return fun

        return wrapper

    def __init__(self, effect_data):
        GameObject.__init__(self, effect_data)

    def execute_on(self, user: User, **kwargs):
        """
        Executes this effect on a given user.
        :param user:    Target user.
        :param kwargs   Forward `kwargs` to execution logic
        """
        Effect.effect_resolvers[self._data['effect_type']]['execute'](user=user, effect_data=self._data, **kwargs)

    def has_display(self) -> bool:
        """
        Checks if this effect should be displayed to the user in an appropriate circumstance.
        :return:    `True` if this effect should be displayed. Otherwise `False`.
        """
        return 'info' in self.effect_resolvers[self._data['effect_type']]

    def generate_infos(self) -> List[List[str]]:
        """
        Generates one info element (formatted as a list of strings) that describes this effect outcome.
        Expects to be only called if `has_display` confirms this is to be displayed.
        :return:    The effect's info data to display.
        """
        return self.effect_resolvers[self._data['effect_type']]['info'](self._data)


# Effect Object validation code (calls)

# Register base parameter that every Effect has:
Effect.validation_parameters(('effect_type', str))


@Effect.validation_function()
def validate_effect_data(data: dict, response: GameResponse):
    """
    Implementation of generic validation function for effects.
    :param data:        Effect data
    :param response:    Game Response object to log results in
    """
    # Base Parameter `effect_type` is ensured already.
    # Based on effect_type, check additional validation parameters
    for param_name, param_type in Effect.effect_resolvers[data['effect_type']]['validation_parameters']:
        if param_name not in data:
            response.add_fail_msg(f"Does not contain {param_name} (required by {data['effect_type']})")
        elif not isinstance(data[param_name], param_type):
            response.add_fail_msg(f"Parameter {param_name} must be instance of {param_type}, but is: {type(data[param_name])}")

# Some basic effects


@Effect.type('push_data', ('to_push', object), ('push_target', str))
def push_data(user: User, effect_data: dict, **kwargs):
    """
    Event execution for an arbitrary push (list append) of data.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[data-id] = delta
    """
    to_push = effect_data['to_push']
    push_target = effect_data['push_target']
    user.update(push_target, to_push, mongo_command='$push')


@Effect.type('pull_data', ('to_pull', object), ('pull_target', str))
def pull_data(user: User, effect_data: dict, **kwargs):
    """
    Event execution for an arbitrary push (list append) of data.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[data-id] = delta
    """
    pull_data = effect_data['to_pull']
    pull_target = effect_data['pull_target']
    print(f"pulling {pull_target} from {pull_data}")
    user.update(pull_target, pull_data, mongo_command='$pull')


@Effect.type('ui_update', ('type', str))
def ui_update(user: User, effect_data: dict, **kwargs):
    """
    Event execution for a user ui update
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[data-id] = delta
    """
    user.frontend_update('ui', effect_data)


@Effect.type('repeat', ('repeat_times', int), ('repeat_data', dict))
def repeat_event(user: User, effect_data: dict, **kwargs):
    """
    Repeats a given effect multiple times.
    :param user:        targget user.
    :param effect_data: effect data.
    :param kwargs:
    """
    repeat_times = int(effect_data['repeat_times'])
    target_effect = Effect(effect_data['repeat_data'])
    for _ in range(repeat_times):
        target_effect.execute_on(user)


@Effect.type('id_update', ('game_id', str), ('value', object))
def id_update(user: User, effect_data: dict, **kwargs):
    """
    Updates a given ID with a given value.
    :param user:        Target user
    :param effect_data: Effect data formatted as:
    ```python
    {
        'effect_type': 'id_update',
        'game_id': 'attr.workshop.slots',
        'value': 1,
        'mongo_command': '$mul' # This parameter is optional, default is attr-default ("$inc")
    }
    ```
    :param kwargs:      kwargs
    """
    if 'game_id' not in effect_data or 'value' not in effect_data:
        raise Exception(f"Missing data for ID Update: {effect_data}")

    # If mongo_update type is set, ensure it is followed through in the update execution
    if 'mongo_command' in effect_data:
        kwargs['mongo_command'] = effect_data['mongo_command']

    # Run the update
    user.update(effect_data['game_id'], effect_data['value'], **kwargs)
