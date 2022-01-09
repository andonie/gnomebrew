import logging

from flask import Flask
from flask_login import LoginManager
from flask_pymongo import PyMongo
from flask_bootstrap import Bootstrap
from flask_socketio import SocketIO
from gnomebrew.logging import log


# Start App
app = Flask(__name__)

# Load Configuration
log('gb_core', 'Loading Config')
app.config.from_envvar('GNOMEBREW_CONFIG')

log('gb_core', f'Booting server at {app.config["SERVER_NAME"]} ...')

# Load Database (flask-pymongo)
mongo = PyMongo(app)

# SocketIO Setup
socketio = SocketIO(app, logger=False)





# Load Bootsrap Handler
bootstrap = Bootstrap(app)

# Load Login Manager (flask-login)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Import functions and with it the routes
import gnomebrew.auth
import gnomebrew.index
import gnomebrew.play

import gnomebrew.game
