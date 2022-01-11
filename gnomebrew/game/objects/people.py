"""
This module describes and generates people in Gnomebrew.
People are a concrete implementation of `Entity` and share their general
"""
from numbers import Number

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.entity import Entity
from gnomebrew.game.objects.generation import generation_type, Generator, GeneratedGameObject, Environment
from gnomebrew.game.testing import application_test


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

    def get_styling_postfix(self):
        """
        :return: Returns a postfix (e.g. 'light', 'dark', 'green') to be used for state icons that are sensitive to
                different person.
        """
        return Person._race_postfixes[self._data['race']]

    def get_data(self):
        return self._data

    def name(self):
        return self._data['name']


# Person Data Validation

Person.validation_parameters(('personality', dict), ('race', str))


@Person.validation_function()
def validate_person_data(data: dict, response: GameResponse):
    """
    Validates the data of a person.
    """
    # Firstly, interpret oneself as a general entity and run tests
    response.append_into(Entity(data).validate())

    # Ensure personality is not malformatted
    if not all([test_field in data['personality'] and isinstance(data['personality'][test_field], Number)
                for test_field in ['openness', 'conscientousness', 'extraversion', 'agreeableness', 'neuroticism']]):
        response.add_fail_msg(f"Malformatted Personality Data: {data['personality']}")


# Generation Functions

@generation_type(gen_type='Person', ret_type=Person)
def generate_person(gen: Generator):
    """
    Generates a person.
    :param gen: The generator to use.
    :return:    The generated Person.
    """
    data = dict()
    data['entity_class'] = 'person'
    # Generate
    data['race'] = gen.generate('Race')
    data['gender'] = gen.generate('Gender')
    data['name'] = gen.generate('Person Name')
    # Budget is standardized independent of upgrade status of user. Budget will be modified upon patron entry
    # data['budget'] = random_normal(min=MIN, max=100)
    data['personality'] = gen.generate('Personality')
    data['size'] = 1
    return Person(data)


@generation_type(gen_type='Gender', ret_type=str)
def generate_gender(gen: Generator):
    # if gen.get_env_var('Race') == 'warforged':
    #     return 'nonbinary'

    return gen.choose(Person.GENDER_CHOICES)


@generation_type(gen_type='Personality', ret_type=dict)
def generate_personality(gen: Generator):
    personality = dict()
    personality['extraversion'] = gen.rand_normal(min=-1, max=1)
    personality['agreeableness'] = gen.rand_normal(min=-1, max=1)
    personality['openness'] = gen.rand_normal(min=-1, max=1)
    personality['conscientiousness'] = gen.rand_normal(min=-1, max=1)
    personality['neuroticism'] = gen.rand_normal(min=-1, max=1)
    return personality


_RACE_BASE_CHOICES = {
    'human': 30,
    'warforged': 1,
    'elf': 5,
    'half-elf': 12,
    'orc': 7
}


@generation_type(gen_type='Race', ret_type=str)
def generate_race(gen: Generator):
    return gen.choose(gen.get_env_var('Prevalent People', default=_RACE_BASE_CHOICES))


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

    gen = Generator(Generator.true_random_generator_seed(), Environment())

    for _ in range(seq_size):
        response.log(str(gen.generate("Person")))

    return response
