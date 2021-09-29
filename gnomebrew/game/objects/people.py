"""
This module describes and generates people in Gnomebrew.
"""
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.generation import generation_type, Generator, GeneratedGameObject
from gnomebrew.game.testing import application_test


class Person(GeneratedGameObject):
    """
    Describes a person in Gnomebrew through some 'fundamental' attributes. People can generally be used for any module.
    """

    def __init__(self, data: dict):
        self._data = data

    _race_postfixes = {
        'human': 'light',
        'dwarf': 'dark',
        'orc': 'green',
        'elf': 'light',
        'half_elf': 'light'
    }

    def get_styling_postfix(self):
        """
        :return: Returns a postfix (e.g. 'light', 'dark', 'green') to be used for state icons that are sensitive to
                different person.
        """
        return Person._race_postfixes[self._data['race']]

    def get_id(self):
        """
        Returns the unique ID for this patron. Assumes the patron has already been assigned a user. Otherwise breaks
        """
        return self._data['id']

    def get_data(self):
        return self._data

    def name(self):
        return self._data['name']


@generation_type(gen_type='Person', ret_type=Person)
def generate_person(gen: Generator):
    """
    Generates a person.
    :param gen: The generator to use.
    :return:    The generated Person.
    """
    data = dict()
    # Generate
    data['race'] = gen.generate('Race')
    data['gender'] = gen.generate('Gender')
    data['name'] = gen.generate('Person Name')
    # Budget is standardized independent of upgrade status of user. Budget will be modified upon patron entry
    # data['budget'] = random_normal(min=MIN, max=100)
    data['personality'] = gen.generate('Personality')
    return Person(data)


@generation_type(gen_type='Gender', ret_type=str)
def generate_gender(gen: Generator):
    if gen.get_env_var('Race') == 'warforged':
        return 'nonbinary'
    choices = {
        'male': 498,
        'female': 498,
        'nonbinary': 4
    }
    return gen.choose(choices)


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
    Generates `seq_size` (default=200) people and prints the results.
    """
    response = GameResponse()

    if seq_size is None or seq_size == '':
        seq_size = 200
    else:
        seq_size = int(seq_size)

    return response
