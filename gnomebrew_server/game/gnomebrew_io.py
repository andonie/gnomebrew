"""
This module handles user input and user output.
Both input and output are formatted as JSON.

This module centralizes the interaction between server and player client and acts as the only place that manages player
interaction.
"""

from gnomebrew_server import socketio


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

    def log(self, log: str):
        """
        Adds to the log message of this game response.
        :param log: A string to be added to the log.
        """
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

    def set_ui_update(self, ui_data: dict):
        assert not self.ui
        self.ui = ui_data

    def finalize(self, user):
        """
        To be called before the GameResponse is returned to the player.
        :return:
        """
        if self.ui:
            # Send UI update
            user.frontend_update('ui', self.ui)

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


class PlayerMsg(object):
    """
    Handler class for PlayerMessages.
    Wraps the input JSON a player sends over.
    """

    def __init__(self, player_json: dict):
        """
        Initialize object
        :param player_json: The complete JSON object sent by the player
        """
        self._data = player_json
