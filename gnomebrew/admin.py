"""
This file contains administrative routines.
"""

from flask import render_template
from flask_login import login_required

from gnomebrew.game.user import User, load_user
from gnomebrew.game.testing import application_test
from gnomebrew.game.gnomebrew_io import GameResponse

from gnomebrew import app, mongo


@application_test(name='Reset User Data', category='Admin')
def reset_game_data_frontend(username: str):
    """
    Reset a user's game data entirely.
    """
    response = GameResponse()
    if not User.user_exists(username):
        response.add_fail_msg(f"User {username} does not exist.")
        return response
    load_user(username).reset_game_data()
    response.log(f"Reset data of {username} to starting conditions.")
    return response

@application_test(name='Create User', category='Admin')
def create_user(username: str, pw: str):
    """
    Create a new user in Gnomebrew.
    `pw` will be in clear text (unsafe, only for testing) and `username` must not be taken yet.
    """
    response = GameResponse()
    if User.user_exists(username):
        response.add_fail_msg(f"{username} is already taken.")
        return response
    User.create_user(username, pw)
    response.log(f"Created {username} with password {pw}")
    return response


# VIEW/Interaction FUNCTIONS

@app.route('/admin')
@login_required
def admin():
    """
    Shows the admin interface.
    """
    return render_template('admin.html')
