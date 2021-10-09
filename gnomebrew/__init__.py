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
log('gb_core', 'Loading Config', 'boot_routines')
app.config.from_envvar('GNOMEBREW_CONFIG')

# Load Database (flask-pymongo)
log('gb_core', 'Starting PyMongo', 'boot_routines')
mongo = PyMongo(app)

# SocketIO Setup
log('gb_core', 'Starting SocketIO', 'boot_routines')
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
