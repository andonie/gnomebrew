"""
This module manages the game's in-loading
"""
from os.path import join
from typing import Type, Any, Callable

from flask import url_for, render_template

from gnomebrew import mongo
from gnomebrew.game import boot_routine
from gnomebrew.game.user import get_resolver, User
from gnomebrew.game.util import global_jinja_fun


class GameObject:
    """
    Describes any object in Gnomebrew
    """

    def __init__(self, data):
        self._data = data

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
        return self._data['game_id'].split('.')[1]

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

    @staticmethod
    def from_id(game_id) -> 'StaticGameObject':
        """
        Returns the respective station from game_id
        :param game_id: The stations game_id
        :return:    A `Station` object corresponding to the given ID
        """
        global _static_lookup_total
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
            assert doc['game_id'] not in base_dict
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
