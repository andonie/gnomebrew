"""
This module manages Player Requests as game objects.
"""
from typing import Callable

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects.game_object import GameObject
from gnomebrew.game.user import User, IDBuffer


class PlayerRequest(GameObject):
    """
    Handler class for PlayerMessages.
    Wraps the input JSON a player sends over.
    """

    request_types = dict()

    @classmethod
    def type(cls, request_type: str, is_buffered: bool=True):
        """
        Decorator function. Designates a reaction to a player request type.
        Expected to be decorated on a function that receives:
        1. `user` Target User
        2. `request_object` JSON data of given `request-type`
        3. Possible kwargs
        :param request_type:    The type of Request this
        :param is_buffered:     If `True`, the request type will be executed with an ID Buffer stored in
                                `kwargs['id_buffer']`.
        """
        if request_type in cls.request_types:
            raise Exception(f"{request_type} is already a used Request Type.")

        def wrapper(fun: Callable):
            cls.request_types[request_type] = dict()
            cls.request_types[request_type]['fun'] = fun
            cls.request_types[request_type]['is_buffered'] = is_buffered
            return fun

        return wrapper


    def __init__(self, player_json: dict):
        """
        Initialize object
        :param player_json: The complete JSON object sent by the player
        """
        GameObject.__init__(self, player_json)

    def execute(self, user: User, **kwargs) -> GameResponse:
        """
        Executes this request once.
        :param user:    Target user.
        :return:        The resulting `GameResponse` object.
        """
        if 'id_buffer' not in kwargs:
            kwargs['id_buffer'] = IDBuffer()
        result = PlayerRequest.request_types[self.get_static_value('request_type')]['fun'](user=user, request_object=self._data, **kwargs)

        return result