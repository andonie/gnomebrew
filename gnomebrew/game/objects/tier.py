"""
Tiers describe a general level of tier/gameplay.
On the same tier, challenges have similar tier and provide similar benefits.
Across tiers, challenge, risk, and reward increases.
"""
from typing import List

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
