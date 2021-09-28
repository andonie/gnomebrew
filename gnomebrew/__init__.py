import logging

from flask import Flask
from flask_login import LoginManager
from flask_pymongo import PyMongo
from flask_bootstrap import Bootstrap
from flask_socketio import SocketIO
import logging

# Start App
app = Flask(__name__)

# SocketIO Setup
socketio = SocketIO(app, logger=False)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Load Configuration
app.config.from_envvar('GNOMEBREW_CONFIG')

# Load Database (flask-pymongo)
mongo = PyMongo(app)

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
