"""
This module contains the name generation logic of Gnomebrew.
"""

from gnomebrew.game.objects.generation import generator_logic, Generator


@generator_logic(gen_type='PName', ret_type=str)
def generate_person_name(gen: Generator):
    """
    Takes into account any relevant environment data and generates a name for a person.
    :param gen:     The connected generator object
    :return:        The generated name
    """
    pass


@generator_logic(gen_type='CName', ret_type=str)
def generate_city_name(gen: Generator):
    pass


@generator_logic(gen_type='Title', ret_type=str)
def generate_title(gen: Generator):
    pass


@generator_logic(gen_type='Fname', ret_type=str)
def generate_title(gen: Generator):
    pass


@generator_logic(gen_type='Surname', ret_type=str)
def generate_surname(gen: Generator):
    return gen.choose({
        'Harold': 1,
        'Kumar': 2
    })

@generator_logic(gen_type='Context Name', ret_type=str)
def generate_context_name(gen: Generator):
    pass

