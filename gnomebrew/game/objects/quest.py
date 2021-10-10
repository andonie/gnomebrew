"""
Implements basic quest logic in Gnomebrew.
Governed by the 'quest'-ID-prefix
"""
from typing import List, Callable

from gnomebrew.game.objects.generation import GeneratedGameObject
from gnomebrew.game.objects.game_object import StaticGameObject, load_on_startup, GameObject, PublicGameObject
from gnomebrew.game.user import User, get_resolver


class Objective(GameObject):

    """
    Describes a quest objective in Gnomebrew
    """
    def __init__(self, objective_data):
        GameObject.__init__(self, objective_data)



class Quest(Objective):
    """
    Describes a general quest in Gnomebrew.
    """

    def __init__(self, quest_data):
        GameObject.__init__(self, quest_data)
        Objective.__init__(self, quest_data)

    def get_objectives(self) -> List[Objective]:
        """
        Returns all objectives of this quest as a list.
        :return:    all objectives of this quest as a list.
        """

    def get_status(self, user: User) -> List[dict]:
        """
        Returns the status of this quest based on a given user.
        :param user:    target user.
        :return:        status of this quest for the given user. Formatted as a list of dicts that contain the status
                        data of the quest in given order.
        """
        objectives = self.get_objectives()
        status_list = list()
        for objective in objectives:
            status_list.append({
                ''
            })
        return status_list


@load_on_startup('static_quests')
class StaticQuest(Quest, StaticGameObject):
    """
    Wrapper class for human-defined quests from DB data.
    """

    def __init__(self, db_data: dict):
        StaticGameObject.__init__(self, db_data)
        Quest.__init__(self, db_data)

@PublicGameObject.setup(collection_name='public_quests', game_id_prefix='public_quest')
class GeneratedQuest(Quest, PublicGameObject):
    """
    Describes a generated quest in Gnomebrew with the use of a generator.
    """

    def __init__(self, data):
        PublicGameObject.__init__(self, data)
        Quest.__init__(self, data)


@get_resolver('quest')
def quest_get_resolver(game_id: str, user: User, **kwargs):
    """
    Resolves `quest.` - Game IDs
    :param game_id:     ID to resolve. Special cases: `quest._active`: List of all active quests of this user.
    :param user:        Target user.
    :param kwargs:      kwargs
    :return:            Result
    """
    pass
