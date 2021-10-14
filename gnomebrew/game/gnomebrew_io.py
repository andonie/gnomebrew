"""
This module handles user input and user output.
Both input and output are formatted as JSON.

This module centralizes the interaction between server and player client and acts as the only place that manages player
interaction.
"""

from gnomebrew import socketio
from gnomebrew.game.util import css_friendly, is_game_id_formatted, render_info


class GameResponse(object):
    """
    Handler Class for Responses.
    """

    def __init__(self):
        self._data = dict()
        self.ui = None  # Used for SocketIO ui stream updates

    def append_into(self, other_response):
        """
        Receives another `GamesResponse` and adds its inputs into this instances overall response data. After executing
        this response will contain the `log`, 'type' and `fail_msg` of the given response.
        :param other_response:  Another `GameResponse` object
        """
        # Add together logs and fail messages
        if 'fail_msg' in other_response._data:
            self._data['type'] = 'fail'
            if 'fail_msg' not in self._data:
                self._data['fail_msg'] = other_response._data['fail_msg']
            else:
                self._data['fail_msg'] += '\n' + other_response._data['fail_msg']

        if 'log' in other_response._data:
            if 'log' not in self._data:
                self._data['log'] = other_response._data['log']
            else:
                self._data['log'] += '\n' + other_response._data['log']

        # Add together parameters
        if 'params' in other_response._data:
            if 'params' not in self._data:
                self._data['params'] = other_response._data['params']
            else:
                self._data['params'].update(other_response._data['params'])


    def add_fail_msg(self, msg: str) -> None:
        """
        Adds a message to illustrate why the player request failed.
        Can be called multiple times.

        Once this function is called once, the game response will automatically be a fail response type
        :param msg: The error message to be added.
        """
        if 'fail_msg' in self._data:
            self._data['fail_msg'] += '<br/>' + msg
        else:
            self._data['fail_msg'] = msg
        self._data['type'] = 'fail'


    def player_info(self, core_message, *info_elements, **kwargs):
        """
        Shorthand code to efficiently communicate from backend to frontend.
        Generates one info element with an arbitrary number of info content.
        :param info_elements: Info elements. Game IDs will automatically be recognized and turned into an icon of the ID.
                              All other elements will be added straight into the info box in a wrapper div.
        """
        html_content = render_info(*info_elements, info_class='gb-info-warning', title=core_message)
        self.add_ui_update({
            'type':  'player_info',
            'target': kwargs['target'] if 'target' in kwargs else self.get_ui_target(),
            'content': html_content,
            'duration': 40
        })

    def log(self, log: str):
        """
        Adds to the log message of this game response.
        :param log: A string to be added to the log.
        """
        # Clean Up log for view:
        log = log.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
        if 'log' in self._data:
            self._data['log'] += '<br/>' + log
        else:
            self._data['log'] = log

    def set_parameter(self, param: str, value):
        """
        Sets a response parameter.
        :param param:   The id of the parameter to set.
        :param value:   The parameter's new value
        """
        if 'params' not in self._data:
            self._data['params'] = dict()
        self._data['params'][param] = value

    def to_json(self) -> dict:
        """
        Returns
        :return:
        """
        return self._data

    def succeess(self):
        """
        To be executed when the response to the player's request is successful.
        """
        self._data['type'] = 'success'

    def set_value(self, key: str, value):
        """
        Sets a response value
        :param key:     A key
        :param value:   A value
        :return:
        """
        self._data[key] = value

    def add_ui_update(self, ui_data: dict):
        if not self.ui:
            self.ui = list()
        self.ui.append(ui_data)

    def set_ui_target(self, target_selector: str):
        """
        Sets the UI target for this Game Responses UI updates.
        Any `player_info` invokes called AFTER this is set will ensure that the info will be added to the selector's
        result's info container.
        :param target_selector: Selector of container that should add UI targets now.
        """
        self.ui_target = target_selector

    def get_ui_target(self, **kwargs) -> str:
        """
        :keyword  default   If set, `default` will be returned instead of an exception.
        :return:  The current UI target or `default` if set.
        """
        try:
            return self.ui_target
        except AttributeError as a:
            if 'default' in kwargs:
                return kwargs['default']
            else:
                raise a

    def finalize(self, user, **kwargs):
        """
        To be called before the GameResponse is returned to the player.
        :return:
        """
        if self.ui:
            # Send UI update
            for ui_update in self.ui:
                user.frontend_update('ui', ui_update, **kwargs)

    def has_failed(self):
        """
        Returns whether or not this response has fail messages associated with it.
        :return:    `True` if this is a fail response, else `False`
        """
        return self._data['type']=='fail' if 'type' in self._data else False


TYPE_ERROR = GameResponse()
TYPE_ERROR._data = {
    'type': 'fail',
    'fail_msg': 'The Game Request Type is unknown.'
}
SERVER_ERROR = GameResponse()
SERVER_ERROR._data = {
    'type': 'fail',
    'fail_msg': 'The server encountered an error.'
}
