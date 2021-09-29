"""
Contains Recipe logic/implementation
"""
import datetime
from bisect import bisect_left

from flask import url_for

from gnomebrew import mongo
from gnomebrew.game import event as event
from gnomebrew.game.objects.static_object import load_on_startup, StaticGameObject
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.upgrades import Upgrade
from gnomebrew.game.user import get_resolver, User
from gnomebrew.play import request_handler


@get_resolver('recipe')
def recipe(game_id: str, user: User):
    return Recipe.from_id(game_id)


@get_resolver('recipes')
def recipes(game_id: str, user: User):
    splits = game_id.split('.')
    assert len(splits) == 2
    # Add default values to make the system not crap out before the workshop is unlocked
    user_ws_data = user.get('data.workshop', default={'upgrades': [], 'finished_otr': []})
    return [r for r in Recipe.get_recipes_by_station(splits[1]) if r.can_execute(user,
                                                                                 user_upgrades=user_ws_data['upgrades'],
                                                                                 user_otr=user_ws_data['finished_otr'])]


@load_on_startup('recipes')
class Recipe(StaticGameObject):
    """
    Recipe Wrapper Class.
    """

    def __init__(self, mongo_data):
        """
        Intialize the Recipe
        :param mongo_data: data stored in Mongo Database sans game and Mongo ID
        """
        super().__init__(mongo_data)

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
                user.update('data.storage.content', update_data, is_bulk=True)

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

            # Enqueue the update event that triggers on recipe completion
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
        return False if 'requirements' not in self._data else upgrade.get_static_value('game_id') in self._data['requirements']

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
                        <img class="gb-icon-sm" src="{url_for('get_icon', game_id='item.' + item)}">
                        {self._data['result']['delta_inventory'][item]}
                    </div>"""

        # if the recipe contains upgrade(s), access the upgrades description:
        if 'upgrade' in self._data['result']:
            for upgrade in self._data['result']['upgrade']:
                upgrade_entity = Upgrade.from_id(upgrade)
                output += upgrade_entity.describe_outcome()
        return output

    # Maps a station to a list of recipes associated with this station
    _station_recipe_map = dict()

    @classmethod
    def on_data_update(cls):
        """
        This method is called from the backend whenever the entire recipe dataset has been updated.
        In here, the Recipe class updates the recipe-by-station data.
        """
        recipe_lookup = dict()
        for recipe in StaticGameObject.get_all_of_type('recipe').values():
            station_name = recipe.get_static_value('station')
            if station_name not in recipe_lookup:
                recipe_lookup[station_name] = list()
            recipe_lookup[station_name].append(recipe)
        cls._station_recipe_map = recipe_lookup

    @staticmethod
    def get_recipes_by_station(station_name: str):
        """
        :param station_name: Name of a station **shortened** (e.g. 'well')
        :return:    A `list` of recipes this station can execute.
        """
        return [] if station_name not in Recipe._station_recipe_map else Recipe._station_recipe_map[station_name]


@request_handler
def recipe(request_object: dict, user):
    response = Recipe.from_id(request_object['recipe_id']).check_and_execute(user)
    return response

