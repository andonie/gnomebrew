"""
Implements basic quest logic in Gnomebrew.
Governed by the 'quest'-ID-prefix
"""
from typing import List, Callable

from gnomebrew.game import user
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.condition import Condition
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.generation import GeneratedGameObject
from gnomebrew.game.objects.game_object import StaticGameObject, load_on_startup, GameObject, PublicGameObject
from gnomebrew.game.objects.objective import Objective
from gnomebrew.game.testing import application_test
from gnomebrew.game.user import User, get_resolver, load_user


@PublicGameObject.setup(dynamic_collection_name='generated_quests', game_id_prefix='quest')
@load_on_startup('scripted_quests')
class Quest(StaticGameObject, PublicGameObject):
    """
    Describes a general quest in Gnomebrew.
    """

    def __init__(self, quest_data):
        GameObject.__init__(self, quest_data)

    def initialize_for(self, user: User, **kwargs):
        """
        Initializes this quest. Is called once as a quest enters the player's `active` quest collection.
        Sets up any necessary user data and executes any initial effects.
        :param user:    Target user
        :param kwargs:  kwargs
        """
        # Update User Data to include this as an active quest
        base_quest_data = {
            'name': self._data['name'],
            'description': self._data['description'],
            'foldout': self._data['foldout'],
            'current_state': self._data['quest_start'],
            'icon': self._data['icon']
        }
        user.update(f"data.quest.active.{self.get_minimized_id()}", base_quest_data)

        # Transition into the first quest state
        self.transition_state(user, self._data['quest_start'], **kwargs)

    def transition_state(self, user: User, state_id: str, **kwargs):
        """
        Transitions from any current state into a given state.
        :param user         Target user
        :param state_id:    The ID of the state to transition to as used in the quest data.
        """
        next_state = QuestState(self._data['quest_flow'][state_id])

        # Add any listeners that are needed in this state but currently not registered
        current_listener_ids = set([listener_data['target_id'] for listener_data in user.get_id_listeners()
                             if listener_data['effect_type'] == 'qu'])
        new_listener_ids = set(next_state.get_all_target_ids())
        user.register_id_listeners(list(new_listener_ids-current_listener_ids), {'effect_type': 'qu'}, starts_with=True)

        # Initialize next state.
        next_state.initialize_for(user, self.get_minimized_id())

    def progress_quest(self, user: User, **kwargs):
        """
        Called when the Quest system detects all conditions of all current objectives to be met.
        Moves the quest into the next state.
        :param user:    Target user.
        :param kwargs:  kwargs
        """
        last_state = user.get(f"data.quest.active.{self.get_minimized_id()}.current_state", **kwargs)
        next_state = self._data['quest_flow'][last_state]['on_complete']
        self.transition_state(user, next_state, **kwargs)


class QuestState(GameObject):
    """
    Describes one possible quest state. Quests can have multiple nonlinear states. This class describes one such state.
    """

    def __init__(self, data):
        GameObject.__init__(self, data)

    def initialize_for(self, user: User, quest_id: str, **kwargs):
        """
        Initializes this quest state for the user.
        This triggers any effects connected to this quest state and updates user data.
        :param user:    Target user
        :param quest_id: Minimized name of the parent quest ID
        """
        # Update user data.
        user.update(f"data.quest.active.{quest_id}.current_objectives", self.generate_user_objective_data(user), **kwargs)

        # Execute all effects attached
        for effect in [Effect(data) for data in self._data['effect']]:
            effect.execute_on(user, **kwargs)

    def get_all_target_ids(self) -> List[str]:
        """
        Returns a list of all IDs this quest state has.
        :return:        A list of all GameIDs targetted by any condition within this quest state.
        """
        id_list = list()
        for obj in self._data['objectives']:
            for con in obj['conditions']:
                if 'target_id' in con and con['target_id'] not in id_list:
                    id_list.append(con['target_id'])
        return id_list

    @staticmethod
    def _generate_playerdata_conditions(condition_raw: list):
        """
        Prepares raw condition data to be adapted for
        :param condition_raw:   Raw condition JSON data.
        :return:    JSON data ready to be added to user data.
        """
        for condition_data in condition_raw:
            condition_data['state'] = 0
        return condition_raw

    def generate_user_objective_data(self, user: User) -> List[dict]:
        """
        Generates the current user's current objective data.
        :param user:    target user.
        :return         The current objectives with all relevant frontend data.
        """
        return [{
            'name': obj['name'],
            'description': obj['description'],
            'state': 0,
            'info': [],
            'conditions': QuestState._generate_playerdata_conditions(obj['conditions'])
        } for obj in self._data['objectives']]

    @staticmethod
    @PublicGameObject.special_id_get('quest._active')
    def get_all_active_quests(user: User, game_id: str, **kwargs) -> dict:
        """
        Special ID `quest._active` returns a list of all active quests as data.
        :param user:    target user
        :param game_id: `quest._active`
        :param kwargs:  kwargs
        :return:        A `dict` with all active quests.
        """
        return user.get('data.quest.active', **kwargs)

    @staticmethod
    def get_all_quest_ids(user: User, **kwargs) -> List[str]:
        """
        Returns all game ID's the quest system is currently listening for.
        :param user:    Target user
        :param kwargs:  kwargs
        :return:        A list of all game ids that need to accounted for for this user.
        """


@load_on_startup('static_quests')
class StaticQuest(Quest, StaticGameObject):
    """
    Wrapper class for human-defined quests from DB data.
    """

    def __init__(self, db_data: dict):
        StaticGameObject.__init__(self, db_data)
        Quest.__init__(self, db_data)


@Effect.type('qu')
def review_quest_objectives(user: User, effect_data: dict, **kwargs):
    if 'updated_id' not in kwargs or 'updated_value' not in kwargs:
        raise Exception(f"This effect should always be called on update but did not receive any 'updated_id' kwarg.")

    update_id = kwargs['updated_id']
    new_value = kwargs['updated_value']

    # Bulk update dict for a $set data update for quest data.
    update_data = dict()

    # An ID relevant to at least one quest has been updated. Propagate the update to all quests
    active_quest_dict = user.get('quest._active', **kwargs)
    check_for_completion_quests = list()
    for quest_id in active_quest_dict:
        obj_index = 0

        for objective_data in active_quest_dict[quest_id]['current_objectives']:
            obj_changed = False
            cond_index = 0
            for condition_data in objective_data['conditions']:
                condition = Condition(condition_data)
                if condition.cares_for(update_id):
                    new_completion = condition.current_completion(new_value)
                    update_data[f'{quest_id}.current_objectives.{obj_index}.conditions.{cond_index}.state'] = new_completion
                    # Also update local copy to make summing up for main state easier
                    condition_data['state'] = new_completion
                    obj_changed = True
                cond_index += 1
            if obj_changed:
                # Calculate new objective completion.
                objective_state = sum([c_data['state'] for c_data in objective_data['conditions']]) / len(objective_data['conditions'])
                update_data[f"{quest_id}.current_objectives.{obj_index}.state"] = objective_state
                objective_data['state'] = objective_state
                if objective_state == 1:
                    check_for_completion_quests.append(quest_id)
            obj_index += 1

    if update_data:
        user.update('data.quest.active', update_data, is_bulk=True, **kwargs)

    for quest_id in check_for_completion_quests:
        if all([obj['state'] == 1 for obj in active_quest_dict[quest_id]['current_objectives']]):
            user.get(f"quest.{quest_id}").progress_quest(user, **kwargs)


@application_test(name='Give Quest', category='Default')
def give_quest(quest_id: str, target_username: str):
    result = GameResponse()
    if not User.user_exists(target_username):
        result.add_fail_msg(f'Cannot find user {target_username}')
    target_user = load_user(target_username)
    # Get quest and give to user.
    quest = target_user.get(quest_id)

    quest.initialize_for(target_user)

    return result
