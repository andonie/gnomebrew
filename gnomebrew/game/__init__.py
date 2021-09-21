"""
Init module
"""
from gnomebrew import mongo
from gnomebrew.game.util import shorten_num
from gnomebrew.game.event import EventThread
from gnomebrew.game.play_modules.tavern import TavernSimulationThread
from gnomebrew.game.objects.static_object import update_static_data

## SETUP

# Load all Game Modules
_game_module_names = ['gnomebrew.game.objects', 'gnomebrew.game.play_modules',
                      'gnomebrew.game.testing', 'gnomebrew.admin', 'gnomebrew.game.ig_event']

game_modules = list(map(__import__, _game_module_names))


# Load in static data (Recipes, Stations, etc.) from MongoDB
update_static_data()


# Start Event Thread
_EVENT_THREAD = EventThread(mongo_instance=mongo)
_TAVERN_THREAD = TavernSimulationThread(mongo_instance=mongo)


## API Providing:
