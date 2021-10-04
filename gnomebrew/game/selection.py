"""
This module manages user selection.
"""
from typing import Type, Callable, Union

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.user import User, get_resolver, update_resolver
from gnomebrew.play import request_handler

selection_ids = dict()


def selection_id(base_id: str, is_generic: bool = False):
    """
    Registers an ID as a resolvable selection. To be used as a decorator function. Decorated function is expected to
    parameters `game_id`, `user`, `set_value`, and `**kwargs` and expected to return the value currently selected.

    * When **reading** a selection: `set_value` is set to None.
    * When **writing** a selection: `set_value` defines the value to write.

    :param base_id:         The selection ID to register, e.g. 'selection.alchemy.next_recipe'
    :param is_generic:      If this is set to `True`, any selection string that starts with `selection_id` will call
                            the decorated method. If set to `False`, only the exact `selection_id` called will call
                            the function.
    """
    assert base_id not in selection_ids
    assert base_id.split('.')[0] == 'selection'

    def wrapper(fun: Callable):
        selection_ids[base_id] = dict()
        selection_ids[base_id]['fun'] = fun
        selection_ids[base_id]['is_generic'] = is_generic
        return fun

    return wrapper


@request_handler
def select(request_object: dict, user: User):
    response = GameResponse()
    target_id = request_object['target_id']
    value = request_object['value']
    # Ensure target ID is valid selection.
    user.update()
    return response


def _get_matching_fun(game_id: str) -> Union[Callable, None]:
    """
    This function returns the most appropriate ID resolver for a given ID.
    :param game_id:     A selection ID, e.g. 'selection.it_cat.fruit'
    :return:            The matching ID resolver function, assuming it exists. `None` otherwise.
    """
    if game_id in selection_ids:
        # The exact ID is registered.
        return selection_ids[game_id]['fun']
    # No direct match: Check for basic match with generic-type resolvers
    matches = [selection_id_obj['fun'] for selection_id, selection_id_obj in selection_ids.items()
               if selection_id_obj['is_generic'] and game_id.startswith(selection_id)]
    if matches:
        return matches[0]
    # No match could be found. Return None
    return None


@get_resolver('selection')
def get_selection(game_id: str, user: User, **kwargs):
    """
    Returns a selection from a selection ID.
    :param user:        A user.
    :param game_id:     A user selection/choice ID, e.g. 'selection.world_focus'
    :param kwargs:      `default`: A value to return if no ID result matches.
    :raises             Exception if ID cannot be resolved an no `default` is set.
    :return:            Currently selected ID under this selection ID.
    """
    selection_function = _get_matching_fun(game_id)
    if selection_function:
        return selection_function(game_id=game_id, user=user, set_value=None, **kwargs)
    else:
        if 'default' in kwargs:
            return kwargs['default']
        else:
            raise Exception(f"Cannot interpret {game_id=}")


@update_resolver('selection')
def selection_update(user: User, game_id: str, update, **kwargs):
    """
    Called when a user selection update occurs.
    :param user:        Target user
    :param game_id:     ID of the selection made
    :param update:      Value of the selection made
    :param kwargs:
    :raises             Exception if `game_id` is unknown.
    """
    selection_function = _get_matching_fun(game_id)
    if selection_function:
        selection_function(game_id=game_id, user=user, set_value=update, **kwargs)
    else:
        raise Exception(f"Cannot interpret {game_id=}")

