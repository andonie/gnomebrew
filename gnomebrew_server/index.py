"""
This file manages the basic '/' view and generic views
"""

from gnomebrew_server import app
from flask import render_template, send_from_directory, redirect, url_for
from flask_login import login_required
from os.path import isfile


@app.route('/')
@login_required
def index():
    return render_template('playscreen.html')


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
    if isfile(app.config['ICO_DIR'] + '/' + game_id + '.png'):
        return send_from_directory(app.config['ICO_DIR'], game_id + '.png')
    else:
        # If Icon does not exist (yet), send default img
        return send_from_directory(app.config['ICO_DIR'], 'default.png')


@app.route('/favicon.ico')
def favicon_forward():
    return redirect(url_for('static_res', res='favicon.ico'))


@app.route('/fonts/<font_name>')
def get_font(font_name: str):
    return send_from_directory(app.config['FONT_DIR'], font_name)
