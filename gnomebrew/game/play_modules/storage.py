"""
Storage Module
"""
import operator
from os.path import join

from flask import render_template

from gnomebrew.game.objects.item import ItemCategory, Item
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import html_generator, User, frontend_id_resolver

@html_generator('html.storage.content')
def render_storage_content(game_id: str, user: User, **kwargs):
    return render_template(join('snippets', '_storage_content.html'),
                           content=user.get('data.storage.content'))


@frontend_id_resolver(r'^data\.storage\.*')
def show_storage_updates_in_general(user: User, data: dict, game_id: str, **kwargs):
    if 'command' in kwargs and kwargs['command'] == '$set':
        user.frontend_update('update', data)
    else:
        user.frontend_update('ui', {
            'type': 'reload_element',
            'element': 'storage.content'
        })


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
        assert set_value.startswith('item.')
        user.update(f"data.storage.it_cat_selections.{target_category.get_minimized_id()}", set_value)
        return 'no_mongo', {}
    else:
        # Give current item selection from Category
        selected_item = user.get(f"data.storage.it_cat_selections.{target_category.get_minimized_id()}", default=None)
        if selected_item and selected_item != '_unset':
            # There's an item selected in this category
            return selected_item
        else:
            # There is no item selection in this category
            # Instead, choose the item in the category you have the most of.
            cat_item_names = list(map(lambda item_obj: item_obj.get_minimized_id(), target_category.get_matching_items()))
            cat_user_options = {it_name: amount for it_name, amount in user.get('data.storage.content').items()
                                if it_name in cat_item_names}
            if cat_user_options:
                # The user has inventory for this item:
                return max(cat_user_options.items(), key=operator.itemgetter(1))[0]
            else:
                if 'default' in kwargs:
                    return kwargs['default']
                else:
                    raise Exception(f"No selection avaiable for {game_id} for user {user.get_id()}")




