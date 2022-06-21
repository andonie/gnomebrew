"""
This module contains the name generation logic of Gnomebrew.
Provides environment-dependent generation rules for all kinds of strings, from real names for people and places to more
generic strings like adjectives.
"""
import re
from typing import Tuple

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects import Person
from gnomebrew.game.objects.generation import Generator, Environment
from gnomebrew.game.objects.people import Race
from gnomebrew.game.testing import application_test
from gnomebrew.game.static_data import dataframes

# PERSON Names

_name_regex = re.compile(r"\w+")

@Generator.generation_type(gen_type='Person Name', ret_type=str)
def generate_person_name(gen: Generator):
    """
    Takes into account any relevant environment data and generates a name for a person.
    :param gen:     The connected generator object
    :return:        The generated name
    """
    full_name = ''
    # If this person has a title, give them an extra first name
    if gen.get_variable('Title', default=None):
        full_name += f"{gen.generate('First Name') } "

    # Basic: First + Last Name
    full_name += f"{gen.generate('First Name')} {gen.generate('Surname')}"

    # Optional: Double Last-Name
    if gen.rand_int_limited(100) > 95:
        full_name += f"-{gen.generate('Surname')}"

    return full_name


@Generator.generation_type(gen_type='Title', ret_type=str)
def generate_title(gen: Generator):
    return gen.choose_from_data('titles')


def _ensure_race_and_gender(gen: Generator) -> Tuple:
    gender = gen.get_variable('Gender', default=None)
    race = gen.get_variable('Race', default=None)
    if gender is None:
        # No gender was defined. Choose at random
        gender = gen.choose(Person.GENDER_CHOICES)
    if race is None:
        # No race was defined. Choose at random
        race = gen.choose(Person.RACE_BASE_CHOICES)
    return race, gender


@Generator.generation_type(gen_type='First Name', ret_type=str)
def generate_first_name(gen: Generator):
    # Might have multiple first names
    if gen.rand_int_limited(50) > 40:
        return f"{gen.generate('First Name')} {gen.generate('First Name')}"

    race_name, gender = _ensure_race_and_gender(gen)
    race: Race = Race.from_id(f"race.{race_name}")
    return race.generate_name(gen, gender, 'names')


@Generator.generation_type(gen_type='Surname', ret_type=str)
def generate_surname(gen: Generator):
    race_name, gender = _ensure_race_and_gender(gen)
    race: Race = Race.from_id(f"race.{race_name}")
    return race.generate_name(gen, gender, 'surnames')


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
