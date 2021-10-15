"""
Storage Module
"""
import operator
from os.path import join
from typing import List

from flask import render_template, url_for

from gnomebrew import log
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.game_object import StaticGameObject
from gnomebrew.game.objects.item import ItemCategory, Item
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import html_generator, User, id_update_listener, get_resolver, get_postfix, update_resolver
from gnomebrew.game.util import global_jinja_fun, css_friendly


def _get_display_function(game_id: str) -> str:
    """
    Returns the string that describes which display function to use for a given ID.
    :param game_id:     A game_id
    :return:            The function with which this data is to be displayed (e.g. 'shorten_num')
    """
    if game_id in ['data.storage.content.gold']:
        return 'shorten_cents'
    if game_id in ['special.time']:
        return 'shorten_time'

    # Default Case: Handle data at ID as number
    return 'shorten_num'


@id_update_listener(r'^data\.storage\.content\.*')
def forward_storage_update_to_ui(user: User, data: dict, game_id: str, **kwargs):
    updated_elements = {css_friendly(f"storage.{'.'.join(item_id.split('.')[3:])}"): {'data': data[item_id],
                                                                                      'display_fun': _get_display_function(
                                                                                          game_id)} for item_id in data}
    if 'command' in kwargs:
        update_type = 'inc' if kwargs['command'] == '$inc' else 'set'
    else:
        update_type = 'set'

    user.frontend_update('update', {
        'update_type': update_type,
        'updated_elements': updated_elements
    })


@selection_id('selection.cat_toggle', is_generic=True)
def category_toggle(game_id: str, user: User, set_value, **kwargs):
    """
    Sets/reads the `cat_toggle` selection. For every category that is visible in the UI, `selection.cat_toggle.category_name`
    :param kwargs:
    :return:        `True`, when this category is toggled on. If it's toggled off, returns `False`.
    """
    game_id_splits = game_id.split('.')
    if len(game_id_splits) != 3:
        raise Exception(f"Cannot evaluate Game-ID: {game_id}")

    target_data_id = f'data.storage.it_cat_toggles.{game_id_splits[2]}'
    if set_value == None:
        # Return current toggle status
        return user.get(target_data_id, default=True, **kwargs)
    elif set_value == '_toggle':
        # Special case. Just toggle the current value.
        user.update(target_data_id, not user.get(target_data_id, default=True, **kwargs))
    else:
        # Update Category Toggle
        user.update(target_data_id, set_value)


@selection_id('selection.it_cat', is_generic=True)
def selection_from_it_cat(game_id: str, user: User, set_value, **kwargs):
    """
    Used to determine when a recipe asks for any item from within one category to choose which item to actually discount.
    :param game_id:     The ID of the selection to be made, starting with `'selection.it_cat'`.
    :param user:        Target user
    :param set_value:   `None`: The function returns the current selection under this value. Otherwise sets the
                        selection to `set_value`.
    :param kwargs:      `default`: Value to return in case the user has no options available for this selection and a
                        selection should be returned.
    """
    game_id_splits = game_id.split('.')
    target_category: ItemCategory = ItemCategory.from_id(f"it_cat.{game_id_splits[2]}")
    if set_value:
        # Update item category choice.
        current_selection = user.get(game_id)
        if set_value == current_selection:
            # The selected item got selected again. Instead _unset
            set_value = '_unset'
        return user.update(f"data.storage.it_cat_selections.{target_category.get_minimized_id()}", set_value)
    else:
        # Give current item selection from Category
        if 'default' in kwargs:
            del kwargs['default']
        selected_item = user.get(f"data.storage.it_cat_selections.{target_category.get_minimized_id()}", default=None,
                                 **kwargs)
        if selected_item and selected_item != '_unset':
            # There's an item selected in this category
            return selected_item
        else:
            # There is no item selection in this category
            # Instead, choose the item in the category you have the most of.

            best_item = _best_option_for_category(user, target_category)
            if best_item:
                return best_item

            # No valid result was found
            if 'default' in kwargs:
                return kwargs['default']
            else:
                raise Exception(f"No selection avaiable for {game_id} for user {user.get_id()}")


def _best_option_for_category(user, target_category, **kwargs):
    cat_item_names = list(map(lambda item_obj: item_obj.get_id(), target_category.get_matching_items()))
    user_storage = user.get('storage._content', **kwargs)
    cat_user_options = [(item_id, user_storage[item_id]) for item_id in user_storage if item_id in cat_item_names]
    if cat_user_options:
        return max(cat_user_options, key=lambda o: o[1])[0]
    else:
        return None


@id_update_listener(r'^data\.storage\.it_cat_selections\.*')
def forward_selection_update_to_frontends(user: User, data: dict, game_id: str, **kwargs):
    update_data = list()
    for element in data:
        if data[element] == '_unset':
            # Special Case, selection was unset. Pick most appropriate item instead.
            best_id = _best_option_for_category(user, ItemCategory.from_id(f"it_cat.{game_id.split('.')[3]}"))
            target_item = user.get(best_id, **kwargs)
        else:
            target_item = user.get(data[element], **kwargs)

        # Change Icon Image
        reload_img = dict()
        reload_img['selector'] = f".selection-it_cat-{css_friendly('.'.join(element.split('.')[3:]))}"
        reload_img['attr'] = 'src'
        reload_img['value'] = url_for("get_icon", game_id=target_item.get_id())
        update_data.append(reload_img)
        # Change Title attribute

        update_data.append({
            'selector': f".selection-it_cat-{css_friendly('.'.join(element.split('.')[3:]))}",
            'attr': 'title',
            'value': target_item.name()
        })

    user.frontend_update('update', {
        'update_type': 'change_attributes',
        'attribute_change_data': update_data
    })


def _storage_dict_iter(data_source: dict, storage_dict: dict, parent_id: str) -> int:
    """
    Helper function to be used recursively. Iterates one layer of a storage dict and fills all relevant data for the
    storage-dict-output.
    :param data_source:     The source-dict to iterate. Expected to only contain dicts and end point int values.
    :param storage_dict:    The storage dict to fill with the relevant data from this iteration.
    :param parent_id:       The parent id layers to ensure correct naming in there.
    :return                 Returns the sum of all underlying values.
    """
    total = 0
    if not parent_id:
        path_base = ""
    else:
        path_base = f"{parent_id}."
    for source_split in data_source:
        path = path_base + source_split
        val = data_source[source_split]
        if isinstance(val, int):
            # Simple case. Add this value to the full storage dict:
            storage_dict[path] = val
            total += val
        elif isinstance(val, dict):
            # Layered case. iterate this dict recursively.
            underlying = _storage_dict_iter(val, storage_dict, path)
            storage_dict[path] = underlying
            total += underlying
        else:
            raise Exception(f"Unexpected data source: {val}")
    return total


def _full_storage_dict(user: User, **kwargs):
    """
    Generates a dict for a given user, mapping every owned item ID to the amount in storage.
    :param user:        A user.
    :return:            A dict with {game_id: amount} for all owned items.
    """
    storage_data = user.get('data.storage.content')
    result = dict()

    _storage_dict_iter(storage_data, result, "")

    return result


@get_resolver('storage', dynamic_buffer=False)
def get_storage_amounts(user: User, game_id: str, **kwargs):
    splits = game_id.split('.')
    storage_data = user.get('data.storage.content', **kwargs)
    if splits[1] == '_content':
        # Return a full dict that describes the exact content with full item_id's mapped to the amount
        return _full_storage_dict(user, **kwargs)
    target_item = user.get('.'.join(splits[1:]))
    if target_item.has_postfixes() and len(splits) == 2:
        # storage-data for first postfix is always a dict. Return sum of all
        return sum(storage_data['item'][target_item.get_minimized_id()].values())
    else:
        result = storage_data[splits[1]]
        for split in splits[2:]:
            result = result[split]
        return result


@update_resolver('storage')
def update_storage_amount(user: User, game_id: str, update, **kwargs):
    # Format update data to conform with 'data' locations
    if 'mongo_command' in kwargs:
        command = kwargs['mongo_command']
    else:
        command = '$set'

    user.update('data.storage.content', update, mongo_command=command, is_bulk=True)
    return command, update


@Effect.type('delta_inventory')
def delta_inventory(user: User, effect_data: dict, **kwargs):
    """
    Event execution for a change in inventory data.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[material_id] = delta`
    """
    log('effect', f'executing effect', 'delta_inventory', f'usr:{user.get_id()}')
    user_inventory = user.get('storage._content', **kwargs)
    max_capacity = user.get('attr.storage.max_capacity', **kwargs)
    inventory_update = dict()
    for item_id in effect_data['delta']:
        item_object: Item = user.get(item_id)
        if item_id not in user_inventory:
            inventory_update[f'storage.content.{item_id}'] = min(max_capacity, effect_data['delta'][item_id])
            # The new item might be orderable. In that case --> Add it to the price list
            if item_object.is_orderable():
                # inventory_update[f'tavern.prices.{item_object.get_minimized_id()}'] = item_object.get_static_value('base_value')
                # TODO replace this logic with on_storage_added feature calling arbitrary effects
                pass

        if not item_object.has_storage_cap():
            # Gold is an exception and can grow to infinity always:
            inventory_update[f"storage.content.{item_id}"] = user_inventory[item_id] + effect_data['delta'][item_id]
        else:
            if item_id not in user_inventory:
                user_inventory[f"storage.content.{item_id}"] = min(max_capacity, effect_data['delta'][item_id])
            else:
                inventory_update[f"storage.content.{item_id}"] = min(max_capacity,
                                                                      user_inventory[item_id] + effect_data['delta'][
                                                                          item_id])

    user.update('data', inventory_update, is_bulk=True)


@Effect.type_info('delta_inventory')
def generate_type_info_for(effect_data: dict) -> List[List[str]]:
    """
    Generates the info for a delta inventory event.
    :param effect_data: Data to render info for.
    :return:            Info-lines to display
    """
    infos = list()
    for item_id in effect_data['delta']:
        infos.append([item_id, effect_data['delta'][item_id]])
    return infos


@global_jinja_fun
def get_available_category_data(user: User, **kwargs) -> List[dict]:
    """
    Returns a complete list of all categories this user currently has items in.
    :param user:    target user
    :param kwargs:  List of elements will be filtered by JSON data key/values from kwargs
    :return:        List of all item categories that meet the requirements.
    """
    player_storage = user.get('storage._content')
    cat_dict = ItemCategory.get_all_of_type('it_cat')
    result = list()

    for category in cat_dict.values():
        if all([category.has_static_key(key) and category.get_static_value(key) == kwargs[key] for key in kwargs]) and \
                any([item for item in category.get_matching_items() if item.get_id() in player_storage]):
            to_append = dict()
            to_append['category'] = category
            to_append['collapsed'] = user.get(f"selection._bool.cat_{category.get_minimized_id()}_collapsed", default=True)
            to_append['visible'] = user.get(f"selection._bool.cat_{category.get_minimized_id()}_visible", default=True)
            to_append['cat_order'] = category.get_static_value('cat_order') if category.has_static_key('cat_order') else 50
            result.append(to_append)

    return sorted(result, key=lambda cat: cat['cat_order'])
