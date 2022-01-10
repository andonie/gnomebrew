"""
Storage Module
"""
from typing import List

from flask import url_for

from gnomebrew import log
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.game_object import render_object
from gnomebrew.game.objects.item import ItemCategory, Item
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import User, id_update_listener, get_resolver, update_resolver
from gnomebrew.game.util import global_jinja_fun, css_friendly, render_info, css_unfriendly, get_id_display_function


@id_update_listener(r'^data\.station\.storage\.content\.*')
def forward_storage_update_to_ui(user: User, data: dict, game_id: str, **kwargs):
    updated_elements = {
        css_friendly(f"storage.{'.'.join(data_update_id.split('.')[4:])}"): {'data': data[data_update_id],
                                                                             'display_fun': get_id_display_function(
                                                                                 game_id)} for data_update_id in data}
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

    target_data_id = f'data.station.storage.it_cat_toggles.{game_id_splits[2]}'
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
        return user.update(f"data.station.storage.it_cat_selections.{target_category.get_minimized_id()}", set_value)
    else:
        # Give current item selection from Category
        if 'default' in kwargs:
            del kwargs['default']
        selected_item = user.get(f"data.station.storage.it_cat_selections.{target_category.get_minimized_id()}",
                                 default=None,
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


@id_update_listener(r'^data\.station\.storage\.it_cat_selections\.*')
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
    storage_data = user.get('data.station.storage.content')
    result = dict()

    _storage_dict_iter(storage_data, result, "")

    return result


@get_resolver('storage', dynamic_buffer=False)
def get_storage_amounts(user: User, game_id: str, **kwargs):
    splits = game_id.split('.')
    storage_data = user.get('data.station.storage.content', **kwargs)
    if splits[1] == '_content':
        # Return a full dict that describes the exact content with full item_id's mapped to the amount
        return _full_storage_dict(user, **kwargs)
    else:
        # Evaluate storage data
        ret = storage_data
        for split in game_id.split('.')[1:]:
            try:
                ret = ret[split]
            except:
                # Did not find this in storage. Return default value if given or raise exception
                if 'default' in kwargs:
                    return kwargs['default']
                else:
                    raise Exception(f"Did not find {game_id} in storage")
        if isinstance(ret, dict):
            # Return value is a dict. Sum up all its content
            ret = _storage_dict_iter(ret, dict(), "")
        return ret


@update_resolver('storage')
def update_storage_amounts(user: User, game_id: str, update, **kwargs):
    # Forward update data straight to the data location
    splits = game_id.split('.')
    appendage = '.' + '.'.join(splits[1:]) if game_id != 'storage' else ''
    return user.update(f"data.station.storage.content{appendage}", update, **kwargs)


@Effect.type('delta_inventory', ('delta', dict))
def delta_inventory(user: User, effect_data: dict, **kwargs):
    """
    Event execution for a change in inventory data.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as
    ```python
    {
        'effect_type': 'delta_inventory',
        'delta': {
            'item-water': -10,
            'item-sword-short-diamond': 1
        }
    }
    ```
    """
    log('effect', f'executing effect', 'delta_inventory', f'usr:{user.get_id()}')
    user_inventory = user.get('storage._content', **kwargs)
    max_capacity = user.get('attr.station.storage.max_capacity', **kwargs)
    inventory_update = dict()
    known_frontend_category_ids = list(
        map(lambda x: x['category'].get_id(), get_available_category_data(user, storage_ui=True)))
    new_items = []
    for item_id_input in effect_data['delta']:
        # Translate content of dict which might be css_formatted
        item_object: Item = user.get(css_unfriendly(item_id_input))
        item_id = item_object.get_id()
        item_delta = effect_data['delta'][item_id_input]

        if item_id not in user_inventory:
            inventory_update[item_id] = min(max_capacity, item_delta)
            new_items.append(item_object)

        if not item_object.has_storage_cap():
            # Some Items can go beyond storage caps:
            inventory_update[item_id] = user_inventory[item_id] + item_delta
        else:
            if item_id not in user_inventory:
                user_inventory[item_id] = min(max_capacity, item_delta)
            else:
                # Default Case: Add inventory + delta
                inventory_update[item_id] = min(max_capacity, user_inventory[item_id] + item_delta)

    user.update('storage', inventory_update, is_bulk=True)

    for new_item in new_items:
        # Generate The classes this item_amount render would belong to based on known convenctions
        container_class = "gb-storage-item-view gb-info gb-info-highlight"
        # Generate data that is the same for all renders independently of category
        base_data = {'item_id': new_item.get_id(), "amount": inventory_update[new_item.get_id()], "class": container_class }
        # Add `current_user` to this render to enable user-context-bound get requests (e.g. for quest data)
        item_amount_html = render_object('render.item_amount', data=base_data, current_user=user)
        for category in new_item.get_categories():
            if category.get_id() not in known_frontend_category_ids and category.is_frontend_category():
                # Update user inventory locally to reflect the changes in this item before rendering the new category
                user_inventory[new_item.get_id()] = inventory_update[new_item.get_id()]
                # New category added. Add this to the frontend.]
                render_data = generate_category_render_data(user, category)
                user.frontend_update('ui', {
                    'type': 'append_element',
                    'selector': '.gb-storage-category-view',
                    'element': render_object('render.storage_category',
                                             data=render_data,
                                             player_inventory=user_inventory,
                                             category_selection_id=user.get(
                                                 f'data.station.storage.it_cat_selections.{category.get_minimized_id()}',
                                                 default='_unset', **kwargs))
                })
            else:
                user.frontend_update('ui', {
                    'type': 'append_element',
                    'selector': f'#{css_friendly(category.get_id())}-items',
                    'element': item_amount_html
                })
        user.frontend_update('ui', {
            'type': 'player_info',
            'target': '#gb-global-info',
            'content': render_info(user, 'NEW:', new_item.get_id()),
            'duration': 120
        })

        # The new item might be orderable. In that case --> Add it to the price list


@Effect.type_info('delta_inventory')
def generate_type_info_for(effect_data: dict) -> List[List[str]]:
    """
    Generates the info for a delta inventory event.
    :param effect_data: Data to render info for.
    :return:            Info-lines to display
    """
    infos = list()
    for item_id in effect_data['delta']:
        if item_id == 'item-gold':
            # Special Treatment for Gold
            infos.append(['item.gold', f"txt:{str(effect_data['delta'][item_id] / 100)}"])
        else:
            infos.append([item_id.replace('-', '.'), str(effect_data['delta'][item_id])])
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
            result.append(generate_category_render_data(user, category))

    return sorted(result, key=lambda cat: cat['cat_order'])


def generate_category_render_data(user: User, category: ItemCategory):
    """
    Generates the data expected by `render.storage_category` to render the data.
    :param user:        Target user.
    :param category:    Target category.
    :return:            Appropriate data.
    """
    cat_data = dict()
    cat_data['category'] = category
    cat_data['collapsed'] = user.get(f"selection._bool.cat_{category.get_minimized_id()}_collapsed", default=True)
    cat_data['visible'] = user.get(f"selection._bool.cat_{category.get_minimized_id()}_visible", default=True)
    cat_data['cat_order'] = category.get_static_value('cat_order') if category.has_static_key('cat_order') else 50
    return cat_data
