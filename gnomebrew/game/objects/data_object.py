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
        if cls not in cls.type_validators:
            raise Exception(f"Must create validation for base class {cls} before creating subtypes.")

        def wrapper(subtype_class):
            # Checks
            if not issubclass(subtype_class, cls):
                raise Exception(f"{subtype_class} must be subclass of {cls} to be subtype.")
            if subtype_class in cls._subtype_data:
                raise Exception(f"Subtype Class is already in use: {subtype_class}")

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

    @classmethod
    def get_subtype_by_fieldname(cls, subtype_fieldname: str):
        """
        Lookup function mapping a `subtype_fieldname` to its designated subtype.
        :param subtype_fieldname:   Name of the subtype field.
        :return:                    Corresponding type class
        """
        subtype_job = next(filter(lambda job: job['typefield'] == subtype_fieldname, cls._subtype_data.values()), None)
        if not subtype_job:
            raise Exception(f"Cannot find info on subtype fieldname: {subtype_fieldname}")

        return subtype_job['typeclass']

    @classmethod
    def subtype_data_generator(cls):
        """
        Decorates a function that can generate subtype data from given object data.
        """
        if cls not in cls._subtype_data:
            raise Exception(f"Unknown subtype: {cls}")
        elif 'generator_fun' in cls._subtype_data[cls]:
            raise Exception(f"Already have a generator function for subtype {cls}.")

        def wrapper(fun: Callable):
            cls._subtype_data[cls]['generator_fun'] = fun
            return fun
        return wrapper

    def is_subtype_compatible(self, subtype) -> bool:
        """
        Checks if this object is compatible with a certain subtype.
        :param subtype: Subtype to check
        :return:        `True` if this object should be able to transform into `subtype`. Otherwise `False`
        """
        return not self.subtype_compatibility_check(subtype).has_failed()

    def subtype_compatibility_check(self, subtype) -> GameResponse:
        """
        Checks this object's compatibility with a given subtype and returns the 'rich' result as a GameResponse.
        :param subtype:     Type to check.
        :return:            `GameResponse` object showing compatibility check results.
        """
        response = GameResponse()
        if subtype not in DataObject._subtype_data:
            # No direct match. Is this a parent type?
            if any([s_type for s_type in DataObject._subtype_data if subtype == DataObject._subtype_data[s_type]['parenttype']]):
                # This is a parent type and by convention accepted
                return response
            raise Exception(f"Unknown Suptype Class: {subtype}")

        typefield = DataObject._subtype_data[subtype]['typefield']
        if typefield not in self._data:
            response.add_fail_msg(f"Missing subtype-field '{typefield}' in object: {self}")
            return response

        # Run a basic field-and-types test on my typefield data
        DataObject._test_field_and_types(data=self._data[typefield],
                                         fields_and_types=DataObject._subtype_data[subtype]['validation_parameters'],
                                         response=response,
                                         parent_fieldname=typefield)

        return response

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


        sub_comp_check_res = self.subtype_compatibility_check(subtype)
        if sub_comp_check_res.has_failed():
            raise Exception(f"{subtype} is not compatible with {self}\nDetailed response:\n{sub_comp_check_res.get_fail_messages()}")

        subtype_data = self._subtype_data[subtype]

        if subtype_data['typefield'] not in self._data:
            if 'default' in kwargs:
                return kwargs['default']
            raise Exception(f"Cannot convert. Missing field {subtype_data['typefield']} in object.")

        return subtype(self._data)#

    def generate_subtype(self, subtype, gen = None):
        from gnomebrew.game.objects.generation import Generator
        """
        Generates data corresponding to a given `subtype`, making this object part of the subtype.
        ```
        person.generate_subtype(Patron)
        patron = person.as_subtype(Patron)
        ```
        
        A freshly generated patron is just about to enter the tavern and excited to place an order.
        
        :param subtype:     Target subtype
        :param gen:         Generator to use
        :raise              Exception if `self` already is of `subtype`
        """

        if subtype not in self._subtype_data:
            raise Exception(f"Unknown subtype: {subtype}")
        elif 'generator_fun' not in self._subtype_data[subtype]:
            raise Exception(f"No generation function known for {subtype}.")

        # If no generator was provided, create a purely random one
        if not gen:
            gen = Generator.fresh()

        # Generate appropriate subtype data and add it to the data
        subtype_data = self._subtype_data[subtype]['generator_fun'](source_data=self._data, gen=gen)
        self._data[self._subtype_data[subtype]['typefield']] = subtype_data

    def remove_subtype(self, subtype):
        """
        Convenience function. Removes all data associated with a given `subtype` from this object.
        :param subtype:     Target subtype
        """
        if subtype not in self._subtype_data:
            raise Exception(f"Unknown subtype: {subtype}")

        # Identify my associated typefield and remove it entirely from my data.
        typefield = self._subtype_data[subtype]['typefield']
        del self._data[typefield]

    # Object Events

    _event_handlers_by_code = dict()

    @classmethod
    def on(cls, event_code: str):
        """
        Decorator function. Used to mark the handling of an object event for a given event code.
        :param event_code:  Event code the decorated function is listening on.
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

    @staticmethod
    def _format_data_str(data: dict, indentation=0) -> str:
        """Recursive Helper Function"""
        indents = "\t" * indentation
        result = "{\n"
        for field, value in data.items():
            if isinstance(value, dict):
                value_str = DataObject._format_data_str(value, indentation + 1)
            else:
                value_str = str(value)
            result += indents + f"{field:<20}: {value_str}\n"
        result += indents + "}"
        return result

    def __str__(self):
        """
        Custom String Conversion to make data easy to read.
        :return:    String representation of object with line breaks.
        """
        return DataObject._format_data_str(self._data)

    def update_to(self, mongo_collection):
        """
        Writes this object into an *upsert* `update_one` command on the provided collection handle
        :param mongo_collection:    Mongo collection handle
        """
        if 'game_id' not in self._data:
            raise Exception(f"Cannot update object without game_id field set: { str(self) }")
        mongo_collection.update_one({
            'game_id': self._data['game_id']
        }, {
            '$set': self._data
        }, upsert=True)

    def remove_from(self, mongo_collection):
        """
        Removes this object from a given collection.
        :param mongo_collection:    PyMongo target collection handle
        """
        if 'game_id' not in self._data:
            raise Exception(f"Cannot remove object without game_id field set: { str(self) }")
        mongo_collection.delete_many({
            'game_id': self._data['game_id']
        })

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

    @staticmethod
    def _test_field_and_types(data: dict, fields_and_types: List[Tuple], response: GameResponse, parent_fieldname:str = ""):
        for field, field_type in fields_and_types:
            # If `field` starts with leading underscore '_', consider this field to be optional. In that case,
            # do not remark if the field is missing, but remark any subsequent errors (e.g. malformatted nested data)
            if field[0] == '_':
                # Cut off leading underscore for testing
                optional_field = True
                field = field[1:]
            else:
                optional_field = False

            if field not in data and not optional_field:
                response.add_fail_msg(
                    f"Expected field {field} not found in{f' subelement {parent_fieldname}' if parent_fieldname else ''} data")
            elif field in data:
                # Field is there. Check it for type correctness
                if isinstance(field_type, list):
                    # `field_type` is a list -> Describing a NESTED bit of info data instead of an actual type.
                    # Check if the data itself is a dict
                    if not isinstance(data[field], dict):
                        response.add_fail_msg(f"Expected nested dict at {field} but found {type(data[field])}")
                    else:
                        # Passed dict check! Now recursively check this dict the list of nested parameters
                        DataObject._test_field_and_types(data[field], field_type, response,
                                                         field if not parent_fieldname else f"{parent_fieldname}.{field}")
                elif not isinstance(data[field], field_type):
                    response.add_fail_msg(
                        f"Type of field {field} should be {field_type} but is {type(data[field])}")

    @staticmethod
    def test_data_validity(data: dict, fields_and_types: List[Tuple]) -> bool:
        r = GameResponse()
        DataObject._test_field_and_types(data, fields_and_types, r)
        return not r.has_failed()

    def _apply_validation_job(self, validation_job: dict, response: GameResponse):
        """
        Helper Method for validating data objects. Executes *only* one `validation_job` dict
        :param validation_job:  Validation Job to do
        :return:                Response object for logging output
        """
        # If this class has associated required fields (& types), make the necessary (strict) checks now.
        if 'required_fields' in validation_job:
            DataObject._test_field_and_types(self._data, validation_job['required_fields'], response)

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

        # Validate based on own type
        if own_type in DataObject.type_validators:
            validation_types.append(own_type)

        # Subtype Checks if applicable



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
