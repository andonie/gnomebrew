"""
This module manages the Quest Board module.
"""

from gnomebrew_server.play import request_handler
from gnomebrew_server.game.user import User
from gnomebrew_server.game.gnomebrew_io import GameResponse

@request_handler
def make_bid(request_object: dict, user: User):
    """
    Makes a bid for an item, representing an entry on the quest board.
    :param request_object:  Data from frontend. Must contain:

    `item`: The item the user makes a bid for, e.g. `mythril`
    `bid`: The amount in gold the user bids with, must compile with `float(...)`

    :param user:    The executing user.
    :return:    The corresponding `GameResponse`
    """
    response = GameResponse()



    return response