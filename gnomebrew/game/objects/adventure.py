"""
Governs adventure module of Gnomebrew
"""
from gnomebrew.game.objects.game_object import PublicGameObject


@PublicGameObject.setup(collection_name='adventures', game_id_prefix='adventure')
class Adventure(PublicGameObject):
    pass