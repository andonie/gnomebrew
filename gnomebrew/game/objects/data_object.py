"""
Essentially, Gnomebrew tries to keep all entity information formatted as JSON data.
The `DataObject` class wraps any such data with rich features and a dedicated inheritance tree.
"""
import copy
import logging
import uuid
from typing import Union, Any, Callable, List, Tuple

from gnomebrew import log
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.user import User


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

    @classmethod
    def use_validation_scheme_of(cls, other_cls):
        """
        Will ensure that the called-on data class will use the same validation scheme as an existing class.
        :param other_cls:   Another data class to copy the validation scheme from. Must have validation scheme.
        """
        # Ensure parameters are OK
        if cls in cls.type_validators:
            raise Exception(f"{cls} already has a validation scheme.")
        if other_cls not in cls.type_validators:
            raise Exception(f"{other_cls} does not have a validation scheme attached.")

        # Copy Validation Scheme and assign it to this class
        cls.type_validators[cls] = copy.copy(cls.type_validators[other_cls])


    # SUBTYPE SYSTEM - Implemented generically for every DataObject class

    _subtype_data = dict()

    @classmethod
    def subtype(cls, subtype_fieldname: str, *validation_subparameters: Tuple[str, Any]):
        """
        Annotation Function to mark a **class** a subtype of another type.
        To be used as:
        ```python
        @Item.subtype('fuel')
        class Fuel(Item):
            # ...
        ```
        :param cls:                         To be called on DIRECT parent class
        :param subtype_fieldname:           If an object of the main type contains `subtype_fieldname`,
                                            it will be considered to be of this subtype.
        :param validation_subparameters:    Parameters to add for validation *within* the field of `subtype_fieldname`
        """
        if subtype_fieldname in cls._subtype_data:
            raise Exception(f"Subtype Fieldname is already in use: {subtype_fieldname}")

        if cls not in cls.type_validators:
            raise Exception(f"Must create validation for base class {cls} before creating subtypes.")

        def wrapper(subtype_class):
            # Check to make sure the subtype class
            if not issubclass(subtype_class, cls):
                raise Exception(f"{subtype_class} must be subclass of {cls} to be subtype.")

            # Create and store subtype data
            data = dict()
            data['typeclass'] = subtype_class
            data['parenttype'] = cls
            data['typefield'] = subtype_fieldname
            if validation_subparameters:
                data['validation_parameters'] = validation_subparameters
            else:
                data['validation_parameters'] = []
            cls._subtype_data[subtype_class] = data

            # Add Validation Features to this class


            return subtype_class

        return wrapper

    def is_subtype_compatible(self, subtype) -> bool:
        """
        Checks if this object is compatible with a certain subtype.
        :param subtype: Subtype to check
        :return:        `True` if this object should be able to transform into `subtype`. Otherwise `False`
        """
        if subtype not in DataObject._subtype_data:
            # No direct match. Is this a parent type?
            if any([s_type for s_type in DataObject._subtype_data if subtype == DataObject._subtype_data[s_type]['parenttype']]):
                # This is a parent type and by convention accepted
                return True
            raise Exception(f"Unknown Suptype Class: {subtype}")

        typefield = DataObject._subtype_data[subtype]['typefield']
        return typefield in self._data and all(
                [par_name in self._data[typefield] and isinstance(self._data[typefield][par_name], par_type)
                 for par_name, par_type in DataObject._subtype_data[subtype]['validation_parameters']])


    def as_subtype(self, subtype, **kwargs) -> subtype:
        """
        Convenience Method. Makes this object available as a specific subtype.
        :param subtype:     Subtype to convert to, e.g. `Fuel`
        :keyword default:   If provided, will return `default` instead of an exception in case of missing `typefield` in
                            object data.
        :return:            The same object data in a class object of type `subtype`.
        """
        own_type = type(self)
        # Special Cases: Identity and Parent Class
        if own_type == subtype:
            return self

        if not self.is_subtype_compatible(subtype):
            raise Exception(f"{subtype} is not compatible with {self}.\nCan be either bad object data or wrong subtype.")

        subtype_data = self._subtype_data[subtype]

        if subtype_data['typefield'] not in self._data:
            if 'default' in kwargs:
                return kwargs['default']
            raise Exception(f"Cannot convert. Missing field {subtype_data['typefield']} in object.")

        return subtype(self._data)


    # Object Events

    _event_handlers_by_code = dict()

    @classmethod
    def on(cls, event_code: str):
        """
        Decorator function. Used to mark the handling of an object event for a given event code.
        :param event_code:  Unique event code
        """
        if event_code not in cls._event_handlers_by_code:
            cls._event_handlers_by_code[event_code] = dict()
        if cls in cls._event_handlers_by_code[event_code]:
            raise Exception(f"Type ({cls}) already is registered for handling {event_code}.")

        def wrapper(fun: Callable):
            cls._event_handlers_by_code[event_code][cls] = fun
            return fun

        return wrapper


    def process_event(self, event_code: str, user: User, data: dict = None):
        """
        Called to register an event on an object.
        Calling this method results in the respectively listening routines to trigger.
        :param event_code:  Code of the event that has happened, e.g. "first_inventory"
        :param user:    Target user
        :param data:    Optional. Containing any data that might be expected as per convention of the `event_code`
        """
        if event_code not in DataObject._event_handlers_by_code:
            raise Exception(f"Unknown event code {event_code}")

        for type_known in DataObject._event_handlers_by_code[event_code]:
            if self.is_subtype_compatible(type_known):
                to_execute = DataObject._event_handlers_by_code[event_code][type_known]
                if not data:
                    to_execute(self.as_subtype(type_known), user)
                else:
                    to_execute(self.as_subtype(type_known), user, data)


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

    def _apply_validation_job(self, validation_job: dict, response: GameResponse):
        """
        Helper Method for validating data objects. Executes *only* one `validation_job` dict
        :param validation_job:  Validation Job to do
        :return:                Response object for logging output
        """
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

    def validate(self) -> GameResponse:
        """
        Tests the wrapped data's integrity. Based on the wrapped data's `data_type` field, the appropriate validation
        code runs and checks the data thoroughly.
        :return:        A `GameResponse` object that represents the results of the validation.
        """
        own_type = type(self)

        # Response Object to log nuanced result
        response = GameResponse()

        # Stores all validation types matched on this objet
        validation_types = list()

        # Validate any parent Types that apply first
        for parent_type in own_type.__bases__:
            if parent_type in DataObject.type_validators:
                validation_types.append(parent_type)

        # Validate Self
        if own_type in DataObject.type_validators:
            validation_types.append(own_type)

        if not validation_types:
            raise Exception(f"No known validation strategies for: {own_type}")

        # Execute all validation jobs now (+ remove duplicates):
        for validation_type in set(validation_types):
            validation_job = DataObject.type_validators[validation_type]
            self._apply_validation_job(validation_job, response)

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
