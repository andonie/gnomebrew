"""
This module manages the workshop and also the general upgrade logic which is (mainly) managed within the workshop.
"""

from gnomebrew_server.game.user import User, user_assertion, frontend_id_resolver
from gnomebrew_server.game.static_data import Upgrade
from gnomebrew_server.game.event import Event
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


@Event.register
def upgrade(user: User, effect_data: list):
    """
    Event execution for an upgrade.
    :param user:            The user to execute on.
    :param effect_data:     The registered effect data formatted as `['upgrade1', 'upgrade2']`
    """
    # Get Upgrade list (always sorted)
    user_upgrade_list = user.get('data.workshop.upgrades')

    stations_to_update = set()

    for upgrade in effect_data:
        assert upgrade not in user_upgrade_list
        # Add the upgrade in the correct sorted position
        user_upgrade_list.insert(bisect.bisect_left(user_upgrade_list, upgrade), upgrade)
        # Check if there is a UI update to be done
        upgrade_object = Upgrade.from_id(upgrade)
        stations_to_update.update(upgrade_object.stations_to_update())

    # Flush. Update Game Data
    user.update_game_data('data.workshop.upgrades', user_upgrade_list)

    # Flush to Frontend: Update User Frontends
    for station in stations_to_update:
        user.frontend_update('ui', {
            'type': 'reload_station',
            'station': station
        })
