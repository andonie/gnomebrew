"""
This module houses the gameplay-interface view: HTTP and SocketIO interactions between server and client.
"""
import datetime
import logging

from gnomebrew import app, socketio
from flask_socketio import emit
from flask_login import login_required, current_user
from flask import request
from typing import Callable
from gnomebrew.game.gnomebrew_io import TYPE_ERROR, GameResponse
import functools
from flask_socketio import disconnect, join_room

from gnomebrew.game.objects.request import PlayerRequest
from gnomebrew.logging import log, log_execution_time, log_exception


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
    """
    Core Interface Function. Expects player data in request and evaluates it accordingly.
    """
    player_request_object = PlayerRequest(request.form)

    log('gb_system', f"received", 'request', request.form['request_type'], f'usr:{current_user.get_id()}', verbose=player_request_object)

    # Create a buffer for this request to store all evaluated IDs
    try:
        response: GameResponse = log_execution_time(lambda: player_request_object.execute(current_user), 'gb_system', 'processed', 'request', request.form['request_type'], f'usr:{current_user.get_id()}')
        response.finalize(current_user)
    except Exception as e:
        log_exception('gb_system', e, 'request', level=logging.ERROR)
        return TYPE_ERROR.to_json()


    log('gb_system', f"processed", 'request', request.form['request_type'], f'usr:{current_user.get_id()}')

    return response.to_json()


@app.route('/play/game_id/<game_id>', methods=['POST'])
@login_required
def evaluate_game_id(game_id: str):
    """
    Base Function To Allow A Player To Evaluate their game data.
    :param game_id: Game-ID to be requested.
    :return:        The result of the Game-ID being requested.
    """
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
    log('gb_system', f"user disconnected", current_user.get_id())
    pass


@PlayerRequest.type('time_sync', is_buffered=False)
def time_sync(user, request_object: dict, **kwargs):
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
