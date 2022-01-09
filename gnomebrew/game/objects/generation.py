"""
This module manages the general generation logic by implementing a pseudorandom number generator, the back-bone for things like generating names, locations, etc.
"""
import math
import re
from numbers import Number
from typing import Dict, Any, Union, Tuple, Callable, List

import numpy

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.static_data import dataframes
from gnomebrew.game.testing import application_test
from gnomebrew.game.util import random_uniform
from gnomebrew.game.objects.game_object import load_on_startup, StaticGameObject, GameObject


class Environment:
    """
    Manages an environment of generated (and fixed) variables.
    """

    # Stragies for updating an existing value based on the update value type
    _update_strategies_by_type = {
        Number: lambda gen, old, new: old + new,
        str: lambda gen, old, new: new,
        list: lambda gen, old, new: old + new,
        dict: lambda gen, old, new: {**old, **new}
    }

    _update_strategies_by_name = dict()

    def __init__(self):
        self.variables = dict()

    def __str__(self):
        var_str = ''
        for variable in self.variables:
            var_str += f"{variable}: {str(self.variables[variable])}\n"
        return f"<Environment:\n{var_str}>"

    def create_copy(self):
        """
        Creates a new environment with identical properties to this one.
        :return:    A new environment with identical properties to this one.
        """
        copy = Environment()
        copy.variables = self.variables.copy()
        return copy

    def is_set(self, varname) -> bool:
        return varname in self.variables

    def set_env_var(self, varname, val):
        self.variables[varname] = val

    def get(self, varname):
        return self.variables[varname]

    def get_variables(self):
        return self.variables

    def update(self, gen: 'Generator', varname: str, value):
        """
        Updates an environment variable with given details.
        If the variable has not been set, it will be set. If it already exists and there is a more sophisticated
        strategy available, the existing and the update value will be combined accordingly; if not, the value will
        be set hard to the new input.
        :param gen:         The active generator of this environment
        :param varname:     The variable to update.
        :param value:       The update value.
        """
        if varname not in self.variables:
            self.variables[varname] = value
        else:
            # Variable is already defined. Pick the most appropriate update strategy
            if varname in Environment._update_strategies_by_name:
                # There's a strategy specific to this variable name. Use it
                strategy = Environment._update_strategies_by_name[varname]
            else:
                strategy = next(Environment._update_strategies_by_type[datatype]
                                for datatype in Environment._update_strategies_by_type
                                if isinstance(value, datatype))
            if not strategy:
                # no match, hard set
                self.variables[varname] = value
            else:
                self.variables[varname] = strategy(gen, self.variables[varname], value)

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
        intersect = set(self.variables.keys()) & set(rules.keys())
        # Directly insert whatever value from other we don't have set in self
        self.variables.update({k: v for k, v in rules.items() if k not in intersect})
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


class Generator:
    """
    Implementation of a controllable Random Number Generator for Gnomebrew.
    Instances of `Generator` are not used to generate intended randomness in game but rather are used as a crutch
    to simulate huge variety in the game world without having to save the raw data.

    Additionally, `Generator` provides abstract access to **environment variables** that might impact probabilities
    during generation.
    """

    # RNG constants

    a = 29943829  # Thank you: https://www.iro.umontreal.ca/~lecuyer/myftp/papers/latrules99Errata.pdf
    c = 182903  # Any odd number should work
    m = 4294967296  # 2 ^ 32
    m_bit_and = m - 1  # Value used for bitwise AND to speed up modulo operations

    # Other Constants used

    euler_mascheroni = numpy.euler_gamma

    # Calculate the first harmonic numbers 'by hand', because the approximating function is really bad
    # for small values.
    MAX_LOOKUP_HARMONIC_NUMBER = 30
    # Harmonic Numbers Table
    H = {n: sum(1 / i for i in range(1, n + 1)) for n in range(1, MAX_LOOKUP_HARMONIC_NUMBER + 1)}

    def __init__(self, seed: Union[int, str], environment: Environment):
        if type(seed) == str:
            # Convert string to valid int.
            seed = Generator.string_to_seed(seed)

        assert 0 <= seed < Generator.m
        self.x = seed
        self.environment = environment

    #               RNG

    def next(self) -> int:
        """
        Fundamental number generation function. Calculates the next number in this generator's random number sequence fast.
        Changes this generator's state so that the next number will be different (most probably)
        :return:    The generated random number.
        """
        self.x = (Generator.a * self.x + Generator.c) & Generator.m_bit_and
        return self.x

    def rand_int_limited(self, max_excl: int) -> int:
        """
        Generates the next number, ensuring it is anywhere between `0` (inclusive) and `max_excl` (exclusive).
        :param max_excl:    The upper limit of the next number needed (exclusive)
        :return:            A generated number n with 0 <= n < `max_excl`
        """
        return self.next() % max_excl

    def rand_unit(self) -> float:
        """
        Generates a random number between 0 and 1.
        :return:    A number in [0;1)
        """
        return self.next() / Generator.m

    def rand_float(self, min_value: float, max_value: float):
        """
        Generates a random float in given bounds.
        :param min_value: Minimum (inclusive)
        :param max_value: Maximum (exclusive)
        :return:    A generated float in bounds (uniformly distributed probability)
        """
        return self.rand_unit() * (max_value - min_value) + min_value

    def rand_normal(self, **kwargs) -> float:
        """
        Generates a normally distributed variable
        :keyword deviation  Standard deviation, 1 by default
        :keyword media  Median. 0 by default
        :return:    A random number following the standard normal distribution, unless specified otherwise.
        """
        if 'min' and 'max' in kwargs:
            median = (kwargs['min'] + kwargs['max']) / 2
            std_deviation = (kwargs['max'] - kwargs['min']) / 6
            return max(min(self.rand_normal(median=median, deviation=std_deviation),
                           kwargs['max']),
                       kwargs['min'])

        u_1, u_2 = self.rand_unit(), self.rand_unit()
        res = math.sqrt(-2 * math.log(u_1)) * math.cos(2 * math.pi * u_2)
        # Deviation = 1
        if 'deviation' in kwargs:
            res *= kwargs['deviation']
        if 'median' in kwargs:
            res += kwargs['median']
        return res

    def choose(self, choices_and_weights: Dict[Any, int]):
        """
        Makes a pseudorandom choice of one element in a set of options.
        :param choices_and_weights: a `dict` where each key is a choice and the associated value an `int` representing
                                    this choice's 'weight' relative to alternative choices. Weights smaller or equal to
                                    `0` are ignored entirely and can safely be included.
        :return:                    One key of `choices_and_weights` as the de-facto choice.
        """
        reverse_lookup = dict()
        weight_total = 0
        for option in choices_and_weights:
            if choices_and_weights[option] <= 0:
                continue
            weight_total += choices_and_weights[option]
            reverse_lookup[weight_total] = option

        random_val = self.rand_int_limited(weight_total)
        # Return the next biggest lookup value
        return reverse_lookup[min(filter(lambda v: random_val < v, reverse_lookup.keys()))]

    def generate_pareto_index(self, num_choices) -> int:
        """
        Generates a pareto index.
        Assuming a choice of `num_choices` different options with pareto-distributed probability (first option most
        probable, last option least probable).
        :param num_choices:     The total number of choices.
        :return:                An index between `0` and `num_choices-1` (each inclusive) that represents the generated
                                pareto-choice.
        """
        if num_choices <= Generator.MAX_LOOKUP_HARMONIC_NUMBER:
            # Too small to approximate with function
            total_weight = Generator.H[num_choices]
        else:
            # Big enough to use approximate with function
            total_weight = Generator.euler_mascheroni + math.log(num_choices)

        # Generate a uniformly distributed random value in the weight-space defined
        uniform_variable = self.rand_float(0, total_weight)

        if uniform_variable >= max(Generator.H.values()):
            # Variable is greater than the largest value in the lookup. Use approximation
            return math.floor(math.exp(uniform_variable - Generator.euler_mascheroni))  # floor to be zero indexed
        else:
            # Variable within value range of lookup table. Use it.
            return min(filter(lambda n: uniform_variable < Generator.H[n],
                              Generator.H.keys())) - 1  # -1 to be zero indexed

    def choose_pareto(self, options: list):
        """
        Makes a choice with pareto-distribution, meaning that the earlier an element appears in the given list of
        options, the more probable it is to be selected.
        :param options:     I list of options to choose one from.
        :return:            One chosen element from the list.
        """
        index = self.generate_pareto_index(len(options))
        return options[index]

    # Regex to check against during string evaluations

    _type_regex = re.compile(r"<([\w ]*)>")

    def evaluate_string(self, command_string: str) -> str:
        """
        Evaluates a command string and returns the resulting string
        :param command_string:  A string representing a 'recipe' to create a string, using `Raw text <Type>|Alternative`
                                notation.
        :return:                A generated string
        """
        options = command_string.split('|')
        if len(options) > 1:
            # Choose one option randomly and continue
            return self.evaluate_string(options[self.rand_int_limited(len(options))])

        # We now have no more options to weigh, only clear text and <Type> subgenerations
        res = ''
        next_index = 0
        for match in Generator._type_regex.finditer(command_string):
            match_start, match_end = match.span()
            # Add the next clean part
            res += command_string[next_index:match_start]
            # Replace the match context
            gen_type = match.group()
            gen_type = gen_type[1:len(gen_type) - 1]
            res += self.generate(gen_type)
            next_index = match_end
        if next_index < len(command_string):
            res += command_string[next_index:]
        return res

    def generate(self, type: str, **kwargs):
        """
        Generates any type that can be generated.
        :param type:    The type to be generated. Must have associated function decorated with `generator_logic`.
        :return:        A generated entity of the given type.
        """
        assert type in _generation_functions
        result = _generation_functions[type]['fun'](self, **kwargs)
        return result

    def choose_from_data(self, source: str, strategy: str = 'uniform', columns: Union[int, str, List] = 0):
        """
        Wrapper to semi-randomly choose one row from a source of static data.
        :param source:          The complete and unique ID string of the data source.
        :param strategy:        Describes the desired probability distribution for the results. Possible values are:
                                * `uniform` (default): Every data row has the same probability of being chosen.
                                * `pareto`: The probability of a row to be chosen is pareto-distributed across the
                                entire data source (with the first rows being most and the last rows being least probable)
        :param columns:         Describes the columns to be included in the selection of the selected row.
                                By default only returns only the value at column index 0. Used to address results
                                via `iloc`. Can be:
                                * String: Describing the CSV column header to select from
                                * Int:    Describing the CSV column index (starts at 0) to select from
                                * List:   Must be either exclusively `int` or `str` values. Will include all
        :return:                The value(s) of the chosen row. If a column name/index was given, returns the direct
                                value. If a list was given (also a list of length 1), returns a list ordered like the
                                input column list with the values retrieved.
        :raises                 Any pandas-generated exception due to bad input.
        """
        assert source in dataframes
        target_df = dataframes[source]
        total_rows = len(target_df.index)

        # Pick an Index in bounds based on strategy chosen
        if strategy == 'uniform':
            index = self.rand_int_limited(total_rows)
        elif strategy == 'pareto':
            index = self.generate_pareto_index(total_rows)
        else:
            raise Exception(f'Unknown strategy to pick from data source: {strategy}')

        # Get the row of the generated index
        selection = target_df.iloc[index][columns]
        if isinstance(columns, list):
            # List of columns was provided. Turn output into list to get rid of panda frame
            selection = selection.values.tolist()
        return selection

    # Generation Rules

    def process_generation_rule(self, rule: dict):
        """
        Processes a generation rule as defined by its rule data.
        :param rule:    Correctly formatted rule data, e.g. `{}`
        :return:        The result of the generation.
        """
        if len(rule) != 1:
            raise Exception(f"Don't know how to process rule: {str(rule)}")

        ruletype = next(iter(rule))
        if ruletype not in _generation_rules_by_name:
            raise Exception(f"Don't know how to process rule type: {ruletype}")

        return _generation_rules_by_name[ruletype](self, rule[ruletype])

    # Environment Wrap

    def get_env_var(self, varname: str, **kwargs):
        """
        Evaluates an environment variable.
        :param varname: The environment variable to test, e.g. 'Humidity'
        :keyword default:    Should the variable not be defined in this context, `default` will be returned instead.
        :return:        The result of the evaluation, or `default`. If `default` is not set and the variable does not
                        exist, raises an Exception
        """
        if self.environment.is_set(varname):
            return self.environment.get(varname)
        elif 'default' in kwargs:
            return kwargs['default']
        else:
            raise Exception(f"Variable {varname} is not set in this context: {self.environment}.")

    def get_environment(self):
        """
        :return:    This generator's entire environment.
        """
        return self.environment

    def update_env_var(self, varname: str, val):
        """
        Updates an environment variable value.
        :param varname:     The name of the variable to update.
        :param val:         The value of the variable to update.
        """
        self.environment.update(self, varname, val)

    def incorporate_env_rules(self, rules: dict):
        """
        Incorporates a set of environment rules into this generator's environment.
        :param rules:   A set of rules to be incorporated into this generator's environment.
        """
        self.environment.incorporate_rule_dict(self, rules)

    # Static Methods

    @staticmethod
    def string_to_seed(string: str) -> int:
        """
        Formats a valid string into its corresponding `int` to be used as a generator's seed
        :param string:  A string. Must be formatted as a **hexadecimal** (e.g. `A83e`, `BEeF`). Character caps is
                        irrelevant.
        :return:    The valid seed for a `Generator` that corresponds 1-to-1 to the given string.
        """
        return int(string, 16)

    @staticmethod
    def seed_to_string(seed: int) -> str:
        """
        Formats a valid seed into its corresponding string to be used for data representation.
        :param seed:    A valid seed for a `Generator`
        :return:        The corresponding encoded string that represents the given seed.
        """
        hex_repr = hex(seed)  # Creates a hex-representation of the seed starting with '0x'
        hex_repr = hex_repr[2:]  # Trim redundant leading digits
        if len(hex_repr) < 4:  # Add leading zeros up to 4 digits if necessary
            hex_repr = '0' * (4 - len(hex_repr)) + hex_repr
        return hex_repr

    @staticmethod
    def true_random_generator_seed():
        """
        Generates a random generator seed.
        For many use cases, we want generators to be 'deterministic' (e.g always generate the same location at the same
        coordinates). Sometimes we consciously don't want that.
        :return:    A random seed for the game's generator.
        """
        generated = int(random_uniform(min=0, max=Generator.m_bit_and))
        return generated


class GeneratedGameObject(GameObject):
    """
    Describes a game object that, unlike e.g. a `StaticGameObject` is not read from a data repository but instead
    generated dynamically on the fly.
    A `seed` is given when instantiating any such object. The same seed generates the same game object every time.
    """


@load_on_startup('generation_rules')
class GenerationRule(StaticGameObject):
    """
    Describes a general rule for generating something based on simple rules in the game.
    Used for World Generation, can be used for more.
    """

    rules_by_name = dict()

    def __init__(self, mongo_data):
        super().__init__(mongo_data)

    def get_generation_class(self):
        return self._data['game_id'].split('.')[1]

    @classmethod
    def get_rule_by_name(cls, name: str, **kwargs) -> 'GenerationRule':
        """
        :param name:        A unique `name` of a generation rule.
        :keyword default    If this keyword is included and `name` is not a known generation rule, will return
                            `default` instead of raising a `KeyError`.
        :return:            The rule object corresponding to the given `name`
        """
        if name not in cls.rules_by_name:
            if 'default' in kwargs:
                return kwargs['default']
            else:
                raise KeyError(f"{name} is not a known generation rule")
        return cls.rules_by_name[name]

    @classmethod
    def on_data_update(cls):
        """
        Called when all generation rules from the DB have been loaded (or re-loaded).
        In here,
        """
        all_rules = StaticGameObject.get_all_of_type('gen')
        for rule in all_rules:
            cls.rules_by_name[all_rules[rule].name()] = all_rules[rule]


# Generation Rule Data Validation

GenerationRule.validation_parameters(('game_id', str), ('name', str), ('description', str),
                                     ('gen_attr', dict), ('env_rules', dict))

## INTERFACING for generation algos:

_generation_functions: Dict[str, Dict] = dict()


def generation_type(gen_type: str, ret_type: Any = Any, update_env: bool = True, **kwargs):
    """
    Decorator to mark a **function** as a generator for Gnomebrew.
    A decorated function expects a `generator` variable to use for any and all RNG based operation and for potentially
    generating sub-parts of the associated entity.
    :keyword replace:   If `True`, no checks will be made with the mentioned logic already exists. Instead,
                        any possibly existing logic associated with `gen_type` will be replaced
    :param gen_type:    The type of the generated entity. Calling `generator.generate(gen_type)` executes the decorated
                        function.
    :param ret_type:    (optional) Type of the returned value when a respective entity is generated. 
    """
    if 'replace' not in kwargs or kwargs['replace']:
        assert gen_type not in _generation_functions

    def wrapper(fun: Callable):
        fun_data = dict()
        fun_data['fun'] = fun
        fun_data['return'] = ret_type
        fun_data['update_env'] = update_env
        _generation_functions[gen_type] = fun_data
        return fun

    return wrapper


_generation_rules_by_name = dict()


def generation_rule(name: str):
    """
    Annotation function. Creates a generic generation rule based upon which the game can generate data.
    Annotated functions are expected return the result of the generation and to have these parameters:
    * `generator`   The executing generator
    * `rule_data`   The data to be evaluated in the style of the rule.
    :param name:    The unique name of this generation rule
    """
    assert name not in _generation_rules_by_name

    def wrapper(fun: Callable):
        _generation_rules_by_name[name] = fun
        return fun

    return wrapper


@generation_rule('str')
def generate_string(gen: Generator, rule_data: str):
    return gen.evaluate_string(rule_data)


# Processing Rules

_processing_rules = dict()


def processing_rule(name: str):
    """
    Annotation function. Marks a function as a processing function for generation purposes.
    Processing functions are used for updating environment variables. A processing function expects:
    * A generator
    * The old value
    * The new update data (can be any JSON data)
    :param name:    Name of this processing rule
    """
    assert name not in _processing_rules

    def wrapper(fun: Callable):
        _processing_rules[name] = fun
        return fun

    return wrapper


def apply_processing_rule(gen: Generator, old, new):
    """
    Applies a processing rule and returns the result.
    :param gen:     Active generator for this processing.
    :param old:     Old value.
    :param new:     New data containing processing rule data.
    :return:        Result of applying the processing rule
    """
    rule_name = next(iter(new))
    assert rule_name in _processing_rules
    return _processing_rules[rule_name](gen, old, new[rule_name])


@processing_rule('move_towards')
def move_towards(gen: Generator, old: float, new: dict):
    """
    Move `max_move` closer to a given `target`
    """
    total_distance = abs(old - new['target'])
    if total_distance < new['max_move']:
        return new['target']
    else:
        return old + new['max_move'] * math.copysign(1, new['target'] - old)


@application_test(name='RNG Test', category='Mechanics')
def rng_test(seq_size, seed):
    """
   Generates numbers between 0 and `seq_size` using the game's internal RNG feature and prints test results.
   Optionally, you can define the `seed` (can be left empty)
   """
    response = GameResponse()

    if not seed or seed == '':
        seed = Generator.true_random_generator_seed()
    else:
        seed = int(seed)

    if not seq_size or seq_size == '':
        seq_size = 12
    else:
        seq_size = int(seq_size)

    gen = Generator(seed, None)
    cnt_uniform = dict()
    cnt_normal = dict()
    total = 2000000
    for i in range(total):
        num_linear = gen.rand_int_limited(seq_size)
        if num_linear not in cnt_uniform:
            cnt_uniform[num_linear] = 0
        cnt_uniform[num_linear] += 1

        num_normal = int(gen.rand_normal(min=0, max=seq_size))
        if num_normal not in cnt_normal:
            cnt_normal[num_normal] = 0
        cnt_normal[num_normal] += 1

    response.log('Uniform Distribution Results:')
    in_percent = {key: f"{value / total:.3%}" for key, value in cnt_uniform.items()}
    for i in sorted(in_percent.keys()):
        response.log(f"{'&nbsp;' * (4 - math.floor(math.log10(i if i > 0 else 1)))}{i}: {in_percent[i]}")
    response.log('==================================================')
    response.log('Normal Distribution Results:')
    in_percent = {key: f"{value / total:.3%}" for key, value in cnt_normal.items()}
    for i in sorted(in_percent.keys()):
        response.log(
            f"{'&nbsp;' * (4 - math.floor(math.log10(i if i > 0 else 1)))}{i}: {in_percent[i]} ({cnt_normal[i]})")

    return response


@application_test(name='Pareto RNG Test', category='Mechanics')
def pareto_test(seq_size, num_options):
    """
    Tests the game's pareto distribution function `seq_size` times and summarizes the results.
    If `seq_size` is empty, will perform 200000 runs
    If `num_options` is empty, will use internal list
    """
    response = GameResponse()

    if seq_size is None or seq_size == '':
        seq_size = 200000
    else:
        seq_size = int(seq_size)

    if num_options is None or num_options == '':
        options = ['Lydan', 'Syrin', 'Ptorik', 'Joz', 'Varog', 'Gethrod', 'Hezra', 'Feron', 'Ophni', 'Colborn',
                   'Fintis',
                   'Gatlin', 'Jinto', 'Hagalbar', 'Krinn', 'Lenox', 'Revvyn', 'Hodus', 'Dimian', 'Paskel', 'Kontas',
                   'Weston', 'Azamarr', 'Jather', 'Tekren', 'Jareth', 'Adon', 'Zaden', 'Eune', 'Graff', 'Tez', 'Jessop',
                   'Gunnar', 'Pike', 'Domnhar', 'Baske', 'Jerrick', 'Mavrek', 'Riordan', 'Wulfe', 'Straus', 'Tyvrik',
                   'Henndar', 'Favroe', 'Whit', 'Jaris', 'Renham', 'Kagran', 'Lassrin', 'Vadim', 'Arlo', 'Quintis',
                   'Vale', 'Caelan', 'Yorjan', 'Khron', 'Ishmael', 'Jakrin', 'Fangar', 'Roux', 'Baxar', 'Hawke']
    else:
        options = [f"Option {i}" for i in range(int(num_options))]

    generator = Generator(Generator.true_random_generator_seed(), None)
    counter = dict()
    for option in options:
        counter[option] = 0

    for n in range(seq_size):
        selection = generator.choose_pareto(options)
        counter[selection] += 1

    in_percent = {key: f"{value / seq_size:.3%}" for key, value in counter.items()}
    expected = {options[i]: (1 / (i + 1)) / (Generator.euler_mascheroni + math.log(len(options))) for i in
                range(len(options))}
    expected_count = {options[i]: expected[options[i]] * seq_size for i in range(len(options))}
    for option in options:
        if True or expected_count[option] < counter[option]:
            response.log(f"{option}: {in_percent[option]} [expected: {expected[option]:.3%}]({counter[option]})")

    for n in range(1, 100):
        print(f"--- n={n} ---")
        h_n = sum(1 / i for i in range(1, n + 1))
        approx = Generator.euler_mascheroni + math.log(n)
        print(f"Harmonic Number: {h_n}")
        print(f"With Formula:    {approx}")
        print(f"Difference:      {h_n - approx} ({(h_n - approx) / h_n:.2%})")

    return response


@application_test(name='Choose from Datasource', category='Mechanics')
def choose_from_data_test(source: str, strategy: str, seq_size):
    """
    Makes `seq_size` random selections from a given `source` using a `strategy` (`uniform` or `pareto`).
    """
    response = GameResponse()

    if strategy is None or strategy == '':
        strategy = 'pareto'

    if seq_size is None or seq_size == '':
        seq_size = 50000
    else:
        seq_size = int(seq_size)

    generator = Generator(Generator.true_random_generator_seed(), Environment())
    count = dict()

    for i in range(seq_size):
        res = generator.choose_from_data(source, strategy)
        if res not in count:
            count[res] = 0
        count[res] += 1

    for res in count:
        response.log(f"{res}: {count[res]}")

    return response
