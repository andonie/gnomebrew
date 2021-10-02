from os.path import join

from flask import render_template

from gnomebrew.game.event import Event
from gnomebrew.game.objects.static_object import load_on_startup, StaticGameObject
from gnomebrew.game.user import User, get_resolver, html_generator
from gnomebrew.game.util import global_jinja_fun


@get_resolver('station')
def station(game_id: str, user: User):
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

    def initialize_for(self, user):
        """
        Initializes this station for a given user with the station's `init_data`.
        :param user:    a user. We assume this user has not yet had data connected to this station.
        """
        # Add new station in user data with default values.
        # Also ignore the frontend, since we will manually send an add_station update to the frontend.
        user.update(f"data.{self._data['game_id'].split('.')[1]}", self._data['init_data'], suppress_frontend=True)

        # If this station has an init-effect to be executed, do so now.
        if 'init_effect' in self._data:
            from gnomebrew.game.event import Event
            for effect in self._data['init_effect']:
                Event.execute_event_effect(user, effect_type=effect, effect_data=self._data['init_effect'][effect])

    def has_slots(self) -> bool:
        """
        :return: `True`, if this station has slots to calcuate for. Otherwise `False`.
        """
        return 'slots' in self._data


@Event.register_effect
def add_station(user: User, effect_data: dict, **kwargs):
    """
    Fired when a new station is to be added to a user's game data.
    :param user:        a user
    :param effect_data: effect data dict formatted as `effect_data['station'] = station_id`
    """
    # Load the respective station and initialize it for this user
    station = StaticGameObject.from_id(effect_data['station'])
    station.initialize_for(user)

    # Send the respective update to all active frontends
    user.frontend_update('ui', {
        'type': 'add_station',
        'station': station.get_minimized_id()
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
    if 'game_data' not in kwargs:
        # Provide as much game data as necessary
        kwargs['game_data'] = {splits[1]: user.get(f"data.{splits[2]}")}
    if 'station' not in kwargs:
        kwargs['station'] = Station.from_id(f"station.{splits[2]}")
    if 'slots' not in kwargs:
        # Also provide minimal slot info
        if kwargs['station'].has_slots():
            kwargs['slots'] = {splits[2]: user.get(f'slots.{splits[2]}')}
        else:
            kwargs['slots'] = dict()
    res = render_template(join("stations", splits[2] + ".html"), **kwargs)
    return res


@global_jinja_fun
def has_station_special_ui(station_name: str) -> bool:
    """
    Jinja Utility. Checks if a given station has a special position withing Gnomebrew's UI.
    :param station_name:    A simple station name, e.g. 'well'
    :return:                `True`, if this station has a special role within Gnomebrew's UI.
    """
    return 'special_ui' in Station.from_id(f"station.{station_name}").get_json()
