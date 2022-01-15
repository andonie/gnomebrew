"""
This module covers the functionality of the Market station
"""
import math
from datetime import datetime
from numbers import Number
from typing import List, Tuple
import re

from gnomebrew.game.objects import DataObject, PlayerRequest, PeriodicEvent, Effect, Item
from gnomebrew.game.objects.game_object import render_object
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import User, id_update_listener
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.util import global_jinja_fun, css_friendly, fuzzify


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


# Market Offer Validation Parameters

MarketOffer.validation_parameters(('item', str), ('stock', int), ('cost', int))
MARKET_BASE_MARGIN = 1.3

@Item.subtype('market', ('value', int))
class MarketItem(Item):
    """Item Extension to cover properties unique to Market Items"""

    def __init__(self, data: dict):
        Item.__init__(self, data)

    def get_base_value(self):
        return self._data['market']['value']

    def price_at_amount(self, amount: int):
        """
        :param amount:  An amount of items in stock
        :return:        Price point per items based on this amount
        """
        return int(self.get_base_value() * MARKET_BASE_MARGIN * (1 + amount/500))

    def current_stock_for(self, user: User) -> int:
        offers = user.get('data.station.market.offers')
        if self.get_minimized_id() not in offers:
            # This item has not been offered yet.
            return 0
        else:
            return offers[self.get_minimized_id()]['stock']


@MarketItem.on('market_restock')
def on_market_restock(item: MarketItem, user: User):
    current_offers = user.get("data.station.market.offers")

    # If this item was not in stock before, update frontends with this.
    pass

@MarketItem.on('market_back_in_stock')
def on_back_in_stock(item: MarketItem, user: User):
    offer_data = MarketOffer.from_datasource(item.get_id(), user.get(f"data.station.market.offers.{item.get_id()}")).get_json()
    user.frontend_update('ui', {
        'type': 'append_element',
        'selector': "#market-offers",
        'element': render_object('render.market_offer',
                                 data=offer_data,
                                 current_user=user)
    })

@MarketItem.on("market_out_of_stock")
def on_market_out_of_stock(item: MarketItem, user: User):
    """called when `item` is out of stock for `user`"""
    # Remove this item from the market's offer view
    user.frontend_update('ui', {
        'type': 'remove_element',
        'selector': f"#{css_friendly(item.get_id())}-market-offer"
    })


@global_jinja_fun
def get_offers_for(user: User) -> List[MarketOffer]:
    """
    Returns a list of this user's currently running offers
    :param user:    A user.
    :return:        Offer list
    """
    return [MarketOffer.from_datasource(f"item.{item_min_id}", offer_data)
            for item_min_id, offer_data in user.get("data.station.market.offers.item").items()]


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
    # Get Current Market Data
    market_data = user.get('data.station.market')
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
    if requested_offer.get_current_stock() < amount_to_buy or amount_to_buy == 0:
        response.add_fail_msg(f'Not enough {user.get(request_object["item_id"], **kwargs).name()} in stock.')
        response.player_info(user, 'There is not enough of this left.', 'station.market', 'is out')
    if requested_offer.get_current_price() * amount_to_buy > user_gold:
        response.add_fail_msg("You can't afford this.")
        response.player_info(user, "You can't afford this.", 'not enough', 'item.gold')

    if response.has_failed():
        return response

    # All checks passed. Execute trade
    response.succeess()
    response.player_info(user, 'Trade Successful', f"+{amount_to_buy}", item_id)

    # Calculate Revenue & Profit
    revenue = amount_to_buy * requested_offer.get_current_price()
    profit = revenue - user.get(item_id).as_subtype(MarketItem).get_base_value() * amount_to_buy
    stock_left = requested_offer.get_current_stock() - amount_to_buy

    # Update User Storage to reflect gained items and lost gold
    # To do this, use `delta_inventory` as that takes into account all kinks
    Effect({
        'effect_type': 'delta_inventory',
        'delta': {
            css_friendly(requested_offer.get_item_id()): amount_to_buy,
            'item-gold': -revenue
        }
    }).execute_on(user)

    # Update Market Data to reflect reduced inventory
    user.update("data.station.market", {
        f"offers.{item_id}.stock": -amount_to_buy,
        f"books.{item_id}.popularity": profit,
        "books.interval_revenue": revenue
    }, is_bulk=True, mongo_command="$inc")

    # Reset last sale timestamp for this item
    user.update(f"data.station.market.books.{item_id}.last_sale", datetime.utcnow())

    # Statistics Update
    user.update("stat.market", {
        'transactions': 1,
        'total_revenue': amount_to_buy * requested_offer.get_current_price(),
        'total_profit': profit,
        'items_bought': amount_to_buy,
        f"{item_id}.sold": amount_to_buy
    }, is_bulk=True)

    # Object Events
    if stock_left == 0:
        item: Item = user.get(requested_offer.get_item_id())
        item.process_event("market_out_of_stock", user)

    return response


@Effect.type('market_stockup', ('item_id', str), ('amount', int))
def stock_up_on(user: User, effect_data: dict, **kwargs):
    """
    Stocks up `item_id` with `amount` new stock.
    If `price` is provided, will also change the price in the item's offer listing (optional).
    """
    # Get Effect Data
    item: MarketItem = user.get(effect_data['item_id']).as_subtype(MarketItem)
    amount = effect_data['amount']

    offers = user.get("data.station.market.offers.item")

    # What\'s the current amount & price?
    if item.get_minimized_id() in offers:
        current_amount = offers[item.get_minimized_id()]['stock']
    else:
        current_amount = 0

    update_data = {
        'stock': current_amount + amount
    }

    print(f"{update_data=} {current_amount=}")

    if 'price' in effect_data:
        update_data['price'] = effect_data['price']

    user.update(f"data.station.market.offers.{item.get_id()}", update_data, is_bulk=True)

    # Invoke a `market_restock` event
    item.process_event("market_restock", user)

    if current_amount == 0:
        item.process_event('market_back_in_stock', user)



# Increasing time intervals (in s) delineating longer wait times after player inactivity
# before updating market inventory. Each time, no purchase was made, an update will occur at a later time
MARKET_UPDATE_BASE_INTERVAL = 20
MARKET_UPDATE_INTERVAL_LEVELS_FACTOR = 1.8
MAX_MARKET_UPDATE_INTERVAL = 60 * 60




def _current_popularity_of(market_item: MarketItem, user: User) -> Number:
    books = user.get('data.station.market.books')
    if market_item.get_minimized_id() not in books:
        # This item has not been offered yet. High prio
        return 0
    else:
        return books[market_item.get_minimized_id()]['popularity']


def _item_restock_fitness(market_item: MarketItem, user: User) -> Number:
    """
    Helper Function used to prioritize multiple MarketItem options.
    :param market_item: A Market Item
    :param user:        A user
    :return:            This market-item's current fitness value
    """
    return _current_popularity_of(market_item, user)


@PeriodicEvent.repeat_type("market_update", default_interval=MARKET_UPDATE_BASE_INTERVAL)
def market_update(user: User, event: PeriodicEvent):
    """
    Executed regularly for every active `user` to re-assess market offers.
    :param user:    Target user.
    :param event:   Event that triggered this effect.
    """
    # Retrieve Base Variables
    offers = user.get("data.station.market.offers")
    books = user.get("data.station.market.books")

    # Get the interval from this interval cycle
    interval_revenue = books['interval_revenue']

    # Shopping Message to write to frontend
    update_message = "Thanks for <strong>shopping</strong> with me!"

    market_update_data = {
        'books.interval_revenue': 0,  # Reset Revenue success from this round
    }

    if interval_revenue > 0:
        # We have made sales in this interval.

        # Determine Purchase Power of this round
        purchase_power = fuzzify(user.get('attr.station.market.purchase_power'))
        max_item_value = user.get('attr.station.market.max_item_value')

        # RESTOCK a little
        restock_options: List[MarketItem] = [market_item for market_item in Item.get_all_static_of_subtype(MarketItem)
                                             if market_item.get_base_value() < max_item_value]
        restock_data: List[Tuple[MarketItem, int]] = list()
        # Sort Available restock options
        restock_options = sorted(restock_options, key=lambda market_item: _item_restock_fitness(market_item, user))

        # Distribute my resources in Pareto-Style across all available options.
        pareto_total = sum([1 / (i + 1) for i in range(len(restock_options))])

        for option, index in zip(restock_options, range(len(restock_options))):
            # Purchase as many as you can within the Pareto Percentage of budget
            pareto_percentage = (1 / (index + 1)) / pareto_total
            to_buy = math.floor(pareto_percentage * purchase_power / option.get_base_value())
            if to_buy > 0:
                restock_data.append((option, to_buy))

        # Stock Up based on calculations
        for m_item, amount in restock_data:
            Effect({
                'effect_type': 'market_stockup',
                'item_id': m_item.get_id(),
                'amount': amount,
                'price': m_item.price_at_amount(amount)
            }).execute_on(user)

        # Level out popularities by *deflating* all popularities by a fixed %
        popularity_deflation = user.get("attr.station.market.popularity_deflation") / 100
        for item_min_id in books['item']:
            current_popularity = books['item'][item_min_id]['popularity']
            market_update_data[f"books.item.{item_min_id}.popularity"] = current_popularity * (1 - popularity_deflation)

        # Reset Update Interval
        # event.set_interval(MARKET_UPDATE_BASE_INTERVAL)
        event.set_event_data('no_transaction_cycles', 0)
    else:
        # We have made no sales in this interval.
        # Increase wait period until next update
        event.set_event_data('no_transaction_cycles', event.get_event_data('no_transaction_cycles', default=0) + 1)
        # event.set_interval(min(MAX_MARKET_UPDATE_INTERVAL, event.get_interval() * MARKET_UPDATE_INTERVAL_LEVELS_FACTOR))
        pass

    market_update_data['feedback'] = update_message

    # Update the market's data to reflect the changes made
    user.update('data.station.market', market_update_data, is_bulk=True)


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
    if 'command' in kwargs:
        update_type = 'inc' if kwargs['command'] == '$inc' else 'set'
    else:
        update_type = 'set'

    user.frontend_update('update', {
        'update_type': update_type,
        'updated_elements': updated_elements
    })


@id_update_listener(r"^data\.station\.market\.feedback$")
def forward_market_feedback(user: User, data: dict, game_id: str, **kwargs):
    """Used to forward the market's feedback to the frontend."""
    updated_elements = {
        "data-station-market-feedback": {'data': data["data.station.market.feedback"]}
    }
    user.frontend_update('update', {
        'update_type': 'set',
        'updated_elements': updated_elements
    })
