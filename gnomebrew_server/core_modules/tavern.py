"""
This module manages the tavern and patron logic of the game.
"""
import logging
import math
import operator
import threading
import datetime
import time
from functools import reduce
from math import floor, ceil, log

from flask import render_template

from gnomebrew_server.game.static_data import Item, patron_order_list
from gnomebrew_server.game.user import User, load_user, frontend_id_resolver, user_assertion, html_generator
from gnomebrew_server.play import request_handler
from gnomebrew_server.game.event import Event
from gnomebrew_server.game.util import random_normal, random_uniform, is_weekday, fuzzify
from gnomebrew_server.play import request_handler
from gnomebrew_server.game.gnomebrew_io import GameResponse
from gnomebrew_server import mongo

from random import choice
from datetime import datetime, timedelta
from uuid import uuid4

# Calculation Constants:
TWO_PI = math.pi * 2
ROOT_TWO = math.sqrt(2)

# Gameplay Constants
MAX_BASE_WAIT_TIME = 1200
MIN_BASE_WAIT_TIME = 120

MIN_BASE_THIRST = 1
MAX_BASE_THIRST = 5

BASE_THIRST_DECAY = 1

AVG_DESIRE_THRESHOLD = 0.3

_CYCLE_TIME = 60 * 15
_PATRONS_PER_CYCLE = 50


class Patron:
    """
    Patron class
    """

    # A list of Fantasy names to generate patron names
    # Thanks to:
    # https://student-tutor.com/blog/200-iconic-fantasy-last-names-for-your-next-bestseller/
    # https://medium.com/@barelyharebooks/a-master-list-of-300-fantasy-names-characters-towns-and-villages-47c113f6a90b
    names = {
        'male': [
            'Lydan', 'Syrin', 'Ptorik', 'Joz', 'Varog', 'Gethrod', 'Hezra', 'Feron', 'Ophni', 'Colborn', 'Fintis',
            'Gatlin', 'Jinto', 'Hagalbar', 'Krinn', 'Lenox', 'Revvyn', 'Hodus', 'Dimian', 'Paskel', 'Kontas',
            'Weston', 'Azamarr', 'Jather', 'Tekren', 'Jareth', 'Adon', 'Zaden', 'Eune', 'Graff', 'Tez', 'Jessop',
            'Gunnar', 'Pike', 'Domnhar', 'Baske', 'Jerrick', 'Mavrek', 'Riordan', 'Wulfe', 'Straus', 'Tyvrik',
            'Henndar', 'Favroe', 'Whit', 'Jaris', 'Renham', 'Kagran', 'Lassrin', 'Vadim', 'Arlo', 'Quintis',
            'Vale', 'Caelan', 'Yorjan', 'Khron', 'Ishmael', 'Jakrin', 'Fangar', 'Roux', 'Baxar', 'Hawke',
            'Gatlen', 'Michael',
            'Barak', 'Nazim', 'Kadric', 'Paquin', 'Kent', 'Moki', 'Rankar', 'Lothe', 'Ryven', 'Clawsen', 'Pakker',
            'Embre', 'Cassian', 'Verssek', 'Dagfinn', 'Ebraheim', 'Nesso', 'Eldermar', 'Rivik', 'Rourke',
            'Barton'],
        'female': [
            'Hemm', 'Sarkin', 'Blaiz', 'Talon', 'Agro', 'Zagaroth', 'Turrek', 'Esdel', 'Lustros', 'Zenner',
            'Baashar', 'Dagrod', 'Gentar', 'Syrana', 'Resha', 'Varin', 'Wren', 'Yuni', 'Talis', 'Kessa',
            'Magaltie', 'Aeris', 'Desmina',
            'Krynna', 'Asralyn', 'Herra', 'Pret', 'Kory', 'Afia', 'Tessel', 'Rhiannon', 'Zara', 'Jesi', 'Belen',
            'Rei', 'Ciscra', 'Temy', 'Renalee', 'Estyn', 'Maarika', 'Lynorr', 'Tiv', 'Annihya', 'Semet',
            'Tamrin', 'Antia', 'Reslyn', 'Basak', 'Vixra', 'Pekka', 'Xavia', 'Beatha', 'Yarri', 'Liris',
            'Sonali', 'Razra', 'Soko', 'Maeve', 'Everen', 'Yelina', 'Morwena', 'Hagar', 'Palra', 'Elysa', 'Sage',
            'Ketra', 'Lynx', 'Agama', 'Thesra', 'Tezani', 'Ralia', 'Esmee', 'Heron', 'Naima', 'Rydna', 'Sparrow',
            'Baakshi', 'Ibera', 'Phlox', 'Dessa', 'Braithe', 'Taewen', 'Larke', 'Silene', 'Phressa', 'Esther',
            'Anika', 'Rasy', 'Harper', 'Indie', 'Vita', 'Drusila', 'Minha', 'Surane', 'Lassona', 'Merula', 'Kye',
            'Jonna', 'Lyla', 'Zet', 'Orett', 'Naphtalia', 'Turi', 'Rhays', 'Shike', 'Hartie', 'Beela', 'Leska',
            'Vemery', 'Lunex', 'Fidess', 'Tisette', 'Lisa'],
        'nonbinary': [
            'Clay', 'Linden', 'Rhun', 'Lennox', 'Billie', 'Robin', 'Les', 'Nic', 'Sage', 'Teagan'
        ],
        'last': [
            'Atwater', 'Agassi', 'Apatow', 'Akagawa', 'Averescu', 'Arrington', 'Agrippa', 'Aiken', 'Albertson',
            'Alexander', 'Amado', 'Anders', 'Ashsorrow', 'Humblecut', 'Ashbluff', 'Marblemaw', 'Armas', 'Akka',
            'Aoki', 'Aldrich', 'Apak', 'Alinsky', 'Desai', 'Darby', 'Draper', 'Dwyer', 'Dixon', 'Danton',
            'Desmith', 'Ditka', 'Dominguez', 'Decker', 'Dobermann', 'Dunlop', 'Dumont', 'Dandridge', 'Diamond', '',
            'Dukas', 'Agnello', 'Alterio', 'Bidbury', 'Botkin', 'Benoit', 'Biddercombe', 'Baldwin', 'Bennett',
            'Bourland', 'Boadle', 'Bender', 'Best', 'Bobshaw', 'Bersa', 'Belt', 'Bourn', 'Barke', 'Beebe', 'Banu',
            'Bozzelli', 'Bogaerts', 'Blanks', 'Evert', 'Eastwood', 'Elway', 'Eslinger', 'Ellerbrock', 'Eno',
            'Endo', 'Etter', 'Ebersol', 'Everson', 'Esapa', 'Ekker', 'Escobar', 'Eggleston', 'Ermine', 'Erickson',
            'Keller', 'Kessler', 'Kobayashi', 'Klecko', 'Kicklighter', 'Kidder', 'Kershaw', 'Kaminsky', 'Kirby',
            'Keene', 'Kenny', 'Keogh', 'Kipps', 'Kendrick', 'Kuang', 'Fairchild', 'October', 'Vespertine',
            'Fellowes', 'Omen', 'Willow', 'Gannon', 'Presto', 'Windward', 'Grell', 'Powers', 'Wixx', 'Halliwell',
            'Quellings', 'Xanthos', 'Hightower', 'Quill', 'Xenides', 'Idlewind', 'Rast', 'Chamillet',
            'Bougaitelet', 'Hallowswift', 'Coldsprinter', 'Winddane', 'Yarrow', 'Illfate', 'Riddle', 'Yew',
            'Jacaranda', 'Yearwood', 'Yellen', 'Yaeger', 'Yankovich', 'Yamaguchi', 'Yarborough', 'Youngblood',
            'Yanetta', 'Yadao', 'Winchell', 'Winters', 'Walsh', 'Whalen', 'Watson', 'Wooster', 'Woodson',
            'Winthrop', 'Wall', 'Sacredpelt', 'Rapidclaw', 'Hazerider', 'Shadegrove', 'Wight', 'Webb', 'Woodard',
            'Wixx', 'Wong', 'Whesker', 'Yale', 'Yasumoto', 'Yates', 'Younger', 'Yoakum', 'York', 'Rigby', 'Zaba',
            'Surrett', 'Swiatek', 'Sloane', 'Stapleton', 'Seibert', 'Stroud', 'Strode', 'Stockton', 'Scardino',
            'Spacek', 'Spieth', 'Stitchen', 'Stiner', 'Soria', 'Saxon', 'Shields', 'Stelly', 'Steele',
            'Chanassard', 'Ronchessac', 'Boneflare', 'Monsterbelly', 'Truthbelly', 'Sacredmore', 'Malfoy', 'Moses',
            'Moody', 'Morozov', 'Mason', 'Metcalf', 'McGillicutty', 'Montero', 'Molinari', 'Marsh', 'Moffett',
            'McCabe', 'Manus', 'Malenko', 'Mullinax', 'Morrissey', 'Mantooth', 'Kucharczk', 'Andonie']
    }

    def __init__(self, data: dict):
        # Generate Patron Base Attributes Randomly:
        self._data = data

    def get_data(self):
        return self._data

    def name(self):
        return self._data['name']

    def adapt_to(self, user: User):
        """
        Applies a given user's upgrades to the data of this patron. Called when the patron enters a tavern
        Assumes the data of this patron is:

        * Unique to the given user
        * Currently unmodified from `generate_random`'s result
        :param user:    a user
        :return: Returns a UUID for this patron on this user
        """
        # Budget was a standardized value. Budget however depends on game upgrades of specific user, too
        # In play, gold values only make sense in cents, so format the actual budget to an int
        self._data['budget'] = int(self._data['budget'] * user.get('attr.tavern.budget_multiplicator', default=1))
        self._data['tab'] = dict()
        uuid = str(uuid4())
        self._data['id'] = uuid
        return uuid

    def add_to_tab(self, order: list, user: User):
        """
        Adds an order to this patron's tab.
        The order amounts will be logged in the patron's corresponding `tab` value. If no such value exists yet,
        it will be added.
        :param user:    The active user.
        :param order:   Order data that has been **successfully** served, e.g. [{'item': 'beer', 'amount': 5}]
        """
        to_update = dict()
        for order_item in order:
            if order_item['item'] not in self._data['tab']:
                # Doesn't exist yet in tab. Just set to current order
                to_update[order_item['item']] = order_item['amount']
            else:
                # Already exists in tab. Add new value to update dict
                to_update[order_item['item']] = self._data['tab'][order_item['item']] + order_item['amount']
        user.update(f"data.tavern.patrons.{self._data['id']}.tab", to_update, is_bulk=True)

    def schedule_next_decision(self, user: User):
        """
        Schedules the next `decision_step` for this patron.
        :param user:    a user
        """
        # When will I make my next decision step?
        due_time = datetime.utcnow() + timedelta(
            seconds=random_normal(min=120, max=user.get('attr.tavern.patron_decision_time', default=60 * 15)))
        _generate_patron_next_step_event(target=user.get_id(),
                                         patron=self,
                                         due_time=due_time).enqueue()

    def decision_step(self, user: User):
        """
        This function lets the patron run one decision step. A decision step assumes that the patron is not enqueued and
        inside the tavern.
        The decision step results in one of these three options:
        
        1. The patron stays seated in the tavern but doesn't order.
        2. The patron enters the queue with an order.
        3. The patron leaves the tavern.
        
        :param user:    a user
        """
        prices = user.get('data.tavern.prices')
        # I'm noting down my orders here
        order_list = []

        # I'm managing my order preferences here
        wish_list = []

        # Take a look at the menu. Assign a perceived value to each item and create a wish-list
        # sorted by my desire to buy

        for item in [Item.from_id(f'item.{it_id}') for it_id in prices]:
            saturation = self.calculate_individual_saturation_factor(item, user)
            fair_price = item.determine_fair_price(user)
            personality_adjust = 1 + item.personality_adjust(self._data['personality']) * user.get(
                'attr.tavern.personality_flex', default=1)
            current_price = prices[item.get_minimized_id()]
            result = {
                'desire': self.generate_desire_for(orderable_item=item,
                                                   current_price=current_price,
                                                   user=user,
                                                   saturation=saturation,
                                                   fair_price=fair_price,
                                                   personality_adjust=personality_adjust),
                'demand': self.generate_demand_for(orderable_item=item,
                                                   current_price=current_price,
                                                   user=user,
                                                   saturation=saturation,
                                                   fair_price=fair_price,
                                                   personality_adjust=personality_adjust),
                'item': item
            }
            wish_list.append(result)

        wish_list = sorted(wish_list, key=lambda d: d['desire'])

        # I am motivated to order. Let's go:
        # Go through my wish list in descending order of preference and start ordering

        total_saturation = self.calculate_total_saturation_factor(user=user)
        thirst = self.generate_thirst(user, saturation_factor=total_saturation)

        budget_count = self._data['budget']
        desire_threshold = AVG_DESIRE_THRESHOLD * user.get('attr.tavern.desire_threshold_factor', default=1)


        for wish in wish_list:
            item_name = wish['item'].get_minimized_id()

            # Check if minimum requirements for all four parameters are met:
            if budget_count > prices[item_name] and \
                    thirst > 0 and \
                    wish['demand'] >= 1 and \
                    wish['desire'] > desire_threshold:
                orderable_data = wish['item'].get_value('orderable')
                # I want the most possible of this limited by:
                # a) Budget
                # b) Thirst
                # c) Demand
                amount = int(min(floor(budget_count / prices[item_name]),
                                 ceil(thirst / orderable_data['thirst_reduction']),
                                 wish['demand']))
                budget_count -= amount * prices[item_name]
                thirst -= amount * (
                        orderable_data['thirst_reduction'] * user.get('attr.tavern.thirst_reduction_mul',
                                                                      default=1))
                order_list.append({
                    'item': item_name,
                    'amount': amount
                })

        print(f"Decision of {self._data['name']}:")
        print(f"{wish_list=}")
        print(f"thirst:\t{thirst}")
        print(f"budget:\t{self._data['budget']} down to {budget_count}")
        print(f"orders: {order_list}\n\n")

        if not order_list:
            # My order list is empty. I can't afford/don't want anything. Let's leave.
            self.leave_tavern(user)
            return

        # I have finished my order list. Time to enqueue!
        self.enter_queue(user, {
            'id': self._data['id'],
            'order': order_list
        })

    def enter_queue(self, user: User, order_data: dict):
        """
        Enrolls this patron in the tavern queue, if possible
        :param order_data:      Data of the order to be added.
        :param user:    a user
        """
        queue_data = user.get('data.tavern.queue')

        # Add my order to the queue
        queue_data.append(order_data)
        user.update('data.tavern.queue', queue_data)

        # I will get impatient if my order is not handled within a timeframe.
        # -> Create timed event to handle this
        # Calculate the time at which the patron is impatient

        due_time = datetime.utcnow() + self.generate_wait_time(user)
        seconds = random_normal(min=120, max=user.get('attr.tavern.patron_patience', default=1200))
        _generate_patron_impatient_event(target=user.get_id(), patron=self, due_time=due_time).enqueue()

    def leave_queue(self, user: User):
        """
        Removes the patron from the user's tavern queue.
        """
        queue = user.get('data.tavern.queue')

        # Filter out any and all orders with the patron's id
        user.update('data.tavern.queue', list(filter(lambda order: order['id'] != self._data['id'], queue)))

        self.schedule_next_decision(user)

    def leave_tavern(self, user: User):
        """
        Leaves the tavern forever.
        :param user:    a user
        """
        # Remove Patron from Tavern Data
        user.update('data.tavern.patrons.' + self._data['id'], {}, command='$unset')

        # Remove the next step event that still exists
        mongo.db.events.delete_many({
            'target': user.get_id(),
            '$or': [{'effect.patron_next_step.id': self._data['id']}, {'effect.patron_impatient.id': self._data['id']}]
        })

        # Delete Raw Data to make sure this object is unusable
        del self._data

    def reconsider_order(self, user: User, price_change: dict):
        """
        Called if the patron is currently queued and one of the items they're standing in line for has changed price
        (only called if the price increased compared to previously).
        Depending on circumstances (budget, willingness, etc.) the patron will either:

        1. Stay in queue or
        2. Leave the queue and get seated again in the tavern, scheduling a next decision.
        :param user:    a user
        :param price_change: a dict with all changed prices formatted `price_change[item_id] = new_price`
        """
        pass

    @staticmethod
    def _saturation_factor_formula(num_item, saturation_factor) -> float:
        """
        Base function to calculate how number of items (and a 'constant' type parameter) define the saturation
        factor.
        :param num_item:            Number of items consumed
        :param saturation_factor:   Factor to be considered the individual entity's 'depreciation' factor
        :return:                    The numeric result of the saturation formula.
        """
        return log(num_item * saturation_factor + math.e)

    def calculate_individual_saturation_factor(self, orderable_item: Item, user: User) -> float:
        """
        Calculates the saturation experienced from an individual item already.
        :param orderable_item:  An item that can be ordered.
        :param user:            The executing user
        :return:                This patron's level of saturation. Going from `1` (not saturated at all) to positive
                                Infinity in a logarithmic ascend.
        """
        item_name = orderable_item.get_minimized_id()
        if item_name in self._data['tab']:
            # This item has already been ordered. Apply saturation factor
            return self._saturation_factor_formula(self._data['tab'][item_name],
                                                   orderable_item.get_value('orderable')['saturation_speed'] * user.get(
                                                       'attr.tavern.saturation_factor', default=1))
        else:
            # Not ordered this yet. Factor = 1
            return 1

    def calculate_total_saturation_factor(self, user: User) -> float:
        """
        Calculates the cumulative saturation experienced from ALL items consumed so far.
        :param user:    The executing user.
        :return:        The total saturation factor value taking into account all parameters.
        """
        return self._saturation_factor_formula(sum(self._data['tab'].values()),
                                               BASE_THIRST_DECAY * user.get('attr.tavern.thirst_decay_factor',
                                                                            default=1))

    def generate_wait_time(self, user: User) -> timedelta:
        """
        Generates a wait time based on:
        * Game Attributes
        * Patron Personality
        * Random factors

        Thank you Farhad Khormaie and Roghaye Ghorbani for
        [research that helped me model this](https://www.researchgate.net/publication/331867592_Relationship_between_Big_Five_Personality_Traits_and_Virtue_of_Wisdom_The_Mediating_Role_of_Patience).

        :return:    a `timedelta` that represents the time the patron is willing to wait in queue.
        """
        # Base Willingness to wait
        wait_in_s = random_normal(min=MIN_BASE_WAIT_TIME, max=MAX_BASE_WAIT_TIME)
        # Calculate influence of personality on the patron as a factor
        personality_influence = (((self._data['personality']['agreeableness'] * 0.29) +
                                  (self._data['personality']['conscientiousness'] * 0.35) +
                                  (self._data['personality']['neuroticism'] * -0.30) +
                                  ((self._data['personality']['extraversion'] - 1) * len(
                                      user.get('data.tavern.queue')) * 0.02)) *
                                 user.get('attr.tavern.personality_flex', default=1)) + 1
        wait_in_s *= personality_influence
        return timedelta(seconds=wait_in_s)

    def generate_desire_for(self, orderable_item: Item, current_price: float, user: User, **kwargs) -> float:
        """
        Helper function. Assigns a perceived value to an **orderable** item.
        :param orderable_item:    An item. Must be **orderable**.
        :param current_price:     The current price of the item in question.
        :param user:              A user.
        :keyword saturation:      Optional. Calculated saturation factor
        :keyword fair_price:      Optional. Calculated fair item price
        :keyword personality_adjust:      Optional. Calculated personality adjust factor
        :return:                  A perceived desire for this item.
                                  0: I don't want this at all.
                                  1: I must have this.
        """
        saturation_factor = kwargs[
            'saturation'] if 'saturation' in kwargs else self.calculate_individual_saturation_factor(
            orderable_item, user)
        fair_price = kwargs['fair_price'] if 'fair_price' in kwargs else orderable_item.determine_fair_price(user)
        personality_adjust = kwargs['personality_adjust'] if 'personality_adjust' in kwargs else \
            1 + orderable_item.personality_adjust(self._data['personality']) * user.get(
                'attr.tavern.personality_flex', default=1)
        if current_price < fair_price:
            denominator = 3 - math.cos(TWO_PI * (current_price - fair_price) / fair_price)
        elif current_price > fair_price:
            denominator = 1 + math.cos(TWO_PI / math.pow(ROOT_TWO, fair_price / (current_price - fair_price)))
        else:
            # Current price is fair price exactly ==> 2 (so that denominator/4 = 0.5)
            denominator = 2
        base_value = denominator / (4 * saturation_factor)

        print(f"Base Desire is {base_value}, {personality_adjust=}")

        # Apply Personality shift
        return min(1, max(0, base_value * personality_adjust))

    def generate_demand_for(self, orderable_item: Item, current_price: float, user: User, **kwargs) -> int:
        """
        Helper function. Assigns a maximum desired amount for an orderable item for a possible purchase.
        :param orderable_item:    An item. Must be **orderable**.
        :param current_price:     The current price of the item in question.
        :param user:              A user.
        :keyword saturation:      Optional. Calculated saturation factor
        :keyword fair_price:      Optional. Calculated fair item price
        :keyword personality_adjust:      Optional. Calculated personality adjust factor
        :return:                  A whole number between 0 and positive infinity defining the maximum desired amount
                                  of an item this patron would like next, taking into account variables and environment.
        """
        orderable_data = orderable_item.get_value('orderable')
        personality_adjust = kwargs['personality_adjust'] if 'personality_adjust' in kwargs else \
            1 + orderable_item.personality_adjust(self._data['personality']) * user.get(
                'attr.tavern.personality_flex', default=1)
        saturation_factor = kwargs[
            'saturation'] if 'saturation' in kwargs else self.calculate_individual_saturation_factor(
            orderable_item, user)
        fair_price = kwargs['fair_price'] if 'fair_price' in kwargs else orderable_item.determine_fair_price(user)
        return floor(fuzzify(personality_adjust * orderable_data['fair_demand'] /
                             (math.pow((current_price / fair_price),
                                       orderable_data['elasticity']) * saturation_factor)))

    def generate_thirst(self, user: User, **kwargs) -> float:
        """
        Generates a number that represents this patrons willingness/need for beer and consumption in general for the current
        round.
        :param user:    A user.
        :keyword saturation_factor: Saturation Factor to be applied to the overall thirst. If set, it will not be re-calculated.
                                    Since thirst is generated once **per order round** (unlike desire/demand which are generated
                                    per-item), this saturation factor takes in the total amount of items consumed.
        :return:    A number that represents user thirst. The larger the more meaningful the thirst.
        """
        if is_weekday():
            personality_influence = ((self._data['personality']['agreeableness'] * -.14) +
                                     (self._data['personality']['extraversion'] * .02) +
                                     (self._data['personality']['neuroticism'] * .02)
                                     * user.get('attr.tavern.personality_flex', default=1)) + 1
        else:
            personality_influence = ((self._data['personality']['neuroticism'] * .08) +
                                     (self._data['personality']['extraversion'] * .02) +
                                     (self._data['personality']['openness'] * -.12)
                                     (self._data['personality']['conscientiousness'] * -.10)
                                     * user.get('attr.tavern.personality_flex', default=1)) + 1

        saturation_factor = kwargs['saturation_factor'] if 'saturation_factor' in kwargs else \
            self.calculate_total_saturation_factor(user)

        base_thirst = random_normal(min=MIN_BASE_THIRST, max=MAX_BASE_THIRST)
        return base_thirst * personality_influence * user.get('attr.tavern.thirst_multiplier',
                                                              default=1) / saturation_factor

    @staticmethod
    def generate_random():
        """
        Generates a random Patron
        :return:    A patron with randomly distributed attributes
        """
        data = dict()
        # Generate a gender
        random_val = random_uniform()
        data['gender'] = 'male' if random_val < .498 else 'female' if random_val < .996 else 'nonbinary'
        # Generate a name
        data['name'] = choice(Patron.names[data['gender']]) + ' ' + choice(Patron.names['last'])
        # Budget is standardized independent of upgrade status of user. Budget will be modified upon patron entry
        data['budget'] = random_normal(min=15, max=100)

        data['personality'] = Patron.generate_random_personality()

        return Patron(data)

    @staticmethod
    def generate_random_personality() -> dict:
        """
        Generates a dict (JSON) of a patron's personality
        :return:    A dict to be saved as the patron's personality.
        """
        personality = dict()
        personality['extraversion'] = random_normal(min=-1, max=1)
        personality['agreeableness'] = random_normal(min=-1, max=1)
        personality['openness'] = random_normal(min=-1, max=1)
        personality['conscientiousness'] = random_normal(min=-1, max=1)
        personality['neuroticism'] = random_normal(min=-1, max=1)
        return personality

    @staticmethod
    def generate_patron_list(num_patrons: int = _PATRONS_PER_CYCLE) -> list:
        return [Patron.generate_random() for x in range(num_patrons)]


class TavernSimulationThread(object):
    """
    Thread Object that simulates the tavern logic for *all* users
    """

    def __init__(self, mongo_instance):
        self.mongo = mongo_instance

        self.thread = threading.Thread(target=self.run, args=())
        self.thread.daemon = True
        self.thread.start()

    def run(self):
        while True:
            start_time = datetime.utcnow()

            # Start of Tavern Logic

            # Generate new patrons for this iteration
            PATRONS: list[Patron] = Patron.generate_patron_list()

            # Iteratively Process each user individually
            for user, tavern_data in self._user_iterator():
                _process_user(user=user, tavern_data=tavern_data, patron_list=PATRONS)

            # END of Tavern Logic

            end_time = datetime.utcnow()
            # print(f'Total time: {(end_time - start_time).total_seconds() }')
            sleep_time = _CYCLE_TIME - (end_time - start_time).total_seconds()
            if sleep_time > 0:
                try:
                    time.sleep(sleep_time)
                except KeyboardInterrupt:
                    print('Shutting down tavern thread')
                    exit()

    def _user_iterator(self):
        """
        Utility function that helps iterate a list of ALL game users at the time of the game call
        """
        for document in self.mongo.db.users.find({}, {'username': 1, 'data.tavern': 1}):
            if 'tavern' not in document['data']:
                # A user could not have yet activated their tavern. Ignore those
                continue
            yield load_user(document['username']), document['data']['tavern']


def _process_user(user: User, tavern_data: dict, patron_list: list):
    """
    Helper Function that processes one user within the Tavern Thread
    :param user:
    :param tavern_data:
    :return:
    """
    now = datetime.utcnow()

    # Define the number of Patrons that will join the tavern in this cycle
    num_patrons = int(random_normal(min=0, max=user.get('attr.tavern.patron_influx', default=10)))
    patron_entry_times = random_uniform(min=0, max=_CYCLE_TIME, size=num_patrons)
    for patron, entry_delay in zip(patron_list[:num_patrons], patron_entry_times):
        _generate_patron_enter_event(target=user.get_id(),
                                     patron=patron,
                                     due_time=now + timedelta(seconds=entry_delay)).enqueue()


def _generate_patron_enter_event(target: str, patron: Patron, due_time: datetime):
    """
    Generates a fresh event that starts generates a new market offer listing once it fires.
    :param patron:  The Patron who will enter
    :param target:  user ID target
    :param due_time: due time (server UTC) at which the event fires
    """
    data = dict()
    data['target'] = target
    data['type'] = 'tavern'
    data['effect'] = dict()
    data['effect']['patron_enter'] = patron.get_data()
    data['due_time'] = due_time
    data['station'] = 'tavern'
    return Event(data)


def _generate_patron_impatient_event(target: str, patron: Patron, due_time: datetime):
    data = dict()
    data['target'] = target
    data['type'] = 'tavern'
    data['effect'] = dict()
    p_data = patron.get_data()
    data['effect']['patron_impatient'] = {
        'id': p_data['id']
    }
    data['due_time'] = due_time
    data['station'] = 'tavern'
    return Event(data)


def _generate_patron_next_step_event(target: str, patron: Patron, due_time: datetime):
    data = dict()
    data['target'] = target
    data['type'] = 'tavern'
    data['effect'] = dict()
    p_data = patron.get_data()
    data['effect']['patron_next_step'] = {
        'id': p_data['id']
    }
    data['due_time'] = due_time
    data['station'] = 'tavern'
    return Event(data)


@Event.register
def patron_next_step(user: User, effect_data: dict):
    """
    Fires when a patron is due to decide what to do next.
    :param user:    A user
    :param effect_data: Effect data details
    """
    # Get the targetted patron
    try:
        patron: Patron = Patron(user.get('data.tavern.patrons.' + effect_data['id']))
    except KeyError:
        # The patron could not be found
        logging.error(f'Patron with data {effect_data} could not be found!')
        return
    patron.decision_step(user)


@Event.register
def patron_enter(user: User, effect_data: dict):
    """
    Fires when a patron enters the tavern.
    :param user:        the user
    :param effect_data: effect data details
    """
    tavern_capacity = user.get('attr.tavern.capacity')
    tavern_data = user.get('data.tavern')

    # Check if pub is full
    if len(tavern_data['patrons']) >= tavern_capacity:
        # The Tavern is full. Patron cannot enter
        return

    # Generate Patron and apply user upgrade modifications
    patron = Patron(effect_data)
    patron_uuid = patron.adapt_to(user)

    # Add Patron to patron list
    tavern_data['patrons'][patron_uuid] = patron.get_data()
    # Write in the new patron
    user.update('data.tavern.patrons.' + patron_uuid, patron.get_data())

    # Patron enters --> First Decision
    patron.decision_step(user=user)


@Event.register
def patron_impatient(user: User, effect_data: dict):
    """
    Handles a `patron_impatient` event.
    :param user:        Target User
    :param effect_data: Effect Data
    """
    # Get the targeted patron
    patron: Patron = Patron(user.get('data.tavern.patrons.' + effect_data['id']))

    # Patrons leaves the queue
    patron.leave_queue(user)

    # The patron also leaves the tavern
    patron.leave_tavern(user)


@request_handler
def serve_next(request_object: dict, user: User):
    """
    Handles a game request from the user to serve the next patron.
    :param request_object:  Contains `action`. Can be:
                            * `sell` to sell
                            * `decline` to send away
    :param user:            A user
    """

    if request_object['what_do'] == 'sell':
        return sell_to_next(user)
    else:
        return decline_next(user)


def decline_next(user: User):
    """
    Declines and sends back the patron in front of the queue
    :param user:    a user
    """
    response = GameResponse()
    tavern_data = user.get('data.tavern')
    queue = tavern_data['queue']
    if not queue:
        # queue is empty
        response.add_fail_msg('Noone to serve in queue.')
        return response

    next_order = queue.pop(0)

    # Every queued patron has an impatience-event waiting. Make sure to remove it now
    mongo.db.events.delete_one({
        'target': user.get_id(),
        'effect.patron_impatient.id': next_order['id']
    })

    user.update('data.tavern.queue', queue)

    # The patron will now sit back down in the tavern
    # They will need to decide when to leave
    Patron(tavern_data['patrons'][next_order['id']]).schedule_next_decision(user)

    response.succeess()
    return response


def sell_to_next(user: User):
    """
    Sells to the next patron in front of the queue, if possible
    :param user:    a user
    """
    tavern_data = user.get('data.tavern')
    response = GameResponse()

    # Check if there's someone waiting to be served
    if len(tavern_data['queue']) == 0:
        response.add_fail_msg('Noone to serve in queue.')
        return response

    # Get next order in Queue
    next_order = tavern_data['queue'][0]

    # Check if enough of the required product is in storage
    storage = user.get('data.storage.content')
    for order in next_order['order']:
        if storage[order['item']] < order['amount']:
            response.add_fail_msg(f"Not enough {Item.from_id('item.' + order['item']).name()} in storage.")

    if response.has_failed():
        return response

    # All Checks are passed. Serve the patron now:

    # Take the order out of the queue
    tavern_data['queue'].pop(0)

    # Every queued patron has an impatience-event waiting. Make sure to remove it now
    mongo.db.events.delete_one({
        'target': user.get_id(),
        'effect.patron_impatient.id': next_order['id']
    })

    # The patron will now sit back down in the tavern to have a drink.
    # They will need to decide when to leave
    # Also make sure the patron tracks their consumption
    patron_to_serve = Patron(tavern_data['patrons'][next_order['id']])
    patron_to_serve.schedule_next_decision(user)
    patron_to_serve.add_to_tab(next_order['order'], user)

    # Update all user data with the transaction result
    user_gold = storage['gold']
    inventory_changes = dict()
    order_total = 0
    for order in next_order['order']:
        # Calculate the new user gold you're making with this transaction
        order_total += order['amount'] * tavern_data['prices'][order['item']]

        # Calculate the inventory changes
        inventory_changes['storage.content.' + order['item']] = storage[order['item']] - order['amount']

    patron_budget = tavern_data['patrons'][next_order['id']]['budget']
    update_data = {
        'storage.content.gold': user_gold + order_total,
        'tavern.queue': tavern_data['queue'],
        'tavern.patrons.' + next_order['id'] + '.budget': patron_budget - order_total
    }
    update_data.update(inventory_changes)

    user.update('data', update_data, is_bulk=True)

    # TODO: UI Updates
    response.succeess()
    return response


@request_handler
def set_price(request_object: dict, user: User):
    """
    For a user to change the pricing of a beer.
    :param request_object:  Contains the request data.
    :param user:            a user
    """
    response = GameResponse()

    tavern_data = user.get('data.tavern')
    prices = tavern_data['prices']

    item, price = request_object['item'], int(request_object['price'])
    old_price = prices[item]
    if item not in prices:
        response.add_fail_msg('ERROR - Tell Mike about this.')
        return response

    if price < 0:
        response.add_fail_msg("You cannot charge negative prices. This is how you go out of business!")
        return response

    user.update('data.tavern.prices.' + item, price)

    if old_price < price:
        # The price has increased. Are all queued patrons cool with this?
        for patron_order in tavern_data['queue']:
            # Is this order relevant for the price update?
            if any(filter(lambda o: o['item'] == item, patron_order['order'])):
                # Generate the patron object to handle the decision
                patron = Patron(tavern_data['patrons'][patron_order['id']])
                patron.reconsider_order(user=user, price_change={item: price})

    response.succeess()
    return response


@frontend_id_resolver(r'^data\.tavern\.name$')
def normal_update_for_tavern_name(user: User, data: dict, game_id: str):
    user.frontend_update('update', data)


@frontend_id_resolver(r'data\.tavern\.queue')
def reload_tavern_on_queue_update(user: User, data: dict, game_id: str):
    user.frontend_update('ui', {
        'type': 'reload_element',
        'element': 'tavern.queue'
    })


@frontend_id_resolver(r'data\.tavern\.prices')
def reload_prices_on_price_update(user: User, data: dict, game_id: str):
    user.frontend_update('ui', {
        'type': 'reload_element',
        'element': 'tavern-prices'
    })


@frontend_id_resolver(r'^data\.tavern\.[\w\-\.]+$')
def ignore_tavern_data(user: User, data: dict, game_id: str):
    """
    This implementation is a little dirty, because the above function matches the tavern queue only and this function
    matches all tavern data, including the queue.
    However, since the above is added first internally, this function will not kick in for tavern updates.
    """
    pass  # Ignore Tavern Data. UI updates for tavern data are managed during processing logic


@user_assertion
def all_enqueued_have_impatient_event(user: User):
    # Get order queue
    queue = user.get('data.tavern.queue')

    for order in queue:
        assert mongo.db.events.count_documents({
            'effect.patron_impatient.id': order['id']
        }, limit=1) != 0


@html_generator('html.tavern.queue')
def render_patron_queue(user: User):
    """
    Generates up-to-date HTML that represents the patron queue.
    :param user:    a user
    :return:        HTML for the patron-queue
    """
    tavern_data = user.get('data.tavern')
    return render_template('snippets/_patron_queue.html',
                           patrons=tavern_data['patrons'],
                           queue=tavern_data['queue'])


@html_generator('html.tavern-prices')
def render_tavern_prices(user: User):
    """
    Generates up-to-date HTML that represents the tavern's current pricing list
    :param user:    a user
    :return:        HTML for pricing list
    """
    return render_template('snippets/_tavern_price_list.html',
                           prices=user.get('data.tavern.prices'))
