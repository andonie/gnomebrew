"""
Essentially, Gnomebrew tries to keep all entity information formatted as JSON data.
The `DataObject` class wraps any such data with rich features and a dedicated inheritance tree.
"""
import logging
import uuid
from typing import Union, Any, Callable, List, Tuple

from gnomebrew import log
from gnomebrew.game.gnomebrew_io import GameResponse


class DataObject:
    """
    Wraps any data that is exchanged and used - from frontend to backend.
    """

    # Type Validator Data is stored in here.
    type_validators = dict()

    @classmethod
    def validation_function(cls):
        """
        Decorator Function. Adds a decorated function as a **Gnomebrew Type Validator**.
        :param cls:         Expected to be called from within wrapper class context,
                            e.g. `Objective.type_validation`.
        Decorated function is expected to have two parameters:
        1. `data` to validate
        2. `response` object to be used in (possibly cascading) sub-validations and to contain all logged info.
        """
        data_type = cls
        if data_type not in cls.type_validators:
            cls.type_validators[data_type] = dict()

        if 'fun' in cls.type_validators[data_type]:
            raise Exception(f"Class {cls} already has a validation function associated.")

        def wrapper(fun: Callable):
            cls.type_validators[data_type]['fun'] = fun
            return fun

        return wrapper

    @classmethod
    def validation_parameters(cls, *fields: Tuple[str, Any]):
        """
        Adds field names to a list of expected/required fields for type validation.
        :param cls:         Expected to be called from within wrapper class context,
                            e.g. `Objective.validation_parameters`.
        :param fields:      The fields to be added, e.g. 'quest_type', 'quest_name', 'quest_target'
        """
        # Validate Input fields
        if any([param_name for param_name, param_type in fields if not isinstance(param_name, str)]):
            raise Exception(f"Input {fields} does contain illegal input.")

        if cls not in cls.type_validators:
            cls.type_validators[cls] = dict()

        if 'required_fields' in cls.type_validators[cls]:
            raise Exception(f"Class {cls} already has associated required fields.")

        cls.type_validators[cls]['required_fields'] = list(fields)

    def __init__(self, data: dict):
        """
        Initializes the dataobject wrapper. This is a lightweight container designed to wrap data.
        :param data:    The JSON data to wrap.
        """
        if not data:
            raise Exception(f"Invalid data added: {data=}")
        if not isinstance(data, dict):
            log('gb_system', f'object data was not a dict. Was: {str(data)}', level=logging.WARN)
        self._data = data

    def __str__(self):
        """
        Custom String Conversion to make data easy to read in console.
        :return:    String representation of object with line breaks.
        """
        string = "{\n"
        for key in self._data:
            string += f"{key}: {self._data[key]},"
        string += "\n}"
        return string

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
            raise Exception(f"No data with key '{key}' found in {self}.")

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

    def validate(self) -> GameResponse:
        """
        Tests the wrapped data's integrity. Based on the wrapped data's `data_type` field, the appropriate validation
        code runs and checks the data thoroughly.
        :return:        A `GameResponse` object that represents the results of the validation.
        """
        if type(self) not in DataObject.type_validators:
            raise Exception(f"No known validation strategies for: {type(self)}")

        # Response Object to log nuanced result
        response = GameResponse()

        try:
            validation_job = DataObject.type_validators[type(self)]
        except KeyError:
            log('gb_core', f'Requested Object Type {type(self)} has no associated validation scheme.',
                level=logging.WARN)
            validation_job = dict()

        # If this class has associated required fields (& types), make the necessary (strict) checks now.
        if 'required_fields' in validation_job:
            for field, field_type in validation_job['required_fields']:
                if field not in self._data:
                    response.add_fail_msg(f"Expected field {field} not found.")
                elif not isinstance(self._data[field], field_type):
                    response.add_fail_msg(
                        f"Type of field {field} should be {field_type} but is {type(self._data[field])}")

        # If this class has associated required check function, run it now.
        if 'fun' in validation_job:
            validation_function: Callable = validation_job['fun']
            # Hand response object to handling function along object data.
            # Response object is expected to record issues via `add_fail_msg`
            validation_function(data=self._data, response=response)

        # If there have been no issues until this point, the validation is considered successful. Update response:
        if not response.has_failed():
            response.succeess()

        return response

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
