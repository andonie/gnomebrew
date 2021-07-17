"""
Module for utility functions that are used in several modules of the game, such as random numbers.
"""

from numpy.random import default_rng
from gnomebrew_server import app
from typing import Callable
from gnomebrew_server.game.static_data import ItemCategory, Item

rng = default_rng()


def global_jinja_fun(fun: Callable):
    """
    Annotation. Marks a function as available in Gnomebrew's Template engine.
    :param fun: A function to be available in Gnomebrew's jinja instance.
    """
    kwarg = {
        fun.__name__: fun
    }
    app.jinja_env.globals.update(**kwarg)


def random_normal(**kwargs):
    """
    Wrapper for normal-distributed random variables

    If 'size' is set, the function returns a list of `size` independent random varibales in the given bounds.
    Default is 1.

    Distribution options:
    * 'min' and 'max' ensures a normal distribution with input/output bounds
    * 'median' and 'std_deviation'
    * no input provides a normal distribution between 0 and 1 (median 0.5)
    """
    # Define Median and std deviation
    if 'min' and 'max' in kwargs:
        median = (kwargs['min'] + kwargs['max']) / 2
        std_deviation = (kwargs['min'] + kwargs['max']) / 6
    elif 'median' and 'std_deviation' in kwargs:
        median = kwargs['median']
        std_deviation = kwargs['std_deviation']
    else:
        median = 0.5
        std_deviation = 1 / 6

    size = kwargs['size'] if 'size' in kwargs else 1
    result = rng.normal(loc=median, scale=std_deviation, size=size)

    if 'min' or 'max' in kwargs:
        # It happens rarely, but sometimes values are beyond 3 standard deviations.
        # To ensure 'min' and 'max' hold, we map
        if 'max' not in kwargs:
            # Only min
            map_fun = lambda x: max(x, kwargs['min'])
        elif 'min' not in kwargs:
            # Only max
            map_fun = lambda x: min(x, kwargs['max'])
        else:
            # Min and Max
            map_fun = lambda x: min(max(x, kwargs['min']), kwargs['max'])
        result = map(map_fun, result)

    return list(result)[0] if size == 1 else result


def random_uniform(**kwargs):
    """
    Generates uniformly distributed random variables

    * If 'size' is set, the function returns a list of `size` independent random varibales in the given bounds.
    Default is 1.
    * `min` sets the minimum value. Default is 0
    * `max` sets the maximium value. Default is 1
    """
    return rng.uniform(low=kwargs['min'] if 'min' in kwargs else 0,
                       high=kwargs['max'] if 'max' in kwargs else 1,
                       size=kwargs['size'] if 'size' in kwargs else None)


@global_jinja_fun
def shorten_num(val) -> str:
    """
    Number shortening code that works identical to JS implementation.
    :param val:     A number, e.g. `1337`
    :return:        A string that represents a shortened version of that number, e.g. `1.34 K`
    """
    shortcodes = ['', 'K', 'M', 'MM']
    num_level = 0
    while val > 1000:
        val /= 1000
        num_level += 1

    if num_level > 0:
        val = "{:.2f}".format(val)

    return str(val) + (' ' + shortcodes[num_level] if num_level != 0 else '')


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
    ret = dict()

    for item in storage_data:
        if item == 'gold':
            continue

        item_object: Item = Item.from_id('item.' + item)
        main_category: ItemCategory = next(filter(lambda cat: cat.is_main_category(),
                                                  map(lambda cat_str: ItemCategory.from_id('it_cat.' + cat_str),
                                                      item_object.get_value('categories'))))
        if main_category not in ret:
            ret[main_category] = dict()
        ret[main_category].update({item_object: storage_data[item]})

    return ret
