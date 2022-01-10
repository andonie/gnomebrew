"""
Describes objectives in Gnomebrew. Objectives are game objects that can track progress and declare it to be met.
This logic is helpful for players to determine quest progress but can also used in other contexts, for example for
tracking the progress of an adventure party.
"""
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.condition import Condition
from gnomebrew.game.objects.game_object import GameObject


class Objective(GameObject):
    """
    Describes a quest objective in Gnomebrew
    """

    def __init__(self, objective_data):
        GameObject.__init__(self, objective_data)


# Objective Data Validation

Objective.validation_parameters(('name', str), ('description', str), ('conditions', list))


@Objective.validation_function()
def validate_objective_data(data: dict, response: GameResponse):
    """
    Validates objective data.
    :param data:        obj data
    :param response:    response to log
    """
    # Validate all nested conditions:
    for condition in [Condition(c_data) for c_data in data['conditions']]:
        response.append_into(condition.validate())
