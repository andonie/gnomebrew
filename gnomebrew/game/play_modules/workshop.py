"""
This module manages the workshop and also the general upgrade logic which is (mainly) managed within the workshop.
"""

from gnomebrew.game.user import User, user_assertion, id_update_listener
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

