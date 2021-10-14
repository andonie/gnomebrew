"""
Describes conditions in game
"""
from collections import Callable
from typing import List

from gnomebrew.game.objects.game_object import GameObject
from gnomebrew.game.user import User


class Condition(GameObject):
    """
    Wraps condition data.
    """

    condition_resolvers = dict()

    @classmethod
    def type(cls, condition_type: str, **kwargs):
        """
        Describes a condition type. Used as a decorator for condition resolvers.
        Decorated function is expected to take these parameters:

        1. `user: User`
        2. `condition_data: dict`
        3. **kwargs: Will contain any known current values of any GameID.

        :param condition_type:   Unique Name of the condition this resolves.
        """
        if condition_type in cls.condition_resolvers:
            raise Exception(f"Condition Type {condition_type} already in use.")

        def wrapper(fun: Callable):
            cls.condition_resolvers[condition_type] = dict()
            cls.condition_resolvers[condition_type]['fun'] = fun
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
        return False if 'target_id' not in self._data or self._data['state'] == 1 else self._data['target_id'] == game_id

    def current_completion(self, value) -> float:
        """
        Checks if the current value meets the condition.
        :param value:   A value.
        :return:        A number between 0 and 1, representing the degree of completion of this conditon.
                        Only 1 will be recognized as condition met.
        """
        return Condition.condition_resolvers[self._data['condition_type']]['fun'](value, self._data)

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


# Condition Types


@Condition.type('flag')
def flag_check(value, condition_data: dict):
    """
    Checks if a certain flag is set.
    :param value:
    :param condition_data:
    :return:
    """

id_eval_types = {
    'equals': lambda val, data: 1 if val == data['target_value'] else 0,
    'any': lambda val, data: 1
}

@Condition.type('id_eval')
def id_eval_check(value, condition_data: dict):
    if condition_data['eval_type'] not in id_eval_types:
        raise Exception(f"Evaluation Type {condition_data['eval_type']} not supported")
    return id_eval_types[condition_data['eval_type']](value, condition_data)

