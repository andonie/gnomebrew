"""
This module manages events and event dispatching
"""
import time
import traceback
import uuid
from typing import Callable

from gnomebrew import mongo
from gnomebrew.game import boot_routine
import datetime

from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.game_object import StaticGameObject, GameObject
from gnomebrew.game.user import User, load_user, html_generator
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
                event = Event(mongo_data=event_data)
                try:
                    event.execute()
                except Exception as err:
                    # An error occured managing the event.
                    # In this case, just log the traceback but still remove the event.
                    print('--------------\nException in Event Thread:')
                    traceback.print_exc()
                    print('--------------')

                if event.is_remove_on_trigger():
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


class Event(GameObject):

    def __init__(self, mongo_data: dict):
        """
        Intialize an event based on the data from MongoDB
        :param mongo_data:  mongoDB data to initialize this object with
        """
        GameObject.__init__(self, mongo_data)
        if 'event_id' not in self._data:
            self._data['event_id'] = str(uuid.uuid4())

    """
    Wrapper Class for Events
    Used for creating and enqueuing events as well as for executing them.
    """

    def execute(self):
        """
        Executes the event's logic.
        :return:
        """
        # Ensure all data is 'dirty' (dots in dict-keys) up
        self.dirty_keys()
        # Get user object that represents the target
        user: User = load_user(self._data['target'])

        if not user:
            raise Exception(f"Invalid username given: {self._data['target']}")

        for effect_data in self._data['effect']:
            # Call the registered handling function for the effect key
            Effect(effect_data).execute_on(user)

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

    def is_remove_on_trigger(self) -> bool:
        """
        :return: `True` if this event is removed after it triggers (default case). Otherwise `False`.
        """
        return not self._data['locked'] if 'locked' in self._data else True

    def set_due_time(self, due_time: datetime.datetime):
        self._data['due_time'] = due_time

    @staticmethod
    def generate_event_from_recipe_data(target: str, result: list,
                                        due_time: datetime.datetime, slots: int, station: str, recipe_id: str,
                                        total_cost: dict):
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
        data['effect'] = result
        # for effect_type in data['effect']:
        #     if type(data['effect'][effect_type]) is dict:
        #         # Change dots (.) to dashes (-) because BSON/Mongo gets sad :(
        #         for key, _ in data['effect'][effect_type].copy().items():
        #             # Take an iteration copy to avoid concurrent modification horrors
        #             data['effect'][effect_type][key.replace('.', '-')] = data['effect'][effect_type].pop(key)
        data['due_time'] = due_time
        data['slots'] = slots
        data['station'] = station
        data['recipe_id'] = recipe_id
        data['cost'] = total_cost
        return Event(data)

    def enqueue(self):
        """
        Registers this event with the event queue. This ensures that - once the event's due time happened - the event will
        be executed.
        """
        self._data['since'] = datetime.datetime.utcnow()
        # Clean Up object data
        self.clean_keys()
        mongo.db.events.insert_one(self._data)



@boot_routine
def start_event_thread():
    EventThread(mongo_instance=mongo)


@html_generator(base_id='html.effect.', is_generic=True)
def render_effect_info(game_id: str, user: User, **kwargs):
    pass
