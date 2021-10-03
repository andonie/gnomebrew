"""
This module covers the functionality of the Market station
"""

from gnomebrew.game.user import User, user_assertion, frontend_id_resolver
from gnomebrew.game.event import Event
from gnomebrew.play import request_handler
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew import mongo
from gnomebrew.game.objects.item import Item
from gnomebrew.game.util import random_normal
from datetime import datetime, timedelta
from random import random
from numpy import random

# Gameplay Dial Constants

# Minimum/Maximum of Budget RNG component
MARKETING_RNG_MEDIAN = 75
MARKETING_RNG_STD_DEVIATION = 20

# Market Game Mechanics

def generate_new_inventory(user: User):
    """
    Generates a fresh inventory for a given user, taking into account all internal paramaters as well as
    any and all upgrades they might have made.
    :param user:
    :return:
    """
    # Get List of Items that are technically available in market
    possible_items = user.get('attr.market.available_items', default=['grains', 'wood'])

    # Identify this iteration's available funds
    market_budget = generate_procurement_budget(user)

    new_inventory = dict()

    for item in possible_items:
        item_data: Item = Item.from_id('item.' + item).get_json()
        # TODO Make re-supply interesting and efficient
        new_inventory[item] = {
            'stock': item_data['base_supply'],
            'price': item_data['base_value']
        }

    return new_inventory

def generate_procurement_budget(user: User) -> float:
    """
    Generates a market cycle budget for this user.
    :param user:    a user.
    :return:        An amount of value this market is willing to spend this procurement cycle at max.
    """
    # RNG Factor
    rng_factor = random_normal(median=MARKETING_RNG_MEDIAN, std_deviation=MARKETING_RNG_STD_DEVIATION)
    # Revenue Factor Calculation

    return rng_factor * user.get('attr.market.budget_factor', default=1)

@request_handler
def market_buy(request_object: dict, user: User):
    """
    Handles a player request to buy something from the market.
    :param request_object: player request. Should look something like:
    {
        'type': 'market_buy',
        'item_id': 'item.grains',
        'amount': 5
    }
    :return:
    """
    amount = int(request_object['amount'])
    assert amount > 0
    response = GameResponse()
    item_name = request_object['item_id'].split('.')[1]
    # Get Current Market Inventory
    item = user.get('data.market.inventory.' + item_name)
    storage_capacity = user.get('attr.storage.max_capacity')
    user_gold = user.get('data.storage.content.gold')
    user_item_amount = user.get('data.storage.content.' + item_name, default=0)
    ok = True

    if amount + user_item_amount > storage_capacity:
        ok = False
        response.add_fail_msg('Not enough space in your storage.')
    if item['stock'] < amount:
        ok = False
        response.add_fail_msg(f'Not enough {user.get(request_object["item_id"]).name()} in stock.')
    if item['price'] * amount > user_gold:
        ok = False
        response.add_fail_msg("You can't afford this.")

    if ok:
        response.succeess()
        item['stock'] -= amount
        user_gold -= amount * item['price']
        user_item_num = int(user.get('data.storage.content.' + item_name, default=0))
        user.update('data', {
            'market.inventory.' + item_name: item,  # New Item Inventory
            'storage.content.gold': user_gold,
            'storage.content.' + item_name: user_item_num + amount
        }, is_bulk=True)

    return response


@user_assertion
def assert_market_update_queued(user: User):
    """
    Assertion script.
    At any point in the game, each user should have one 'market' update event targeted to them.
    :param user:    A user
    :raise: `AssertionError` if there's no queued update for a market inventory update for the user.
    """
    result = mongo.db.events.find_one({'target': user.get_id(), 'type': 'market'})
    if result is None:
        raise AssertionError(f"{user.get_id()} has no market event data!")


def _generate_market_update_event(target: str, due_time: datetime):
    """
    Generates a fresh event that starts generates a new market offer listing once it fires.
    :param target:  user ID target
    :param due_time: due time (server UTC) at which the event fires
    """
    data = dict()
    data['target'] = target
    data['type'] = 'market'
    data['effect'] = dict()
    data['effect']['market_update'] = {}  # Market updates require no data. Computation happens at time of firing.
    data['due_time'] = due_time
    data['station'] = 'market'
    return Event(data)


@Event.register_effect
def market_update(user: User, effect_data: dict, **kwargs):
    """
    Updates a user's inventory
    :param user:        User targeted by the update.
    :param effect_data: Inconsequential, as market_update does everything internally.
    :keyword source     Should always be set.
    """
    latest_inventory = generate_new_inventory(user)
    next_duetime = datetime.utcnow() + timedelta(minutes=3)
    user.update('data.market', {
        'due': next_duetime,
        'inventory': latest_inventory
    }, is_bulk=True)
    #kwargs['source'].
    _generate_market_update_event(user.get_id(), next_duetime).enqueue()


@frontend_id_resolver('^data.market.inventory$')
def full_update_on_market_update(user: User, data: dict, game_id: str, **kwargs):
    user.frontend_update('ui', {
        'type': 'reload_station',
        'station': 'market'
    })


@frontend_id_resolver(r'^data.market.due$')
def update_market_duetime(user: User, data: dict, game_id: str, **kwargs):
    pass # Due Time need not be updated, because on inventory update the entire market module will be reloaded

