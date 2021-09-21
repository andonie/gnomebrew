"""
This module manages the game's in-loading
"""
from typing import Type
from gnomebrew import mongo


class StaticGameObject(object):
    """
    This class describes a static game object in the game.
    A static game object is:
    * Identical for all players
    * Stored in a dedicated database collection
    * Managed in RAM entirely during server runtime
    """

    def __init__(self, data):
        self._data = data

    def get_json(self):
        return self._data

    def get_value(self, key: str):
        return self._data[key]

    def get_id(self):
        return self._data['game_id']

    def get_minimized_id(self):
        """
        Helper method used to generate a heuristic, human-readable id for a static game object **without dots**.
        Trims the ID by only returning the ID after a string-split for dots on the second index, effectively removing
        the object-category identifier.
        Therefore, this ID is only guaranteed to be unique within the same class of static game objects.
        :return:    A trimmed ID, e.g. turns `item.wood` into `wood` or `recipe.simple_beer` to `simple_beer`.
        """
        return self._data['game_id'].split('.')[1]

    @staticmethod
    def from_id(game_id):
        """
        Returns the respective station from game_id
        :param game_id: The stations game_id
        :return:    A `Station` object corresponding to the given ID
        """
        global _static_lookup_total
        return _static_lookup_total[game_id]

    @staticmethod
    def get_all_of_type(type: str):
        """
        :param type:    A type class of Gnomebrew Entities. Must be a type that's marked as a static data class.
                        e.g. 'item', 'recipe', 'station', etc.
        :return: A `dict` that stores all entities of this type by their full game ID
        """
        return _static_lookup_tiered[type]


# List of updates to run on reload
_load_job_list = list()
# Lookup table with fully qualified game IDs as keys for all static objects
_static_lookup_total = dict()
# Lookup table split cleanly by object class
_static_lookup_tiered = dict()


# Interface

def load_on_startup(collection_name: str):
    """
    Marks a class of **static** game data that's identical for all players and should be stored in RAM always.
    Expects a **dedicated collection** in the game's MongoDB instance to load from.
    :param collection_name      Name of the DB collection to load from
    :return:            Ensures this class is loaded
    """
    def wrapper(static_data_class: Type[StaticGameObject]):
        job_object = {
            'class': static_data_class,
            'collection': collection_name
        }
        _load_job_list.append(job_object)
        return static_data_class
    return wrapper


# Module Logic

def update_static_data():
    """
    This function causes a complete RAM update of the game's static data.
    Called during initialization of the server.
    Reads all database collections and updates the associated game data.
    """
    # Read all known static data collections

    flat_lookup = dict()
    tiered_lookup = dict()

    for job in _load_job_list:
        base_dict = dict()
        entity_type = None
        for doc in mongo.db[job['collection']].find({}, {'_id': False}):
            read_type = doc['game_id'].split('.')[0]
            if entity_type is None:
                entity_type = read_type
            else:
                assert read_type == entity_type
            base_dict[doc['game_id']] = job['class'](doc)
        flat_lookup.update(base_dict)
        tiered_lookup[entity_type] = base_dict

    # Update Game Entity Registry

    global _static_lookup_total
    _static_lookup_total = flat_lookup

    global _static_lookup_tiered
    _static_lookup_tiered = tiered_lookup

    # Inform all classes that the underlying data has just been updated:
    for static_data_class in [job['class'] for job in _load_job_list]:
        listener_fun = getattr(static_data_class, 'on_data_update', None)
        if listener_fun is not None:
            # Listener Function exists. Execute
            listener_fun()
