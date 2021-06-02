from flask import Flask

app = Flask(__name__)

# Import functions and with it the routes
import gnomebrewserver.login
import gnomebrewserver.index
