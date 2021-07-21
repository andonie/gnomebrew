"""
Init module
"""
from gnomebrew_server import app, mongo
import gnomebrew_server.game.event
import gnomebrew_server.game.static_data
from gnomebrew_server.game.util import shorten_num
from gnomebrew_server.game.event import EventThread
from gnomebrew_server.core_modules.tavern import TavernSimulationThread

# Load in static data (Recipes, Stations, etc.)
static_data.update_static_data()

# Load all Game Modules
game_module_names = ['gnomebrew_server.core_modules.market', 'gnomebrew_server.core_modules.tavern',
                     'gnomebrew_server.core_modules.workshop', 'gnomebrew_server.core_modules.storage']

game_modules = list(map(__import__, game_module_names))


# Start Event Thread
_EVENT_THREAD = EventThread(mongo_instance=mongo)
_TAVERN_THREAD = TavernSimulationThread(mongo_instance=mongo)
