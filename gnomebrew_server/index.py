"""
This file manages the basic '/' view and generic views
"""

from gnomebrew_server import app
from flask import render_template, send_from_directory
from flask_login import login_required


@app.route('/')
@login_required
def index():
    return render_template('playscreen.html')


@app.route('/res/<path:res>')
def static_res(res):
    """
    Returns a static resource
    :param subpath: Resource name. Can be a path
    :return: Resource or 404
    """
    return send_from_directory(app.config['STATIC_DIR'], res)
