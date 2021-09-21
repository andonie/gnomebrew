*This game is currently under development and has no stable release*

# Gnomebrew: Best in the Multiverse!

Gnomebrew is an idle game that has you manage a tavern in a tabletop-style fantasy setting.


This file will be updated with more information when the game's development has progressed.

Until then, [My Game Devlog](https://andonie.net/?tags=gnomebrew) is the best place to get an overview.

# For Deployment


## App Configs:

Gnomebrew loads the config stored from the `GNOMEBREW_CONIFG` environment variable.

These config items are necessary:

* `SECRET_KEY`: For signing flask session cookies
* `MONGO_URI`: URI for gnomebrew database
* `STATIC_DIR`: Directory for static elements (css/js)
* `ICO_DIR`: Icon directory with PNG files for game entities
* `FONT_DIR`: Directory for fonts 


## Database:

The game relies heavily on access to a MongoDB instance containing the game data. As of now, the database is managed completely outside this project until a later stage.

## Local Deploy

The most basic way to run the server locally:

```bash
export FLASK_APP=gnomebrew && export GNOMEBREW_CONFIG=path/to/config/config.py && flask run
```
