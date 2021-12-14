import copy
from os.path import join
from typing import List

from flask import render_template

from gnomebrew.game.event import Event
from gnomebrew.game.objects.effect import Effect
from gnomebrew.game.objects.game_object import load_on_startup, StaticGameObject
from gnomebrew.game.selection import selection_id
from gnomebrew.game.user import User, get_resolver, html_generator
from gnomebrew.game.util import global_jinja_fun, css_friendly
from gnomebrew.logging import log_exception, log


@get_resolver('station')
def station(game_id: str, user: User, **kwargs):
    return StaticGameObject.from_id(game_id)


@load_on_startup('stations')
class Station(StaticGameObject):
    """
    Station Wrapper Class
    """

    def __init__(self, mongo_data):
        super().__init__(mongo_data)

    def generate_html(self, user):
        """
        Generate the HTML to interact with the station in a web interface.
        :param user: user for which this station HTML is being generated.
        :return:
        """
        pass

    def get_base_value(self, attr):
        """
        Used for `attr` evaluation. Technically this method is redundant since it's equivalent to `get_static_value` in
        `StaticGameObject`. It stays in the code for now in case the `attr` evaluation gets more fancy.
        """
        assert self._data[attr]
        return self._data[attr]

    def initialize_for(self, user, **kwargs):
        """
        Initializes this station for a given user with the station's `init_data`.
        :param user:    a user. We assume this user has not yet had data connected to this station.
        """
        log('data', f'Initializing {self.name()}', f"usr:{user.get_id()}")
        # Add station ID to station list to ensure it's recognized as an active station
        user.update("data.special.stations", self.get_id(), mongo_command="$push", **kwargs)

        update_data = dict()
        # If this station has data to add,
        # Add new station in user data with default values
        if 'init_data' in self._data:
            init_data = copy.deepcopy(self._data['init_data'])
            update_data[self.get_id()] = init_data

        if 'init_attr' in self._data:
            # I must initialize attributes
            for attr_name in self._data['init_attr']:
                update_data[f"special.attr.{self.get_id()}.{attr_name}"] = self._data['init_attr'][attr_name]
        user.update(f"data", update_data, is_bulk=True, **kwargs)

        # If this station has an init-effect to be executed, do so now.
        if 'init_effect' in self._data:
            for effect in [Effect(data) for data in self._data['init_effect']]:
                effect.execute_on(user, **kwargs)

        # Finally, send the respective update to all active frontends
        user.frontend_update('ui', {
            'type': 'add_station',
            'station': self.get_id()
        })

    def has_slots(self) -> bool:
        """
        :return: `True`, if this station has slots to calcuate for. Otherwise `False`.
        """
        return 'slots' in self._data

    def has_init_recipes(self) -> bool:
        return 'init_data' in self._data and 'recipes' in self._data['init_data']

    def has_special_ui(self) -> bool:
        """
        :return:    `True`, if this station has a special UI. Otherwise `False`
        """
        return 'special_ui' in self._data

    def get_current_recipe_list(self, user: User, **kwargs) -> List['Recipe']:
        """
        Generates a list of `Recipe` handler objects that represent all recipes this station currently has available
        for a given user.
        :param user:        Target user.
        :param kwargs:      kwargs
        :return:            The current list of recipes available to `user`
        """
        return [user.get(recipe_id) for recipe_id in user.get(f"data.{self.get_id()}.recipes")]

@Effect.type('add_station')
def add_station(user: User, effect_data: dict, **kwargs):
    """
    Fired when a new station is to be added to a user's game data.
    :param user:        a user
    :param effect_data: effect data dict formatted as `effect_data['station'] = station_id`
    """
    if 'station' not in effect_data:
        raise Exception(f"Missing element 'station'")

    station_id = effect_data['station']
    try:
        station: Station = user.get(station_id, **kwargs)
    except Exception as a:
        # Load the respective station and initialize it for this user
        log_exception('effect', a, 'Could not find station')
        return

    # Initialize Station
    station.initialize_for(user)


@Effect.type('remove_station')
def remove_station(user: User, effect_data: dict, **kwargs):
    """
    Removes a station from the user's game data.
    :param user:            target user
    :param effect_data:     Effect data. Expecting ID of station to remove as 'station'
    :param kwargs:          kwargs
    """
    station_id = effect_data['station']

    # If this is NOT quest station, raise an exception for the moment
    if not station_id.startswith('quest_data'):
        raise Exception(f"A non-quest station ({station_id}) was asked to be removed. This is a non supported feature.")

    # Remove Station ID from station list
    user.update("data.special.stations", station_id, mongo_command='$pull', **kwargs)

    # Remove the station from frontends
    user.frontend_update('ui', {
        'type': 'remove_element',
        'selector': f"#{css_friendly(station_id)}"
    })


@html_generator(base_id='html.station', is_generic=True)
def generate_station_html(game_id: str, user: User, **kwargs):
    """
    Generates HTML for a station in game.
    :param game_id: An Id starting with 'html.station'
    :param user:    A user
    :return:        Most appropriate HTML rendering of the station.
    """
    splits = game_id.split('.')
    if 'station' not in kwargs:
        kwargs['station'] = Station.from_id(f"station.{splits[2]}")
    if 'slots' not in kwargs:
        kwargs['slots'] = user.get('slots._all', **kwargs)
    res = render_template(join("stations", splits[2] + ".html"), **kwargs)
    return res


@global_jinja_fun
def get_unlocked_station_list(user: User, **kwargs) -> List[Station]:
    """
    Convenience function for playscreen rendering. Returns
    :return:
    """
    return [user.get(station_id, **kwargs) for station_id in user.get("data.special.stations")]


@selection_id('selection.station.collapsed', is_generic=True)
def process_alchemy_recipe_selection(game_id: str, user: User, set_value, **kwargs):
    # Check Game ID formatting
    splits = game_id.split('.')
    if len(splits) != 4:
        raise Exception(f'Game ID {game_id} is malformatted.')

    target_location = f'data.special.station_selections.{splits[3]}'

    if set_value:
        user.update(target_location, set_value)
    else:
        # Read out the current selection.
        return user.get(target_location, default=False, **kwargs)

