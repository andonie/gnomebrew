"""
This module manages the tavern and patron logic of the game.
"""

import threading
import datetime
import time

from gnomebrew_server.game.user import User
from gnomebrew_server.play import request_handler

_SLEEP_TIME = 2


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
            # Find all events that are due
            start_time = datetime.datetime.utcnow()

            # Do Stuff
            end_time = datetime.datetime.utcnow()
            # print(f'Total time: {(end_time - start_time).total_seconds() }')
            sleep_time = (end_time - start_time).total_seconds() - _SLEEP_TIME
            if sleep_time > 0:
                try:
                    time.sleep(sleep_time)
                except KeyboardInterrupt:
                    print('Shutting down tavern thread')
                    exit()


class Patron:
    """
    Patron class
    """
