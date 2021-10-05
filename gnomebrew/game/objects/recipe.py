"""
Contains Recipe logic/implementation
"""
import datetime
from bisect import bisect_left
from datetime import datetime, timedelta
from os.path import join

from flask import url_for, render_template
from typing import List, Dict

from gnomebrew import mongo
from gnomebrew.game import event as event
from gnomebrew.game.objects.item import ItemCategory
from gnomebrew.game.objects.game_object import load_on_startup, StaticGameObject, render_object
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.request import PlayerRequest
from gnomebrew.game.objects.upgrades import Upgrade
from gnomebrew.game.user import get_resolver, User, html_generator
from gnomebrew.game.util import global_jinja_fun


@get_resolver('recipe')
def recipe(game_id: str, user: User):
    return Recipe.from_id(game_id)


@get_resolver('recipes')
def recipes(game_id: str, user: User, **kwargs):
    splits = game_id.split('.')
    assert len(splits) == 2
    # Add default values to make the system not crap out before the workshop is unlocked
    user_ws_data = user.get('data.workshop', default={'upgrades': [], 'finished_otr': []}, **kwargs)
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

    def check_and_execute(self, user: User, **kwargs) -> GameResponse:
        """
        Execute the recipe.
        Checks if the user *can* execute the recipe (all requirements are met) and if so enqueues the recipe.
        :param response:Response Object to add context to
        :param user:    User object representing the user to execute this recipe for.
        :return:        The Game Response object summarizing the transaction.
        """
        response = GameResponse()

        # ~~~~ Check if prerequisites are met ~~~~

        # 0.5. If Item Categories are involved, convert the categories to additional hard material Cost
        total_cost = self._data['cost'].copy()

        if 'it_cat' in total_cost:
            for category in total_cost['it_cat']:
                selected_cat_item = user.get(f"selection.it_cat.{category}", default=None, **kwargs)
                if not selected_cat_item:
                    response.add_fail_msg(f"Cannot find an item in your inventory matching the category {ItemCategory.from_id(f'selection.it_cat.{category}').name()}.")
                    return response
                if selected_cat_item in total_cost:
                    total_cost[selected_cat_item] += total_cost['it_cat'][category]
                else:
                    total_cost[selected_cat_item] = total_cost['it_cat'][category]
            del total_cost['it_cat']

        # 1. Hard Material Cost
        player_inventory = user.get('data.storage.content', **kwargs)
        if not all([x in player_inventory and player_inventory[x] >= total_cost[x] for x in
                    total_cost.keys() if x != 'it_cat']):
            response.add_fail_msg('Not enough resources to execute recipe.')

        # 2. Available Slots
        slots_list = user.get(f"slots.{self._data['station']}", **kwargs)
        slots_available = len([slot for slot in slots_list if slot['state'] == 'free'])
        if slots_available < self._data['slots']:
            response.add_fail_msg(f"Not enough slots available in {self._data['station']}")

        # 3. One Time Recipes
        if self.is_one_time():
            # This is a one-time recipe. Ensure it has not yet been crafted by user (or being crafted currently).
            if not self._otr_check(user):
                # The recipe is already logged in the list of finished one-time-recipes. This cannot be crafted again.
                response.add_fail_msg("This recipe can't be run more than once.")

        # 4. Recipe Already Available
        if not self.requirements_met(user):
            response.add_fail_msg('Recipe not unlocked yet.')

        # 5. Inventory change event can theoretically improve player inventory
        if 'delta_inventory' in self._data['result']:
            max_capacity = user.get('attr.storage.max_capacity', **kwargs)
            at_max_capacity = [item for item in self._data['result']['delta_inventory']
                               if item in player_inventory and player_inventory[item] == max_capacity]
            if len(at_max_capacity) == len(self._data['result']['delta_inventory']):
                # Everything is at max capacity
                response.add_fail_msg('You are at storage capacity for all resulting items.')

        # ~~~~ If all requirements are met, execute Recipe ~~~~
        if response.has_failed():
            return response

        # Remove material from Inventory now
        update_data = dict()
        for material in total_cost:
            update_data[material] = player_inventory[material] - total_cost[material]
        if update_data:
            user.update('data.storage.content', update_data, is_bulk=True)

        # (slots don't have to be discounted as they are logged via the eventqueue)

        # Create Event to trigger when crafting time is over and enqueue it
        due_time = datetime.utcnow() + timedelta(
            seconds=self._data['base_time'])

        # If the recipe is a one-time recipe, add a push to the result that ensures the finished recipe is logged
        result: list = self._data['result'].copy()
        if self.is_one_time():
            result.append({
                'effect_type': 'push_data',
                'push_target': 'data.workshop.finished_otr',
                'to_push': self.get_id()
            })
            result.append({
                'effect_type': 'ui_update',
                'type': 'reload_element',
                'element': f"recipes.{self._data['station']}"
            })

        # Enqueue the update event that triggers on recipe completion
        event.Event.generate_event_from_recipe_data(target=user.get_id(),
                                                    result=result,
                                                    due_time=due_time,
                                                    slots=self._data['slots'],
                                                    station=self._data['station'],
                                                    recipe_id=self._data['game_id'],
                                                    total_cost=total_cost).enqueue()

        response.succeess()
        response.add_ui_update({
            'type': 'reload_element',
            'element': f"slots.{self._data['station']}"
        })

        return response

    def _otr_check(self, user, **kwargs):
        """
        Helper Function.
        Checks if a OTR recipe can (still) be executed
        :param user:    a user
        :return:        `True` if this recipe can still be executed, otherwise `False`
        """
        user_otr = user.get('data.workshop.finished_otr', **kwargs)
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

        user_upgrades = user.get('data.workshop.upgrades', **kwargs)

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
        return False if 'requirements' not in self._data else upgrade.get_static_value('game_id') in self._data[
            'requirements']

    def describe_outcome(self) -> str:
        """
        Convencience formatting code Returns HTML
        """
        return render_template(join('snippets', '_recipe_'))

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

    @staticmethod
    def cancel_running_recipe(recipe_event_id: str, user: User) -> GameResponse:
        """
        Cancels a running recipe.
        :param user:            target user.
        :param recipe_event_id: unique ID of the event to cancel.
        :return:
        """
        response = GameResponse()
        recipe_event = mongo.db.events.find_one_and_delete({
            'target': user.get_id(),
            'event_id': recipe_event_id
        })
        response.add_ui_update({
            'type': 'reload_element',
            'element': f"slots.{Recipe.from_id(recipe_event['recipe_id']).get_static_value('station')}"
        })
        cost = recipe_event['cost']
        if cost:
            user.update('data.storage.content', cost, command='$inc', is_bulk=True)
        response.succeess()
        return response


def generate_complete_slot_dict(game_id: str, user: User, **kwargs) -> Dict[str, List[dict]]:
    """
    Behavior for `slots._all` feature.
    :param game_id: game ID that resulted in this call.
    :param user:    calling user.
    :param kwargs:
    :return:        a dict mapping all known stations with slots to a list representing their current slot allocation.
    """
    ret = dict()
    mongo_result = {x['_id']: x['etas'] for x in mongo.db.events.aggregate([{'$match': {
        'target': user.username,
        'due_time': {'$gt': datetime.utcnow()}
    }}, {'$group': {'_id': '$station', 'etas': {'$push': {
        'due': '$due_time',
        'since': '$since',
        'slots': '$slots',
        'effect': '$effect',
        'recipe': '$recipe_id',
        'event_id': '$event_id'
    }}}}])}
    complete_station_data = mongo.db.users.find_one({"username": user.get_id()}, {'data': 1, '_id': 0})['data']
    for _station in complete_station_data:
        max_slots = user.get('attr.' + _station + '.slots', default=0, **kwargs)
        if max_slots:
            # _station is slotted. Add the necessary input to return value
            ret[_station] = list()
            print(f"{mongo_result=}")
            if _station in mongo_result:
                # By Default, add the implicit occupied state
                for item in mongo_result[_station]:
                    item['state'] = 'occupied'
                ret[_station] = mongo_result[_station] + ([{'state': 'free'}] * (max_slots - len(mongo_result[_station])))
            else:
                ret[_station] = [{'state': 'free'}] * max_slots

    return ret


_special_slot_behavior = {
    '_all': generate_complete_slot_dict
}


@get_resolver('slots')
def slots(game_id: id, user: User, **kwargs) -> List[dict]:
    """
    Calculates slot data for a given station.

    :param user:
    :param game_id:       e.g. 'slots.well'
    :return:              A list

    """
    splits = game_id.split('.')

    # Interpret the game_id input
    if splits[1] in _special_slot_behavior:
        return _special_slot_behavior[splits[1]](game_id, user, **kwargs)

    # Default: slots of a station

    active_events = mongo.db.events.find({
        'target': user.username,
        'station': splits[1],
        'due_time': {'$gt': datetime.utcnow()}
    }, {
        "_id": 0,
        "effect": 1,
        "due_time": 1,
        "slots": 1,
        "recipe_id": 1,
        "since": 1,
        "event_id": 1
    })

    slot_list = list()
    total_slots_allocated = 0

    for recipe_event in active_events:
        slot_list.append({
            'state': 'occupied',
            'due': recipe_event['due_time'],
            'since': recipe_event['since'],
            'slots': recipe_event['slots'],
            'effect': recipe_event['effect'],
            'recipe': recipe_event['recipe_id'],
            'event_id': recipe_event['event_id']
        })
        total_slots_allocated += recipe_event['slots']

    # Fill up list with empty slots with appropriate empty slots
    max_slots = user.get(f'attr.{splits[1]}.slots', **kwargs)
    slot_list += [{
        'state': 'free'
    }] * (max_slots - total_slots_allocated)

    return slot_list


@PlayerRequest.type('recipe', is_buffered=True)
def recipe(user: User, request_object: dict, **kwargs):
    if request_object['action'] == 'execute':
        response = Recipe.from_id(request_object['recipe_id']).check_and_execute(user, **kwargs)
    elif request_object['action'] == 'cancel':
        response = Recipe.cancel_running_recipe(request_object['event_id'], user)
    return response


@html_generator('html.slots', is_generic=True)
def generate_slot_html(game_id: str, user: User, **kwargs):
    """
    Generates slot HTML for a given station.
    :param user:        A user.
    :param game_id:     e.g. 'html.slots.well'
    :return:            HTML rendering for the given slot environment/station. Returns an empty string for now slot data.
    """
    station_name = game_id.split('.')[2]
    return ''.join([render_object('render.slot', data=slot_data)
                    for slot_data in user.get(f"slots.{station_name}", **kwargs)])


@html_generator('html.recipes', is_generic=True)
def generate_recipe_list(game_id: str, user: User, **kwargs):
    """
    Generates a station's available recipes.
    :param game_id:
    :param user:
    :param kwargs:
    :return:
    """
    #
    pass


@global_jinja_fun
def format_recipes_by_category(recipe_list: List[Recipe]) -> Dict[str, List[Recipe]]:
    """
    Helper function to keep the template-code lean. Takes a list of recipe and formats it by `category`.
    :param recipe_list: Result of `user.get('recipes.[...]')`
    :return:        A dict that sorts the recipes by category (i.e. `{'category': ['recipe.a', 'recipe.b']}`)
                    If a recipe does not have `category` data, it is instead matched to `'no_category'`
    """
    recipes_by_category = dict()
    for recipe in recipe_list:
        if recipe.has_static_key('category'):
            category = recipe.get_static_value('category')
        else:
            category = 'no_category'
        if category not in recipes_by_category:
            recipes_by_category[category] = list()
        recipes_by_category[category].append(recipe)
    return recipes_by_category
