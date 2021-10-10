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

    def met_for(self, user: User, **kwargs) -> bool:
        """
        Checks if the current user meets this condition.
        :param user:    A user.
        :param kwargs   should contain any known data mapped as `{ game_id: value }`
        :return:        `True` if the condition is met for this user. Otherwise `False`.
        """
        return Condition.condition_resolvers[self._data['condition_type']](user, **kwargs)


@Condition.type('reach')
def reach_condition(user: User, condition_data: dict, **kwargs):
    """
    Requires the user to reach a certain target amount of an entity (or more).
    :param user:            target user.
    :param condition_data:  JSON data from Condition object.
    :param kwargs:          Any already resolved Game-IDs in format `{ game_id: value }`
    :return:                `True`, if the conditition is met. Otherwise, `False`.
    """
    target_name = condition_data['target']
    if target_name in kwargs:
        target_value = kwargs[target_name]
    else:
        # I have to calculate the value myself right now. :(
        target_value = user.get(f"data.storage.content.{target_name}", **kwargs)
    return target_value >= condition_data['to_reach']


@Condition.type('give')
def give_condition(user: User, condition_data: dict, **kwargs):
    """
    Requires the user to give a number of items from their inventory via dedicated game request.
    :param user:                target user.
    :param condition_data:      JSON data from Condition object.
    :param kwargs:              Any already resolved Game-IDs in format `{ game_id: value }`
    :return:                    `True`, if the conditition is met. Otherwise, `False`.
    """

@Condition.type('quest')
def quest_condition(user: User, condition_data: dict, **kwargs):
    """

    :param user:
    :param condition_data:
    :param kwargs:
    :return:
    """
