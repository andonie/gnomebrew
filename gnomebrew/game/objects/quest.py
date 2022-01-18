"""
Implements basic quest logic in Gnomebrew.
Governed by the 'quest'-ID-prefix
"""
import copy
from os.path import join, isdir, isfile
from typing import List, Callable

from flask import render_template, render_template_string

import gnomebrew.game.objects.effect
from gnomebrew import app
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects import Station, Generator, Environment, Person
from gnomebrew.game.objects.request import PlayerRequest
from gnomebrew.game.objects.condition import Condition
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.item import Item
from gnomebrew.game.objects.recipe import Recipe
from gnomebrew.game.objects.entity import Entity
from gnomebrew.game.objects.game_object import StaticGameObject, load_on_startup, GameObject, DynamicGameObject, \
    render_object
from gnomebrew.game.objects.objective import Objective
from gnomebrew.game.testing import application_test
from gnomebrew.game.user import User, get_resolver, load_user, id_update_listener, html_generator, get_postfix, \
    update_resolver
from gnomebrew.game.util import generate_uuid, css_friendly, render_info, is_game_id_formatted


@DynamicGameObject.setup(dynamic_collection_name='generated_quests', game_id_prefix='quest', dynamic_buffer=False)
@load_on_startup('scripted_quests')
class Quest(DynamicGameObject):
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
        qid = self.get_minimized_id()
        quest_data = user.get("data.station.quest", **kwargs)

        if qid in quest_data['active']:
            raise Exception(f"Quest {qid} is already active.")

        # If this quest ID is currently in `available`, remove now.
        if qid in quest_data['available']:
            user.update(f"data.station.quest.available.{qid}", '', mongo_command='$unset', **kwargs)

        # Generate a basic generator in case this quest has variables
        # TODO context sensitive generator (environment & seed) instead of random seed & empty environment
        gen = Generator(Generator.true_random_seed(), Environment.empty())

        # Update User Data to include this as an active quest and have the storage's `quest_data` fields include this
        # category's ID:
        update_data = dict()
        # Base Quest Data
        update_data[f"quest.active.{self.get_minimized_id()}"] = {
            'quest_id': self._data['game_id'],
            'name': self._data['name'],
            'description': self._data['description'],
            'foldout': self._data['foldout'],
            'icon': self._data['icon'],
            'slots': self._data['slots'] if 'slots' in self._data else 0,
            'data': self.generate_initial_quest_data(gen)
        }

        # Update for Storage
        update_data[f"storage.content.quest_data.{self.get_minimized_id()}"] = {
            'item': {}
        }

        user.update("data.station", update_data, is_bulk=True, **kwargs)

        # Transition into the first quest state
        self.transition_state(user, self._data['quest_start'], **kwargs)

        # Once all is done, add this quest to the user's frontend.
        user.frontend_update('ui', {
            'type': 'append_element',
            'selector': "#quests-active",
            'element': render_object('render.active_quest',
                                     data=user.get(f"data.station.quest.active.{self.get_minimized_id()}"))
        })

    def transition_state(self, user: User, state_id: str, **kwargs):
        """
        Transitions from any current state into a given state.
        :param user         Target user
        :param state_id:    The ID of the state to transition to as used in the quest data.
        """
        next_state = QuestState(self._data['quest_flow'][state_id])
        new_listener_ids = set(next_state.get_all_target_ids())

        user.register_id_listeners(list(new_listener_ids),
                                   {'effect_type': 'qu', 'quest': f"{self.get_minimized_id()}.{state_id}"},
                                   starts_with=True)
        user.update(f"data.station.quest.active.{self.get_minimized_id()}.current_state", state_id, **kwargs)
        # Initialize next state.
        next_state.initialize_for(user, self.get_minimized_id())

        # Ensure that the user reloads their quest to have the correct information.
        user.frontend_update('ui', {
            'type': 'reload_element',
            'element': f'quest.objectives.{self.get_minimized_id()}'
        })

    def progress_quest(self, user: User, **kwargs):
        """
        Called when the Quest system detects all conditions of all current objectives to be met.
        Moves the quest into the next state.
        :param user:    Target user.
        :param kwargs:  kwargs
        """
        last_state = user.get(f"data.station.quest.active.{self.get_minimized_id()}.current_state", **kwargs)
        # CLEAN UP CURRENT STATE
        # Remove all listeners from my the current quest state before transitioning
        user.remove_from_id_listeners(
            lambda data: 'quest' in data and data['quest'] == f"{self.get_minimized_id()}.{last_state}")

        if 'on_complete' not in self._data['quest_flow'][last_state]:
            raise Exception(f"Quest {self} does not have on_complete data at state {last_state}")
        next_state = self._data['quest_flow'][last_state]['on_complete']

        # Check if next_state indicates the quest is over
        if next_state == '_complete':
            # Quest is completed.
            self.on_complete(user, **kwargs)
        else:
            self.transition_state(user, next_state, **kwargs)
            user.frontend_update('ui', {
                'type': 'player_info',
                'target': '#gb-global-info',
                'content': render_info(user, 'station.quest', 'progress'),
                'duration': 100
            })

    def on_complete(self, user: User, **kwargs):
        """
        Called when this quest is completed. Resolves any pending actions such as rewards/effects and then removes all
        quest data from the `data.station.quest` region.
        :param user:        Target user.
        :param kwargs:      kwargs
        """
        # Execute any reward effects
        if 'reward' in self._data:
            for effect in [Effect(r_data) for r_data in self._data['reward']]:
                effect.execute_on(user)

        # Remove all traces from this quest from the user data
        user.update(f"data.station.quest.active.{self.get_minimized_id()}", "", mongo_command='$unset', **kwargs)

        # Remove any traces of quest items (from storage) and quest stations (from station list)
        station_list = user.get("data.special.stations", **kwargs)
        user.update("data.special.stations",
                    list(filter(lambda s_id: not s_id.startswith(f"quest_data.{self.get_minimized_id()}.station"),
                                station_list)), **kwargs)
        # Remove any quest items
        user.update(f"data.station.storage.content.quest_data.{self.get_minimized_id()}", '', mongo_command='$unset',
                    **kwargs)

        # Remove this quest from the quest data
        user.frontend_update('ui', {
            'type': 'remove_element',
            'selector': f"#{css_friendly(self.get_id())}-active"
        })

        # Add this quest to user statistics
        user.update('stat.quests_finished', self.get_id(), mongo_command='$push')

    def get_station_id_list(self) -> List[str]:
        """
        Convenience function. Returns a list of all station IDs that are associated with this quest.
        :return:    A list of station IDs. Can be empty if no stations are associated with this quest.
        """
        if 'data' not in self._data or 'station' not in self._data['data']:
            return []
        else:
            return list(self._data['station'].keys())

    # Formatting Helpers
    def generate_available_user_data(self) -> dict:
        """
        Generates this quest's data for the `available` user storage to be possibly selected.
        :return:    A dict representing this quest at `data.quest.available.<quid>`
        """
        av_data = dict()
        av_data['quest_id'] = self._data['game_id']
        av_data['name'] = self._data['name']
        av_data['description'] = self._data['description']
        av_data['foldout'] = self._data['available_foldout']
        av_data['type'] = self._data['type']
        av_data['icon'] = self._data['icon']
        av_data['challenge_infos'] = self.generate_challenge_infos()
        av_data['reward_infos'] = self.generate_reward_infos()

        return av_data

    def generate_challenge_infos(self) -> list:
        """
        Generates the infos this quest would display as an available quest. This includes infos such as
        rewards, difficulties, etc.
        :return:    The infos to be rendered for this quest when available for taking.
        """
        infos = list()
        # Tier Info
        infos.append(StaticGameObject.from_id(f"tier.{self._data['tier']}").generate_info())

        return infos

    def generate_reward_infos(self) -> list:
        """
        Generates info data to display to a user as they see the quest as available.
        :return:    A list of lists representing player_info data.
        """
        infos = list()
        for reward_effect in [Effect(e_d) for e_d in self._data['reward']]:
            if reward_effect.has_display():
                for info in reward_effect.generate_infos():
                    infos.append(info)
        return infos

    no_id_quest_data_entities = ['_flags']

    def generate_initial_quest_data(self, gen: Generator) -> dict:
        """
        Generates this quest's intial data.
        Quests can contain various data from quest entities (quest stations/recipes/items/etc.) to quest variables
        (e.g. player quest decisions). All of this data is stored in `data.quest.active.<quid>.data`.
        This function generates the this quest's initial data.
        :param gen  Generator to use for blueprint evaluation
        :return:    Quest's initial `data`.
        """
        quest_data = dict()
        # Quest internal data
        quest_data['_flags'] = {}

        # Quest Entities visible to player:
        if 'data' in self._data:
            for entity_class in self._data['data']:
                # Evaluate each entity as a blueprint to individualize where possible
                quest_data[entity_class] = gen.evaluate_blueprint(copy.deepcopy(self._data['data'][entity_class]))
                if entity_class not in Quest.no_id_quest_data_entities:
                    # Add generated Game IDs (on `quest_data` prefix)
                    for entity_name in quest_data[entity_class]:
                        quest_data[entity_class][entity_name][
                            'game_id'] = f"quest_data.{self.get_minimized_id()}.{entity_class}.{entity_name}"

        return quest_data


# Quest Data Validation
Quest.validation_parameters(('game_id', str), ('name', str), ('description', str), ('foldout', str), ('game_id', str),
                            ('slots', int), ('icon', str), ('data', dict), ('quest_start', str), ('tier', str),
                            ('reward', list), ('quest_flow', dict))


@Quest.validation_function()
def validate_quest_data(data: dict, response: GameResponse):
    """
    Validates a quest data object.
    Given the complexity of quests relative to most other dataclasses in the game, this valilidation has more involved
    computation than most validations, involving cascading validations.
    :param data:        Complete JSON data that's supposed to be validated as a quest data object.
                        `validation_parameters` has been taken into account already.
    :param response:    Response object to log fails with.
    """
    # Does 'quest_start' lead somewhere? Check 'quest_flow'
    if data['quest_start'] not in data['quest_flow']:
        response.add_fail_msg(f"<%quest_start%> ({data['quest_start']}) is not found in <%quest_flow%>")

    # Evaluate each element of the `reward` data list as an effect and validate
    for effect in [Effect(e_data) for e_data in data['reward']]:
        response.append_into(effect.validate())

    # Validate each element in `quest_flow` as an individual quest state
    for quest_state in [QuestState(qs_data) for qs_data in data['quest_flow'].values()]:
        response.append_into(quest_state.validate())

    # TODO possible: Validate interconnections in this object here (e.g. quest-states' `on_complete`)


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
        user.update(f"data.station.quest.active.{quest_id}.current_objectives", self.generate_user_objective_data(user),
                    **kwargs)

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
    @DynamicGameObject.special_id_get('quest._active')
    def get_all_active_quests(user: User, game_id: str, **kwargs) -> dict:
        """
        Special ID `quest._active` returns a list of all active quests as data.
        :param user:    target user
        :param game_id: `quest._active`
        :param kwargs:  kwargs
        :return:        A `dict` with all active quests.
        """
        return user.get('data.station.quest.active', **kwargs)


# Validating Quest State Data

QuestState.validation_parameters(('objectives', list), ('effect', list), ('on_complete', object))

@QuestState.validation_function()
def validate_quest_state_data(data: dict, response: GameResponse):
    """
    Validates a quest state data object.
    :param data:        Complete JSON data that's supposed to be validated as a quest state data object.
                        `validation_parameters` has been taken into account already.
    :param response:    Response object to log fails with.
    """
    # each element in `effect` is a an effect to be validated
    for effect in [Effect(e_data) for e_data in data['effect']]:
        response.append_into(effect.validate())

    # each element in `objectives` is an objective to be validated
    for objective in [Objective(o_data) for o_data in data['objectives']]:
        response.append_into(objective.validate())


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


# Quest Objective Data Validation

QuestObjective.validation_parameters(('name', str), ('description', str), ('conditions', list))

@load_on_startup('static_quests')
class StaticQuest(Quest, StaticGameObject):
    """
    Wrapper class for human-defined quests from DB data.
    """

    def __init__(self, db_data: dict):
        StaticGameObject.__init__(self, db_data)
        Quest.__init__(self, db_data)


# Copy Validation Scheme
StaticQuest.use_validation_scheme_of(Quest)

best_entity_subtype = {
    'person': Person
}

def _data_to_best_entity(data: dict) -> Entity:
    if data['entity_class'] in best_entity_subtype:
        return best_entity_subtype[data['entity_class']](data)
    else:
        return Entity(data)

questdata_object_types = {
    'station': Station,
    'item': Item,
    'recipe': Recipe,
    'entity': _data_to_best_entity,
    '_flags': lambda x: x,
}


def _validate_questdata_splits(splits: List[str], user: User):
    """
    :param splits: Splits of a `quest_data` Game ID
    :param user     Target user
    :raises         An exception if the ID is obviously malformatted
    """
    if len(splits) != 4 or splits[2] not in questdata_object_types:
        raise Exception(f"Malformatted ID: {splits=}")
    if splits[1] not in user.get("data.station.quest.active"):
        raise Exception(f"Quest {splits[1]} currently not taken by user.")


@get_resolver('quest_data', dynamic_buffer=True)
def get_quest_data(user: User, game_id: str, **kwargs):
    splits = game_id.split('.')
    _validate_questdata_splits(splits, user)
    on_location = user.get(f"data.station.quest.active.{splits[1]}.data.{'.'.join(splits[2:])}", **kwargs)
    if on_location:
        return questdata_object_types[splits[2]](on_location)
    else:
        raise Exception(f"Cannot find object on location {game_id}")


@update_resolver('quest_data')
def resolve_quest_update(user: User, game_id: str, update, **kwargs):
    """
    Updates player quest data.
    """
    splits = game_id.split('.')
    _validate_questdata_splits(splits, user)
    return user.update(f"data.station.quest.active.{splits[1]}.data.{'.'.join(splits[2:])}", update, **kwargs)


@Effect.type('qu', ('quest', str))
def review_quest_objectives(user: User, effect_data: dict, **kwargs):
    if 'updated_id' not in kwargs or 'updated_value' not in kwargs:
        raise Exception(f"This effect should always be called on update but did not receive any 'updated_id' kwarg.")

    # Remove is_bulk flag that could be set based on the update that triggered this
    if 'is_bulk' in kwargs:
        del kwargs['is_bulk']

    update_id = kwargs['updated_id']
    new_value = kwargs['updated_value']

    # Bulk update dict for a $set data update for quest data.
    update_data = dict()

    # An ID relevant to at least one quest has been updated. Propagate the update to the relevant quest objectives.
    quest_splits = effect_data['quest'].split('.')
    quest_id = quest_splits[0]
    objective_dict = user.get(f"data.station.quest.active.{quest_id}.current_objectives", **kwargs)

    check_for_completion = False

    for o_id in objective_dict:
        objective_data = objective_dict[o_id]
        obj_changed = False
        for c_id in objective_data['conditions']:
            condition_data = objective_data['conditions'][c_id]
            condition = Condition(condition_data)
            if condition.cares_for(update_id):
                new_completion = condition.current_completion(new_value, is_update=True)
                update_data[
                    f"{quest_id}.current_objectives.{objective_data['objective_id']}.conditions.{condition_data['condition_id']}.state"] = new_completion
                # Also update local copy to make summing up for main state easier
                condition_data['state'] = new_completion
                obj_changed = True
        if obj_changed:
            # Calculate new objective completion.
            objective_state = sum(
                [objective_data['conditions'][c_id]['state'] for c_id in objective_data['conditions']]) / len(
                objective_data['conditions'])
            update_data[f"{quest_id}.current_objectives.{objective_data['objective_id']}.state"] = objective_state
            objective_data['state'] = objective_state
            if objective_state == 1:
                check_for_completion = True

    if update_data:
        user.update('data.station.quest.active', update_data, is_bulk=True, **kwargs)

    if check_for_completion and all([objective_dict[obj]['state'] == 1 for obj in objective_dict]):
        user.get(f"quest.{quest_id}").progress_quest(user, **kwargs)


@Effect.type('add_available_quests', ('quest_ids', list))
def add_available_quest(user: User, effect_data: dict, **kwargs):
    """
    This effect adds a number of quest to the given user's list of available quests.
    :param user:            Target user.
    :param effect_data:     Effect data
    :param kwargs:          kwargs
    """
    if 'quest_ids' not in effect_data or len(effect_data['quest_ids']) == 0:
        raise Exception(f"No quest_ids was given for command.")

    quest_data = user.get("data.station.quest", **kwargs)
    update_data = dict()
    for quest_id in effect_data['quest_ids']:
        splits = quest_id.split('.')
        if len(splits) != 2 or splits[0] != 'quest':
            raise Exception(f"Malformatted quest_id: {quest_id}")
        target_id_mini = splits[1]

        if target_id_mini in quest_data['active']:
            raise Exception(f"Quest {target_id_mini} is already active.")

        if target_id_mini in quest_data['available']:
            raise Exception(f"Quest {target_id_mini} is already available.")

        # All checks passed. get the quest object and get its rendered available-data rendering
        update_data[target_id_mini] = user.get(quest_id).generate_available_user_data()

    user.update(f"data.station.quest.available", update_data, is_bulk=True, **kwargs)

    # Update frontend to reflect the added quests
    for quest_id in effect_data['quest_ids']:
        user.frontend_update('ui', {
            'type': 'append_element',
            'selector': "#quests-available",
            'element': render_object('render.available_quest',
                                     data=user.get(f"data.station.quest.available.{quest_id.split('.')[1]}"))
        })


@Effect.type_info('add_available_quests')
def render_available_quest_info(effect_data: dict) -> List[List[str]]:
    """
    Renders an info element for `add_available_quests` effects.
    :param effect_data:     Effect data.
    :return:                Relevant info data.
    """
    # TODO needs proper implementation
    return [['New', 'tier.tier_1']]


@Effect.type('add_active_quest', ('quest_id', str))
def start_quest_immediately(user: User, effect_data: dict, **kwargs):
    """
    Unlike `add_available_quest`, this function adds a quest immediately to the list of active quests.
    This effect does normally not do any checks (e.g. whether the user is allowed to take on this quest or if there
    are enough available slots to take on this mission.
    :param user:            Target user
    :param effect_data:     Effect data
    :param kwargs:          kwargs
    """
    if 'quest_id' not in effect_data:
        raise Exception(f"No quest_id was given for command.")
    splits = effect_data['quest_id'].split('.')

    if len(splits) != 2 or splits[0] != 'quest':
        raise Exception(f"Malformatted quest_id: {effect_data['quest_id']}")

    # Get the quest object for this quest and execute it
    user.get(effect_data['quest_id']).initialize_for(user, **kwargs)


@PlayerRequest.type('accept_quest', is_buffered=True)
def accept_quest(user: User, request_object: dict, **kwargs):
    """
    Reacts to a user request to accept a quest.
    If all requirements are ment, the target quest (in `request_object`) will be removed from available quests and
    the quest's active data will be written as an active quest.
    :param user:            Target user.
    :param request_object:  Request object. Expected to have `quest_id` set.
    :param kwargs:          kwargs
    :return:                Appropriate response
    """
    response = GameResponse()

    if 'quest_id' not in request_object:
        raise Exception(f"No quest_id given in {request_object=}")

    quest_id = '.'.join(request_object['quest_id'].split('.')[1:])
    quest_data = user.get('data.station.quest')

    # Check if quest is currently available and not active
    if quest_id in quest_data['active']:
        response.add_fail_msg('Quest is already active.')

    if quest_id not in quest_data['available']:
        response.add_fail_msg('Quest is not available')

    if response.has_failed():
        return response

    quest = user.get(request_object['quest_id'])

    # Check if the user has slots available still for another quest.
    current_slot_number = sum([quest_data['active'][active_data]['slots'] for active_data in quest_data['active']])
    if current_slot_number + quest.get_static_value('slots') > user.get('attr.station.quest.slots'):
        response.add_fail_msg('Not enough slots to add this quest.')
        response.player_info(None, f"Not enough capacity to execute.", 'special.at_limit')

    if response.has_failed():
        return response

    # All checks passed. Add quest to active quest list of user and remove the available quest.
    user.update(f"data.station.quest.available.{quest_id}", '', mongo_command='$unset', **kwargs)
    quest.initialize_for(user, **kwargs)

    # Update the UI to reflect the changes:
    user.frontend_update('ui', {
        'type': 'remove_element',
        'selector': f"#{css_friendly(quest.get_id())}-available"
    })

    response.succeess()
    return response


@id_update_listener(r'^data\.station\.quest\.active\.[\w:]+\.current_objectives\.[\w:]+\.state')
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
            'target': f'#obj-indicator-{css_friendly(splits[6])}',
            'class_data': 'obj-achieved'
        })


@html_generator(base_id='html.quest_data', is_generic=True)
def render_quest_data(game_id: str, user: User, **kwargs):
    """
    Responds to any request to render quest data. Given that quest data can encompass many different entities,
    this function is built to accommodate this.
    Main usage is for rendering station HTML of quest stations.
    :param game_id:     Target ID
    :param user:        Target user
    :param kwargs:      kwargs
    :return:            Appropriate HTML rendering
    """
    splits = game_id.split('.')
    quest_name = splits[2]
    station_id = game_id[5:]
    station_obj:Station = user.get(station_id, **kwargs)
    if splits[3] == 'station':
        if 'station' not in kwargs:
            kwargs['station'] = user.get(f"quest_data.{quest_name}.station.{splits[4]}", **kwargs)
        if 'slots' not in kwargs:
            kwargs['slots'] = user.get('slots._all', **kwargs)
        # Check if special Station UI exists
        station_path = join(app.config['TEMPLATE_DIR'], quest_name, f"station.{splits[4]}.html")
        if isfile(station_path):
            return render_template(station_path, **kwargs)
        else:
            if station_obj.has_static_key('html_template'):
                return render_template_string(station_obj.get_static_value('html_template'), **kwargs)
            # No template data for this quest exists, so we assume this is rendered as a pure standard station.
            return render_template(join("stations", "_station.html"), **kwargs)
    else:
        raise Exception(f"Cannot render: {game_id}")


@html_generator(base_id='html.quest.objectives', is_generic=True)
def render_quest_objective_html(game_id: str, user: User, **kwargs):
    return render_object('render.objective_list',
                         data=user.get(
                             f"data.station.quest.active.{'.'.join(game_id.split('.')[3:])}.current_objectives",
                             **kwargs))


@application_test(name='Give Quest', category='Default')
def give_quest(quest_id: str, target_username: str):
    result = GameResponse()
    if not User.user_exists(target_username):
        result.add_fail_msg(f'Cannot find user {target_username}')
    target_user = load_user(target_username)


    # Get quest and give to user.
    quest = target_user.get(quest_id)

    quest.initialize_for(target_user)

    result.log(f"Gave quest {quest.name()} to user {target_username}")

    return result
