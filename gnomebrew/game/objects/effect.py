"""
This module wraps Effect objects in Gnomebrew.
"""
from collections import Callable
from typing import List

from gnomebrew.game.objects import Item
from gnomebrew.game.objects.game_object import GameObject
from gnomebrew.game.user import User


class Effect(GameObject):
    """
    Wraps effect data.
    """

    effect_resolvers = dict()

    @classmethod
    def type(cls, effect_type: str):
        """
        Registers a resolver function that can handle a specific effect type.
        Used as annotation for a function that expects a `user`, `effect_data', and `kwargs`
        :param effect_type: The effect type to handle
        """
        if effect_type not in cls.effect_resolvers:
            cls.effect_resolvers[effect_type] = dict()
        if 'execute' in cls.effect_resolvers[effect_type]:
            raise Exception(f"{effect_type} is already a registered effect type.")

        def wrapper(fun: Callable):
            cls.effect_resolvers[effect_type]['execute'] = fun
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


# Some basec effects


@Effect.type('push_data')
def push_data(user: User, effect_data: dict, **kwargs):
    """
    Event execution for an arbitrary push (list append) of data.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[data-id] = delta
    """
    push_data = effect_data['to_push']
    push_target = effect_data['push_target']
    user.update(push_target, push_data, mongo_command='$push')


@Effect.type('ui_update')
def ui_update(user: User, effect_data: dict, **kwargs):
    """
    Event execution for a user ui update
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[data-id] = delta
    """
    user.frontend_update('ui', effect_data)


@Effect.type('repeat')
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

@Effect.type('id_update')
def id_update(user: User, effect_data: dict, **kwargs):
    """
    Updates a given ID with a given value.
    :param user:        Target user
    :param effect_data: Effect data.
    :param kwargs:      kwargs
    """
    if 'game_id' not in effect_data or 'value' not in effect_data:
        raise Exception(f"Missing data for ID Update: {effect_data}")

    user.update(effect_data['game_id'], effect_data['value'], **kwargs)
