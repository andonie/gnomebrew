"""
This module manages events and event dispatching. Events cover all processes that are executed with some *time delay*
(e.g. recipe execution time or time delay between patron actions).
"""
import time
from typing import Callable

from gnomebrew import mongo
from gnomebrew.game.util import generate_uuid, is_uuid
from gnomebrew.game import boot_routine
import datetime

from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.game_object import GameObject, DataObject
from gnomebrew.game.user import User, load_user, html_generator, get_resolver
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
            remove_ids = list()
            for event_data in due_event_buffer:
                # Do something
                event = Event(mongo_data=event_data)
                try:
                    event.execute()
                    event_successes = event_successes + 1
                except Exception as err:
                    # An error occured managing the event.
                    # In this case, just log the traceback but still remove the event.
                    log_exception('event', f"{err}\nThis happened during the exeuction of this event data:\n{event}", f"usr:{event.get_target_username()}")
                    event_errors = event_errors + 1
                    # Remove the trouble-maker Event from the list
                    remove_ids.append(event_data['_id'])

                if event.is_remove_on_trigger():
                    remove_ids.append(event_data['_id'])

            # Now all pending events have been executed and the IDs to remove have been determined.
            # Remove all IDs now.
            self.mongo.db.events.remove({'_id': {'$in': remove_ids}})

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


class Event(DataObject):
    """
    Wrapper Class for Events.
    Used for creating and enqueuing events as well as for executing them.
    """

    def __init__(self, mongo_data: dict):
        """
        Intialize an event based on the data from MongoDB
        :param mongo_data:  mongoDB data to initialize this object with
        """
        DataObject.__init__(self, mongo_data)
        if 'event_id' not in self._data:
            self._data['event_id'] = generate_uuid()
        if 'event_data' not in self._data:
            self._data['event_data'] = dict()

    def get_event_id(self) -> str:
        """
        :return:    Properly formatted `event_id` of this event.
        """
        # Internally, `event_id` is stored to be optimally usable with index. Change to Game ID:
        return f"event.{self._data['event_id']}"

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
            raise Exception(f"Invalid username target in event data: {self._data['target']}")

        for effect_data in self._data['effect']:
            # Call the registered handling function for the effect key
            Effect(effect_data).execute_on(user)

        # Update Event Statistics
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

    def get_target(self) -> User:
        return load_user(self._data['target'])

    def update_db(self, upsert=False):
        """
        Updates the DB collection holding events with this event\'s CURRENT `_data` dictionary via a '$set' call.
        As of now, no '$unset' call is made to account for removed parameters.
        :param upsert:  If `True`, will use MongoDB *upsert* flag. Default is `False`
        """
        # Update DB
        mongo.db.events.update_one({
            'event_id': self._data['event_id']
        }, {
            '$set': self._data
        }, upsert=upsert)

    def set_event_data(self, param_name, value):
        """
        Write-Access to event data feature. Writes event data in this event. This does *not* update the DB automatically.
        :param param_name:  Param to write
        :param value:       Param Value
        """
        self._data['event_data'][param_name] = value

    def get_event_data(self, param_name, **kwargs):
        """
        Read-Access to event data feature. Reads event
        :param param_name: Param to read
        :return:           Value read
        """
        if param_name not in self._data['event_data']:
            if 'default' in kwargs:
                return kwargs['default']
            else:
                raise Exception(f"Unknown event data parameter (and no default): {param_name}")
        return self._data['event_data'][param_name]


class PeriodicEvent(Event):

    periodic_types = dict()

    @classmethod
    def periodic_type(cls, typename: str, default_interval: int = 1200):
        """
        Annotation function. Marks a function as the execution logic of a `RepeatEvent` type.
        :param typename:            Typename to register
        :param default_interval:    Default interval (in s) for execution. Default is 1200 s = 20 min
        """

        if typename in cls.periodic_types:
            raise Exception(f"Repeat Type {typename} already defined.")

        def wrapper(fun: Callable):
            data = dict()
            data['fun'] = fun
            data['default_interval'] = default_interval
            cls.periodic_types[typename] = data
            return fun

        return wrapper

    @classmethod
    def generate_instance_for(cls, user: User, periodic_type: str) -> 'PeriodicEvent':
        """
        Generates a fresh instance of a repeat event ready to enqueue.
        :param user:    target user
        :return:        a fresh (not yet enqueued) instance of a `RepeatEvent` for `user`
        """
        if periodic_type not in cls.periodic_types:
            raise Exception(f"Unknown repeat type: {periodic_type}")

        data = dict()
        data['target'] = user.get_id()
        data['event_id'] = generate_uuid()
        data['event_type'] = 'periodic'
        data['periodic_type'] = periodic_type
        data['effect'] = [{
            'effect_type': 'periodic_event_exec',
            'event_id': data['event_id']
        }]
        data['locked'] = True # Lock this event to ensure it won't be autoremoved on execution
        data['interval'] = cls.periodic_types[periodic_type]['default_interval']
        return PeriodicEvent(data)


    def __init__(self, data: dict):
        Event.__init__(self, data)

    def set_interval(self, time_in_s: int):
        """
        Sets the interval in which this event is to be executed. This event will execute every `time_in_s` seconds until
        it is cancelled.
        :param time_in_s:   The new interval.
        """
        self._data['interval'] = time_in_s

    def get_interval(self):
        return self._data['interval']

    def cancel_self(self):
        """
        Cancels this event from the event collection, making it no longer trigger after the latest execution finished
        """
        self._data['locked'] = False

    def reschedule_self(self):
        """Updates this events DB data and ensures next execution happens in `interval` seconds from now"""
        delay_in_s = self._data['interval']
        self.set_next_execution_in(datetime.timedelta(seconds=delay_in_s))

    def set_next_execution_in(self, timedelta: datetime.timedelta):
        """
        Updates this event's execution time and updates all event data in DB.
        :param timedelta:   Wait Time for next execution of this periodic event from now.
        """
        self._data['due_time'] = datetime.datetime.utcnow() + timedelta
        self.update_db(upsert=True)

    def get_periodic_type(self) -> str:
        return self._data['periodic_type']


# Effects to make repeat events accessible and useful from gameplay flow

@Effect.type('periodic_event_exec', ('periodic_type', str))
def repeat_event_exec(user: User, effect_data: dict, **kwargs):
    """
    This effect type is used by `RepeatEvents` to execute their own, complete logic.
    :param user:        Target user.
    :param effect_data: Effect Data incl. `repeat_type`
    :param kwargs:      kwargs
    """
    # Input Sanity
    event_id = effect_data['event_id']

    # Get Event Object
    periodic_event: PeriodicEvent = user.get(f"event.{event_id}")

    # Execute the repeat type's logic
    PeriodicEvent.periodic_types[periodic_event.get_periodic_type()]['fun'](user=user, event=periodic_event)

    # Re-Schedule myself appropriately
    if not periodic_event.is_remove_on_trigger():
        periodic_event.reschedule_self()


@Effect.type('start_periodic_event', ('periodic_type', str))
def enqueue_periodic_event_for(user: User, effect_data: dict, **kwargs):
    """
    Requests a new `RepeatEvent` to be attached to `user`.
    :param user:            Target user.
    :param effect_data:     Effect Data including `periodic_type`
    :param kwargs:          kwargs
    """
    # Input Sanity
    periodic_type = effect_data['periodic_type']
    if periodic_type not in PeriodicEvent.periodic_types:
        raise Exception(f"Requested Repeat Type does not exist: {periodic_type}")

    # Create (non-scheduled) RepeatEvent for user
    event = PeriodicEvent.generate_instance_for(user, periodic_type)

    # Reschedule yourself. Due to upsert call inserts this new event in DB
    event.reschedule_self()


@get_resolver('event')
def resolve_event_req(game_id: str, user: User, **kwargs):
    splits = game_id.split('.')
    if is_uuid(splits[1]):
        # This is a generated field. We expect there to be an event with the corresponding `event_id`
        proj = {
            'target': user.get_id(),
            'event_id': splits[1]
        }
    elif splits[1] == 'periodic':
        # This is a request for a repeat event. Formulate appropriate DB request:
        proj = {
            'target': user.get_id(),
            'event_type': 'periodic',
            'periodic_type': '.'.join(splits[2:])
        }
    else:
        raise Exception(f"Cannot interpret Game ID: {game_id}")
    res = mongo.db.events.find_one(proj, {'_id': 0})
    if not res:
        raise Exception(f"Cannot find event: {game_id}")
    result = PeriodicEvent(res)

    return result



@boot_routine
def start_event_thread():
    EventThread(mongo_instance=mongo)


@html_generator(base_id='html.effect.', is_generic=True)
def render_effect_info(game_id: str, user: User, **kwargs):
    pass
