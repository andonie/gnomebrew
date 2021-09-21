"""
This module describes and generates people in Gnomebrew.
"""

from gnomebrew.game.objects.generation import generator_logic, Generator, GeneratedGameObject

MIN = 15


class Person(GeneratedGameObject):
    """
    Describes a person in Gnomebrew through some 'fundamental' attributes. People can generally be used for any module.
    """

    def __init__(self, data: dict):
        self._data = data


    def get_styling_postfix(self):
        """
        :return: Returns a postfix (e.g. 'light', 'dark', 'green') to be used for state icons that are sensitive to
                different person.
        """



    def get_id(self):
        """
        Returns the unique ID for this patron. Assumes the patron has already been assigned a user. Otherwise breaks
        """
        return self._data['id']

    def get_data(self):
        return self._data


    def name(self):
        return self._data['name']



@generator_logic(gen_type='Person', ret_type=Person)
def generate_person(gen: Generator):
    """
    Generates a person.
    :param gen: The generator to use.
    :return:    The generated Person.
    """
    data = dict()
    # Generate a gender
    data['race'] = gen.generate('Race')
    data['gender'] = gen.generate('Gender')
    data['name'] = gen.generate('PName')
    # Budget is standardized independent of upgrade status of user. Budget will be modified upon patron entry
    # data['budget'] = random_normal(min=MIN, max=100)
    data['personality'] = gen.generate('Personality')
    return Person(data)


@generator_logic(gen_type='Gender', ret_type=str)
def generate_gender(gen: Generator):
    if gen.get('Race') == 'warforged':
        return 'nonbinary'
    choices = {
        'male': 498,
        'female': 498,
        'nonbinary': 4
    }
    return gen.choose(choices)


@generator_logic(gen_type='Personality', ret_type=dict)
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

@generator_logic(gen_type='Race', ret_type=str)
def generate_race(gen: Generator):
    return gen.choose(gen.get('Prevalent People', default=_RACE_BASE_CHOICES))
