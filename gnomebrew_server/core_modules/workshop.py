"""
This module manages the workshop and also the general upgrade logic which is (mainly) managed within the workshop.
"""

from gnomebrew_server.game.user import User, user_assertion, frontend_id_resolver
from gnomebrew_server.game.static_data import Upgrade



@user_assertion
def check_upgrade_integrity(user: User):
    """
    Assertion Script. Checks if the upgrades for all already-finished one-time recipes are stored in the user's
    upgrades list.
    :param user: a user
    """
    pass


@frontend_id_resolver('^data.workshop.upgrades$')
def reload_workshop_on_upgrade(user: User, data: dict, game_id: str):
    """
    A workshop upgrade has happened. We might want to update some recipe lists.
    """
    latest_upgrade = Upgrade.from_id(user.get('data.workshop.upgrades')[-1])
    for station in latest_upgrade.stations_to_update():
        user.frontend_update('ui', {
            'type': 'reload',
            'station': station
        })

