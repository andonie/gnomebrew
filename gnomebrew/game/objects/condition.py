"""
Describes conditions in game
"""
from collections import Callable

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


@Condition.type('id_eval')
def id_eval_check(value, condtion_data: dict):
    if condtion_data['eval_type'] == 'equals':
        return 1 if value == condtion_data['target_value'] else 0
