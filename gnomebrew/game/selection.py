"""
This module manages user selection.
"""
from typing import Type, Callable, Union

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.request import PlayerRequest
from gnomebrew.game.user import User, get_resolver, update_resolver

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
        selection_ids[base_id]['base_id'] = base_id
        return fun

    return wrapper


@PlayerRequest.type('select', is_buffered=True)
def select(user, request_object: dict, **kwargs):
    response = GameResponse()
    target_id = request_object['target_id']
    value = request_object['value']
    # Ensure target ID is valid selection.
    match = next(filter(lambda data: data[0]==target_id or (data[1]['is_generic'] and target_id.startswith(data[0])), selection_ids.items()), None)
    if match:
        match[1]['fun'](game_id=target_id, user=user, set_value=value, **kwargs)
        response.succeess()
    else:
        response.add_fail_msg(f"Could not find a selection ID {target_id}")
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



# Generic Selection Helper Classes

@selection_id('selection._bool', is_generic=True)
def boolean_selection_helper(game_id: str, user: User, set_value, **kwargs):
    """
    Helper Method. Any selection in here will be a boolean and any subname can be used by any application.
    :param game_id:     Target ID (e.g. 'selection._bool.alchemy_is_restart')
    :param user:        Target user
    :param set_value:   If `None`: Read out current boolean content or `default`. If set to a boolean, will
                        update the selection to this boolean.
    :param kwargs:      can have `default`
    """
    splits = game_id.split('.')
    assert len(splits) == 3
    if set_value == None:
        # Set value was none. -> Read output.
        current_data = user.get('data.special.selection._bool', **kwargs)
        if splits[2] in current_data:
            return current_data[splits[2]]
        else:
            if 'default' in kwargs:
                return kwargs['default']
            else:
                raise Exception(f"Selection for {game_id} does not exist for user {user.get_id()}. No default was given.")
    else:
        # Update the value
        user.update(f"data.special.selection._bool", set_value, **kwargs)
