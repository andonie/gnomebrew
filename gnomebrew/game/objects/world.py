"""
This file manages Gnomebrew's Game World consisting of different planes of existence as well as a tiered system
of Regions, Structures, and Maps.

The content of planes is generated by Gnomebrew dynamically but determined fully by location coordinates.
"""
from typing import List

from gnomebrew.game.objects.generation import GeneratedGameObject, generator_logic, Generator, Environment
from gnomebrew.game.objects.people import Person
from gnomebrew.game.objects.static_object import StaticGameObject, load_on_startup
from gnomebrew.game.user import User, get_resolver


class WorldLocation(Environment):
    """
    Abstractly describes a location in the game world from a small room to an entire plane.
    """

    # Lookup table for correct level names:
    _level_names = {
        0: 'World',
        1: 'Plane',
        2: 'Region',
        3: 'Structure',
        4: 'Chunk'
    }

    def __init__(self, address: str):
        """
        Base Initialization of a location.
        :param address: The full address of this location in the game world.
        """
        super().__init__()
        self.address = address

    def generate_people(self, num_people: int) -> List[Person]:
        """
        Generates some people that come from this particular location.
        This is **nondeterministic** in the sense of Generation. Even identical environment and location generate
        different people every time.
        :param num_people:  Amount of people to generate.
        :return:            A list of generated people that would be situated in this location.
        """
        generator = Generator(Generator.true_random_generator_seed(), self.create_copy())
        return [generator.generate('Person', flush_on_finish=True) for i in range(num_people)]

    def generate_sub_location(self, location_address: str):
        """
        Generates a sub-location for this world-location.
        :param location_address:    Address for this location. Must be 4-digit hex string, e.g. `eF25`
        :return:                    The sub-location for this environment at the given address.
        """
        # Instantiate the appropriate generator for the sublocation (= seed)
        generator = Generator(location_address, self.create_copy())
        # Look up my own location level name and put it into the generator
        return generator.generate(WorldLocation._level_names[self.get_location_level()])

    def get_location_level(self):
        """
        Returns the level of this location.
        :return:    The level of this location:
                    Chunk = 4
                    Structure = 3
                    Region = 2
                    Plane = 1
                    [World = 0]
        """
        return len(self.address.split('.')) - 1


@load_on_startup('planes')
class Plane(StaticGameObject, WorldLocation):
    """
    Describes a plane of existence defined in the game's database. Contains the base data to generate sub location
    levels from.
    """

    def __init__(self, db_data):
        StaticGameObject.__init__(self, db_data)
        WorldLocation.__init__(self, self.get_id())


class GeneratedLocation(GeneratedGameObject, WorldLocation):
    """
    Describes a generated location in the game of any scale. Includes regions, structures, and chunks.
    """

    def __init__(self, address):
        GeneratedGameObject.__init__()
        WorldLocation.__init__(address)


@get_resolver('world')
def get_world_location(game_id: str, user: User, **kwargs) -> WorldLocation:
    """
    Returns the corresponding world location
    :param game_id:     ID. Different location tiers are possible,
                        e.g. 'world.material_plane.3EAC.BBD7', 'world.feywild'
    :param user:        a user
    :param kwargs:      ?
    :return:            The location corresponding to the given ID
    """
    splits = game_id.split('.')
    # Get the plane first
    location: Plane = StaticGameObject.from_id(splits[:2])
    for addr in splits[2:]:
        location = location.generate_sub_location(addr)
    return location


@generator_logic(gen_type='Region', ret_type=WorldLocation)
def generate_region(gen: Generator):
    region: GeneratedLocation = reg


@generator_logic(gen_type='Structure', ret_type=WorldLocation)
def generate_region(gen: Generator):
    pass


@generator_logic(gen_type='Region', ret_type=WorldLocation)
def generate_region(gen: Generator):
    pass