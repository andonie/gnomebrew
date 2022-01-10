"""
Manages all logging in Gnomebrew.
To make sure the system is easier to test, the log module, Gnomebrew has a middle layer between engine and python logging.
The module provides a `log()` function that can be called throughout the system to enable logging tasks that can be
affected through the game system.
"""
import copy
import sys
import traceback
from datetime import datetime
import logging
import re
from typing import Dict, Callable, Any

# Gnomebrew's General Logging Config



# Basic Logging Config
logging.basicConfig(format='[%(levelname)s]%(message)s')
logging.getLogger('werkzeug').setLevel(logging.ERROR)


_log_lookup: Dict[str, dict] = dict()

# Code largely taken from Stack Overflow
# https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

#The background is set with 40 plus the number of the color, and the foreground with 30

#These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

def formatter_message(message, use_color = True):
    if use_color:
        message = message.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
    else:
        message = message.replace("$RESET", "").replace("$BOLD", "")
    return message

COLORS = {
    'WARNING': YELLOW,
    'INFO': WHITE,
    'DEBUG': BLUE,
    'CRITICAL': YELLOW,
    'ERROR': RED,
    'game_id': BLUE,
    'gb_core': MAGENTA,
    'gb_system': RED,
    'prompt': YELLOW,
    'effect': BLUE,
    'event': WHITE
}

def _color_string(color, string: str):
    return COLOR_SEQ % (30 + color) + string + RESET_SEQ

class ColoredFormatter(logging.Formatter):
    def __init__(self, msg, use_color = True):
        logging.Formatter.__init__(self, msg)
        self.use_color = use_color

    def format(self, record):
        record = copy.copy(record)
        levelname = record.levelname
        if self.use_color and levelname in COLORS:
            levelname_color = COLOR_SEQ % (30 + COLORS[levelname]) + levelname + RESET_SEQ
            record.levelname = levelname_color
        # Go through record message and add color

        # Special Color for by logging category
        if self.use_color:
            # Color Name
            if record.name in COLORS:
                rec_color = COLORS[record.name]
            else:
                rec_color = CYAN
            record.name = COLOR_SEQ % (30 + rec_color) + record.name + RESET_SEQ

        return logging.Formatter.format(self, record)


# Custom logger class with multiple destinations
class ColoredLogger(logging.Logger):
    FORMAT = "[%(asctime)s][$BOLD%(name)-25s$RESET][%(levelname)-18s]%(message)s"
    COLOR_FORMAT = formatter_message(FORMAT, True)
    def __init__(self, name):
        logging.Logger.__init__(self, name, logging.DEBUG)

        color_formatter = ColoredFormatter(self.COLOR_FORMAT)

        console = logging.StreamHandler()
        console.setFormatter(color_formatter)

        self.addHandler(console)

        return


logging.setLoggerClass(ColoredLogger)


def log(category: str, message: str, *args, **kwargs):
    """
    Standard logging interface method for Gnomebrew.
    All logging in the game should be done throught his method rather than any other form.

    :param category:    Category of this log message. Only short name, not starting with `log_category`.
    :param message:     Log message
    :param args         Can be used to log additional parameters in brackets. Values will be added in brackets before
                        actual messaage content starts.
    :keyword level      If `level` is set, will overwrite the category's default level.
    :keyword verbose    If this variable is set, it will will be added as the verbose content if the `verbose` flag for
                        the given category is currently set.
    """
    config = _log_lookup[category]
    message = _format_message(category, message, *args, **kwargs)
    config['logger'].log(kwargs['level'] if 'level' in kwargs else config['default_level'], message)


# Matches "<%some.text.like.id%>" at \1
bold_log_regex = re.compile(r"<%(\w+(\.([\w:])+)*)%>")

def _format_message(category: str, message: str, *args, **kwargs):
    if category not in _log_lookup:
        raise Exception(f"Logging with category '{category}' is not configured.")
    config = _log_lookup[category]
    if 'bracket_filter' in config:
        # Only log when filter matches
        if any(map(config['bracket_filter'], args)):
            # Escalate any message that fits the filter
            kwargs['level'] = logging.ERROR
    brackets = ''.join([f"[{_color_string(CYAN, arg)}]" for arg in args])
    verbose_addtion = '' if 'verbose' not in kwargs or 'verbose' not in config or not config['verbose'] else f": {kwargs['verbose']}"

    # Format <% %> groups
    message_formatted = formatter_message(bold_log_regex.sub(r"$BOLD\1$RESET", message))
    message = f"{brackets} {message_formatted}{verbose_addtion}"
    return message


def log_execution_time(fun: Callable, category: str, message: str, *args, **kwargs) -> Any:
    """
    Executes a given function alongside log details. Adds the function's execution time as a bracket element.
    :param fun:         Function to execute. Should not contain any parameters.
    :param category:    Log category.
    :param message:     Message
    :param args:        Bracket elements
    :param kwargs:      kwargs will be forwarded to log
    :return             The result of the function.
    """
    start_time = datetime.utcnow()
    result = fun()
    end_time = datetime.utcnow()
    time_difference = str(end_time - start_time)
    args = args + (f't:{time_difference}',)
    log(category, message, *args, **kwargs)
    return result


def log_exception(category: str, exception: Exception, *args, **kwargs):
    """
    Logs any occuring exception.
    :param category:    Log category
    :param exception:   Exception that occured
    """
    config = _log_lookup[category]
    message = _format_message(category, str(exception), *args, **kwargs)
    config['logger'].exception(message)

# Describes Log kwargs that are not allowed because they are used by program logic
_invalid_kwargs = ['logger']

def config_log(category: str, **kwargs):
    """
    Configures log data for a given category.
    :param category:    Category name to config. Do not include the leading `log_category` part.
    :param kwargs:      All `kwargs` will be saved to configuration.

    * `level`   Default log level for this category
    """
    if not re.compile(r"\w+").match(category):
        raise Exception(f"Invalid Category Name: {category}")

    if any(key for key in _invalid_kwargs if key in kwargs):
        raise Exception(f"Cannot use reserved kwargs: {_invalid_kwargs}")

    if category not in _log_lookup:
        _log_lookup[category] = dict()

    _log_lookup[category]['logger'] = ColoredLogger(category)
    if 'log_level' in kwargs:
        _log_lookup[category]['logger'].setLevel(kwargs['log_level'])

    for key in kwargs:
        _log_lookup[category][key] = kwargs[key]

    # Assert game config is minimally configured
    for var_name in ['default_level']:
        if var_name not in _log_lookup[category]:
            raise Exception(f"Log category {category} must have {var_name} configured")


# Configure basic logging categories in Gnombrew

config_log('game_id', default_level=logging.INFO, log_level=logging.WARNING)
config_log('gb_system', default_level=logging.INFO, log_level=logging.INFO, verbose=False)
config_log('gb_core', default_level=logging.INFO, log_level=logging.INFO)
config_log('effect', default_level=logging.INFO, log_level=logging.INFO)
config_log('event', default_level=logging.INFO, log_level=logging.INFO)
config_log('prompt', default_level=logging.INFO, log_level=logging.INFO, verbose=True)
config_log('html', default_level=logging.INFO, log_level=logging.INFO)
config_log('data', default_level=logging.INFO, log_level=logging.INFO)
