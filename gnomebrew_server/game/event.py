"""
This module manages events and event dispatching
"""
import time
from typing import Callable
from traceback import print_tb

from gnomebrew_server import mongo
import datetime

from gnomebrew_server.game.static_data import Item
from gnomebrew_server.game.user import User, load_user
import threading


_EVENT_FUNCTIONS = dict()
_SLEEP_TIME = .5


class EventThread(object):
    """
    Wraps the background thread that dispatches due events.
    """

    def __init__(self, mongo_instance):
        """
        Initialize the Event Thread.
        :param mongo_instance:  PyMongo instance that is used to retrieve event data.
        """
        self.mongo = mongo_instance

        self.thread = threading.Thread(target=self.run, args=())
        self.thread.daemon = True
        self.thread.start()

    def run(self):
        while True:
            # Find all events that are due
            start_time = datetime.datetime.utcnow()
            query = {'due_time': {'$lt': start_time}}
            remove_ids = list()

            for event_data in self.mongo.db.events.find(query):
                # Do something
                try:
                    Event(mongo_data=event_data).execute()
                except Exception as err:
                    # An error occured managing the event.
                    # In this case, just log the traceback but still remove the event.
                    print('--------------\nException in Event Thread:')
                    print_tb(err.__traceback__)
                    print('--------------')

                remove_ids.append(event_data['_id'])

            self.mongo.db.events.remove({'_id': {'$in': remove_ids}})

            end_time = datetime.datetime.utcnow()
            #print(f'Total time: {(end_time - start_time).total_seconds() }')
            sleep_time = _SLEEP_TIME - (end_time - start_time).total_seconds()
            if sleep_time > 0:
                try:
                    time.sleep(sleep_time)
                except KeyboardInterrupt:
                    print('Shutting down event thread')
                    exit()


class Event(object):

    def __init__(self, mongo_data: dict):
        """
        Intialize an event based on the data from MongoDB
        :param mongo_data:  mongoDB data to initialize this object with
        """
        self._data = mongo_data

    """
    Wrapper Class for Events
    Used for creating and enqueuing events as well as for executing them.
    """

    def execute(self):
        """
        Executes the event's logic.
        :return:
        """
        # Get user object that represents the target
        user: User = load_user(self._data['target'])

        # Clean up the escaped dots (.)
        for effect_type in self._data['effect']:
            if type(self._data['effect'][effect_type]) is dict:
                for key, _ in self._data['effect'][effect_type].copy().items():
                    self._data['effect'][effect_type][key.replace('-', '.')] = self._data['effect'][effect_type].pop(key)

        global _EVENT_FUNCTIONS
        for effect in self._data['effect']:
            # Call the registered handling function for the effect key
            assert _EVENT_FUNCTIONS[effect]
            _EVENT_FUNCTIONS[effect](user=user, effect_data=self._data['effect'][effect])

    def get_target_username(self):
        """
        Returns the target user
        :return: the username of the
        """
        pass

    def get_due_time(self) -> datetime.datetime:
        """
        Returns the datetime that represents when this event is due.
        :return:
        """
        pass

    def set_due_time(self, due_time: datetime.datetime):
        self._data['due_time'] = due_time

    @staticmethod
    def generate_event_from_recipe_data(target: str, result: dict,
                                        due_time: datetime.datetime, slots: int, station: str, recipe_id: str):
        """
        Generates an event that modifies user inventory.
        :param station:
        :param slots:
        :param due_time:
        :param target:          the `username` of the target user.
        :param result:
        :return:
        """
        data = dict()
        data['target'] = target
        data['type'] = 'recipe'
        data['effect'] = dict()
        data['effect'].update(result)
        for effect_type in data['effect']:
            if type(data['effect'][effect_type]) is dict:
                # Change dots (.) to dashes (-) because BSON/Mongo gets sad :(
                for key, _ in data['effect'][effect_type].copy().items():
                    # Take an iteration copy to avoid concurrent modification horrors
                    data['effect'][effect_type][key.replace('.', '-')] = data['effect'][effect_type].pop(key)
        data['due_time'] = due_time
        data['slots'] = slots
        data['station'] = station
        data['recipe_id'] = recipe_id
        return Event(data)

    @staticmethod
    def register(effect_callable: Callable):
        """
        Registers an event effect handling function.
        :param effect_id:       The effect ID stored in the event queue
        :param effect_callable: A function to be executed when the event is triggered. Takes the kwargs:
                                * `user: User` the targetted user object
                                * `effect_data`: The stored data under the key `effect_id` in the event queue
        """
        global _EVENT_FUNCTIONS
        assert effect_callable.__name__ not in _EVENT_FUNCTIONS
        _EVENT_FUNCTIONS[effect_callable.__name__] = effect_callable

    def enqueue(self):
        """
        Registers this event with the event queue. This ensures that - once the event's due time happened - the event will
        be executed.
        """
        self._data['since'] = datetime.datetime.utcnow()
        mongo.db.events.insert_one(self._data)


# Some Builtin Event Handling

@Event.register
def delta_inventory(user: User, effect_data: dict):
    """
    Event execution for a change in inventory data.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[material_id] = delta`
    """
    user_inventory = user.get('data.storage.content')
    max_capacity = user.get('attr.storage.max_capacity')
    inventory_update = dict()
    for material in effect_data:
        if material not in user_inventory:
            inventory_update['storage.content.' + material] = min(max_capacity, effect_data[material])
            # The new item might be orderable. In that case --> Add it to the price list
            item_object = Item.from_id('item.' + material)
            if item_object.is_orderable():
                inventory_update['tavern.prices.' + material] = item_object.get_value('base_value')
        elif material == 'gold':
            # Gold is an exception and can grow to infinity always:
            inventory_update['storage.content.' + material] = user_inventory[material] + effect_data[material]
        else:
            inventory_update['storage.content.' + material] = min(max_capacity, user_inventory[material] + effect_data[material])
    user.update_game_data('data', inventory_update, is_bulk=True)


@Event.register
def push_data(user: User, effect_data: dict):
    """
    Event execution for an arbitrary push (list append) of data.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[data-id] = delta
    """
    for data_path in effect_data:
        data = user.get(data_path)
        new_data = effect_data[data_path]
        if type(new_data) is not list:
            # Wrap the update in a list to ensure multiple push-data handling is possible
            new_data = [new_data]

        # Ensure none of the items to push are already in the data
        assert not any(x in data for x in new_data)
        for item in new_data:
            data.append(item)
            # Update each item individually to ensure every frontend_id_resolver
            # Can fetch the list tail and knows this is the pushed change
            user.update_game_data(data_path, data)


@Event.register
def ui_update(user: User, effect_data:dict):
    """
    Event execution for a user ui update
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `effect_data[data-id] = delta
    """
    user.frontend_update('ui', effect_data)

@Event.register
def add_station(user: User, effect_data:dict):
    """
    Fired when a new station is to be added to a user's game data.
    :param user:        a user
    :param effect_data: effect data dict formatted as `effect_data['id'] = station_id`
    """
    pass
