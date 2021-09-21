"""
This module houses the gameplay-interface view: HTTP and SocketIO interactions between server and client.
"""
import datetime

from gnomebrew import app, socketio
from flask_socketio import emit
from flask_login import login_required, current_user
from flask import request
from typing import Callable
from gnomebrew.game.gnomebrew_io import TYPE_ERROR, GameResponse
import functools
from flask_socketio import disconnect, join_room

# All Request handlers
_REQUEST_HANDLERS = dict()


def request_handler(func: Callable):
    """
    Registering a handler for a player request.
    :param func:
    :return:
    """
    assert func.__name__ not in _REQUEST_HANDLERS
    _REQUEST_HANDLERS[func.__name__] = func


def authenticated_only(f):
    """
    Taken Graciously from Miguel Grinberg:
    https://blog.miguelgrinberg.com/post/flask-socketio-and-the-user-session
    :param f: SocketIO Function
    :return:  Wrapped to ensure that only an authenticated user can access this function.
    """

    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            disconnect()
        else:
            return f(*args, **kwargs)

    return wrapped


@app.route('/play/request', methods=['POST'])
@login_required
def player_request():
    if not request.form['type'] in _REQUEST_HANDLERS:
        return TYPE_ERROR.to_json()
    response = _REQUEST_HANDLERS[request.form['type']](request.form, current_user)
    response.finalize(current_user)
    return response.to_json()


@app.route('/play/game_id/<game_id>', methods=['POST'])
@login_required
def evaluate_game_id(game_id: str):
    """
    Base Function To Allow A Player To Evaluate their game data.
    :param game_id: Game-ID to be requested.
    :return:        The result of the Game-ID being requested.
    """
    print(f"!!! I just received {game_id}!")
    return current_user.get(game_id)

# SOCKET IO

@socketio.on('connect')
@authenticated_only
def test_connect(auth=None):
    # User Connected: Automatically add them to their update feed
    # Update Feed is implemented as a flask_socketio room named after their personal username
    join_room(current_user.get_id())


@socketio.on('disconnect')
def test_disconnect():
    # Nothing to do here. On disconnect, users are automatically signed off.
    print('disconnected')
    pass



@request_handler
def time_sync(request_object: dict, user):
    """
    Used to synchronize host and server for more accurate time displays.
    :param request_object:  Request Object
    :param user:            A user. Irrelevant
    :return:                A response with the server's current UTC time.
    """
    res = GameResponse()
    res.set_value('now', datetime.datetime.utcnow())
    res.succeess()
    return res
