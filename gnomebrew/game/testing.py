"""
This package contains some test routines for Gnomebrew
"""
from typing import Callable

from gnomebrew.game.user import User, load_user
from gnomebrew.game.util import global_jinja_fun
from gnomebrew.play import request_handler
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
        return markdown(self.function.__doc__.replace('    ', ''))

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
        _test_suites_by_id[suite.get_id()] = suite
        return fun

    return wrapper


# Executing Tests

@request_handler
def execute_test(request_object: dict, user: User):
    response = GameResponse()
    request_object = dict(request_object)
    request_object.pop('type')
    if not user.is_operator():
        # User is not authorized to execute tests.
        response.add_fail_msg("You are not authorized to execute tests.")
        return response

    start = datetime.now()
    try:
        suite: TestSuite = _test_suites_by_category[request_object.pop('test_id')]
    except KeyError as e:
        response.add_fail_msg(f"Did not find the test ID:<br/>{str(e)}")
    end = datetime.now()

    response.append_into(suite.run_test(**request_object))
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
