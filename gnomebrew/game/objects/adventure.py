"""
Governs adventure module of Gnomebrew
"""
from gnomebrew.game.objects.game_object import PublicGameObject

# @PublicGameObject.setup(dynamic_collection_name='adventures', game_id_prefix='adventure')
from gnomebrew.game.objects.generation import Generator


class Adventure(PublicGameObject):
    pass


# Adventure Data Validation
Adventure.validation_parameters(('game_id', str))


@Generator.generation_type(gen_type='Attributes', ret_type=dict)
def generate_attributes(gen: Generator):
    """
    Generates the six core attributes of any sentient entity in the world: DEX, STR, GRT, WIL, INT, CHA
    :param gen: Generator
    :return:    Data representing adventure attributes for an entity, taking into account any already defined
                environment parameters. If nothing is defined, assumes a human. Will look like:
    ```python
    {
        'str': 3,
        'dex': 8,
        'grt': 5,
        'wil': 4,
        'int': 2,
        'cha': 7
    }
    ```
    """
    # TODO: Implement
    pass
