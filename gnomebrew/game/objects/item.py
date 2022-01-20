import copy
from numbers import Number
from typing import List, Dict, Callable

from gnomebrew.game.objects.data_object import DataObject
from gnomebrew.game.objects.game_object import load_on_startup, StaticGameObject, GameObject
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import get_resolver, User, get_postfix
from gnomebrew.game.util import global_jinja_fun


@load_on_startup('items')
class Item(StaticGameObject):
    """
    Item Wrapper Class
    """

    def __init__(self, mongo_data):
        super().__init__(mongo_data)

    def get_name(self):
        return self._data['name']

    def is_orderable(self):
        """
        Returns `True` if patrons can order this item.
        """
        return True if 'orderable' in self._data else False

    def matches_category_name(self, category_name: str) -> bool:
        """
        Checks if this item belongs to a given category.
        :param category_name:   Name of the category to test this item against, simplified, e.g. `'mundane'`.
        :return:                `True` if the item belongs into this category. Otherwise `False`.
        """
        assert category_name[:7] == 'it_cat.'
        return category_name[7:] in self.get_static_value('categories')

    def item_order(self):
        """
        Returns a number that's used as the order of the item. Used to keep the storage organized
        :return:    A number representing the order of this item.
        """
        if 'categories' in self._data:
            return 1 if 'mundane' in self._data['categories'] \
                else 2 if 'material' in self._data['categories'] \
                else 4

    def has_storage_cap(self):
        """
        :return: `True`, if this item is affected by storage cap. Otherwise `False`. Managed through
        `disable_storage_cap`
        """
        return not self._data['disable_storage_cap'] if 'disable_storage_cap' in self._data else True

    def get_categories(self) -> List['ItemCategory']:
        """
        :return: a list of all Item Category objects which include this item.
        """
        return [ItemCategory.from_id(f"it_cat.{cat_name}") for cat_name in self._data['categories']]

    def in_category(self, cat_id: str) -> bool:
        """
        Tests if this item is in a given category
        :param cat_id:      Full ID of the category (e.g. it_cat.tier_0)
        :return:            `True` if the item belongs to the given category. Otherwise `False`
        """
        # Magic Number 7 cuts off `'it_cat.'` before using the pure identifier
        return cat_id[7:] in self._data['categories']


# Item Validation Code
Item.validation_parameters(('game_id', str), ('name', str), ('description', str), ('categories', list))


@load_on_startup('item_categories')
class ItemCategory(StaticGameObject):
    """
    Item Category Wrapper Class
    """

    _items_by_category: Dict[str, List[Item]] = dict()

    def __init__(self, mongo_data):
        super().__init__(mongo_data)

    def __lt__(self, other):
        """
        Custom Implemented __lt__ method.
        Used to ensure *consistent upgrade behavior* when applying several several Upgrades one after another:
        Before executing Upgrade behavior, all existing upgrades are sorted in a list before folding it with reduce(...)
        :param other:   Element to compare this to.
        :return:        True if self<other. False if self>=other
        """
        # Upgrades are only comparable with each other
        assert type(other) is ItemCategory
        return self._data['cat_order'] < other._data['cat_order']

    def __str__(self):
        return f'<ItemCategory {self._data["game_id"]}>'

    def has_item(self, item_name: str):
        """
        Checks if an item belongs to this category.
        :param item_name:   Name of the item to check against.
        :return:            `True` if the item belongs to this category. Otherwise `False`.
        """
        return item_name in self.get_matching_items()

    def is_main_category(self):
        """
        Returns `True`, if this object represents a main category. An item can have an arbitrary amount of categories,
        but only belong into one main-category.
        """
        return self._data['is_main'] if 'is_main' in self._data else False

    def is_frontend_category(self) -> bool:
        """
        :return: `True` if this category is visible in the frontend (e.g. in storage). Otherwise `False`
        """
        return 'storage_ui' not in self._data or self._data['storage_ui']

    def get_matching_items(self) -> List[Item]:
        """
        Returns a list of all items that belong into this category.
        :return:    A list of all items that belong in this category.
        """
        return ItemCategory._items_by_category[self._data['game_id']]

    @classmethod
    def on_data_update(cls):
        """
        This method is called from the backend whenever static item data is freshly updated from the database.
        """
        new_data = dict()
        all_items = StaticGameObject.get_all_of_type('item')
        all_categories = StaticGameObject.get_all_of_type('it_cat')
        for category in all_categories:
            new_data[all_categories[category].get_id()] = [all_items[item_name] for item_name in all_items
                                                           if all_items[item_name].matches_category_name(
                    all_categories[category].get_id())]
        cls._items_by_category = new_data

    def get_category_total_of(self, user: User, **kwargs) -> int:
        """
        Returns the total number of items a user owns that all belong to this category.
        :param user:        target user.
        :param kwargs:      any resolved IDs we already have.
        :return:            The sum of all items this user owns in storage that belong to this category.
        """
        inventory = user.get('storage._content', **kwargs)
        return sum([inventory[item.get_minimized_id()] for item in self.get_matching_items()
                    if item.get_minimized_id() in inventory])


# Item Category Data Validation

ItemCategory.validation_parameters(('game_id', str), ('name', str), ('description', str),
                                   ('name_individual_entity', str), ('cat_order', int))


# GAME ID STUFF


@get_resolver('item', dynamic_buffer=False, postfix_start=2)
def item(game_id: str, user: User, **kwargs) -> Item:
    return Item.from_id(game_id)


@get_postfix('item')
def append_postfix(old: Item, splits: List[str]) -> Item:
    new_data = copy.deepcopy(old.get_json())
    if 'postfixed' not in new_data:
        raise Exception(f'Cannot process postfix for {str(old)}')

    assert len(splits) == 1
    split = splits[0]

    new_data['game_id'] = f"{new_data['game_id']}.{split}"
    if 'postfix' not in new_data:
        new_data['postfix'] = dict()
    if new_data['postfixed']['postfix_type'] == 'it_cat':
        # The post fix adds an item from a given Item Category.
        cat_item = Item.from_id(f"item.{split}")
        new_data['name'] = f"{cat_item.get_static_value('postfix_name_addition', default='')}{new_data['name']}"
        new_data['postfix']['src_item'] = cat_item.get_minimized_id()
        new_data[
            'description'] = f"{new_data['description']}{cat_item.get_static_value('postfix_description_addition', default='')}"
    elif new_data['postfix_type'] == 'quality':
        new_data['name'] = f"{new_data['name']} ({split})"
        new_data['postfixed']['quality'] = split
    else:
        raise Exception(f"Could not process postfix {split} of {str(item)}.")
    return Item(new_data)


@get_resolver('it_cat')
def it_cat(game_id: str, user: User, **kwargs):
    return ItemCategory.from_id(game_id)


# Some Item Subtypes

@Item.subtype('fuel', ('energy', int))
class Fuel(Item):
    """
    Can burn and release energy
    """

    def __init__(self, data: dict):
        Item.__init__(self, data)

    def get_burn_value(self):
        """Returns energy value per item burned"""
        return self._data['fuel']['energy']

@Item.subtype("order", ('personality_adjust',
                        [('_openness', Number), ('_conscientiousness', Number), ('_extraversion', Number),
                         ('_agreeableness', Number), ('_neuroticism', Number)]),
              ('fair_value', Number), ('fair_demand', Number), ('elasticity', Number),
              ('saturation_speed', Number))
class OrderItem(Item):
    """Wraps the patron order specific subtype features."""

    MIN_PERSONALITY_ADJUST = 0.25
    MAX_PERSONALITY_ADJUST = 4

    def __init__(self, data):
        Item.__init__(self, data)

    def calculate_personality_adjust(self, personality: dict) -> float:
        """
        Applies a personality to this (*Order*) item and returns the % personality adjust.
        This percentage represents how an items desirability and demand is affected by patron personality.
        :param personality:     A patron's personality JSON as `dict`
        :return:                The % change due to personality adjust, NOT the multiplication factor.
                                i.e. multiply by **1 +** `personality_adjust` to get the adjusted demand/desire
        """
        if 'personality_adjust' not in self._data['orderable']:
            # This item has no personality adjustment-data. No action.
            return 1

        adjust_val = 0
        for personality_attribute in self._data['orderable']['personality_adjust']:
            adjust_val += self._data['orderable']['personality_adjust'][personality_attribute] * personality[
                personality_attribute]

        return max(OrderItem.MIN_PERSONALITY_ADJUST, min(1 + adjust_val, OrderItem.MAX_PERSONALITY_ADJUST))

    def determine_fair_price(self, user, **kwargs) -> float:
        """
        Determines the 'fair' price for this item.
        :param user:    Executing user.
        :return:        A number representing this item's fair price considering the item's intrinsic value and
                        possible user upgrades.
        """
        return self._data['orderable']['base_value'] * user.get('attr.station.tavern.price_acceptance', **kwargs)
