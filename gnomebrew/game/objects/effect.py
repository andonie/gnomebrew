"""
This module wraps Effect objects in Gnomebrew.
"""
from collections import Callable

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
        if effect_type in cls.effect_resolvers:
            raise Exception(f"{effect_type} is already a registered effect type.")

        def wrapper(fun: Callable):
            cls.effect_resolvers[effect_type] = fun
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
        Effect.effect_resolvers[self._data['effect_type']](user=user, effect_data=self._data, **kwargs)


# Some basec effects

@Effect.type('delta_inventory')
def delta_inventory(user: User, effect_data: dict, **kwargs):
    """
    Event execution for a change in inventory data.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[material_id] = delta`
    """
    user_inventory = user.get('data.storage.content', **kwargs)
    max_capacity = user.get('attr.storage.max_capacity', **kwargs)
    inventory_update = dict()
    for material in effect_data['delta']:
        if material not in user_inventory:
            inventory_update['storage.content.' + material] = min(max_capacity, effect_data['delta'][material])
            # The new item might be orderable. In that case --> Add it to the price list
            item_object: Item = Item.from_id('item.' + material)
            if item_object.is_orderable():
                inventory_update[f'tavern.prices.{material}'] = item_object.get_static_value('base_value')
        elif material == 'gold':
            # Gold is an exception and can grow to infinity always:
            inventory_update[f'storage.content.{material}'] = user_inventory[material] + effect_data['delta'][material]
        else:
            inventory_update['storage.content.' + material] = min(max_capacity,
                                                                  user_inventory[material] + effect_data['delta'][material])
    user.update('data', inventory_update, is_bulk=True)


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

