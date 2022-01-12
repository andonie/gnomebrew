"""
Describes conditions in game.
A condition in Gnomebrew consists of:
`target_id`, describing the relevant ID for this condition
`eval_type`, describing the evaluation type
"""
from collections import Callable
from numbers import Number
from typing import List, Any, Tuple

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects import Effect
from gnomebrew.game.objects.game_object import GameObject
from gnomebrew.game.user import User


class Condition(GameObject):
    """
    Wraps condition data.
    """

    condition_resolvers = dict()

    @classmethod
    def type(cls, condition_type: str, *validation_parameters: Tuple[str, Any]):
        """
        Describes a condition type. Used as a decorator for condition resolvers.
        Decorated function is expected to take these parameters:

        1. `user: User`
        2. `condition_data: dict`
        3. **kwargs: Will contain any known current values of any GameID.

        :param condition_type:   Unique Name of the condition this resolves.
        :param validation_parameters    Parameters specified (e.g. `('target_id', str)`) will be checked for every
                                        validation call on `condition_type`
        """
        if condition_type in cls.condition_resolvers:
            raise Exception(f"Condition Type {condition_type} already in use.")

        # If validation parameters have been provided, format to list object to be added.
        if validation_parameters:
            extra_validation = list(validation_parameters)
        else:
            extra_validation = list()

        def wrapper(fun: Callable):
            cls.condition_resolvers[condition_type] = dict()
            cls.condition_resolvers[condition_type]['fun'] = fun
            cls.condition_resolvers[condition_type]['validation_parameters'] = extra_validation
            return fun

        return wrapper

    def __init__(self, condition_data: dict):
        GameObject.__init__(self, condition_data)

    def cares_for(self, game_id: str) -> bool:
        """
        Checks if this conditions cares for a given ID.
        :param game_id: ID to check.
        :return:    `True`, if `game_id` is relevant to this condition. Otherwise `False`.
        """
        if 'target_id' not in self._data or self._data['state'] == 1:
            return False

        return self._data['target_id'] == game_id

    def current_completion(self, value, is_update=False) -> float:
        """
        Checks if the current value meets the condition.
        :param value:   A value.
        :param is_update:   If this is `True`, expects `value` to be the result of a `user.update` call of the relevant
                            Game ID.
        :return:        A number between 0 and 1, representing the degree of completion of this conditon.
                        Only 1 will be recognized as condition met.
        """
        return Condition.condition_resolvers[self._data['eval_type']]['fun'](value, self._data, is_update=is_update)

    def has_display(self) -> bool:
        """
        Checks if this condition has a display. If so, the condition will have a `gb-info` to visualize this condition.
        :return:    `True` if this condition has a display. Otherwise `False`
        """
        return 'display' in self._data

    def generate_info(self) -> List[str]:
        """
        Generates this condition's info to visualize. Assumes `has_display() := True`
        :return:    This condition's info data.
        """
        display_data = self._data['display']
        if isinstance(display_data, str):
            # Primitive case. Return list to just render base text.
            return [display_data]
        else:
            # Assume the quest data is the info display as it is to be shown.
            return display_data

    def completion_for(self, user: User) -> float:
        """
        Checks the completion-percentage of this condition.
        :param user:    Target user.
        :return:        A number between 0 (condition not met at all) and 1 (condition fully met). Only with 1 value of
                        1 is this condition considered met.
        """
        return self.current_completion(user.get(self._data['target_id']))

    def is_fulfilled_for(self, user: User) -> bool:
        """
        Tests, if this condition is fulfilled for a given user `user`.
        :param user:        Target user.
        :return:            `True`, if this condition is currently fulfilled. Otherwise `False`.
        """
        return self.completion_for(user) == 1


# Condition Data Validation

Condition.validation_parameters(('target_id', str), ('eval_type', str))


@Condition.validation_function()
def validate_condition_data(data: dict, response: GameResponse):
    """
    Validates Condition Data.
    :param data:            data
    :param response:        response to log
    """
    # Check if `eval_type` is known
    if data['eval_type'] not in Condition.condition_resolvers:
        response.add_fail_msg(f"Unknown evaluation type: <%{data['eval_type']}%>")

    if response.has_failed():
        return response

    # Make additional parameter checks for the given `eval_type`
    for p_name, p_type in Condition.condition_resolvers[data['eval_type']]['validation_parameters']:
        if p_name not in data:
            response.add_fail_msg(f"Missing Condition Parameter <%{p_name}%>")
        elif not isinstance(data[p_name], p_type):
            response.add_fail_msg(
                f"Malformatted Condition Data: <%{p_name}%> should be {p_type}, is {type(data[p_name])}")


# Condition Types

@Condition.type('equals', ('value', object))
def equals_check(value, condition_data: dict, **kwargs):
    return 1 if value == condition_data['value'] else 0


@Condition.type('minimum', ('value', Number))
def min_check(value, condition_data: dict, **kwargs):
    return 1 if value >= condition_data['value'] else value / condition_data['value']


@Condition.type('update')
def update_check(value, condition_data: dict, **kwargs):
    return kwargs['is_update']


@Effect.type('conditional', ('condition', dict), ('on_condition', dict))
def conditional_effect(user: User, effect_data: dict, **kwargs):
    """
    Executes another effect `on_condition` if a condition `condition` is fulfilled.
    Otherwise, does nothing.
    :param user:            Target user
    :param effect_data:     Effect data
    :param kwargs:          kwargs
    """
    if Condition(effect_data['condition']).is_fulfilled_for(user):
        Effect(effect_data['on_condition']).execute_on(user, **kwargs)
