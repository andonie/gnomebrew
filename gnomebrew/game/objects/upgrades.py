import re

from gnomebrew.game.user import get_resolver
from gnomebrew.game.user import User
from gnomebrew.game.objects.static_object import StaticGameObject, load_on_startup


@get_resolver('attr')
def attr(game_id: str, user: User, **kwargs):
    """
    Evaluates an attribute for this user taking into account all unlocked upgrades.
    :param user:
    :param game_id: An attribute ID, e.g. 'attr.well.slots'
    :return: The result of the evaluation:
    """

    splits = game_id.split('.')
    assert splits[0] == 'attr' and len(splits) > 2

    # Get Base Value
    station = StaticGameObject.from_id('station.' + splits[1])
    try:
        val = station.get_base_value('.'.join(splits[2:]))
        if type(val) is list or type(val) is dict:
            # If the value is a reference, make sure we use a copy for this operation
            val = val.copy()
    except (KeyError, AssertionError):
        # Key does not exist. --> default
        if 'default' in kwargs:
            val = kwargs['default']
        else:
            raise AttributeError(f"Station does not have a base value {'.'.join(splits[2:])} and now default was set.")

    # Get all relevant Upgrades
    upgrades = sorted(filter(lambda x: x.relevant_for(game_id),
                             [StaticGameObject.from_id(x) for x in user.get('data.workshop.upgrades', default=[])]))

    # Apply upgrades in sorted order
    for upgrade in upgrades:
        val = upgrade.apply_to(val=val, game_id=game_id)
    return val


@load_on_startup('upgrades')
class Upgrade(StaticGameObject):

    def __init__(self, mongo_data):
        super().__init__(mongo_data)

    def apply_to(self, val, game_id: str):
        """
        Applies upgrade effect to an attribute
        :param val: An attribute value before the upgrade
        :param game_id: The Game ID of the target value (formatted in `attr.x.y`)
        :return:    The attribute value after the upgrade
        """
        assert game_id in self._data['effect']
        for key in self._data['effect'][game_id]:
            if key == 'delta':
                val += self._data['effect'][game_id][key]
            elif key == 'phi':
                val *= self._data['effect'][game_id][key]
            elif key == 'pull':
                val.remove(self._data['effect'][game_id][key])
            else:
                raise AttributeError(f"Don't know how to process {key}")
        return val

    def upgrade_order(self) -> int:
        """
        Returns the order of this upgrade.
        Used to ensure consistent `attr` evaluation based on station base data and upgrades.

        In general:

        * Upgrades of the same order are commutative
        * Upgrades of lower order are guaranteed to execute before upgrades of higher order

        :return:    An `int` that represents the order of this upgrade.
        """
        effect = self._data['effect']
        # If an order is defined directly, return the order of this upgrade
        if 'order' in effect:
            return self._data['effect']['order']

        # If the upgrade contains a `delta` (+), its order is 1
        if 'delta' in effect:
            return 1

        # If the upgrade contains a `phi` (*), its order is 2
        if 'phi' in effect:
            return 2

        # If the upgrade contains a `pull` (remove from list), its order is 3
        if 'pull' in effect:
            return 4

        # If the upgrade is a hard-set of a value, its order is 5
        if 'set' in effect:
            return 5

        # Default: 0
        return 0

    def relevant_for(self, game_id: str):
        """
        Checks if this upgrade is relevant for a given game-id.
        :param game_id: A game-id to check.
        :return:        `True` if this upgrade modifies the attribute at `game_id` in some way, otherwise `False`.
        """
        return game_id in self._data['effect']

    def stations_to_update(self):
        """
        Returns a list of stations that need to be updated once this upgrade takes place.
        :return: A set of station names that should be updated after this upgrade takes place, e.g. because of a change in
                 frontend attributes.
        """
        stations_to_update = set()

        # Every Station with a recipe that is unlocked by this upgrade is to be updated
        global _RECIPE_LIST
        for station in map(lambda r: r.get_value('station'),
                           filter(lambda recipe: recipe.unlocked_by_upgrade(self), _RECIPE_LIST)):
            stations_to_update.add(station)

        # Go Through the actual upgrade effect and check if something needs to be updated
        # Relevent regexes to check for
        regexes = [
            re.compile(r'^attr\.(?P<station_name>\w+)\.slots$')  # Changes in Slots should be UI updated
        ]

        for attribute in self._data['effect']:
            print(f"{attribute=}")
            for regex in regexes:
                match = regex.match(attribute)
                print(f"{match=}")
                if match:
                    # Attribute match. Get station name
                    stations_to_update.add(match.group('station_name'))

        return stations_to_update

    def __lt__(self, other):
        """
        Custom Implemented __lt__ method.
        Used to ensure *consistent upgrade behavior* when applying several several Upgrades one after another:
        Before executing Upgrade behavior, all existing upgrades are sorted in a list before folding it with reduce(...)
        :param other:   Element to compare this to.
        :return:        True if self<other. False if self>=other
        """
        # Upgrades are only comparable with each other
        assert type(other) is Upgrade
        return self.upgrade_order() < other.upgrade_order()

    def describe_outcome(self):
        """
        Utility Method that generates HTML text that summarizes the outcome of this upgrade.
        """
        if 'description' in self._data:
            return self._data['description']