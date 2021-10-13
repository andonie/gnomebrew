"""
Implements basic quest logic in Gnomebrew.
Governed by the 'quest'-ID-prefix
"""
import copy
from typing import List, Callable

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.condition import Condition
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.game_object import StaticGameObject, load_on_startup, GameObject, PublicGameObject, \
    render_object
from gnomebrew.game.objects.objective import Objective
from gnomebrew.game.testing import application_test
from gnomebrew.game.user import User, get_resolver, load_user, id_update_listener, html_generator
from gnomebrew.game.util import generate_uuid, css_friendly


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
            'quest_id': self._data['game_id'],
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
        new_listener_ids = set(next_state.get_all_target_ids())

        user.register_id_listeners(list(new_listener_ids), {'effect_type': 'qu', 'quest': f"{self.get_minimized_id()}.{state_id}"}, starts_with=True)

        # Initialize next state.
        next_state.initialize_for(user, self.get_minimized_id())

        # Ensure that the user reloads their quest to have the correct information.
        user.frontend_update('ui', {
            'type': 'reload_element',
            'element': f'quest-objectives.{self.get_minimized_id()}'
        })

    def progress_quest(self, user: User, **kwargs):
        """
        Called when the Quest system detects all conditions of all current objectives to be met.
        Moves the quest into the next state.
        :param user:    Target user.
        :param kwargs:  kwargs
        """
        last_state = user.get(f"data.quest.active.{self.get_minimized_id()}.current_state", **kwargs)
        # CLEAN UP CURRENT STATE
        # Remove all listeners from my the current quest state before transitioning
        user.remove_from_id_listeners(lambda data: data['quest'] == f"{self.get_minimized_id()}.{last_state}")

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




    def _generate_current_objective_infos(self) -> List:
        """
        Generates a view of infos that can be rendered to display the current objectives progress.
        :return:    A list representing the infos to be rendered.
        """
        objective_infos = list()
        for objective_data in self._data['objectives']:
            for condition in [Condition(data) for data in objective_data['conditions']]:
                if condition.has_display():
                    objective_infos.append(condition.generate_info())

        return objective_infos

    def generate_user_objective_data(self, user: User) -> dict:
        """
        Generates the current user's initial objective data.
        :param user:    target user.
        :return         A bulk update dict mapping the uuid's of current quest objectives to their respective data.
        """

        update_dict = dict()

        for obj in self._data['objectives']:
            objective_data = dict()
            core_quest_obj = QuestObjective(obj)
            objective_data['name'] = obj['name']
            objective_data['description'] = obj['description']
            objective_data['state'] = 0
            objective_data['infos'] = core_quest_obj.generate_infos()
            objective_data['conditions'] = core_quest_obj.generate_playerdata_conditions()
            uuid = generate_uuid()
            objective_data['objective_id'] = uuid
            update_dict[uuid] = objective_data

        return update_dict

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


class QuestObjective(GameObject):
    """
    Wraps a Quest Objective.
    """

    def __init__(self, data):
        GameObject.__init__(self, data)

    def generate_infos(self) -> List[List[str]]:
        """
        Generates this objective's info to be displayed under the objective.
        :return:    A list of lists, representing `render_info` data.
        """
        info_list = list()
        for condition in [Condition(data) for data in self._data['conditions']]:
            if condition.has_display():
                info_list.append(condition.generate_info())
        return info_list

    def generate_playerdata_conditions(self) -> dict:
        """
        Generates a condition object that can be stored in player data as conditions for this
        :param condition_raw:   Raw condition JSON data. Expected to be a deepcopy
        :return:    JSON data ready to be added to user data.
        """
        player_conditions = dict()
        for condition_data in self._data['conditions']:
            player_data = copy.deepcopy(condition_data)
            player_data['state'] = 0
            uuid = generate_uuid()
            player_data['condition_id'] = uuid
            player_conditions[uuid] = player_data
        return player_conditions


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

    # An ID relevant to at least one quest has been updated. Propagate the update to the relevant quest objectives.
    quest_splits = effect_data['quest'].split('.')
    quest_id = quest_splits[0]
    objective_dict = user.get(f"data.quest.active.{quest_id}.current_objectives", **kwargs)

    check_for_completion = False

    for o_id in objective_dict:
        objective_data = objective_dict[o_id]
        obj_changed = False
        for c_id  in objective_data['conditions']:
            condition_data = objective_data['conditions'][c_id]
            condition = Condition(condition_data)
            if condition.cares_for(update_id):
                new_completion = condition.current_completion(new_value)
                update_data[f"{quest_id}.current_objectives.{objective_data['objective_id']}.conditions.{condition_data['condition_id']}.state"] = new_completion
                # Also update local copy to make summing up for main state easier
                condition_data['state'] = new_completion
                obj_changed = True
        if obj_changed:
            # Calculate new objective completion.
            objective_state = sum([objective_data['conditions'][c_id]['state'] for c_id in objective_data['conditions']]) / len(objective_data['conditions'])
            update_data[f"{quest_id}.current_objectives.{objective_data['objective_id']}.state"] = objective_state
            objective_data['state'] = objective_state
            if objective_state == 1:
                check_for_completion = True

    if update_data:
        user.update('data.quest.active', update_data, is_bulk=True, **kwargs)

    if check_for_completion and all([objective_dict[obj]['state'] == 1 for obj in objective_dict]):
        user.get(f"quest.{quest_id}").progress_quest(user, **kwargs)


@id_update_listener(r'^data\.quest\.active\.[\w:]+\.current_objectives\.[\w:]+\.state')
def react_to_objective_state_change(user: User, data: dict, game_id: str, **kwargs):
    """
    Called whenever a user's current_objective state for any quest changes.
    :param user:        Target user who's data changed.
    :param data:        The new data value as given to MongoDB.
    :param game_id:     The updated full Game ID
    :param kwargs:      kwargs
    """
    # An objective state has been updated. Is the update worthy to
    objective_state = data[game_id]
    if objective_state == 1:
        # This objective is complete. Make sure the frontend has this objective marked as met.
        splits = game_id.split('.')
        user.frontend_update('ui', {
            'type': 'update_class',
            'action': 'add_class',
            'target': f'#obj-indicator-{css_friendly(splits[5])}',
            'class_data': 'obj-achieved'
        })


@html_generator(base_id='html.quest-objectives', is_generic=True)
def render_quest_objective_html(game_id: str, user: User, **kwargs):
    return render_object('render.objective_list', data=user.get(f"data.quest.active.{game_id.split('.')[2]}.current_objectives", **kwargs))


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
