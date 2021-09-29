from gnomebrew.game.event import Event
from gnomebrew.game.objects.static_object import load_on_startup, StaticGameObject
from gnomebrew.game.user import User, get_resolver


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