"""
Module for utility functions that are used in several modules of the game, such as random numbers.
"""
import datetime
import math
import random
import re
import uuid

from numpy.random import default_rng
from gnomebrew import app
from typing import Callable, List, Any
from markdown import markdown
from flask import url_for, render_template_string

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
def icon(game_id: str, **kwargs):
    """
    Wraps the <img> tag formatted for game icons to increase code readability in HTML templates.
    :param game_id: An entity ID
    :keyword class  (default `gb-icon`), will set the content of the class attribute of the image tag. Can therefore
                    include multiple classes separated by a space.
    :keyword href   href attribute content
    :keyword id     ID attribute content
    :return:        An image tag that will properly display the image.
    """
    element_addition = ''
    from gnomebrew.game.objects import StaticGameObject
    if StaticGameObject.is_known_prefix(game_id.split('.')[0]):
        entity = StaticGameObject.from_id(game_id)
        element_addition = f' title="{entity.name()}"'

    if 'class' not in kwargs:
        if 'img_class' in kwargs: # Added because python compiler did not like class= in python code :(
            kwargs['class'] = kwargs['img_class']
        else:
            kwargs['class'] = 'gb-icon'

    if 'href' in kwargs:
        element_addition += f' href="{kwargs["href"]}"'

    if 'id' in kwargs:
        element_addition += f' id="{kwargs["id"]}"'

    return f'<img class="{kwargs["class"]}"{element_addition} src="{url_for("get_icon", game_id=game_id)}">'


@global_jinja_fun
def render_info(user, *info_elements, **kwargs):
    new_info = f'<div class="gb-info {kwargs["info_class"] if "info_class" in kwargs else "gb-info-default"}" title="{kwargs["title"] if "title" in kwargs else ""}">'
    for element in info_elements:
        if element.startswith('id:'):
            # Assume this to be a to-be updated Game ID and hence wrap it in an appropriate <span>
            target_id = element[3:]
            target_value = user.get(target_id, **kwargs, default=0)
            new_info += f'<div class="{css_friendly(target_id)} gb-info-content">{target_value}</div>'
        elif element.startswith('txt:'):
            new_info += f'<div class="gb-info-content">{element[4:]}</div>'
        elif is_game_id_formatted(element):
            with app.app_context():
                new_info += icon(element, img_class='gb-icon-sm' if 'icon_class' not in kwargs else kwargs['icon_class'])
        else:
            new_info += f'<div class="gb-info-content">{element}</div>'
    new_info += '</div>'
    return new_info


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
def shorten_time(val: int) -> str:
    """
    Renders a given number as a human-readable time.
    :param val: A number representing an amount of seconds to wait
    :return:
    """
    if val <= 60:
        return f"{math.floor(val)} s"
    elif val <= 60 * 60:
        rest = val % 60
        return f"{math.floor(val / 60)} m{f', {shorten_time(rest)}' if rest > 0 else ''}"
    elif val <= 60 * 60 * 24:
        rest = val % 60 * 60
        return f"{math.floor(val / (60 * 60))} h{f', {shorten_time(rest)}' if rest > 0 else ''}"
    else:
        rest = val % (60 * 60 * 24)
        return f"{math.floor(val / (60 * 60 * 24))} days{f', {shorten_time(rest)}' if rest > 0 else ''}"


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
def format_markdown(code: str) -> str:
    """
    Basic markdown formatter for access in templates. Includes a pre-compiler that evaluates the input as a jinja
    template. This enables **arbitrary code exeucution**. Hence this function should remain inaccessible to users.
    :param code:   Input string formatted in markdown. It is **highly critical that this input is safe**.
    :return:        Output string formatted as HTML
    """
    code = render_template_string(code)
    return markdown(code)


@global_jinja_fun
def render_string(string: str, current_user: 'User') -> str:
    """
    Renders a Game Content String as HTML to display. In order to ensure the string is adapted to the user's current
    state, template code is executed in the process.
    :param string:  A string to render as stored in engine data. Could contain template code.
    :param current_user:    A 'current_user' variable. Will be used in template content strings.
    :return:        HTML formatted version of input string.
    """
    if current_user:
        return render_template_string(string, current_user=current_user)
    else:
        raise Exception(f"Current User must be provided.")



@global_jinja_fun
def transpose_matrix(matrix: List[List]) -> List[List]:
    """
    Transposes a matrix formatted as a list of lists.
    :param matrix:  A list of list that's expected to behave as a matrix, i.e. every list on the second layer is
                    expected to have the same length.
    :return:        A transposed version of this matrix, i.e. `matrix[x][y] = result[y][x]` for all `x` and `y`
    """
    return [[matrix[x][y] for x in range(len(matrix))] for y in range(len(matrix[0]))]


@global_jinja_fun
def shift_matrix(matrix: List[List], d_x, d_y) -> List[List]:
    """
    Shifts a matrix.
    :param matrix:  A list of list that's expected to behave as a matrix, i.e. every list on the second layer is
                    expected to have the same length.
    :param d_x:     How much to shift matrix in X direction.
    :param d_y:     How much to shift matrix in Y direction.
    :return:        A shifted version of `matrix`. Values that are shifted beyond the limits of the matrix will rotate
                    around in modulo fashion.
    """
    return [[matrix[(x + d_x) % len(matrix)][(y + d_y) % len(matrix[0])] for y in range(len(matrix[0]))] for x in
            range(len(matrix))]


game_id_regex = re.compile(r"^\w+(\.([\w:])+)+$")
game_id_split_regex = re.compile(r"\w+")


@global_jinja_fun
def is_game_id_formatted(string: str) -> bool:
    """
    Tests if a given String is formatted like a Game ID, following its conventions and rules.
    :param string:  String to test.
    :return:        `True`, if the string is formatted like a Game ID, otherwise `False`. Does not check if the ID
                    resolves.
    """
    if not isinstance(string, str):
        return False
    if game_id_regex.match(string):
        return True
    return False


@global_jinja_fun
def is_game_split_formatted(string: str) -> bool:
    """
    Tests if a given string is formatted like one 'split' of a Game ID (which is an element between `.` characters).
    :param string:  String to test.
    :return:        `True` if `string` is formatted correctly. Otherwise `False`.
    """
    if game_id_split_regex.match(string):
        return True
    return False


game_uuid_re = re.compile(r"[a-f0-9]{8}:[a-f0-9]{4}:[a-f0-9]{4}:[a-f0-9]{4}:[a-f0-9]{12}")
game_uuid_re_reverse = re.compile(r"([a-f0-9]{8})-([a-f0-9]{4})-([a-f0-9]{4})-([a-f0-9]{4})-([a-f0-9]{12})")

def is_uuid(string: str) -> bool:
    """
    Checks if a string is formatted like a game UUID.
    :param string:  A string to check.
    :return:        `True` if the string is an appropriately formatted game UUID. Otherwise `False`
    """
    if game_uuid_re.match(string):
        return True
    else:
        return False

@global_jinja_fun
def generate_uuid() -> str:
    """
    Generates a UUID that can be used in game.
    :return:    A unique identifier string that can be used to uniquely address an object in the game.
    """
    return str(uuid.uuid4()).replace('-', ':')

@global_jinja_fun
def css_friendly(game_id: str) -> str:
    """
    Takes a (game) ID string and turns it into a string that's easy to process in CSS.
    :param game_id:  An ID, e.g. 'data.storage.content.gold'
    :return:    A CSS friendly ID, e.g. 'data-storage-content-gold'
    """
    return game_id.replace('.', '-').replace(':', '-')


@global_jinja_fun
def css_unfriendly(css_game_id: str) -> str:
    """
    Turns a CSS friendly formatted GameID into the core engine's Format
    :param css_game_id:     Game ID CSS formatted
    :return:                Game ID commonly formatted
    """
    # both ':' and '.' map to '-'. Since only generated UUIDs contain ':' so far, we check for their
    # unique format and replace their characters first
    uuid_matches = game_uuid_re_reverse.search(css_game_id)
    if uuid_matches:
        css_game_id = game_uuid_re_reverse.sub(r"\1:\2:\3:\4:\5", css_game_id)

    # Now replace all remaining '-' with '.' since all '-' left are "legitimate" '.'-characters
    return css_game_id.replace('-', '.')

def get_id_display_function(game_id: str) -> str:
    """
    Returns the string that describes which display function to use for a given ID.
    :param game_id:     A game_id
    :return:            The function with which this data is to be displayed (e.g. 'shorten_num')
    """
    if game_id in ['data.station.storage.content.gold']:
        return 'shorten_cents'
    if game_id in ['special.time']:
        return 'shorten_time'

    # Default Case: Handle data at ID as number
    return 'shorten_num'