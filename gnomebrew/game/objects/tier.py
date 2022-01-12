"""
Tiers describe a general level of tier/gameplay.
On the same tier, challenges have similar tier and provide similar benefits.
Across tiers, challenge, risk, and reward increases.
"""
from typing import List

from gnomebrew.game.objects import Generator
from gnomebrew.game.objects.game_object import StaticGameObject, load_on_startup


@load_on_startup('tier')
class Tier(StaticGameObject):
    """
    Wraps tier data
    """

    def __init__(self, data):
        StaticGameObject.__init__(self, data)

    def generate_info(self) -> List[str]:
        """
        Generates an info list object that describes this tier.
        """
        info = [self._data['game_id']]
        if 'quest_description' in self._data:
            info.append(self._data['quest_description'])
        return info


# Tier data validation
Tier.validation_parameters(('game_id', str), ('name', str), ('description', str), ('quest_description', str))


@Generator.generation_type(gen_type='Tier', ret_type=str)
def generate_tier(gen: Generator):
    # TODO implement
    return 'tier_1'
