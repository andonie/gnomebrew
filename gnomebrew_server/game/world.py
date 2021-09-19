"""
This file manages Gnomebrew's Game World consisting of different planes of existence as well as a tiered system
of Regions, Structures, and Maps.

The content of planes is generated by Gnomebrew dynamically but determined fully by location coordinates.
"""

from gnomebrew_server.game.static_data import StaticGameObject


class WorldLocation:
    """
    Abstractly describes a location in the game world from a small room to an entire plane.
    """

    def __init__(self, data, parent=None):
        """
        Base Initialization of a location.
        :param data:        The data that describes this location.
        :param parent:      This locations parent. Default is `None` (for Planes who are parentless)/
        """
        self._data = data
        self.parent = parent

    def get_property(self, prop: str):
        """
        Queries a property from this location.
        :param prop:    A property to check for.
        :return:        The requested property, if existing.
        """
        if prop in self._data['prop']:
            # Property is set in here
            return self._data['prop'][prop]
        if self.parent:
            # This world location has a parent. If parent has the property set, escalate.
            return self.parent.get_property(prop)
        else:
            raise Exception(f"The property {prop} does not exist in this location (and its parents).")


class Plane(WorldLocation, StaticGameObject):
    """
    Describes a plane of existence as defined by the player.
    """

class Region(WorldLocation):
    """
    Describes a region on a plane of existence
    """

class Structure(WorldLocation):
    """
    Describes a smaller subsection of a region, one coherent structure.
    """

class Chunk(WorldLocation):
    """
    Describes a small location (e.g. like a room).
    """


if __name__ == '__main__':
    pass