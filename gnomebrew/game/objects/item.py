from typing import List, Dict

from gnomebrew.game.objects.game_object import load_on_startup, StaticGameObject
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import get_resolver, User
from gnomebrew.game.util import global_jinja_fun


@get_resolver('item')
def item(game_id: str, user: User, **kwargs):
    return Item.from_id(game_id)


@get_resolver('it_cat')
def it_cat(game_id: str, user: User, **kwargs):
    return ItemCategory.from_id(game_id)


@load_on_startup('items')
class Item(StaticGameObject):
    """
    Item Wrapper Class
    """

    def __init__(self, mongo_data):
        super().__init__(mongo_data)

    def __str__(self):
        return f"<Item {self._data['name']} -- {self._data=}>"

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
        return category_name[7:] in self._data['categories']

    def item_order(self):
        """
        Returns a number that's used as the order of the item. Used to keep the storage organized
        :return:    A number representing the order of this item.
        """
        if self.is_orderable():
            # Orderable Items have the highest order
            return 0
        if 'categories' in self._data:
            return 1 if 'mundane' in self._data['categories'] \
                else 2 if 'material' in self._data['categories'] \
                else 4

    def personality_adjust(self, personality: dict) -> float:
        """
        Applies a personality to this (*orderable*) item and returns a the % personality adjust.
        This percentage represents how an items desirability and demand is affected by patron personality.
        :param personality: A patron's personality JSON stored as `dict`
        :return:            The % change due to personality adjust, NOT the multiplication factor.
                            i.e. multiply by **1 +** `personality_adjust` to get the adjusted demand/desire
        """
        if 'orderable' not in self._data:
            raise AssertionError(f"This item ({self}) is not orderable.")
        if 'personality_adjust' not in self._data['orderable']:
            # This item has no personality adjustment-data. No action.
            return 1

        adjust_val = 0
        for adjustment in self._data['orderable']['personality_adjust']:
            if adjustment in personality:
                adjust_val += self._data['orderable']['personality_adjust'][adjustment] * personality[adjustment]

        return adjust_val

    def determine_fair_price(self, user) -> float:
        """
        Determines the 'fair' price for this item.
        :param user:    Executing user.
        :return:        A number representing this item's fair price considering the item's intrinsic value and
                        possible user upgrades.
        """
        return self._data['base_value'] * user.get('attr.tavern.price_acceptance', default=1)

    _order_list = list()

    @classmethod
    def on_data_update(cls):
        """
        This method is called from the backend whenever static item data is freshly updated from the database.
        """
        cls._order_list = list(filter(lambda item: item.is_orderable(), StaticGameObject.get_all_of_type('item').values()))


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

    def is_main_category(self):
        """
        Returns `True`, if this object represents a main category. An item can have an arbitrary amount of categories,
        but only belong into one main-category.
        """
        return self._data['is_main'] if 'is_main' in self._data else False

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
                                                           if all_items[item_name].matches_category_name(all_categories[category].get_id())]
        cls._items_by_category = new_data


@global_jinja_fun
def format_player_storage(storage_data: dict):
    """
    Formats a player's storage data nicely.
    :param storage_data: The value of `data.storage.content`
    :return:    An 'ordered' dict that will contain dicts ordered by item categories (main categories only), e.g.
    ```
    {
        <ItemCategory it_cat.mundane>: {
            <Item water>: 100,
            <Item simple_beer>: 200
        },
        <ItemCategory it_cat.material>: {
            <Item wood>: 1
        }
    }
    ```
    The order of the keys is ordered by item main category. Within the category, the order is arbitrary.
    Also omits 'item.gold' since it has a special role in-game.
    """
    to_be_sorted = dict()

    for item in storage_data:
        if item == 'gold':
            # Gold is special case. Ignore
            continue
        item_object: Item = Item.from_id(f"item.{item}")
        main_category: ItemCategory = next(filter(lambda cat: cat.is_main_category(),
                                                  map(lambda cat_str: ItemCategory.from_id('it_cat.' + cat_str),
                                                      item_object.get_static_value('categories'))))
        if main_category not in to_be_sorted:
            to_be_sorted[main_category] = dict()
        to_be_sorted[main_category].update({item_object: storage_data[item]})

    ret = dict()
    for key in sorted(to_be_sorted.keys()):
        # Insertion order is guaranteed iteration order. This way the Storage is rendered consistently.
        ret[key] = to_be_sorted[key]

    return ret