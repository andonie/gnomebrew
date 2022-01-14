"""
This module manages events and event dispatching
"""
import time
import traceback
from typing import Callable

from gnomebrew import mongo
from gnomebrew.game.util import generate_uuid
from gnomebrew.logging import log, log_exception
from gnomebrew.game import boot_routine
import datetime

from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.game_object import StaticGameObject, GameObject
from gnomebrew.game.user import User, load_user, html_generator
import threading

from gnomebrew.logging import log, log_exception

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

    # Interval in minutes
    LOG_INTERVAL = 30

    def run(self):
        log('gb_core', '<%Event Thread starting%>')
        last_log = datetime.datetime.utcnow()
        event_successes = event_errors = 0
        while True:
            # START measuring exeuction time
            start_time = datetime.datetime.utcnow()

            # Find all events that are due
            query = {'due_time': {'$lt': start_time}}
            due_event_buffer = list(self.mongo.db.events.find(query))
            remove_ids = [event['_id'] for event in due_event_buffer]
            self.mongo.db.events.remove({'_id': {'$in': remove_ids}})
            for event_data in due_event_buffer:
                # Do something
                event = Event(mongo_data=event_data)
                try:
                    event.execute()
                    event_successes = event_successes + 1
                except Exception as err:
                    # An error occured managing the event.
                    # In this case, just log the traceback but still remove the event.
                    log_exception('event', f"{err}\nThis happened during the exeuction of this event data:\n{event_data}", f"usr:{event.get_target_username()}")
                    event_errors = event_errors + 1

                if event.is_remove_on_trigger():
                    remove_ids.append(event_data['_id'])

            # END measuring exeuction time and sleep if necessary
            end_time = datetime.datetime.utcnow()

            # If the `LOG_INTERVAL` has passed, log an update to the console
            if (end_time - last_log).total_seconds() / 60 > EventThread.LOG_INTERVAL:
                log("event", f"Dispatched <%{event_successes+event_errors:>5}%> timed events in the last {EventThread.LOG_INTERVAL} minutes (<%{(event_successes / event_successes+event_errors) * 100 if event_successes + event_errors > 0 else '-':>5}%>% success)")
                last_log = end_time
                event_successes = event_errors = 0
            sleep_time = _SLEEP_TIME - (end_time - start_time).total_seconds()
            if sleep_time > 0:
                try:
                    time.sleep(sleep_time)
                except KeyboardInterrupt:
                    log('event', 'Keyboard Interrupt detected. Event thread stopped.')
                    exit()


class Event(GameObject):

    def __init__(self, mongo_data: dict):
        """
        Intialize an event based on the data from MongoDB
        :param mongo_data:  mongoDB data to initialize this object with
        """
        GameObject.__init__(self, mongo_data)
        if 'event_id' not in self._data:
            self._data['event_id'] = generate_uuid()

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

        # Update Statistics
        user.update('stat', {
            f"event.{self._data['event_type']}_total": 1
        }, is_bulk=True)

    def get_target_username(self):
        """
        Returns the target user
        :return: the username of the
        """
        return self._data['target']

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

    def enqueue(self):
        """
        Registers this event with the event queue. This ensures that - once the event's due time happened - the event will
        be executed.
        """
        self._data['since'] = datetime.datetime.utcnow()
        # Clean Up object data
        self.clean_keys()
        mongo.db.events.insert_one(self._data)

    def get_type(self) -> str:
        return self._data['event_type']


@boot_routine
def start_event_thread():
    EventThread(mongo_instance=mongo)


@html_generator(base_id='html.effect.', is_generic=True)
def render_effect_info(game_id: str, user: User, **kwargs):
    pass
