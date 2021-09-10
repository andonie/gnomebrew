"""
This file contains administrative routines.
"""

from flask import render_template
from flask_login import login_required

from gnomebrew_server.game.user import User

from gnomebrew_server import app, mongo


def remove_all_event_data(user: User):
    """
    Removes all event data in the `events` database for a user.
    :param user:    Target User
    """
    mongo.db.events.delete_many({'target': user.get_id()})


def reset_game_data(user: User):
    """
    Resets this user's game data to the **initial** state.
    :param user:    User who should be reset.
    """
    # Remove user from event database
    remove_all_event_data(user)
    # Set relevant data points to default values
    mongo.db.users.update_one({'target': user.get_id()}, {'$set': {
        'data': {'storage': {'content': {'gold': 0}}},
        'ingame_event': {
            'queued': ['ig_event.start'],
            'finished': []
        }
    }})


# VIEW/Interaction FUNCTIONS

@app.route('/admin')
@login_required
def admin():
    """
    Shows the admin interface.
    """
    return render_template('admin.html')
