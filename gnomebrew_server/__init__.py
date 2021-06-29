from flask import Flask
from flask_login import LoginManager
from flask_pymongo import PyMongo
from flask_bootstrap import Bootstrap
from flask_socketio import SocketIO

# Start App
app = Flask(__name__)
socketio = SocketIO(app)

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
import gnomebrew_server.auth
import gnomebrew_server.index
import gnomebrew_server.play
import gnomebrew_server.testing

import gnomebrew_server.game.static_data

