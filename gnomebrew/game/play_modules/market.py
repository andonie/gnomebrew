"""
This module covers the functionality of the Market station
"""
from typing import List
import re

from gnomebrew.game.objects.data_object import DataObject
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.request import PlayerRequest
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import User, user_assertion, id_update_listener
from gnomebrew.game.event import Event
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew import mongo
from gnomebrew.game.objects.item import Item
from gnomebrew.game.util import random_normal, global_jinja_fun, css_friendly
from datetime import datetime, timedelta
from random import random
from numpy import random


# Gameplay Dial Constants

class MarketOffer(DataObject):
    """
    Wraps Data of one market offer for object-oriented handling
    """

    @classmethod
    def from_datasource(cls, item_id: str, source_data: dict) -> 'MarketOffer':
        """
        Converts the data found in an offer into
        :param item_id:     Item ID
        :param source_data: Source Data
        :return:            Fully set up market offer
        """
        mo_data = source_data
        mo_data.update({'item': item_id})
        return MarketOffer(mo_data)

    def __init__(self, data: dict):
        DataObject.__init__(self, data)

    def get_current_stock(self) -> int:
        return self._data['stock']

    def get_current_price(self) -> int:
        return self._data['price']

    def get_item_id(self) -> str:
        return self._data['item']


@global_jinja_fun
def get_offers_for(user: User) -> List[MarketOffer]:
    """
    Returns a list of this user's currently running offers
    :param user:    A user.
    :return:        Offer list
    """
    return [MarketOffer.from_datasource(f"item.{item_min_id}", offer_data)
            for item_min_id, offer_data in user.get("data.station.market.offers.item").items()]


def get_offer_for(user: User, item_id: str) -> MarketOffer:
    """
    Returns a market offer corresponding to a given item.
    :param user:        target user
    :param item_id:     target item
    :return:            Market Offer if exists else `None`
    """


# Market Offer Validation Parameters

MarketOffer.validation_parameters(('item', str), ('stock', int), ('cost', int))


@selection_id('selection.market.amount', is_generic=False)
def select_purchase_amount(game_id: str, user: User, set_value, **kwargs):
    if set_value:
        return user.update('data.station.market.amount_choice', set_value, **kwargs)
    else:
        # Read out the current selection.
        return user.get('data.station.market.amount_choice', **kwargs)


@PlayerRequest.type('market_buy', is_buffered=True)
def market_buy(user: User, request_object: dict, **kwargs):
    """
    Handles a player request to buy something from the market. Called when the player clicks on one item offer.
    :param request_object: player request. Should look something like:
    {
        'type': 'market_buy',
        'item_id': 'item.iron'
    }
    """
    response = GameResponse()
    response.set_ui_target("#station-market-infos")

    item_id = request_object['item_id']
    # Get Current Market Inventory
    storage_capacity = user.get('attr.station.storage.max_capacity', **kwargs)
    user_gold = user.get('storage.item.gold', **kwargs)
    user_item_amount = user.get(f"storage.{item_id}", default=0, **kwargs)

    requested_offer = MarketOffer.from_datasource(item_id, user.get(f'data.station.market.offers.{item_id}'))

    amount_selection = user.get('selection.market.amount')
    amount_to_buy = int(amount_selection) if amount_selection != 'A' else requested_offer.get_current_stock()

    if amount_to_buy + user_item_amount > storage_capacity:
        response.add_fail_msg('Not enough space in your storage.')
        response.player_info(user, 'You cannot keep this much in your storage.', 'not enough',
                             'attr.station.storage.max_capacity')
    if requested_offer.get_current_stock() < amount_to_buy:
        response.add_fail_msg(f'Not enough {user.get(request_object["item_id"], **kwargs).name()} in stock.')
        response.player_info(user, 'There is not enough of this left.', 'station.market', 'is out')
    if requested_offer.get_current_price() * amount_to_buy > user_gold:
        response.add_fail_msg("You can't afford this.")
        response.player_info(user, "You can't afford this.", 'not enough', 'item.gold')

    if response.has_failed():
        return response

    # All checks passed. Execute trade
    response.succeess()

    # Update User Storage to reflect gained items and lost gold
    user.update(f"storage", {
        requested_offer.get_item_id(): amount_to_buy,
        'item.gold': -amount_to_buy * requested_offer.get_current_price()
    }, is_bulk=True, mongo_command='$inc')

    # Update Market Data to reflect reduced inventory
    user.update(f"data.station.market.offers.{item_id}.stock", -amount_to_buy, mongo_command="$inc")

    return response


find_item_name_regex = re.compile(r'^data\.station\.market\.offers\.item\.(\w+\.(stock|price))$')


@id_update_listener('^data\.station\.market\.offers\.item\.(\w+)\.(stock|price)$')
def forward_stock_and_price_updates(user: User, data: dict, game_id: str, **kwargs):
    """
    Listens in on all direct data updates to the values of offer stock/prices to forward those numbers to the frontend.
    :param user:        Target user
    :param data:        Data change
    :param game_id:     Target ID (either `data.station.market.offers.item.<id>.stock` or `... <id>.price`
    """
    updated_elements = {
        css_friendly(f"market-offers-item-{css_friendly(find_item_name_regex.match(game_id).group(1))}"):
            {'data': data[data_update_id]} for data_update_id in data}
    print(updated_elements)
    if 'command' in kwargs:
        update_type = 'inc' if kwargs['command'] == '$inc' else 'set'
    else:
        update_type = 'set'

    user.frontend_update('update', {
        'update_type': update_type,
        'updated_elements': updated_elements
    })
