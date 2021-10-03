"""
This module manages the workshop and also the general upgrade logic which is (mainly) managed within the workshop.
"""

from gnomebrew.game.user import User, user_assertion, frontend_id_resolver
from gnomebrew.game.objects.upgrades import Upgrade
from gnomebrew.game.event import Event
import bisect

@user_assertion
def check_upgrade_integrity(user: User):
    """
    Assertion Script. Checks if the upgrades for all already-finished one-time recipes are stored in the user's
    upgrades list.
    :param user: a user
    """
    pass


@frontend_id_resolver(r'^data\.workshop\.*')
def ignore_workshop_data_updates(user: User, data: dict, game_id: str):
    pass # Do nothing on the data-write. The event method takes care of this after upgrade


