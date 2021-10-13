"""
Essentially, Gnomebrew tries to keep all entity information formatted as JSON data.
The `DataObject` class wraps any such data with rich features and a dedicated inheritance tree.
"""
import uuid
from typing import Union, Any

from gnomebrew import log


class DataObject:
    """
    Wraps any data that is exchanged and used - from frontend to backend.
    """

    def __init__(self, data: dict):
        """
        Initializes the dataobject wrapper. This is a lightweight container designed to wrap data.
        :param data:    The JSON data to wrap.
        """
        if not data:
            raise Exception(f"Invalid data added: {data=}")
        if not isinstance(data, dict):
            log('gb_system', f'object data was not a dict. Was: {str(data)}')
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
        else:
            raise Exception(f"No data with key {key} found in {self.name()}.")

    def has_static_key(self, key: str):
        """
        Checks if a key is part of this object.
        :param key: key to check.
        :return:    `True` if key exists, otherwise `False`
        """
        return key in self._data

    def clean_keys(self):
        """
        Utility function. Ensures all data in this object is easy to store in MongoDB.
        For that, all '.' will be replaced with '-', a character that is unused for Game-IDs otherwise.
        """
        DataObject._collection_key_replace(self._data, '.', '-')

    def dirty_keys(self):
        """
        Utility function. Ensures all data in this object is stored in GB Game ID format (any '-' in keys
        are replaced with '.')
        """
        DataObject._collection_key_replace(self._data, '-', '.')

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
                DataObject._collection_key_replace(e[key], to_replace, replace_with)

        elif isinstance(e, list):
            for sub_element in e:
                DataObject._collection_key_replace(sub_element, to_replace, replace_with)

