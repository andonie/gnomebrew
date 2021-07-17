"""
This module contains the static data classes and logic, like:

* Recipes
* Stations
* Upgrades

etc.
"""
import datetime
import re
from flask import url_for

from gnomebrew_server import app, mongo
from gnomebrew_server.game.gnomebrew_io import GameResponse
import gnomebrew_server.game.event as event
from bisect import bisect_left


class StaticGameObject(object):
    @staticmethod
    def from_id(game_id):
        """
        Returns the respective station from game_id
        :param game_id: The stations game_id
        :return:    A `Station` object corresponding to the given ID
        """
        global _STATIC_GAME_OBJECTS
        return _STATIC_GAME_OBJECTS[game_id]

    def get_json(self):
        return self._data

    def get_value(self, key: str):
        return self._data[key]

    def get_id(self):
        return self._data['game_id']


class Recipe(StaticGameObject):
    """
    Recipe Wrapper Class.
    """

    def __init__(self, mongo_data):
        """
        Intialize the Recipe
        :param mongo_data: data stored in Mongo Database sans game and Mongo ID
        """
        self._data = mongo_data

    def check_and_execute(self, user) -> GameResponse:
        """
        Execute the recipe.
        Checks if the user *can* execute the recipe (all requirements are met) and if so enqueues the recipe.
        :param response:Response Object to add context to
        :param user:    User object representing the user to execute this recipe for.
        :return:        The Game Response object summarizing the transaction.
        """

        response = GameResponse()

        # Check if prerequisites are met
        ok = True



        # 1. Material Cost
        player_inventory = user.get('data.storage.content')
        if not all([x in player_inventory and player_inventory[x] >= self._data['cost'][x] for x in
                    self._data['cost'].keys()]):
            response.add_fail_msg('Not enough resources to execute recipe.')
            ok = False

        # 2. Available Slots
        slots_available = user.get('slots.' + self._data['station'])
        if slots_available < self._data['slots']:
            response.add_fail_msg(f"Not enough slots available in {self._data['station']}")
            ok = False

        # 3. One Time Recipes
        if self.is_one_time():
            # This is a one-time recipe. Ensure it has not yet been crafted by user (or being crafted currently).
            if not self._otr_check(user):
                # The recipe is already logged in the list of finished one-time-recipes. This cannot be crafted again.
                response.add_fail_msg("This recipe can't be run more than once.")
                ok = False

        # 4. Recipe Already Available
        if not self.requirements_met(user):
            ok = False
            response.add_fail_msg('Recipe not unlocked yet.')

        # If all requirements are met, execute Recipe
        if ok:
            # Remove material from Inventory now
            update_data = self._data['cost'].copy()
            for material in update_data:
                update_data[material] = player_inventory[material] - update_data[material]
            if update_data:
                user.update_game_data('data.storage.content', update_data, is_bulk=True)

            # (slots don't have to be discounted as they are logged via the eventqueue)

            # Create Event to trigger when crafting time is over and enqueue it
            due_time = datetime.datetime.utcnow() + datetime.timedelta(
                seconds=self._data['base_time'])

            # If the recipe is a one-time recipe, add a push to the result that ensures the finished recipe is logged
            result = self._data['result']
            if self.is_one_time():
                if 'push_data' not in result:
                    result['push_data'] = dict()
                result['push_data']['data.workshop.finished_otr'] = self._data['game_id']
                result['ui_update'] = {
                    'type': 'reload_station',
                    'station': self._data['station']
                }

            event.Event.generate_event_from_recipe_data(target=user.get_id(),
                                                        result=result,
                                                        due_time=due_time,
                                                        slots=self._data['slots'],
                                                        station=self._data['station'],
                                                        recipe_id=self._data['game_id']).enqueue()
            response.succeess()
            response.set_ui_update({
                'type': 'slot',
                'due': due_time.strftime('%d %b %Y %H:%M:%S') + ' GMT',
                'since': datetime.datetime.utcnow().strftime('%d %b %Y %H:%M:%S') + ' GMT',
                'station': self._data['station']
            })

        return response

    def _otr_check(self, user, **kwargs):
        """
        Helper Function.
        Checks if a OTR recipe can (still) be executed
        :param user:    a user
        :return:        `True` if this recipe can still be executed, otherwise `False`
        """
        if 'user_otr' in kwargs:
            user_otr = kwargs['user_otr']
        else:
            user_otr = user.get('data.workshop.finished_otr')
        return self._data['game_id'] not in user_otr or mongo.db.events.find_one(
            {'target': user.get_id(), 'recipe_id': self._data['game_id']})

    def is_one_time(self):
        return 'one_time' in self._data and self._data['one_time']

    def requirements_met(self, user, **kwargs):
        """
        Checks if the recipe's requirements are met
        :param user:    a user
        :param kwargs:  if `user_upgrades` is set, the function will not call a `get`
        :return:        `True` if this recipe's requirements are met. Otherwise `False`
        """
        if 'requirements' not in self._data:
            # No requirements
            return True

        # Binsearch Helper. Upgrade Data is in an always sorted list
        # Thank you: https://stackoverflow.com/a/2233940/13481946
        def binary_search(a, x, lo=0, hi=None):
            if hi is None: hi = len(a)
            pos = bisect_left(a, x, lo, hi)  # find insertion position
            return True if pos != hi and a[pos] == x else False

        # Make sure all requirements are met, if any
        if 'user_upgrades' in kwargs:
            user_upgrades = kwargs['user_upgrades']
        else:
            user_upgrades = user.get('data.workshop.upgrades')

        return all([binary_search(user_upgrades, req) for req in self._data['requirements']])

    def can_execute(self, user, **kwargs):
        """
        Checks if a given user *could* execute this recipe, not taking into account their current resources.
        This check does NOT factor in the resources the user has available. This takes into account:

        * If the user already unlocked the recipe
        * If the recipe is a one-time-recipe and is already executed

        :param user:  a user
        :return: True, if this recipe can be executed. False, if this recipe is not executable (anymore) no matter the
                    resources.
        """
        return (not self.is_one_time() or self._otr_check(user, **kwargs)) and self.requirements_met(user, **kwargs)

    def unlocked_by_upgrade(self, upgrade):
        """
        Checks if a given upgrade unlocks this recipe
        :param upgrade: an upgrade
        :return:    `True` if this recipe is unlocked by this upgrade
        """
        return False if 'requirements' not in self._data else upgrade.get_value('game_id') in self._data['requirements']

    def describe_outcome(self):
        """
        Utility Method that describes the outcome of this recipe.
        :return:    Outcome of the recipe formatted in HTML (if necessary)
        """
        output = ''
        # If the recipe contains inventory output, we want this formatted in the output.
        if 'delta_inventory' in self._data['result']:
            output += '<span class="gb-outcome-descriptor">Creates</span> '
            for item in self._data['result']['delta_inventory']:
                output += f"""<div class="gb-outcome-item">
                        <img class="gb-icon-sm" src="{ url_for('get_icon', game_id='item.' + item)}">
                        {self._data['result']['delta_inventory'][item]}
                    </div>"""

        # if the recipe contains upgrade(s), access the upgrades description:
        if 'upgrade' in self._data['result']:
            for upgrade in self._data['result']['upgrade']:
                upgrade_entity = Upgrade.from_id(upgrade)
                output += upgrade_entity.describe_outcome()
        return output

    @staticmethod
    def get_recipes_by_station(station_name: str):
        global _RECIPES_BY_STATION
        return [] if station_name not in _RECIPES_BY_STATION else _RECIPES_BY_STATION[station_name]


class Station(StaticGameObject):
    """
    Station Wrapper Class
    """

    def __init__(self, mongo_data):
        self._data = mongo_data

    def generate_html(self, user):
        """
        Generate the HTML to interact with the station in a web interface.
        :param user: user for which this station HTML is being generated.
        :return:
        """
        pass

    def get_base_value(self, attr):
        assert self._data[attr]
        return self._data[attr]


class Upgrade(StaticGameObject):

    def __init__(self, mongo_data):
        self._data = mongo_data

    def apply_to(self, val, game_id: str):
        """
        Applies upgrade effect to an attribute
        :param val: An attribute value before the upgrade
        :param game_id: The Game ID of the target value (formatted in `attr.x.y`)
        :return:    The attribute value after the upgrade
        """
        assert game_id in self._data['effect']
        for key in self._data['effect'][game_id]:
            if key == 'delta':
                val += self._data['effect'][game_id][key]
            elif key == 'phi':
                val *= self._data['effect'][game_id][key]
            elif key == 'pull':
                val.remove(self._data['effect'][game_id][key])
            else:
                raise AttributeError(f"Don't know how to process {key}")
        return val

    def upgrade_order(self) -> int:
        """
        Returns the order of this upgrade.
        Used to ensure consistent `attr` evaluation based on station base data and upgrades.

        In general:

        * Upgrades of the same order are commutative
        * Upgrades of lower order are guaranteed to execute before upgrades of higher order

        :return:    An `int` that represents the order of this upgrade.
        """
        effect = self._data['effect']
        # If an order is defined directly, return the order of this upgrade
        if 'order' in effect:
            return self._data['effect']['order']

        # If the upgrade contains a `delta` (+), its order is 1
        if 'delta' in effect:
            return 1

        # If the upgrade contains a `phi` (*), its order is 2
        if 'phi' in effect:
            return 2

        # If the upgrade contains a `pull` (remove from list), its order is 3
        if 'pull' in effect:
            return 4

        # If the upgrade is a hard-set of a value, its order is 5
        if 'set' in effect:
            return 5

        # Default: 0
        return 0

    def relevant_for(self, game_id: str):
        """
        Checks if this upgrade is relevant for a given game-id.
        :param game_id: A game-id to check.
        :return:        `True` if this upgrade modifies the attribute at `game_id` in some way, otherwise `False`.
        """
        return game_id in self._data['effect']

    def stations_to_update(self):
        """
        Returns a list of stations that need to be updated once this upgrade takes place.
        :return: A set of station names that should be updated after this upgrade takes place, e.g. because of a change in
                 frontend attributes.
        """
        stations_to_update = set()

        # Every Station with a recipe that is unlocked by this upgrade is to be updated
        global _RECIPE_LIST
        for station in map(lambda r: r.get_value('station'),
                           filter(lambda recipe: recipe.unlocked_by_upgrade(self), _RECIPE_LIST)):
            stations_to_update.add(station)

        # Go Through the actual upgrade effect and check if something needs to be updated
        # Relevent regexes to check for
        regexes = [
            re.compile(r'^attr\.(?P<station_name>\w+)\.slots$') # Changes in Slots should be UI updated
        ]

        for attribute in self._data['effect']:
            print(f"{attribute=}")
            for regex in regexes:
                match = regex.match(attribute)
                print(f"{match=}")
                if match:
                    # Attribute match. Get station name
                    stations_to_update.add(match.group('station_name'))

        return stations_to_update

    def __lt__(self, other):
        """
        Custom Implemented __lt__ method.
        Used to ensure *consistent upgrade behavior* when applying several several Upgrades one after another:
        Before executing Upgrade behavior, all existing upgrades are sorted in a list before folding it with reduce(...)
        :param other:   Element to compare this to.
        :return:        True if self<other. False if self>=other
        """
        # Upgrades are only comparable with each other
        assert type(other) is Upgrade
        return self.upgrade_order() < other.upgrade_order()

    def describe_outcome(self):
        """
        Utility Method that generates HTML text that summarizes the outcome of this upgrade.
        """
        if 'description' in self._data:
            return self._data['description']



class Item(StaticGameObject):
    """
    Item Wrapper Class
    """

    def __init__(self, mongo_data):
        self._data = mongo_data

    def name(self):
        return self._data['name']

    def description(self):
        return self._data['description']

    def is_orderable(self):
        """
        Returns `True` if patrons can order this item.
        """
        return self._data['orderable'] if 'orderable' in self._data else False

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


# Internal References
_STATIC_GAME_OBJECTS = dict()
_RECIPES_BY_STATION = dict()
_RECIPE_LIST = list()
_ITEM_LIST = list()
patron_order_list = list()

def _fill_from_db(col, conversion_function):
    """
    Utility to minimize code duplication.
    :param col:          The PyMongo collection to converted into a dict.
    :param conversion_function: Conversion function taking one doc as dict and returning the respective element to
                                store in the dict.
    :return: a dict with keys of `game_id` and value of `conversion_function(base_entry_data)`
    """
    res = dict()
    for doc in col.find({}, {'_id': False}):
        # Remove Game ID and MongoID from data
        # Just to remove redundant data
        # Both keys should exist in all game databases.
        res[doc['game_id']] = conversion_function(doc)
    return res


def update_static_data():
    res = dict()

    app.logger.info('Updating Recipe Data')
    recipe_list = []

    def process_recipe_data(doc):
        recipe_object = Recipe(doc)
        recipe_list.append(recipe_object)
        return recipe_object

    res.update(_fill_from_db(mongo.db.recipes, process_recipe_data))

    global _RECIPE_LIST
    _RECIPE_LIST = recipe_list

    app.logger.info('Recipe Data Updated')

    app.logger.info('Updating Upgrade Data')
    res.update(_fill_from_db(mongo.db.upgrades, lambda doc: Upgrade(doc)))
    app.logger.info('Upgrade Data Updated')

    app.logger.info('Updating Station Data')
    res.update(_fill_from_db(mongo.db.stations, lambda doc: Station(doc)))
    app.logger.info('Station Data Updated')

    app.logger.info('Updating Item Data')
    item_list = []

    def process_item_data(doc):
        item_object = Item(doc)
        item_list.append(item_object)
        return item_object

    res.update(_fill_from_db(mongo.db.items, process_item_data))

    global _ITEM_LIST
    _ITEM_LIST = item_list
    global patron_order_list
    patron_order_list = filter(lambda item: item.is_orderable(), _ITEM_LIST)
    app.logger.info('Item Data Updated')

    global _STATIC_GAME_OBJECTS
    _STATIC_GAME_OBJECTS = res

    # Create Lookup Table for all Recipes by Station
    app.logger.info('Updating Recipe Lookup')
    recipe_lookup = dict()

    for recipe in recipe_list:
        station_name = recipe.get_value('station')
        if station_name not in recipe_lookup:
            recipe_lookup[station_name] = list()
        recipe_lookup[station_name].append(recipe)

    global _RECIPES_BY_STATION
    _RECIPES_BY_STATION = recipe_lookup
    app.logger.info('Recipe Lookup Updated')
