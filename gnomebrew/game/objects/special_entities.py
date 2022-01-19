"""
This module manages the game's special entities that are mostly needed for icon representation.
"""

from gnomebrew.game.user import get_resolver, User
from gnomebrew.game.objects.game_object import StaticGameObject, load_on_startup


@load_on_startup('special_entities')
class SpecialEntity(StaticGameObject):
    def __init__(self, mongo_data):
        super().__init__(mongo_data)

    def get_name(self):
        return self._data['name']

    def get_description(self):
        return self._data['description']

# Special Entity Data Validation

SpecialEntity.validation_parameters(('game_id', str), ('name', str), ('description', str))

@get_resolver('special')
def get_special(game_id: str, user: User, **kwargs) -> SpecialEntity:
    """
    Used to return special item entities.
    :param game_id: ID to resolve, e.g. 'special.time.
    """
    entity: SpecialEntity = SpecialEntity.from_id(game_id)
    return entity
