"""
Manages the entity core logic.
The game considers everything that can move and interact within the game world an entity. These
"chess pieces on the field" include:

- Dragons
- Humans
- Dogs
- Warships
- Dwarves
"""

from gnomebrew.game.objects.game_object import GameObject, DynamicGameObject, load_on_startup


@load_on_startup('entities')
@DynamicGameObject.setup(dynamic_collection_name='entities', game_id_prefix='entity')
class Entity(DynamicGameObject):
    """
    Wraps any movable entity in the game
    """

    def __init__(self, data: dict):
        GameObject.__init__(self, data)


# Entity Data Validation

Entity.validation_parameters(('game_id', str), ('name', str), ('entity_class', str), ('size', float))
