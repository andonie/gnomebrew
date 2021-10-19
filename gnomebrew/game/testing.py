"""
This package contains some test routines for Gnomebrew
"""
import json
from typing import Callable

from flask_login import current_user

from gnomebrew.game.objects.game_object import StaticGameObject, update_static_data
from gnomebrew.game.objects.request import PlayerRequest
from gnomebrew.game.user import User, load_user
from gnomebrew.game.util import global_jinja_fun
from gnomebrew.game.gnomebrew_io import GameResponse
from markdown import markdown
from datetime import datetime
from bisect import insort


class TestSuite:
    def __init__(self, function: Callable, **kwargs):
        """
        Initializes the test suite for the function.
        :param function:    The function to initialize a test suite for
        """
        self.function = function
        self.name = kwargs['name'] if 'name' in kwargs else function.__name__


    def __lt__(self, other):
        return self.function.__name__.__lt__(other.function.__name__)

    def get_parameters(self) -> list:
        """
        Returns a list of parameters for this suite
        :return:    Parameter names ordered as appearing in code
        """
        # To get the parameters of the given test function,
        # Take the total list of variables in its code and take only the first ones, being the arguments
        return list(self.function.__code__.co_varnames[:self.function.__code__.co_argcount])

    def get_id(self):
        return self.function.__name__

    def get_name(self):
        return self.name

    def get_description(self):
        docstring = self.function.__doc__
        if not docstring:
            docstring = f"No description available for {self.get_name()}."
        return markdown(docstring.replace('    ', ''))

    def run_test(self, **kwargs) -> str:
        """
        Runs the test and returns an HTML-formatted string as the output.
        :param response Used for logging test results.
        :param kwargs All parameters for this test.
        :return:    Output of the test formatted in HTML
        """
        return self.function(**kwargs)


# Management of all test suites

_test_suites_by_category = dict()
_test_suites_by_id = dict()

def application_test(**kwargs):
    """
    Marks a function as an application test in Gnomebrew.
    A marked function is available in admin view for run-time execution.
    In any module, a module-specific test can be marked by this annotation to be available to an admin during runtime.
    :param kwargs can be:
    * `name`: Name to be displayed
    """

    category = kwargs['category'] if 'category' in kwargs else 'Default'
    def wrapper(fun: Callable):
        suite = TestSuite(fun, **kwargs)

        if category not in _test_suites_by_category:
            _test_suites_by_category[category] = list()

        insort(_test_suites_by_category[category], suite)
        assert suite.get_id() not in _test_suites_by_id
        _test_suites_by_id[suite.get_id()] = suite
        return fun

    return wrapper


# Executing Tests

@PlayerRequest.type('execute_test', is_buffered=False)
def execute_test(user: User, request_object: dict, **kwargs):
    response = GameResponse()
    request_object = dict(request_object)
    request_object.pop('request_type')
    if not user.is_operator():
        # User is not authorized to execute tests.
        response.add_fail_msg("You are not authorized to execute tests.")
        return response


    try:
        suite: TestSuite = _test_suites_by_id[request_object.pop('test_id')]
    except KeyError as e:
        response.add_fail_msg(f"Did not find the test ID:<br/>{str(e)}")
        return response

    start = datetime.now()
    response.append_into(suite.run_test(**request_object))
    end = datetime.now()
    response.set_parameter('exec_time', str(end-start))

    # No failed test means success in request
    if 'type' not in response.to_json() or response.to_json()['type'] != 'fail':
        response.succeess()

    return response


# UI Compatibility:

@global_jinja_fun
def GET_TEST_SUITE_CATEGORY_LOOKUP():
    return _test_suites_by_category


@global_jinja_fun
def GET_TEST_SUITES_LIST():
    return sorted(_test_suites_by_id.values())


## Some Tests

@application_test(name="User Assertions", category='Testing')
def user_assertions(username: str):
    """
    Runs an assertion script that checks the user's game data for integrity (problems being for example missing game
    events or 'dead' patrons in the tavern data).
    Any assertion that has been registered via `user_assertion` will be tested.

    Requires a valid `username`
    """
    response = GameResponse()

    user = load_user(user_id=username)
    if not user:
        response.add_fail_msg(f"Username {username} not found.")
        return response

    success = False
    try:
        User.game_integrity_assertions(user)
        success = True
    except AssertionError as e:
        response.add_fail_msg(str(e))

    if success:
        response.log("All Assertions were successful.")
        response.succeess()

    return response


@application_test(name='Update Game ID', category='Mechanics')
def update_game_id(game_id: str, update_json: str, username: str):
    response = GameResponse()
    if username and username != "":
        user = load_user(username)
        if not user:
            response.add_fail_msg(f"Could not load user {username}")
    else:
        # TODO implement default update execution without user
        pass

    update = json.loads(update_json)

    user.update(game_id, update)

    response.log(f"Added {update=}\nto {game_id=}")

    return response





@application_test(name='Evaluate Game ID', category='Mechanics')
def evaluate_game_id(game_id: str, username: str):
    """
    Evaluates a given `game_id` on a user and returns a string representation of the result. If no `username` is given,
    evaluates on current player. Valid IDs are for example:

    * `item.gold`
    * `data.station.storage.content.iron`
    """
    response = GameResponse()
    if username is None or username == '':
        user = current_user
    else:
        user = load_user(username)
        if not user:
            response.add_fail_msg(f"Username {username} not found.")
            return response

    result = str(user.get(game_id))
    response.log(result)

    return response


@application_test(name='Reload Static Objects', category='Data')
def reload_static_objects():
    """
    Reloads all static objects from MongoDB. Only after execution will changes in the DB take effect on static objects.
    """
    response = GameResponse()
    update_static_data()
    response.log('Static Data Updated Successfully')
    return response
