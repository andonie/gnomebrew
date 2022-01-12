"""
Environment describes an abstract set of variables that are known in a given context.
The environment class tracks *nested generation contexts*, e.g. enabling a generation chain as:
0. Init generator & environment
1. Generate Region
2. Generate Structure (using Region env. data)
3. Generate Quests (using Region & Structure env. data)
...
"""
from copy import deepcopy
from numbers import Number
from typing import Callable, List

from gnomebrew.game.objects.data_object import DataObject


class Environment(DataObject):
    """
    Wraps environment data.
    """

    _update_strategies_by_name = dict()

    def __init__(self, data: dict):
        DataObject.__init__(self, data)

    @classmethod
    def empty(cls) -> 'Environment':
        """
        Generates an empty environment object.
        :return:    The generated, empty environment
        """
        return Environment({
            'variables': {},
            'stack': [[]]
        })

    def __str__(self):
        var_str = ''
        for variable in self._data['variables']:
            var_str += f"{variable}: {str(self._data['variables'][variable])},\n"
        return f"<Environment:\n{var_str}>"

    def create_copy(self):
        """
        Creates a new environment with identical properties to this one.
        :return:    A new environment with identical properties to this one.
        """
        copy = Environment(deepcopy(self._data))
        return copy

    def has_variable(self, varname) -> bool:
        """
        Checks if a variable is set in this environment.
        :param varname:     Variable name to check.
        :return:            `True`, if variable is set in this environment. Otherwise `False`.
        """
        return varname in self._data['variables'] and self._data['variables'][varname]

    def get(self, varname, **kwargs):
        """
        Retrieves a variable from the environment.
        :param varname:     Variable Name
        :keyword default:   Default in case variable doesn't exist
        :return:            Variable value. If variable is not set and `default` provided, will return
                            the given default value.
        """
        if varname not in self._data['variables'] or not self._data['variables'][varname]:
            if 'default' in kwargs:
                return kwargs['default']
            else:
                raise Exception(f"Unknown variable ({varname}) requested without default.")
        else:
            return self._data['variables'][varname][-1]

    def get_variables(self):
        return self._data['variables']

    def update(self, gen: 'Generator', varname: str, value, stack_offset: int = 0):
        """
        Updates an environment variable with given details.
        If the variable has not been set, it will be set. If it already exists and there is a more sophisticated
        strategy available, the both values will be combined accordingly; if not, the value will
        be set hard to the new input.
        :param gen:         The active generator of this environment
        :param varname:     The variable to update.
        :param value:       The update value.
        """
        if stack_offset < 0:
            raise Exception(f"Negative offset is not allowed: {stack_offset}")

        # STEP 1: Add the variable to the data
        if varname not in self._data['variables']:
            # No entry yet. Add an empty 'editing history' list with the given value
            self._data['variables'][varname] = [value]
        else:
            # Variable is already defined. Pick the most appropriate update strategy
            if varname in Environment._update_strategies_by_name:
                # There's a strategy specific to this variable name. Use it
                strategy = Environment._update_strategies_by_name[varname]
            else:
                # There is no dedicated strategy for this variable name. Instead, pick a fitting strategy from the
                # Default strategies
                strategy = None
            if not strategy:
                # no match, hard set
                self._data['variables'][varname].append(value)
            else:
                self._data['variables'][varname].append(strategy(gen, self._data['variables'][varname], value))

        # STEP 2: Update the stack information
        self._data['stack'][-1 - stack_offset].append(varname)

    def increase_stacklevel(self):
        """
        Increases this environment\'s stack level.
        All variables added before this call are safe from the next `decrease_stacklevel`.
        """
        # Append a new stack list at the end of the list
        self._data['stack'].append([])

    def decrease_stacklevel(self):
        """
        Decreases this environment\'s stack level.
        Removes all variable updates since the last `increase_stacklevel`.
        """
        # Pop the latest stack element: The list of changed variable names
        level_variables: List[str] = self._data['stack'].pop()

        # Remove all variables from latest level
        for variable_to_remove in level_variables:
            self._data['variables'][variable_to_remove].pop()

    def incorporate_env(self, other):
        """
        Incorporates the data from another environment.
        :param other:   Another environment.
        """
        self.incorporate_rule_dict(other.variables)

    def incorporate_rule_dict(self, gen: 'Generator', rules: dict):
        """
        Incorporates a dictionary of environment variables. After this function has been called, this environment will

        * Contain all environment variables that have not been set yet as they appear in `rules`.
        * call `update` on all variables in `rules` that already exist in this environment

        :param gen:   A generator to use for eventual RNG
        :param rules: A `dict` of values to incorporate
        """
        intersect = set(self._data['variables'].keys()) & set(rules.keys())
        # Directly insert whatever value from other we don't have set in self
        self._data['variables'].update({k: v for k, v in rules.items() if k not in intersect})
        for key in intersect:
            # Properly configure updates for variables already set
            self.update(gen, key, rules[key])

    @staticmethod
    def update_rule(var_name: str):
        """
        Annotation method to signify a special rule for how to update a particular environment variable.
        :param var_name:    The name of the environment variable for which this rule is to be applied.
        :return         Expects a function with two parameters (old & new) that returns the result of the applied
                        update rule.
        """

        def wrapper(fun: Callable):
            Environment._update_strategies_by_name[var_name] = fun
            return fun

        return wrapper


# Environment Data Validation
Environment.validation_parameters(('variables', dict), ('stack', list))
