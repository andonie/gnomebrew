"""
This file manages the basic '/' view
"""

from gnomebrewserver import app


@app.route('/')
def index():
    return 'Hello World, this is Gnomebrew!'
