"""
The Alchemy Station module.
"""
from ctypes import Union
from typing import List, Dict

from gnomebrew.game.objects import Recipe
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import User
from gnomebrew.game.util import global_jinja_fun


@selection_id('selection.alchemy.next_recipe')
def process_alchemy_recipe_selection(game_id: str, user: User, set_value, **kwargs):
    if set_value:
        user.update('data.alchemy.next_recipe', set_value)
    else:
        # Read out the current selection.
        return user.get('data.alchemy.next_recipe', **kwargs)

@Effect.type('restart_alchemy')
def restart_alchemy_effect(user: User, effect_data: dict, **kwargs):
    """
    Restarts the alchemy process. This effect is included in every alchemy recipe and ensures that the Alchemy station
    starts the next recipe after a recipe is finished.
    :param user:            Target user.
    :param effect_data:     Complete effect data. Is always expected to be only `{ 'effect_type': 'restart_alchemy' }`, as
                            this effect type does not require any parameters.
    :param kwargs:
    """
    next_recipe_id = user.get('data.alchemy.next_recipe')
    if next_recipe_id == '_off':
        # The station is turned off. Do not execute anything and just end the effect here.
        return
    # We now expect `next_recipe_id` to always point at the ID of a valid recipe.
    recipe = user.get(next_recipe_id, **kwargs)

    # We always want to attempt executing this recipe.
    response = recipe.check_and_execute(user, **kwargs)

    # We want to execute any frontend-info the response received.
    response.finalize(user)

