"""
This module manages the game's in-loading
"""
from os.path import join
from typing import Type, Any, Callable, Union

from flask import url_for, render_template

from gnomebrew import mongo
from gnomebrew.game import boot_routine
from gnomebrew.game.user import get_resolver, User, update_resolver
from gnomebrew.game.util import global_jinja_fun


class GameObject:
    """
    Describes any object in Gnomebrew
    """

    def __init__(self, data):
        self._data = data

    def __str__(self):
        return f"<GameObject: {self._data=}>"

    def get_json(self) -> dict:
        """
        Returns a JSON representation of the object.
        :return: a JSON representation of the object.
        """
        return self._data

    def get_static_value(self, key: str, **kwargs):
        """
        Returns a value of this game-object.
        :param key:     associated key to get the value from.
        :return:        associated value.
        :raise          Exception if value not found.
        :keyword default    If set, will return `default` instead of an exception.
        """
        if key in self._data:
            return self._data[key]
        elif 'default' in kwargs:
            return kwargs['default']
        else:
            raise Exception(f"No data with key {key} found in {self.name()}.")

    def has_static_key(self, key: str):
        """
        Checks if a key is part of this object.
        :param key: key to check.
        :return:    `True` if key exists, otherwise `False`
        """
        return key in self._data

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

    @staticmethod
    def _collection_key_replace(e: Union[dict, list, Any], to_replace: str, replace_with: str):
        """
        Recursively cleans up a dictionary's keys to be BSON compatible
        :param e:   An object to clean. A dict's keys and child keys will be replaced. A list's elements will be
                    iterated. All recursively. Any other input will be ignored.
        :param  to_replace Character to replace
        :param replace_with Character to replace `to_replace` with.
        """
        # If element is a dict, clean keys
        if isinstance(e, dict):
            for key in list([key for key in e if to_replace in key]):
                new_key = key.replace(to_replace, replace_with)
                e[new_key] = e[key]
                del e[key]

            for key in e:
                GameObject._collection_key_replace(e[key], to_replace, replace_with)

        elif isinstance(e, list):
            for sub_element in e:
                GameObject._collection_key_replace(sub_element, to_replace, replace_with)

    def clean_keys(self):
        """
        Utility function. Ensures all data in this object is easy to store in MongoDB.
        For that, all '.' will be replaced with '-', a character that is unused for Game-IDs otherwise.
        """
        GameObject._collection_key_replace(self._data, '.', '-')

    def dirty_keys(self):
        """
        Utility function. Ensures all data in this object is stored in GB Game ID format (any '-' in keys
        are replaced with '.')
        """
        GameObject._collection_key_replace(self._data, '-', '.')


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


class PublicGameObject(GameObject):
    """
    Wraps/describes a game object that is stored on DB Server in dedicated collection and is accessible to **any user on
    server** via it's unique `game_id`.
    """

    _public_id_lookup = dict()

    @classmethod
    def setup(cls, collection_name: str, game_id_prefix: str):
        """
        Decorates a `PublicGameObject` class to set it up as a publicly accessible datatype.
        :param collection_name: the name of the MongoDB-collection that is managing the JSON data of this object type
        :param game_id_prefix: Basic Prefix to associate this class with (e.g. 'adventure')
        """
        if game_id_prefix in cls._public_id_lookup:
            raise Exception(f"{collection_name} is already a registered collection.")

        id_data = dict()
        id_data['mongo_collection'] = collection_name
        cls._public_id_lookup[game_id_prefix] = id_data

        # Check if Mongo Collection with that name already exists. If not, create it.
        if collection_name not in mongo.db.list_collection_names():
            # Create Collection with proper name
            mongo.db[collection_name].create_index('game_id')
            print(f'Collection {collection_name} did not yet exist. Created game_id index for {collection_name} now.')

        # Register a GET resolver for the data
        get_resolver(type=game_id_prefix, dynamic_buffer=True, postfix_start=2)(
            cls.generate_get_resolver(game_id_prefix))

        # Register an UPDATE resolver for the data
        update_resolver(game_id_prefix)(cls.generate_update_resolver(game_id_prefix))

        # Need to return identity function for annotation/decoration placement
        return lambda x: x

    @classmethod
    def generate_get_resolver(cls, id_prefix: str) -> Callable:
        name = cls._public_id_lookup[id_prefix]['mongo_collection']
        target_collection = mongo.db[name]

        def resolve_id_get(game_id: str, user: User, **kwargs) -> 'PublicGameObject':
            result = target_collection.find_one({"game_id": game_id}, {'_id': 0})
            if not result:
                if 'default' in kwargs and kwargs['default']:
                    return kwargs['default']
                else:
                    raise Exception(f"Cannot resolve {game_id}")
            return PublicGameObject(dict(result))

        return resolve_id_get


    @classmethod
    def generate_update_resolver(cls, id_prefix: str) -> Callable:
        target_collection = mongo.db[cls._public_id_lookup[id_prefix]['mongo_collection']]
        def resolve_id_update(user: User, game_id: str, update, **kwargs):
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
        entity_type = None
        for doc in mongo.db[job['collection']].find({}, {'_id': False}):
            if not doc:
                # Read an empty doc!
                raise Exception(f"Loaded an empty doc in {job['collection']}.")
            read_type = doc['game_id'].split('.')[0]
            if entity_type is None:
                entity_type = read_type
            else:
                assert read_type == entity_type
            if doc['game_id'] in base_dict:
                raise Exception(f"Game ID {doc['game_id']} is used on multiple DB documents.")
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


@global_jinja_fun
def icon(game_id: str, **kwargs):
    """
    Wraps the <img> tag formatted for game icons to increase code readability in HTML templates.
    :param game_id: An entity ID
    :keyword class  (default `gb-icon`), will set the content of the class attribute of the image tag. Can therefore
                    include multiple classes separated by a space.
    :keyword href   href attribute content
    :keyword id     ID attribute content
    :return:        An image tag that will properly display the image.
    """
    element_addition = ''

    if StaticGameObject.is_known_prefix(game_id.split('.')[0]):
        entity = StaticGameObject.from_id(game_id)
        element_addition = f' title="{entity.name()}"'

    if 'class' not in kwargs:
        if 'img_class' in kwargs: # Added because python compiler did not like class= in python code :(
            kwargs['class'] = kwargs['img_class']
        else:
            kwargs['class'] = 'gb-icon'

    if 'href' in kwargs:
        element_addition += f' href="{kwargs["href"]}"'

    if 'id' in kwargs:
        element_addition += f' id="{kwargs["id"]}"'

    return f'<img class="{kwargs["class"]}"{element_addition} src="{url_for("get_icon", game_id=game_id)}">'


@global_jinja_fun
def render_object(game_id: str, data: Any, verbose: bool = False, **kwargs) -> str:
    """
    Renders an object to it's HTML representation.
    @:param game_id: Fully qualified ID of the render template; e.g. of a `render.structure`
    @:param data:   Data of the object to be used as template `data`
    @:param kwargs  Will be forwarded to template.

    """
    splits = game_id.split('.')
    assert splits[0] == 'render'
    template = render_template(join('render', f"{''.join(splits[1:])}.html"), data=data, **kwargs)
    if verbose:
        print(f"~~~~ Rendering: {game_id=} on: {data=} ~~~~")
        print(template)
    return template


@get_resolver('render')
def render_object_get_res(game_id: str, user: User, **kwargs):
    return render_object(game_id, **kwargs)
