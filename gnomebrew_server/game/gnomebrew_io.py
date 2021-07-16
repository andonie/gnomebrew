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

    def add_fail_msg(self, msg: str) -> None:
        """
        Adds a message to illustrate why the player request failed.
        Can be called multiple times.

        Once this function is called once, the game response will automatically be a fail response type
        :param msg: The error message to be added.
        """
        if 'fail_msg' in self._data:
            self._data['fail_msg'] += ' -- ' + msg
        else:
            self._data['fail_msg'] = msg
        self._data['type'] = 'fail'

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
