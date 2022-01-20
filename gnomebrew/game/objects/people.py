"""
This module describes and generates people in Gnomebrew.
People are a concrete implementation of `Entity` and share their general
"""
from numbers import Number
from typing import Any

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.game_object import StaticGameObject
from gnomebrew.game.objects.entity import Entity
from gnomebrew.game.objects.game_object import load_on_startup
from gnomebrew.game.objects.generation import Generator, Environment
from gnomebrew.game.static_data import dataframes
from gnomebrew.game.testing import application_test
from gnomebrew.game.user import get_resolver, User
from gnomebrew.game.util import generate_uuid


@load_on_startup('races')
class Race(StaticGameObject):

    def __init__(self, data: dict):
        StaticGameObject.__init__(self, data)

    def generate_size(self, gen: Generator) -> float:
        """Generates an appropriate size for a person of this race"""
        size_data = self._data['gen_info']['size']
        return gen.rand_normal(median=size_data['avg'], deviation=size_data['std_d'])

    def generate_name(self, gen: Generator, gender: str, type: str):
        """
        Helpfer function. Generates a name for this race.
        :param gen:         Generator to use
        :param gender:      Gender to use ('male', 'nonbinary', etc.)
        :param type:        Either `names` or `surnames`
        :return:            One generated name.
        """
        # Check Input
        if type not in ['names', 'surnames'] or gender not in ['male', 'female', 'nonbinary']:
            raise Exception(f"Illegal Input for Name Generation: {type}, {gender}")

        # Pull Relevant Data from `gen_info`
        gen_data = self._data['gen_info']['names']

        # Can this configuration be done?
        # Not all races support nonbinary specific names (yet)
        if gender == 'nonbinary' and not gen_data['nonbinary']:
            return self.generate_name(gen, gen.choose({'male': 1, 'female': 1}), type)

        # Generate the base name of the source file to pull names from
        if type == 'names':
            source_base = f"{self.get_minimized_id()}_{gender}_{type}"
        else:
            source_base = f"{self.get_minimized_id()}_{type}"

        # Does the name generation for this type happen in multiple syllables or at once?
        gen_instruction = gen_data[type]

        if gen_instruction == 'base':
            # Base Case. There is one big name list. Choose one randomly
            return gen.choose_from_data(source_base)
        elif isinstance(gen_instruction, int):
            # Interpret config as syllable number
            name = ""
            for syl_num in range(1, gen_instruction + 1):
                name += str(gen.choose_from_data(f"{source_base}_syl{syl_num}"))
            return name

    def generate_age(self, gen: Generator) -> float:
        """
        Generates an appropriate age for a person of this rage.
        :param gen:     Generator to use.
        :return:        Generated age in years.
        """
        age_data = self._data['gen_info']['age']
        age_gen = gen.rand_normal(median=age_data['old'] * 1/3, deviation=age_data['maturity'] * 2/3)
        return max(Person.MIN_AGE, min(Person.MAX_AGE, age_gen))


    def generate_looks(self, gen: Generator):
        """
        Generate a look for this person.
        :param gen: Generator to use for the generation.
        :return:    A `look` for a person of this race.
        """
        possible_looks = self._data['gen_info']['looks']
        if len(possible_looks) > 1:
            return gen.choose_from_list(possible_looks)
        else:
            raise Exception(f"Cannot choose looks from empty list: {self}")



    def is_mature_age(self, age: float):
        return age >= self._data['gen_info']['age']['maturity']



# Race Data Object Validation

Race.validation_parameters(('game_id', str), ('name', str), ('description', str), ('gen_info', [
    ('names', [('names', object), ('surnames', object), ('nonbinary', bool)]),
    ('size', [('avg', Number), ('std_d', Number)]),
    ('age', [('maturity', Number), ('old', Number)]),
    ('looks', list)]))


@load_on_startup('backgrounds')
class Background(StaticGameObject):

    def __init__(self, data: dict):
        StaticGameObject.__init__(self, data)

    def generate_has_title(self, gen: Generator) -> bool:
        """
        Let generator determine whether or not this background will generate a title for the target person.
        :param gen:     Target generator
        :return:        `True` if a title should be generated, otherwise `False`. Probabilities depend on
                        given background.
        """
        return gen.rand_unit() < self._data['gen_info']['titles']['prob']

    def generate_title(self, gen: Generator) -> str:
        """
        Generates an appropriate title for this background, if any.
        :param gen:     Generator to use
        :return:        Generated title. Empty string if no title is available.
        """
        # Access Titles Dataframe and filter according to background data
        titles_df = dataframes['titles']

        for filter, filter_list in self._data['gen_info']['titles']['filters'].items():
            filter_regex = f"({'|'.join(filter_list)})"
            titles_df = titles_df[titles_df[filter].str.contains(filter_regex, case=False)]

        return gen.choose_from_dataframe(titles_df)


Background.validation_parameters(('game_id', str), ('name', str), ('description', str),
                                 ('gen_info', [
                                     ('titles',
                                      [('prob', Number), ('_filters', [('_function', list), ('_source', list)])]),
                                     ('_tavern', [('budget', Number)])
                                 ]))


class Person(Entity):
    """
    Wraps game person data.
    Any person is an `Entity`, but also has additional abilities and functions.
    """

    def __init__(self, data: dict):
        Entity.__init__(self, data)

    _race_postfixes = {
        'Human': 'light',
        'Dwarf': 'dark',
        'Orc': 'green',
        'Elf': 'light',
        'Half Elf': 'light'
    }

    GENDER_CHOICES = {
        'male': 498,
        'female': 498,
        'nonbinary': 4
    }

    RACE_BASE_CHOICES = {
        'human': 30,
        'elf': 5,
        'half-elf': 17,
        'orc': 7,
        'dwarf': 13
    }

    BACKGROUND_CHOICES = {
        'peasant': 30,
        'noble': 1,
        'soldier': 10,
        'criminal': 5,
        'cleric': 5,
        'artisan': 4
    }

    MIN_AGE = 5
    MAX_AGE = 100000

    def get_data(self):
        return self._data

    def name(self):
        return self._data['name']

    def get_name(self):
        return self.name()

    def first_name(self):
        """
        Returns this person's first name.
        :return:this person's first name.
        """
        return self._data['name'].split(' ')[0]

    def get_race(self) -> Race:
        return Race.from_id(f"race.{self._data['race']}")

    def get_looks(self) -> str:
        """Returns this person's `looks`"""
        return self._data['looks']


@get_resolver('race', dynamic_buffer=False)
def get_race_object(game_id: str, user: User, **kwargs):
    return Race.from_id(game_id)


# Person Data Validation

Person.validation_parameters(('personality', dict), ('race', str), ('background', str), ('gender', str),
                             ('age', Number), ('looks', str))


@Person.validation_function()
def validate_person_data(data: dict, response: GameResponse):
    """
    Validates the data of a person.
    """
    # Firstly, interpret oneself as a general entity and run tests
    response.append_into(Entity(data).validate())

    # Ensure personality is not malformatted
    for test_field in ['openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism']:
        if test_field not in data['personality'] or not isinstance(data['personality'][test_field], Number):
            response.add_fail_msg(f"Missing Personality Data Field: {test_field}")


# Generation Functions

@Generator.generation_type(gen_type='Person', ret_type=Person)
def generate_person(gen: Generator):
    """
    Generates a person.
    :param gen: The generator to use.
    :return:    The generated Person.
    """
    data = dict()
    data['game_id'] = f"entity.{generate_uuid()}"  # By convention: every generated entity has a `entity` uuid Game ID
    data['entity_class'] = 'person'
    data['race'] = gen.generate('Race')
    data['age'] = gen.generate('Person Age')
    data['gender'] = gen.generate('Gender')
    data['background'] = gen.generate('Background')
    data['looks'] = gen.generate('Person Looks')
    data['name'] = gen.generate('Person Name')
    # Maybe the person will have a title. That's up to the character's background
    bg: Background = Background.from_id(f"background.{data['background']}")
    if bg.generate_has_title(gen):
        data['title'] = bg.generate_title(gen)
    data['personality'] = gen.generate('Personality')
    data['size'] = gen.generate('Person Size')
    return Person(data)


@Generator.generation_type(gen_type='Gender', ret_type=str)
def generate_gender(gen: Generator):
    return gen.choose(Person.GENDER_CHOICES)


@Generator.generation_type(gen_type='Personality', ret_type=dict)
def generate_personality(gen: Generator):
    personality = dict()
    personality['extraversion'] = gen.rand_normal(min=-1, max=1)
    personality['agreeableness'] = gen.rand_normal(min=-1, max=1)
    personality['openness'] = gen.rand_normal(min=-1, max=1)
    personality['conscientiousness'] = gen.rand_normal(min=-1, max=1)
    personality['neuroticism'] = gen.rand_normal(min=-1, max=1)
    return personality


@Generator.generation_type(gen_type='Race', ret_type=str)
def generate_race(gen: Generator):
    return gen.choose(gen.get_variable('Prevalent People', default=Person.RACE_BASE_CHOICES))


@Generator.generation_type(gen_type='Background', ret_type=str)
def generate_background(gen: Generator):
    age = gen.get_variable('Person Age', default=None)
    if age:
        # An age has been provided. Check if this is a child.
        race_name = gen.get_variable('Race', default=None)
        if race_name:
            # A race name has been set for this background. Ensure appropriate maturity ages are applied
            race: Race = Race.from_id(f"race.{race_name}")
            if not race.is_mature_age(age):
                return 'child'


    return gen.choose(Person.BACKGROUND_CHOICES)


@Generator.generation_type(gen_type='Person Looks', ret_type=Person)
def generate_person_looks(gen: Generator):
    race_name = gen.get_variable('Race', default=None)
    if race_name:
        # A race name has been set for this background. Ensure appropriate maturity ages are applied
        race: Race = Race.from_id(f"race.{race_name}")
        return race.generate_looks(gen)
    else:
        return gen.choose({
            'light': 1,
            'dark': 1,
        })

@Generator.generation_type(gen_type='Person Size', ret_type=float)
def generate_size(gen: Generator):
    race_name = gen.get_variable('Race', default=None)
    if not race_name:
        # Set a race to use as the size
        race_name = gen.choose(Person.RACE_BASE_CHOICES)

    # Fetch Race Data
    race_obj: Race = Race.from_id(f"race.{race_name}")
    return race_obj.generate_size(gen)


@Generator.generation_type(gen_type='Person Age', reg_type=float)
def generate_age(gen: Generator):
    race_name = gen.get_variable('Race', default=None)
    if not race_name:
        # Set a race to use as the size
        race_name = gen.choose(Person.RACE_BASE_CHOICES)

    race: Race = Race.from_id(f"race.{race_name}")
    return race.generate_age(gen)


@application_test(name='Generate People', context='Generation')
def generate_many_people(seq_size):
    """
    Generates `seq_size` (default=20) people and prints the results.
    """
    response = GameResponse()

    if seq_size is None or seq_size == '':
        seq_size = 20
    else:
        seq_size = int(seq_size)

    gen = Generator(Generator.true_random_seed(), Environment.empty())

    for _ in range(seq_size):
        person: Person = gen.generate("Person")
        response.log(str(person))

    return response
