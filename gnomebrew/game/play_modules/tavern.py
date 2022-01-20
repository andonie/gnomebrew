"""
Tavern interface compatibility and patron control flow implementations are managed in this module.
"""
from math import floor, ceil
from numbers import Number

from flask import url_for

from gnomebrew.game.objects import PlayerRequest, DataObject, Generator, Environment, Patron, Person, Effect
from gnomebrew.game.objects.game_object import render_object
from gnomebrew.game.objects.item import Item
from gnomebrew.game.selection import selection_id
from gnomebrew.game.testing import application_test
from gnomebrew.game.user import User, id_update_listener
from gnomebrew.game.objects.event import Event, PeriodicEvent
from gnomebrew.game.gnomebrew_io import GameResponse

# Basic Patron Interactions
from gnomebrew.game.util import global_jinja_fun, css_unfriendly, css_friendly, shorten_num, shorten_cents


@Patron.action_type('serve')
def serve_patron(user: User, patron: Patron, response: GameResponse):
    """
    Serves the patron (unless the user has insufficient inventory).
    """
    # Fetch user storage and tavern prices
    user_storage = user.get("storage._allitems")
    tavern_prices = user.get("data.station.tavern.prices")

    # What did the patron order?
    patron_order = patron.get_order_data()

    # Make sure the UI feedback will be displayed on this patron's infos field
    response.set_ui_target("#station-tavern-infos")

    order_total = 0

    # Ensure we can afford all changes and calculate order total
    for item_id, amount in patron_order.items():
        # Update the order total before changing item_id formatting away from CSS-friendly
        order_total += amount * tavern_prices[item_id]
        # Clean CSS-friendly (and MongoDB friendly) item_id
        item_id = css_unfriendly(item_id)
        if item_id not in user_storage:
            response.add_fail_msg(f"You don't have {item_id} in storage.")
            return response
        if user_storage[item_id] < amount:
            response.add_fail_msg(f"Not enough to fill order: {item_id}")
            response.player_info(user, f"You need more to serve.", f"{amount - user_storage[item_id]}", item_id, "missing")

    if response.has_failed():
        return response

    # All checks are passed. Serve the patron!

    # Remove all items with an inverted delta_inventory effect:
    delta_inventory_data = {css_friendly(item_id): -amount for item_id, amount in patron_order.items()}
    delta_inventory_data['item-gold'] = order_total
    response.player_info(user, f"You made {shorten_cents(order_total)}", f"+{shorten_cents(order_total)}", "item.gold")
    Effect({
        'effect_type': 'delta_inventory',
        'delta': delta_inventory_data
    }).execute_on(user)

    # Add the order to the patron's tab and reduce their available budget by the `order_total`, remove order data
    patron.add_to_tab(patron_order)
    patron.reduce_budget(order_total)
    patron.set_order({})

    # Update available player interactions, new state, and confirm update (which updates the changed patron data to DB)
    patron.add_available_interaction("gift")
    patron.set_feedback_text(Generator.fresh().choose(Patron.RANDOM_TALK))
    patron.confirm_update(user, "drinking")


@Patron.timeout_strategy(available_states=['entering'])
def just_enter_and_get_thinking(user: User, patron: Patron):
    """Handling the initial `entering` state by making this patron think"""
    print(f"ENTER TAVERN: {patron.get_name()}")

    # Check how full the tavern is and adapt my motivation/energy according to my extraversion

    # Provide valid context actions for user after entering.
    patron.add_available_interaction('gift')
    patron.set_feedback_text(Generator.fresh().choose(Patron.RANDOM_TALK))
    patron.confirm_update(user, 'thinking')


@Patron.timeout_strategy(available_states=['thinking'], weight=500)
def patron_order_decision_flow(user: User, patron: Patron):
    """
    Decision flow for one patron
    :param user:
    :param patron:
    :return:
    """
    if True:
        patron.set_order({
            'item-simple_beer': 2
        })
        # Ensure the "serve" interaction is allowed
        patron.set_feedback_text(Generator.fresh().choose(Patron.RANDOM_TALK))
        patron.add_available_interaction("serve")
        patron.confirm_update(user, "ordering")

    prices = user.get('data.station.tavern.prices')
    # I'm noting down my orders here
    order_dict = dict()

    # I'm managing my order preferences here
    # Take a look at the menu. Assign a perceived value to each item and create a wish-list
    # sorted by my desire to buy
    wish_list = patron.generate_wish_list(user, prices)

    # I am motivated to order. Let's go:
    # Go through my wish list in descending order of preference and start ordering

    total_saturation = patron.calculate_total_saturation_factor(user=user)
    thirst = patron.generate_thirst(user, saturation_factor=total_saturation)

    budget_count = patron._data['patron']['budget']
    desire_threshold = Patron.AVG_DESIRE_THRESHOLD * user.get('attr.station.tavern.desire_threshold_factor', default=1)

    for wish in wish_list:
        item_name = wish['item'].get_minimized_id()

        # Check if minimum requirements for all four parameters are met:
        if budget_count > prices[item_name] and \
                thirst > 0 and \
                wish['demand'] >= 1 and \
                wish['desire'] > desire_threshold:
            orderable_data = wish['item'].get_static_value('orderable')
            # I want the most possible of this limited by:
            # a) Budget
            # b) Thirst
            # c) Demand
            amount = int(min(floor(budget_count / prices[item_name]),
                             ceil(thirst / orderable_data['thirst_reduction']),
                             wish['demand']))
            budget_count -= amount * prices[item_name]
            thirst -= amount * (
                    orderable_data['thirst_reduction'] * user.get('attr.station.tavern.thirst_reduction_mul',
                                                                  default=1))
            order_dict[item_name] = amount

    if not order_dict:
        # My order list is empty. I can't afford/don't want anything. Let's leave.
        patron.leave_tavern(user)
        return

    # I have finished my order list. Time to enqueue!
    patron.set_order(user, order_dict)


@Patron.timeout_strategy(available_states=['ordering'], weight=1)
def patron_not_served_in_time(user: User, patron: Patron):
    """
    Executes when this patron has not been served in time.
    """
    # I cancel my order. Empty order data and transition to thinking
    patron.set_order({})
    patron.confirm_update(user, 'thinking')


@PeriodicEvent.periodic_type("tavern_update", default_interval=Patron.TAVERN_UPDATE_INTERVAL)
def tavern_update(user: User, event: PeriodicEvent):
    """Overall tavern update logic. Reviews and adjusts tavern mechanics, adjusts patron flow, etc."""

    # Generator to use for all subsequent generation tasks
    tavern_environment = Environment.empty()  # TODO add actual environment from world location to influence generation
    gen = Generator(Generator.true_random_seed(), tavern_environment)

    # Determine how many patrons will walk into the bar within the next period
    next_period_patrons_num = 5  # TODO dynamically define this number

    # Add no more patrons than fit into our beloved tavern:
    next_period_patrons_num = min(next_period_patrons_num, user.get('attr.station.tavern.capacity') - len(
        user.get('data.station.tavern.patrons')))

    new_patrons = list()
    if next_period_patrons_num > 0:
        for _ in range(next_period_patrons_num):
            # Generate a base person and subsequently patron data with the generator's config
            person = gen.generate('Person')
            person.generate_subtype(Patron, gen)
            new_patrons.append(person)

    # Iterate the new patron list and process the patrons:
    for patron in [person.as_subtype(Patron) for person in new_patrons]:
        patron.initialize_for(user)


@global_jinja_fun
def generate_patron_list(user: User):
    """Convenience function for HTML templates generates current patron list to HTML ready for printout."""
    patron_list = sorted([Patron(p_data) for p_data in user.get(f"data.station.tavern.patrons").values()],
                         key=lambda patron: patron.get_ui_order())
    return patron_list


@selection_id('selection.tavern.selected_tab')
def process_alchemy_recipe_selection(game_id: str, user: User, set_value, **kwargs):
    if set_value:
        return user.update('data.station.tavern.selected_tab', set_value)
    else:
        # Read out the current selection.
        return user.get('data.station.tavern.selected_tab', **kwargs)


@application_test(name='Generate Patrons', context='Generation')
def generate_patrons(seq_size):
    """
    Generates `seq_size` (default=20) patrons and prints the results.
    """
    response = GameResponse()

    if seq_size is None or seq_size == '':
        seq_size = 20
    else:
        seq_size = int(seq_size)

    gen = Generator(Generator.true_random_seed(), Environment.empty())

    for _ in range(seq_size):
        person: Person = gen.generate("Person")
        person.generate_subtype(Patron)
        res = person.subtype_compatibility_check(Patron)
        if res.has_failed():
            print(f"FAIL:\n{res.get_fail_messages()}")

    return response


@Patron.on("patron_enter_tavern")
def handle_enter_tavern(patron: Patron, user: User):
    """React to `patron` entering the tavern of `user`"""
    # Send HTML of patron to all frontends.
    patron_html = render_object('render.patron', data=patron)
    user.frontend_update('ui', {
        'type': 'append_element',
        'selector': "#tavern-patron-list",
        'element': patron_html
    })


@Patron.on("patron_state_update")
def handle_state_update(patron: Patron, user: User):
    """React to the patron's state updating"""
    user.frontend_update('ui', {
        'type': 'set_element_content',
        'selector': f'.{css_friendly(patron.get_id())}-infos',
        'content': patron.render_current_infos()
    })
    user.frontend_update('ui', {
        'type': 'set_element_content',
        'selector': f'.{css_friendly(patron.get_id())}-feedback',
        'content': patron.get_feedback_text()
    })

    user.frontend_update('update', {
        'update_type': 'change_attributes',
        'attribute_change_data': [{
            'selector': f".{css_friendly(patron.get_id())}-state",
            'attr': 'src',
            'value': url_for("get_icon", game_id=patron.get_state_icon_id())
        }]
    })
