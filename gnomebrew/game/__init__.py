"""
Python Entrypoint for Gnomebrew Server.
This Init files starts the most essential core features of the Gnomebrew server before calling any registered
boot routines marked `@boot_routine`.
"""
import os
from typing import Callable
import logging
import gnomebrew.index


from gnomebrew import log

_boot_routines = list()


def boot_routine(fun: Callable, name: str=None):
    """
    Decorator to mark a function that's supposed to be **executed once as Gnomebrew starts up**.
    :param fun: A function to be executed. Must run without parameters.
    :param name If set, the boot routine will be listed under this name. If not set will use function name.
    """
    routine_data = dict()
    routine_data['fun'] = fun
    routine_data['name'] = name if name != None else fun.__name__
    _boot_routines.append(routine_data)
    return fun


# Load all Game Modules
log('gb_core', 'Loading Core Modules:', 'boot_routines')
_game_module_names = ['gnomebrew.logging', 'gnomebrew.game.objects', 'gnomebrew.game.play_modules', 'gnomebrew.game.objects.world',
                      'gnomebrew.game.testing', 'gnomebrew.admin', 'gnomebrew.game.static_data',
                      'gnomebrew.game.ig_event', 'gnomebrew.game.selection']

# Load in Game Modules
game_modules = list(map(__import__, _game_module_names))

# Execute all boot routines
log('gb_core', 'Starting module boot routines:', 'boot_routines')
for routine in _boot_routines:
    log('gb_core', f"Executing: {routine['name']}", 'boot_routines')
    routine['fun']()
