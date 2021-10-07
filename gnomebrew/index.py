"""
This file manages the basic '/' view and generic views
"""

from gnomebrew import app
from flask import render_template, send_from_directory, redirect, url_for
from flask_login import login_required, current_user
from os.path import isfile, join
from gnomebrew.game.user import IDBuffer


@app.route('/')
@login_required
def index():
    if current_user.is_authenticated:
        return render_template('playscreen.html', buffer=IDBuffer())
    else:
        return redirect(url_for('login'))


@app.route('/res/<res>')
def static_res(res):
    """
    Returns a static resource
    :param res: Resource name. Can be a path
    :return: Resource or 404
    """
    return send_from_directory(app.config['STATIC_DIR'], res)


@app.route('/ico/<game_id>')
def get_icon(game_id: str):
    """
    Returns the most fitting icon for a given game id
    :param game_id: ID of the entity to get the icon for
    """
    splits = game_id.split('.')
    target_directory = join(app.config['ICO_DIR'], splits[0])

    for possible_image_name in [f"{'.'.join(splits[1:x])}.png" for x in range(len(splits), 1, -1)]:
        if isfile(join(target_directory, possible_image_name)):
            return send_from_directory(target_directory, possible_image_name)

    # No image match found. Use best possible default.
    if isfile(join(target_directory, 'default.png')):
        return send_from_directory(target_directory, 'default.png')
    else:
        # If Icon does not exist (yet), send default img
        return send_from_directory(app.config['ICO_DIR'], 'default.png')


@app.route('/favicon.ico')
def favicon_forward():
    return redirect(url_for('static_res', res='favicon.ico'))


@app.route('/fonts/<font_name>')
def get_font(font_name: str):
    return send_from_directory(app.config['FONT_DIR'], font_name)


@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')
