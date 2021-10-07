"""
This module contains core objects in Gnomebrew, such as Items, People, Stations, or
"""


from gnomebrew.game.objects.item import Item as Item
from gnomebrew.game.objects.recipe import Recipe as Recipe
from gnomebrew.game.objects.people import Person as Person
from gnomebrew.game.objects.world import WorldLocation as WorldLocation
from gnomebrew.game.objects.station import Station as Station
from gnomebrew.game.objects.upgrades import Upgrade as Upgrade
from gnomebrew.game.objects.generation import Generator as Generator
from gnomebrew.game.objects.quest import Quest as Quest
from gnomebrew.game.objects.quest import Objective as Objective
from gnomebrew.game.objects.condition import Condition as Condition
from gnomebrew.game.objects.request import PlayerRequest as PlayerRequest
from gnomebrew.game.objects.adventure import Adventure as Adventure

import gnomebrew.game.objects.names
import gnomebrew.game.objects.game_statistics
import gnomebrew.game.objects.special_entities
