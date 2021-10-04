"""
Init module
"""
from typing import Callable

_boot_routines = list()


def boot_routine(fun: Callable):
    """
    Decorator to mark a function that's supposed to be **executed once as Gnomebrew starts up**.
    :param fun: A function to be executed. Must run without parameters.
    """
    _boot_routines.append(fun)
    return fun


# Load all Game Modules
_game_module_names = ['gnomebrew.game.objects', 'gnomebrew.game.play_modules', 'gnomebrew.game.objects.world',
                      'gnomebrew.game.testing', 'gnomebrew.admin', 'gnomebrew.game.static_data',
                      'gnomebrew.game.ig_event', 'gnomebrew.game.selection']

# Load in Game Modules
game_modules = list(map(__import__, _game_module_names))

# Execute all boot routines
for routine in _boot_routines:
    routine()
