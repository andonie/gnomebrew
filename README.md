*This game is currently under development and has no stable release*

# Gnomebrew: Best in the Multiverse!

Gnomebrew is an idle game that has you manage a tavern in a tabletop-style fantasy setting.


This file will be updated with more information when the game's development has progressed.

Until then, [My Game Devlog](https://andonie.net/?tags=gnomebrew) is the best place to get an overview.

# For Deployment


## App Configs:

Gnomebrew loads the config stored from the `GNOMEBREW_CONIFG` environment variable.

These config items are necessary:

- `DB_ADDR`:
- `DB_SPAC`

## Local Deploy

The most basic way to run the server locally:

```bash
export FLASK_APP=gnomebrew_server && flask run
```
