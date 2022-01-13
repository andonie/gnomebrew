import copy
import re
from bisect import bisect_left
from datetime import datetime
from os.path import join
from typing import List, Dict

from flask import render_template

from gnomebrew import mongo
from gnomebrew.game.event import Event
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.user import get_resolver, update_resolver, id_update_listener
from gnomebrew.game.user import User
from gnomebrew.game.objects.game_object import StaticGameObject, load_on_startup, render_object
from gnomebrew.game.util import css_friendly, get_id_display_function


@get_resolver('attr')
def attr(game_id: str, user: User, **kwargs):
    """
    Evaluates an attribute for this user taking into account all unlocked upgrades.
    :param user:
    :param game_id: An attribute ID, e.g. 'attr.well.slots'
    :return: The result of the evaluation:
    """
    splits = game_id.split('.')
    # Read out attribute at data location and return:
    return user.get(f"data.special.attr.{'.'.join(splits[1:])}", **kwargs)


_approved_attr_post_splits = ['station', 'quest_data']

@update_resolver('attr')
def update_attr(user: User, game_id: str, update, **kwargs):
    """
    Updates a user's attribute.
    Attributes are variables that are expected to change (in most cases improve) over time, e.g. in *upgrades*.
    Due to the

    :param user:            Target User
    :param game_id:         Target ID
    :param update:          Update Data
    :keyword mongo_command: The mongo update command. By default is `'$inc'` due to improvements being the typical
                            use case for attribute changes.
    :return:            ~~
    """
    # Check Input
    splits = game_id.split('.')
    if splits[1] not in _approved_attr_post_splits:
        raise Exception(f"Malformatted ID: {game_id}")

    # Ensure The appropriate `mongo_command` is set, if not manually, make it INC instead of SET
    if 'mongo_command' not in kwargs:
        kwargs['mongo_command'] = '$inc'

    # Update attribute data location
    return user.update(f"data.special.attr.{'.'.join(splits[1:])}", update, **kwargs)


@id_update_listener(r'^attr\.\w+(\.\w+)*$')
def forward_attr_update_to_ui(user: User, data: dict, game_id: str, **kwargs):
    """
    Called whenever an `attr.<?>` ID is updated. Forwards the update to the frontend.
    :param user:        Target user.
    :param data:        Update Data
    :param game_id:     Target ID
    :param kwargs:
    """
    if 'command' in kwargs:
        update_type = 'inc' if kwargs['command'] == '$inc' else 'set'
    else:
        update_type = 'set'

    updated_element = { css_friendly(game_id): {
        'data': data[game_id],
        'display_fun': get_id_display_function(game_id)
    }}

    user.frontend_update('update', {
        'update_type': update_type,
        'updated_elements': updated_element
    })


def generate_complete_slot_dict(game_id: str, user: User, **kwargs) -> Dict[str, List[dict]]:
    """
    Behavior for `slots._all` feature.
    :param game_id: game ID that resulted in this call.
    :param user:    calling user.
    :param kwargs:
    :return:        a dict mapping all known stations with slots to a list representing their current slot allocation.
    """
    ret = dict()
    mongo_result = {x['_id']: x['etas'] for x in mongo.db.events.aggregate([{'$match': {
        'target': user.username,
        'due_time': {'$gt': datetime.utcnow()}
    }}, {'$group': {'_id': '$station', 'etas': {'$push': {
        'due': '$due_time',
        'since': '$since',
        'slots': '$slots',
        'effect': '$effect',
        'recipe': '$recipe_id',
        'event_id': '$event_id'
    }}}}])}
    station_list = [user.get(station_id) for station_id in user.get('data.special.stations')]
    for station in station_list:
        max_slots = user.get(f"attr.{station.get_id()}.slots", default=0, **kwargs)
        if max_slots:
            # _station is slotted. Add the necessary input to return value
            ret[station.get_id()] = list()
            if station.get_id() in mongo_result:
                # By Default, add the implicit occupied state
                for item in mongo_result[station.get_id()]:
                    item['state'] = 'occupied'
                ret[station.get_id()] = mongo_result[station.get_id()] + (
                            [{'state': 'free'}] * (max_slots - len(mongo_result[station.get_id()])))
            else:
                ret[station.get_id()] = [{'state': 'free'}] * max_slots

    return ret


_special_slot_behavior = {
    '_all': generate_complete_slot_dict
}


@get_resolver('slots')
def slots(game_id: id, user: User, **kwargs) -> List[dict]:
    """
    Calculates slot data for a given station.

    :param user         Target user
    :param game_id:     Target ID, e.g. 'slots.well'
    :return:            Target ID's result as a list of

    """
    splits = game_id.split('.')

    # Interpret the game_id input
    if splits[1] in _special_slot_behavior:
        return _special_slot_behavior[splits[1]](game_id, user, **kwargs)

    # Default: slots of a station
    station_id = '.'.join(splits[1:])
    active_events = mongo.db.events.find({
        'target': user.username,
        'station': station_id,
        'due_time': {'$gt': datetime.utcnow()}
    }, {
        "_id": 0,
        "effect": 1,
        "due_time": 1,
        "slots": 1,
        "recipe_id": 1,
        "since": 1,
        "event_id": 1
    })

    slot_list = list()
    total_slots_allocated = 0

    for recipe_event in active_events:
        slot_list.append({
            'state': 'occupied',
            'due': recipe_event['due_time'],
            'since': recipe_event['since'],
            'slots': recipe_event['slots'],
            'effect': recipe_event['effect'],
            'recipe': recipe_event['recipe_id'],
            'event_id': recipe_event['event_id']
        })
        total_slots_allocated += recipe_event['slots']

    # Fill up list with empty slots with appropriate empty slots
    max_slots = user.get(f'attr.{station_id}.slots', **kwargs)
    slot_list += [{
        'state': 'free'
    }] * (max_slots - total_slots_allocated)

    return slot_list
