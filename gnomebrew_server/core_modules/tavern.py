"""
This module manages the tavern and patron logic of the game.
"""
import operator
import threading
import datetime
import time
from functools import reduce

from flask import render_template

from gnomebrew_server.game.static_data import Item, patron_order_list
from gnomebrew_server.game.user import User, load_user, frontend_id_resolver, user_assertion, html_generator
from gnomebrew_server.play import request_handler
from gnomebrew_server.game.event import Event
from gnomebrew_server.game.util import random_normal, random_uniform
from gnomebrew_server.play import request_handler
from gnomebrew_server.game.gnomebrew_io import GameResponse
from gnomebrew_server import mongo

from random import choice
from datetime import datetime, timedelta
from uuid import uuid4

_SLEEP_TIME = 60 * 15
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
        'first': ['Lydan', 'Syrin', 'Ptorik', 'Joz', 'Varog', 'Gethrod', 'Hezra', 'Feron', 'Ophni', 'Colborn', 'Fintis',
                  'Gatlin', 'Jinto', 'Hagalbar', 'Krinn', 'Lenox', 'Revvyn', 'Hodus', 'Dimian', 'Paskel', 'Kontas',
                  'Weston', 'Azamarr', 'Jather', 'Tekren', 'Jareth', 'Adon', 'Zaden', 'Eune', 'Graff', 'Tez', 'Jessop',
                  'Gunnar', 'Pike', 'Domnhar', 'Baske', 'Jerrick', 'Mavrek', 'Riordan', 'Wulfe', 'Straus', 'Tyvrik',
                  'Henndar', 'Favroe', 'Whit', 'Jaris', 'Renham', 'Kagran', 'Lassrin', 'Vadim', 'Arlo', 'Quintis',
                  'Vale', 'Caelan', 'Yorjan', 'Khron', 'Ishmael', 'Jakrin', 'Fangar', 'Roux', 'Baxar', 'Hawke',
                  'Gatlen', 'Michael',
                  'Barak', 'Nazim', 'Kadric', 'Paquin', 'Kent', 'Moki', 'Rankar', 'Lothe', 'Ryven', 'Clawsen', 'Pakker',
                  'Embre', 'Cassian', 'Verssek', 'Dagfinn', 'Ebraheim', 'Nesso', 'Eldermar', 'Rivik', 'Rourke',
                  'Barton',
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
        'last': ['Atwater', 'Agassi', 'Apatow', 'Akagawa', 'Averescu', 'Arrington', 'Agrippa', 'Aiken', 'Albertson',
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
        self._data['budget'] *= user.get('attr.tavern.budget_multiplicator', default=1)
        uuid = str(uuid4())
        self._data['id'] = uuid
        self._data['past_orders'] = []
        return uuid

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

    def order_fitness(self, user: User,  order: dict):
        """
        Assigns a fitness value between 0 (absolutely don't want this) to 1 (I definitely want this) to an order.
        :param order:   An order
        :param user:    a user
        :return:        An assigned order fitness value
        """
        prices = user.get('data.tavern.prices')
        # Can I afford the order?
        order_total = reduce(operator.add, map(lambda item: order[item]*prices[item], order))
        if self._data['budget'] < order_total:
            return 0




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
        # TODO: Implement a nice logic
        # For now, bare minimum

        prices = user.get('data.tavern.prices')

        # Can I afford something?
        if prices['simple_beer'] > self._data['budget']:
            # I'm broke. Let's leave.
            self.leave_tavern(user)
            return

        # Do I want beer?
        if random_uniform() > len(self._data['past_orders']) * .4:
            # I want a beer. Enter Queue
            self.enter_queue(user, {
                'id': self._data['id'],
                'order': [{
                    'item': 'simple_beer',
                    'amount': 1
                }]
            })
        else:
            self.leave_tavern(user)

    def enter_queue(self, user: User, order_data: dict):
        """
        Enrolls this patron in the tavern queue, if possible
        :param order_data:      Data of the order to be added.
        :param user:    a user
        """
        queue_data = user.get('data.tavern.queue')

        # Add my order to the queue
        queue_data.append(order_data)
        user.update_game_data('data.tavern.queue', queue_data)

        # I will get impatient if my order is not handled within a timeframe.
        # -> Create timed event to handle this
        # Calculate the time at which the patron is impatient
        due_time = datetime.utcnow() + timedelta(
            seconds=random_normal(min=120, max=user.get('attr.tavern.patron_patience', default=1200)))
        _generate_patron_impatient_event(target=user.get_id(), patron=self, due_time=due_time).enqueue()

    def leave_queue(self, user: User):
        """
        Removes the patron from the user's tavern queue.
        """
        queue = user.get('data.tavern.queue')

        # Filter out any and all orders with the patron's id
        user.update_game_data('data.tavern.queue', list(filter(lambda order: order['id'] != self._data['id'], queue)))

        self.schedule_next_decision(user)

    def leave_tavern(self, user: User):
        """
        Leaves the tavern forever.
        :param user:    a user
        """
        # Remove Patron from Tavern Data
        user.update_game_data('data.tavern.patrons.' + self._data['id'], {}, command='$unset')

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



    @staticmethod
    def generate_random():
        """
        Generates a random Patron
        :return:    A patron with randomly distributed attributes
        """
        data = dict()
        # Generate a name
        data['name'] = choice(Patron.names['first']) + ' ' + choice(Patron.names['last'])
        # Budget is standardized independent of upgrade status of user. Budget will be modified upon patron entry
        data['budget'] = random_normal(min=1, max=10)
        # TODO more cool patron things

        return Patron(data)

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
            sleep_time = _SLEEP_TIME - (end_time - start_time).total_seconds()
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
    patron_entry_times = random_uniform(min=0, max=_SLEEP_TIME, size=num_patrons)
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
    user.update_game_data('data.tavern.patrons.' + patron_uuid, patron.get_data())

    # Patron enters --> First Decision
    patron.decision_step(user=user)


@Event.register
def patron_impatient(user: User, effect_data: dict):
    """
    Handles a `patron_impatient` event.
    :param user:        Target User
    :param effect_data: Effect Data
    """
    # Get the targetted patron
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

    user.update_game_data('data.tavern.queue', queue)

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
    Patron(tavern_data['patrons'][next_order['id']]).schedule_next_decision(user)

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

    user.update_game_data('data', update_data, is_bulk=True)

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

    item, price = request_object['item'], float(request_object['price'])
    old_price = prices[item]
    if item not in prices:
        response.add_fail_msg('ERROR - Tell Mike about this.')
        return response

    if price < 0:
        response.add_fail_msg('You cannot charge negative prices.')
        return response

    user.update_game_data('data.tavern.prices.' + item, price)

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
