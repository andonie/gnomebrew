"""
Patrons in Gnomebrew are stateful, interactable, and are extendable. This module manages fundamental patron strategies
as well as the `Patron` class's features for further extension outside of this module.
"""
import logging
import math
from datetime import timedelta
from math import floor, ceil
from math import log as math_log
from numbers import Number
from typing import Callable, List

from gnomebrew.game.objects.game_object import render_object
from gnomebrew.logging import log
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects import PlayerRequest
from gnomebrew.game.objects.data_object import DataObject
from gnomebrew.game.objects.generation import Generator
from gnomebrew.game.objects.event import PeriodicEvent
from gnomebrew.game.objects.item import Item
from gnomebrew.game.objects.people import Person
from gnomebrew.game.user import User, load_user
from gnomebrew.game.util import random_normal, fuzzify, is_weekday, css_unfriendly

# Calculation Constants:
TWO_PI = math.pi * 2
ROOT_TWO = math.sqrt(2)


@Person.subtype("patron", ('budget', int), ('state', str), ('tab', list), ('thirst', Number),
                ('available_actions', list), ('_order', object), ('ui_order', int), ('feedback', str))
class Patron(Person):
    """Patron class wraps features of the `patron` subtype."""

    TAVERN_UPDATE_INTERVAL = 300

    # Random Feedbacks
    RANDOM_TALK = {
        "I heard there's a new sherrif in town.": 1,
        "Do you think I should talk to that guy over there?": 1,
        "This beer isn't half bad!": 1
    }

    # Gameplay Constants
    MAX_BASE_WAIT_TIME = 1200
    MIN_BASE_WAIT_TIME = 120

    MIN_BASE_THIRST = 1
    MAX_BASE_THIRST = 5

    BASE_THIRST_DECAY = 1

    AVG_DESIRE_THRESHOLD = 0.3

    INIT_BUDGET_MEDIAN = 50
    INIT_THIRST_MEDIAN = 12

    _action_types = dict()

    _strategies = list()

    @classmethod
    def action_type(cls, action_type: str):
        """
        Annotation function decorates a action handling function.
        :param action_type:     The unique name of the action being registered
        """
        if action_type in cls._action_types:
            raise Exception(f"Action Type already registered: {action_type}")

        def wrapper(fun: Callable):
            job = dict()
            job['resolve_fun'] = fun
            cls._action_types[action_type] = job
            return fun

        return wrapper

    @classmethod
    def timeout_strategy(cls, available_states: List[str], weight=1, requirements=None):
        """
        Annotation function registers a timeout-strategy for use with the tavern module.
        :param available_states:    List of states in which this timeout_strategy is available.
        :param weight:              Optional. Describes how often this decision should be chosen
                                    relative to other valid strategies. Default is 1.
        :param requirements:        Optional. If provided, will only make this strategy available if the requirements
                                    are met.
        """

        def wrapper(timeout_strat: Callable):
            data = dict()
            data['available_states'] = available_states
            data['requirements'] = requirements
            data['strategy'] = timeout_strat
            data['weight'] = 1
            cls._strategies.append(data)

            return timeout_strat

        return wrapper

    def __init__(self, data: dict):
        Person.__init__(self, data)

    def get_current_state(self):
        """
        :return: The patron's current state, such as `ordering`, `sitting`, or `drinking`
        """
        return self._data['patron']['state']

    def get_current_budget(self):
        return self._data['patron']['budget']

    def reduce_budget(self, reduction_amount: int):
        """
        Reduces this patron's budget by `reduction_amount`
        :param reduction_amount:    Amount to reduce budget by in total gold cents.
        """
        self._data['patron']['budget'] -= reduction_amount

    def get_current_tab(self):
        return self._data['patron']['tab']

    def add_to_tab(self, order: dict):
        """
        Called when a patron is being served an order.
        This function runs the calculations of *how consuming `order` influences the patron's inner state*. It
        also tracks the `order`.
        :param order:   Order data that has been **successfully** served, e.g. { 'item-beer': 2, 'item-house_special': 3 }
        """
        # Patrons track their total consumption in the tab list
        self._data['patron']['tab'].append(order)

        # TODO apply effects of drinking `order`

    def get_ui_order(self):
        return self._data['patron']['ui_order']

    def set_ui_order(self, ui_order: int):
        """
        Updates this patron's UI order. Patrons are sorted in the UI in *descending order*.
        :param ui_order:    Patron order. The higher this number, the higher up in the listing.
        """
        self._data['patron']['ui_order'] = ui_order

    def set_feedback_text(self, feedback: str):
        """
        Updates this patron's user feedback.
        :param feedback     Feedback to write to user.
        """
        self._data['patron']['feedback'] = feedback

    def get_feedback_text(self) -> str:
        return self._data['patron']['feedback']

    def get_state_icon_id(self) -> str:
        """
        :return:    A fully qualified Game ID that best represents this patron right now, all things considered.
        """
        return f"person.{self._data['patron']['state']}.{self.get_looks()}"

    # Patron State and Transitions

    def confirm_update(self, user: User, next_state: str):
        """
        Base method to transition the patron's state and then updates this patron's source data.
        This method closes off all patron processes.
        :param user:                Target user
        :param next_state:          Target state the patron will be in after the transition.
        """
        # Update new state before updating entire object to user.
        self._data['patron']['state'] = next_state
        self.write_patron_to(user)
        self.process_event("patron_state_update", user)

    def add_available_interaction(self, *interactions: str):
        """
        Add interactions as available for the user during the patron's **current state**.
        :param interactions:    Any number of registered actions available.
        """
        self._data['patron']['available_actions'].extend(interactions)

    def get_available_interactions(self) -> List[str]:
        """
        :return:    A list with all currently valid interaction string codes.
        """
        return self._data['patron']['available_actions']

    def flush_available_interactions(self):
        """
        Removes all interaction-names that were marked as available.
        Conceptually, this can be considered an 'implicit mutex' on patron state changes
        (as an empty available interaction list prevents all user interaction with the patron).
        """
        self._data['patron']['available_actions'] = list()

    def process_interaction(self, user: User, action_type: str, response: GameResponse):
        """
        Called to process an action `action_type` and - if appropriate - initiate a state transition.
        :param user:            Target user.
        :param response:        Handed-down response object to log immediate feedback for the user.
                                This feature is user-initiated and hence requires a response.
        :param action_type:     Desired action to enact on this patron.
        """
        if action_type not in self._data['patron']['available_actions']:
            response.add_fail_msg(f"Interaction {action_type} is not available.")
            return response

        # Action Type is valid. Check for available resolver function
        if action_type not in Patron._action_types:
            response.add_fail_msg(f"Illegal action input: {action_type}")
            log("gb_system", f"Received illegal patron action input: <%{action_type}%>", f"usr:{user.get_id()}", level=logging.WARNING)
            return response

        # Flush all available interactions before processing (& adding new interactions)
        self.flush_available_interactions()

        # Action Type is valid & Resolving Strategy exists
        # Forward the call to the registered function.
        Patron._action_types[action_type]['resolve_fun'](user=user, patron=self, response=response)

        # After the call of the function, we consider any and all changes to the patron state as done.

    def on_timeout(self, user: User, event: PeriodicEvent, gen: Generator = None):
        """
        Called on the patron whenever their associated periodic event times out.
        This is the function that drives the patron forward other than player action.
        Processes a state transition for this patron.
        :param user:    Target user.
        :param gen:     Optional. Generator to use for randomly choosing timeout strategy.
        :param event:   Triggering periodic event.
        """
        # We are now urged to take an action. But which one? Establish a list of all strategies I could take now.
        # Filter strategies first by which allow for this state.
        available_timeout_strategies = list(
            filter(lambda data: self._data['patron']['state'] in data['available_states'],
                   Patron._strategies))

        if not available_timeout_strategies:
            # This is unexpected. Not a single timeout strategy is valid in this state
            log("gb_system", f"Found no available timeout-strategy for patron: {str(self)}", 'timeout',
                level=logging.WARNING)
            # Since I don't know what to do, I finish the patron off completely and cancel the periodic update event
            event.cancel_self()
            self.remove_patron_from(user)
            return

        # Format the available strategies in a [choice] = weight dict for generator
        available_timeout_strategies = {data['strategy']: data['weight'] for data in available_timeout_strategies}

        # Choose and execute one strategy
        if gen is None:
            gen = Generator.fresh()

        gen.choose(available_timeout_strategies)(user=user, patron=self)

    def set_order(self, order_data: dict):
        """
        Updates this patron's `order` data to reflect the patron's willingness to buy `order_data`'s contents from
        the user. In and of itself, this does not update any user data.
        :param order_data:  order data to be given to user.
        """
        # Take over the order data in my patron data.
        self._data['patron']['order'] = order_data

    def get_order_data(self):
        """Returns the user's current order data"""
        return self._data['patron']['order']

    # Data Mgmt

    def initialize_for(self, user: User):
        """
        Called when to prepare a `Patron` to be written into user (tavern) data.

        :param user:        Target user to initialize for.
        """
        # Improve available budget by upgradeable attribute (initial attr value is 1)
        self._data['patron']['budget'] *= user.get('attr.station.tavern.budget_mul')

        # Generate an event instance and exchange IDs for future reference.
        event = PeriodicEvent.generate_instance_for(user, 'patron_update')
        event.set_event_data('patron_id', self.get_minimized_id())
        self._data['patron']['patron_update_event'] = event.get_event_id()

        # Write patron data in its adapted state into user data and remove patron from global DB (if has been present)
        self.write_patron_to(user)
        self.global_db_remove()

        # Forward the init to any instance implementations listening in.
        self.process_event("patron_enter_tavern", user)

        # We are done now. Start the periodic
        event.reschedule_self()

    def write_patron_to(self, user: User):
        """
        Writes this patron to a user's tavern data (as `upsert`).
        :param user:    Target user
        """
        user.update(f"data.station.tavern.patrons.{self.get_minimized_id()}", self._data)

    def remove_patron_from(self, user: User):
        """
        Removes this patron from a user's tavern data.
        :param user:    Target user
        """
        user.update(f"data.station.tavern.patrons.{self.get_minimized_id()}", {}, mongo_command='$unset')

    def get_update_event(self, user: User) -> PeriodicEvent:
        """
        :return:    This patron's update handling periodic event or `None` if not available.
        """
        if 'patron_update_event' not in self._data:
            return None
        return user.get(f"event.{self._data['patron']['patron_update_event']}")

    ## PATRON INTERNAL CALCULATIONS

    @staticmethod
    def _saturation_factor_formula(num_item, saturation_factor) -> float:
        """
        Base function to calculate how number of items (and a 'constant' type parameter) define the saturation
        factor.
        :param num_item:            Number of items consumed
        :param saturation_factor:   Factor to be considered the individual entity's 'depreciation' factor
        :return:                    The numeric result of the saturation formula.
        """
        return math_log(num_item * saturation_factor + math.e)

    def calculate_individual_saturation_factor(self, orderable_item: Item, user: User, **kwargs) -> float:
        """
        Calculates the saturation experienced from an individual item already.
        :param orderable_item:  An item that can be ordered.
        :param user:            The executing user
        :return:                This patron's level of saturation. Going from `1` (not saturated at all) to positive
                                Infinity in a logarithmic ascend.
        """
        item_name = orderable_item.get_minimized_id()
        if item_name in self._data['patron']['tab']:
            # This item has already been ordered. Apply saturation factor
            return self._saturation_factor_formula(self._data['patron']['tab'][item_name],
                                                   orderable_item.get_static_value('orderable')[
                                                       'saturation_speed'] * user.get(
                                                       'attr.station.tavern.saturation_factor', **kwargs))
        else:
            # Not ordered this yet. Factor = 1
            return 1

    def calculate_total_saturation_factor(self, user: User, **kwargs) -> float:
        """
        Calculates the cumulative saturation experienced from ALL items consumed so far.
        :param user:    The executing user.
        :return:        The total saturation factor value taking into account all parameters.
        """
        return self._saturation_factor_formula(sum(self._data['patron']['tab']),
                                               Patron.BASE_THIRST_DECAY * user.get(
                                                   'attr.station.tavern.thirst_decay_factor',
                                                   default=1, **kwargs))

    def generate_wait_time(self, user: User, **kwargs) -> timedelta:
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
        wait_in_s = random_normal(min=Patron.MIN_BASE_WAIT_TIME, max=Patron.MAX_BASE_WAIT_TIME)
        # Calculate influence of personality on the patron as a factor
        personality_influence = (((self._data['personality']['agreeableness'] * 0.29) +
                                  (self._data['personality']['conscientiousness'] * 0.35) +
                                  (self._data['personality']['neuroticism'] * -0.30) +
                                  ((self._data['personality']['extraversion'] - 1) * len(
                                      user.get('data.tavern.queue', **kwargs)) * 0.02)) *
                                 user.get('attr.station.tavern.personality_flex', default=1, **kwargs)) + 1
        wait_in_s *= personality_influence
        return timedelta(seconds=wait_in_s)

    def generate_wish_list(self, user, prices):
        """
        Shorthand Subroutine for the `decision_step`. In there, a wish-list is generated that reviews a user's price
        list and assigns a generated value for `desire` and `demand`.
        :param user:        a user.
        :param prices:      the user's price list to use for the wish list
        :return:            A list of `dict` objects ordered by their `desire` value, containing generated `desire`
                            and `demand` values as well as the its name `item`.
        """
        wish_list = []
        for item in [Item.from_id(f'item.{it_id}') for it_id in prices]:
            saturation = self.calculate_individual_saturation_factor(item, user)
            fair_price = item.determine_fair_price(user)
            personality_adjust = 1 + item.personality_adjust(self._data['personality']) * user.get(
                'attr.station.tavern.personality_flex', default=1, **kwargs)
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

        return sorted(wish_list, key=lambda d: d['desire'])

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
                'attr.station.tavern.personality_flex', default=1, **kwargs)
        if current_price < fair_price:
            denominator = 3 - math.cos(TWO_PI * (current_price - fair_price) / fair_price)
        elif current_price > fair_price:
            denominator = 1 + math.cos(TWO_PI / math.pow(ROOT_TWO, fair_price / (current_price - fair_price)))
        else:
            # Current price is fair price exactly ==> 2 (so that denominator/4 = 0.5)
            denominator = 2
        base_value = denominator / (4 * saturation_factor)

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
        orderable_data = orderable_item.get_static_value('orderable')
        personality_adjust = kwargs['personality_adjust'] if 'personality_adjust' in kwargs else \
            1 + orderable_item.personality_adjust(self._data['personality']) * user.get(
                'attr.station.tavern.personality_flex', default=1, **kwargs)
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
                                     * user.get('attr.station.tavern.personality_flex', default=1, **kwargs)) + 1
        else:
            personality_influence = ((self._data['personality']['neuroticism'] * .08) +
                                     (self._data['personality']['extraversion'] * .02) +
                                     (self._data['personality']['openness'] * -.12)
                                     (self._data['personality']['conscientiousness'] * -.10)
                                     * user.get('attr.station.tavern.personality_flex', default=1, **kwargs)) + 1

        saturation_factor = kwargs['saturation_factor'] if 'saturation_factor' in kwargs else \
            self.calculate_total_saturation_factor(user)

        base_thirst = random_normal(min=Patron.MIN_BASE_THIRST, max=Patron.MAX_BASE_THIRST)
        return base_thirst * personality_influence * user.get('attr.station.tavern.thirst_multiplier',
                                                              default=1, **kwargs) / saturation_factor

    # Markup Generation

    def render_current_infos(self) -> str:
        """
        :return:    The content for a `gb-info-container` element representing this patron's current infos, including
                    buttons for all available actions as HTML.
        """
        result = ""
        # Do I have an order? Show that
        if 'order' in self._data['patron'] and self._data['patron']['order']:
            for item_id, amount in self._data['patron']['order'].items():
                result += render_object('render.item_amount',
                                        data={'item_id': css_unfriendly(item_id), 'amount': amount,
                                              'class': 'gb-info gb-info-highlight'})

        # Render current actions
        for action in self._data['patron']['available_actions']:
            result += render_object('render.person_interaction',
                                    data={'action': action, 'patron_min_id': self.get_minimized_id()})

        return result


@Patron.subtype_data_generator()
def generate_patron_data(source_data: dict, gen: Generator) -> dict:
    """
    Called to generate patron subtype data for a given patron.
    :param source_data: JSON data of a person (that is not yet of the given subtype)
    :param gen:         Generator to use for generation purposes
    :return:            Generated JSON data for the requested subtype, `patron`
    """
    data = dict()

    # Generate a `Person` handle with the source data
    person = Person(source_data)

    data['state'] = 'entering'
    data['ui_order'] = 1
    data['budget'] = int(gen.rand_normal(median=Patron.INIT_BUDGET_MEDIAN, deviation=Patron.INIT_BUDGET_MEDIAN / 3))
    data['thirst'] = gen.rand_normal(median=Patron.INIT_THIRST_MEDIAN, deviation=Patron.INIT_THIRST_MEDIAN / 6)
    data['available_actions'] = []
    data['feedback'] = ""
    data['tab'] = list()

    return data


@PeriodicEvent.periodic_type("patron_update", default_interval=200)
def process_patron_update(user: User, event: PeriodicEvent):
    """
    Called whenever the patron's `timeout` happens.
    :param user:    Target user.
    :param event:   Handling event.
    """
    # Get target patron
    patron_id = event.get_event_data("patron_id")
    # Load Patron from user data
    patron = Patron(user.get(f"data.station.tavern.patrons.{patron_id}"))

    # Flush all available interactions before processing (& adding new interactions)
    patron.flush_available_interactions()

    # Invoke the patron's on_timeout
    patron.on_timeout(user, event)


@PlayerRequest.type('patron_interact', is_buffered=True)
def patron_interact(user: User, request_object: dict, **kwargs):
    """
    Handles a game request from the user to perform one interaction with a patron.
    :param request_object:  Contains `action` that describes the type of interaction requested as well as the
                            patron's ID in `target_patron`
    :param user:            Target user
    """
    response = GameResponse()

    # Sanity Check
    if 'action' not in request_object or 'target_patron' not in request_object:
        raise Exception(f"Malformatted request: {request_object}")

    action_type = request_object['action']
    patron_id = request_object['target_patron']
    patrons = user.get(f"data.station.tavern.patrons")
    if patron_id not in patrons:
        response.add_fail_msg(f"Patron with requested ID is not in user's tavern data: {patron_id}")
        return response

    # Generate patron straight from user data.
    patron = Patron(patrons[patron_id])

    # Forward the interaction call to the patron and log results in response object.
    patron.process_interaction(user, action_type, response)

    return response
