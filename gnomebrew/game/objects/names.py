"""
This module contains the name generation logic of Gnomebrew.
Provides environment-dependent generation rules for all kinds of strings, from real names for people and places to more
generic strings like adjectives.
"""
import re

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects import Person
from gnomebrew.game.objects.generation import Generator, Environment
from gnomebrew.game.testing import application_test
from gnomebrew.game.static_data import dataframes


_name_regex = re.compile(r"\w+")

@Generator.generation_type(gen_type='Person Name', ret_type=str)
def generate_person_name(gen: Generator):
    """
    Takes into account any relevant environment data and generates a name for a person.
    :param gen:     The connected generator object
    :return:        The generated name
    """
    full_name = ''
    if gen.rand_int_limited(100) < 3:
        # People with a fancy title get a free bonus first name
        full_name += f"{gen.generate('Title')} {gen.generate('First Name')} "

    full_name += f"{gen.generate('First Name')} {gen.generate('Surname')}"

    # Sanitize full name to camel case
    full_name = _name_regex.sub(lambda match: f"{match.group()[0].upper()}{match.group()[1:].lower()}", full_name)

    return full_name


@Generator.generation_type(gen_type='Title', ret_type=str)
def generate_title(gen: Generator):
    return gen.choose_from_data('titles')


@Generator.generation_type(gen_type='First Name', ret_type=str)
def generate_first_name(gen: Generator):
    # Might have multiple first names
    if gen.rand_int_limited(50) > 40:
        return f"{gen.generate('First Name')} {gen.generate('First Name')}"

    gender = gen.get_variable('Gender', default=None)
    if gender is None:
        # No gender was defined. Choose at random
        gender = gen.choose(Person.GENDER_CHOICES)
    race = gen.get_variable('Race', default='human')

    data_source = f"{race}_{gender}_names"
    return gen.choose_from_data(data_source)


@Generator.generation_type(gen_type='Surname', ret_type=str)
def generate_surname(gen: Generator):
    surname = gen.choose_from_data('human_surnames', strategy='uniform')
    # Unfortunately, `human_surnames` is formatted in CAPS LOCK. Rectify:
    surname = f"{surname[0].upper()}{surname[1:].lower()}"
    return surname


@Generator.generation_type(gen_type='Context Name', ret_type=str)
def generate_context_name(gen: Generator):
    return gen.choose_from_data(gen.choose({
        'human_male_names': 99,
        'human_female_names': 99,
        'human_nonbinary_names': 5
    }))


@Generator.generation_type(gen_type='Context Adjective', ret_type=str)
def generate_context_name(gen: Generator):
    # TODO: Add environment influence
    return gen.choose_from_data('adjectives')


@Generator.generation_type(gen_type='Context Noun', ret_type=str)
def generate_context_name(gen: Generator):
    # TODO: Add environment influence
    return gen.choose_from_data('nouns')


@Generator.generation_type(gen_type='City Name', ret_type=str)
def generate_city_name(gen: Generator):
    return '<City Name>'
