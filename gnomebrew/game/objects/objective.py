"""
Describes objectives in Gnomebrew. Objectives are game objects that can track progress and declare it to be met.
This logic is helpful for players to determine quest progress but can also used in other contexts, for example for
tracking the progress of an adventure party.
"""
from gnomebrew.game.objects.game_object import GameObject


class Objective(GameObject):

    """
    Describes a quest objective in Gnomebrew
    """
    def __init__(self, objective_data):
        GameObject.__init__(self, objective_data)

