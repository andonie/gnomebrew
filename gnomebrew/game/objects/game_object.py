"""
This module manages the game's in-loading
"""
import logging
from copy import deepcopy
from os.path import join
from typing import Type, Any, Callable, List

from flask import render_template

from gnomebrew import mongo, app
from gnomebrew.game import boot_routine
from gnomebrew.game.objects.data_object import DataObject
from gnomebrew.game.user import get_resolver, User, update_resolver
from gnomebrew.game.util import global_jinja_fun, generate_uuid, is_uuid
from gnomebrew.logging import log


class GameObject(DataObject):
    """
    Wraps any game logic entity that is to be displayed in some form to the player.
    """

    def __init__(self, data):
        DataObject.__init__(self, data)

    def get_id(self):
        """
        Returns the object's game ID.
        :return:    Associated ID.
        """
        return self._data['game_id']

    def get_minimized_id(self):
        """
        Helper method used to generate a heuristic, human-readable id for a static game object **without dots**.
        Trims the ID by only returning the ID after a string-split for dots on the second index, effectively removing
        the object-category identifier.
        Therefore, this ID is only guaranteed to be unique within the same class of static game objects.
        :return:    A trimmed ID, e.g. turns `item.wood` into `wood` or `recipe.simple_beer` to `simple_beer`.
        """
        return '.'.join(self._data['game_id'].split('.')[1:])

    def get_class_code(self):
        """
        Returns the generic type of this static object.
        :return:    The static type of this object, e.g. 'station' or 'recipe'
        """
        return ''.join(self._data['game_id'].split('.')[:-1])

    def name(self):
        """
        Returns the name of this static object, reading from the `name` attribute in the data source.
        :return:    This object's name.
        """
        return self._data['name']

    def description(self):
        """
        Returns the description of this static object, reading from its source data.
        :return:    This object's description.
        """
        return self._data['description']

    def has_postfixes(self) -> bool:
        return 'postfixed' in self._data

    def is_postfixed(self) -> bool:
        """
        :return: `True` if this game object is postfixed.
        """
        return 'postfix' in self._data

    def get_postfix_data(self, postfix_id: str, **kwargs):
        """
        Returns the value of given postfix data.
        :param postfix_id:  Postfix-ID to evaluate (e.g. 'quality', 'src_item')
        :return:    The value of the given postfix ID.
        """
        if 'postfixed' in self._data and postfix_id in self._data['postfixed']:
            return self._data['postfixed'][postfix_id]
        elif 'default' in kwargs:
            return kwargs['default']
        else:
            raise Exception(f"Cannot find {postfix_id} for {str(self)}")


class StaticGameObject(GameObject):
    """
    This class describes a static game object in the game.
    A static game object is:
    * Identical for all players
    * Stored in a dedicated database collection
    * Managed in RAM entirely during server runtime
    """

    def __init__(self, db_data):
        GameObject.__init__(self, db_data)
        # Clean up own data in to remove `-` from keys and replace with `.`
        self.dirty_keys()

    @staticmethod
    def from_id(game_id) -> 'StaticGameObject':
        """
        Returns the respective station from game_id
        :param game_id: The stations game_id
        :return:    A `Station` object corresponding to the given ID
        """
        if game_id not in _static_lookup_total:
            raise Exception(f"{game_id=} cannot be found in static data loaded from database.")
        return _static_lookup_total[game_id]

    @staticmethod
    def get_all_of_type(type: str) -> dict:
        """
        :param type:    A type class of Gnomebrew Entities. Must be a type that's marked as a static data class.
                        e.g. 'item', 'recipe', 'station', etc.
        :return: A `dict` that stores all entities of this type by their full game ID
        """
        return _static_lookup_tiered[type]

    @staticmethod
    def is_known_prefix(prefix: str):
        """
        Checks if a given prefix is a known static data class.
        :param prefix:      A prefix, e.g. 'item'
        :return:            `True` if this prefix is known. Otherwise `False`
        """
        return prefix in _static_lookup_tiered



    @classmethod
    def get_all_static_of_subtype(cls, subtype) -> list:
        """
        Convenience Method. For a given `subtype`, try to find all `StaticGameObject` entities that are currently
        stored in this Gnomebrew session.
        :param subtype:     Target subtype. Must be registered via `subtype` annotation
        :return:            A List of all `subtype` objects known in the static data (as identified by their type
                            parameter)
        """
        if subtype not in cls._subtype_data:
            raise Exception(f"{cls} is not a known subtype.")

        static_data_type = cls._subtype_data[subtype]['parenttype']
        static_data = next(iter([job['data_type'] for job in _load_job_list if job['class'] == static_data_type]), None)
        if not static_data:
            raise Exception(f"Could not find data type for {subtype}")
        return [subtype(o_data.get_json()) for o_data in _static_lookup_tiered[static_data].values() if o_data.is_subtype_compatible(subtype)]


class DynamicGameObject(StaticGameObject):
    """
    Wraps/describes a game object that is stored on DB Server in two dedicated formats: *Static* objects and *Generated*
    objects. This class wraps such a class, wiring together the features of static objects and reducing code overhead
    by registering the appropriate get/update method.
    """

    _public_id_lookup = dict()

    @classmethod
    def setup(cls, dynamic_collection_name: str, game_id_prefix: str, **kwargs):
        """
        Decorates a `DynamicGameObject` class to set it up as a publicly accessible datatype.
        :param dynamic_collection_name: the name of the MongoDB-collection that is managing the JSON data of this object type
        :param game_id_prefix: Basic Prefix to associate this class with (e.g. 'adventure')
        """
        if game_id_prefix in cls._public_id_lookup:
            raise Exception(f"{dynamic_collection_name} is already a registered collection.")

        id_data = dict()
        id_data['special_get'] = dict()
        id_data['dynamic_collection'] = dynamic_collection_name
        cls._public_id_lookup[game_id_prefix] = id_data

        # Check if Mongo Collection with that name already exists. If not, create it.
        if dynamic_collection_name not in mongo.db.list_collection_names():
            # Create Collection with proper name
            mongo.db[dynamic_collection_name].create_index('game_id')
            log('gb_system', f"Created game_id index for collection.",
                f"mongo:{dynamic_collection_name}")

        # Register a GET resolver for the data
        get_resolver(type=game_id_prefix,
                     dynamic_buffer=False if 'dynamic_buffer' not in kwargs else kwargs['dynamic_buffer'],
                     postfix_start=2)(
            cls._generate_get_resolver(game_id_prefix))

        # Register an UPDATE resolver for the data
        update_resolver(game_id_prefix)(cls._generate_update_resolver(game_id_prefix))

        # Need to return identity function for annotation/decoration placement
        return lambda x: x

    @classmethod
    def special_id_get(cls, game_id: str):
        """
        Annotation function. Adds a special ID for a given Game ID.
        Annotates a get-resolving function for execution for only the given ID.
        :param game_id: The game ID for which this special ID resolves. Defining split should always start with
                        an underscore. E.g. `quest._active`
        """
        splits = game_id.split('.')
        prefix = splits[0]
        assert len(splits) == 2
        if prefix not in cls._public_id_lookup:
            raise Exception(f"{prefix} is not a managed prefix. Cannot resolve this unless set up correctly.")

        def wrapper(fun: Callable):
            cls._public_id_lookup[prefix]['special_get'][game_id] = fun
            return fun

        return wrapper

    @classmethod
    def _generate_get_resolver(cls, id_prefix: str) -> Callable:
        dynamic_collection = mongo.db[cls._public_id_lookup[id_prefix]['dynamic_collection']]
        special_id_lookup = cls._public_id_lookup[id_prefix]['special_get']

        def resolve_id_get(game_id: str, user: User, **kwargs) -> 'GameObject':
            if game_id in special_id_lookup:
                return special_id_lookup[game_id](game_id=game_id, user=user, **kwargs)

            splits = game_id.split('.')
            if not is_uuid(splits[1]):
                return StaticGameObject.from_id(game_id)

            result = dynamic_collection.find_one({"game_id": game_id}, {'_id': 0})
            if not result:
                if 'default' in kwargs and kwargs['default']:
                    return kwargs['default']
                else:
                    raise Exception(f"Cannot resolve {game_id}")
            return DynamicGameObject(dict(result))

        return resolve_id_get

    @classmethod
    def _generate_update_resolver(cls, id_prefix: str) -> Callable:
        target_collection = mongo.db[cls._public_id_lookup[id_prefix]['dynamic_collection']]

        def resolve_id_update(user: User, game_id: str, update, **kwargs):
            splits = game_id.split('.')
            if not is_uuid(splits[1]):
                # Not a UUID. Instead of doing this forward this request to the static collection
                raise Exception(f"Cannot update a scripted object: {game_id}.")

            # This is a UUID. Let's look in the data.
            core_query = {"game_id": game_id}
            if 'delete' in kwargs and kwargs['delete']:
                target_collection.delete_one(core_query)
                return None
            mongo_command = '$set' if 'mongo_command' not in kwargs else kwargs['mongo_command']
            if 'is_bulk' in kwargs and kwargs['is_bulk']:
                # Bulk update. Assume `update` to be a dict that contains all values to be set
                mongo_content = dict()
                for key in update:
                    mongo_content[f"{game_id}.{key}"] = update[key]
            else:
                mongo_content = {game_id: update}

            target_collection.update_one(core_query, {mongo_command: update})
            return mongo_command, mongo_content

        return resolve_id_update

    def __init__(self, data: dict):
        """Wrap __init__ function for static loadin purposes"""
        StaticGameObject.__init__(self, data)

    def _get_mongo_handle(self):
        """Convenience function. Retrieves this object's PyMongo collection handle."""
        if 'game_id' not in self._data:
            raise Exception(f"Cannot update object without game_id field set: {str(self._data)}")
        # Find the appropriate mongo handle based on my Game ID.
        return mongo.db[self._public_id_lookup[self._data['game_id'].split('.')[0]]['dynamic_collection']]

    def global_db_update(self):
        """Updates this object's full data in the DB. To be called after transactions if changes were made to the entity."""
        mongo_handle = self._get_mongo_handle()
        self.update_to(mongo_handle)

    def global_db_remove(self):
        """Removes this object's data entry from the designated DB"""
        mongo_handle = self._get_mongo_handle()
        self.remove_from(mongo_handle)



# List of updates to run on reload
_load_job_list = list()
# Lookup table with fully qualified game IDs as keys for all static objects
_static_lookup_total = dict()
# Lookup table split cleanly by object class
_static_lookup_tiered = dict()


# Interface

def load_on_startup(collection_name: str, validate: bool = True):
    """
    Marks a class of **static** game data that's identical for all players and should be stored in RAM always.
    Expects a **dedicated collection** in the game's MongoDB instance to load from.
    :param validate:            Whether or not each object loaded in at startup should be validated before adding it to
                                the object collection. Default `True`
    :param collection_name      Name of the DB collection to load from
    :return:                    Ensures this class is loaded
    """

    def wrapper(static_data_class: Type[StaticGameObject]):
        job_object = {
            'class': static_data_class,
            'collection': collection_name,
            'validate': validate
        }
        _load_job_list.append(job_object)
        return static_data_class

    return wrapper


# Module Logic

@boot_routine
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
        if 'data_type' in job:
            entity_type = job['data_type']
        else:
            entity_type = None
        for doc in mongo.db[job['collection']].find({}, {'_id': False}):
            # Make Checks (for Exception Level Malformatted Input) before adding input to doc
            # Check if Empty Object was given
            if not doc:
                log("gb_system", f"Loaded an empty doc in collection: {job['collection']}.", level=logging.WARN)
                continue

            # Ensure all game_id fields start with the same first split
            read_type = doc['game_id'].split('.')[0]

            if entity_type is None:
                entity_type = read_type
                job['data_type'] = read_type
            else:
                if read_type != entity_type:
                    log("gb_system", f"Invalid Game ID detected in collection document. Must include {entity_type}. Was:{read_type}", level=logging.WARN)
                    continue

            # Ensure the Game ID is not yet taken
            if doc['game_id'] in base_dict:
                raise Exception(f"Game ID {doc['game_id']} is used on multiple DB documents.")

            game_object: DataObject = job['class'](doc)

            # If objects loaded from this source should be validated before adding, do so now.
            if job['validate']:
                validation_result = game_object.validate()
                if validation_result.has_failed():
                    # This object has failed the validation check. This should not happen.
                    # Ignore this object for runtime purposes and log the exception on console.
                    log("gb_system", f"Game Object malformatted:\n{validation_result.get_fail_messages()}",
                        f"id:{game_object.get_static_value('game_id', default='<unkown>')}",
                        "sanity", level=logging.WARN)
                    continue

            # All tests checked approved. Add this document to the others
            base_dict[doc['game_id']] = game_object

        # All tests passed. Add this to the loaded object pool
        flat_lookup.update(base_dict)
        tiered_lookup[entity_type] = base_dict

    # Finished boot routine: Report success succinctly to console
    log('gb_core', f"DB Collections Loaded: {', '.join([job['collection'] for job in _load_job_list])}", 'boot_routines')

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


@global_jinja_fun
def render_object(game_id: str, data: Any, **kwargs) -> str:
    """
    Renders an object to it's HTML representation.
    @:param game_id: Fully qualified ID of the render template; e.g. of a `render.structure`
    @:param data:   Data of the object to be used as template `data`
    @:param kwargs  Will be forwarded to template.

    """
    splits = game_id.split('.')
    assert splits[0] == 'render'
    log('game_id', 'rendering object', f'id:{game_id}')
    with app.app_context():
        template = render_template(join('render', f"{''.join(splits[1:])}.html"), data=data, **kwargs)
    return template


static_getters = {
    'it_cat': lambda id: StaticGameObject.from_id(id),
    'special': lambda id: StaticGameObject.from_id(id),
    'item': lambda id: StaticGameObject.from_id(id)
}


@global_jinja_fun
def static_get(game_id: str) -> GameObject:
    """
    Helper function for templates. Retrieves static data from a game ID. If the given GameID both exists and is a static
    element (e.g. a base item or an item category) it will return this Game Object
    :param game_id: Target ID
    :return:        Result of a static get call for this function.
    """
    splits = game_id.split('.')
    if splits[0] not in static_getters:
        raise Exception(f"Cannot resolve {game_id} statically.")
    return static_getters[splits[0]](game_id)


@get_resolver('render')
def render_object_get_res(game_id: str, user: User, **kwargs):
    return render_object(game_id, **kwargs)
