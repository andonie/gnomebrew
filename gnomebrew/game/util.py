"""
Module for utility functions that are used in several modules of the game, such as random numbers.
"""
import datetime
import random

from numpy.random import default_rng
from gnomebrew import app
from typing import Callable
from markdown import markdown
from flask import url_for

rng = default_rng()

FUZZY_DEVIATION_PERCENTAGE = 0.05


def global_jinja_fun(fun: Callable):
    """
    Annotation. Marks a function as available in Gnomebrew's Template engine.
    :param fun: A function to be available in Gnomebrew's jinja instance.
    """
    kwarg = {
        fun.__name__: fun
    }
    app.jinja_env.globals.update(**kwarg)
    return fun


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
        std_deviation = (kwargs['max'] - kwargs['min']) / 6
    elif 'median' and 'std_deviation' in kwargs:
        median = kwargs['median']
        std_deviation = kwargs['std_deviation']
    else:
        median = 0.5
        std_deviation = 1 / 6

    size = kwargs['size'] if 'size' in kwargs else 1
    result = rng.normal(loc=median, scale=std_deviation, size=size)

    if 'min' in kwargs or 'max' in kwargs:
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


def fuzzify(num, deviation=FUZZY_DEVIATION_PERCENTAGE):
    """
    Creates some random noise. Takes
    :param num: A number to fuzzify.
    :param deviation:   Standard deviation expressed as percentage of median
    :return:    A random normally distributed number with `median=num` and a standard deviation of `5%` unless specified
                differently
    """
    return random_normal(median=num, std_deviation=num * deviation)


def is_weekday() -> bool:
    """
    :return: `True` when today is a weekday (Mon/Tue/Wed/Thu/Fri), otherwise `False` (Sat/Sun).
    """
    return datetime.datetime.utcnow().weekday() < 5


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
def shorten_cents(val) -> str:
    """
    Number display for a unit that's being stored in **cents** rather than in whole units.
    This is relevant for gold
    :param val:     a value in cents
    :return:        a shortened version of the given `val`, displayed similarly to `shorten_num`
    """
    return shorten_num(val / 100)



@global_jinja_fun
def format_markdown(input: str) -> str:
    """
    Basic markdown formatter for access in templates.
    :param input:   Input string formatted in markdown
    :return:        Output string formatted as HTML
    """
    return markdown(input)
