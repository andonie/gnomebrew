"""
This module outsources the simple game statistics feature. The feature is used
for statistics, as the name implies. More generally, a game statistic is a value that is **expected to change frequently
throughout gameplay** and optimized for such operations, unlike the more general `data` module with its' bloaty
`user` collection that manages data with significantly more volume and lower throughput.
Instead of using that genaral collection, the module manages its own collection `player_statistics`.
"""
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.testing import application_test
from gnomebrew.game.user import User, get_resolver, update_resolver, load_user
from gnomebrew import mongo
from gnomebrew.game.event import Event


@update_resolver('stat')
def statistical_update(user: User, game_id: str, update, **kwargs):
    """
    Shorthand-Method for a statistics update for this user. Statistics are managed in a separate MongoDB collection.
    Used throughout executing modules (Base modules, market, tavern, etc.) to put KPIs in the user's statistics.
    :param game_id:  The variable that is to be updated.
                     Should follow the format `stat.module_name.variable_name`, e.g. `stat.market.revenue` or `stat.base.recipes_executed`
    :param update:  The update value. Is usually expressed as a **delta from last value instead of final value, so
                    `update = 5` increments the variable at `game_id` by `5`.
    :param kwargs:
    * `mongo_command`: The MongoDB command to use (default $inc)
    * `is_bulk`: If this is `True`, the command expects a **list** at `statistic_variable` (and a list at `command_value`
        of equal length)
    """
    splits = game_id.split('.')
    assert splits[0] == 'stat'

    mongo_command = kwargs['mongo_command'] if 'mongo_command' in kwargs else '$inc'

    update_content = dict()
    if 'is_bulk' in kwargs and kwargs['is_bulk']:
        # Bulk update: Many values to add
        for path in update:
            update_content[game_id + '.' + path] = update[path]
    else:
        update_content[game_id] = update

    # Update DB
    mongo.db.player_statistics.update_one({'username': user.get_id()}, {mongo_command: update_content})

    return update_content


@get_resolver('stat')
def get_statistical_data(user: User, game_id: str, **kwargs):
    """
    Resolves a user request for statistical data and optimally requests this data from MongoDB.
    :param user:        A user.
    :param game_id:     The ID of what's requested. In special cases (e.g. `bulk`), this must be set to `stat`
    :param kwargs:

    * `default`: A default value to return instead of a `KeyError` if the requested variable does not yet exist.

    Only one of these can be chosen:

    * `bulk`: Requests a bulk-retrieve from the database for multiple values specified in the variable, e.g.
                `bulk=['market.revenue', 'workshop.recipes']` to retrieve all variables in the list
    * `all`: If `get('stat', all=True)` is called, the function returns all known statistical variables associated with
                the user.
    :return:    The result of the statistical data request. Usually a number.
                For special use cases `bulk` and `all`, the return result will be a `dict` instead mapping all requested
                fully qualified `game_id`s to their respective values.

    """
    splits = game_id.split('.')
    assert splits[0] == 'stat'

    # Base projection ignores MongDB _id field
    mongo_projection = {'_id': 0}

    # Special Use Cases:
    if 'bulk' in kwargs:
        for id_patch in kwargs['bulk']:
            mongo_projection[game_id + '.' + id_patch] = 1
    elif not ('all' in kwargs and kwargs['all']):
        # If not ALL option selected, we add the element of the non-bulk statistic requested
        mongo_projection[game_id] = 1

    # All is accounted for. Time to run the MongoDB command
    result = mongo.db.player_statistics.find_one({'username': user.get_id()}, mongo_projection)

    if not ('bulk' in kwargs or ('all' in kwargs and kwargs['all'])):
        # Usual return case: Return direct value
        for split in splits:
            try:
                result = result[split]
            except KeyError as e:
                # Most likely this means a statistic was requested that does not yet exist.
                if 'default' in kwargs:
                    return kwargs['default']
                else:
                    raise e

    return result


@Event.register_effect
def apply_statistics(user: User, effect_data: dict, **kwargs):
    """
    Applies basic (/default) statistics updates for a user when fired.
    :param user:            A user.
    :param effect_data:     Effect data formatted as `effect_data['<stat_id>'] = update_value`
    """
    user.update('stat', effect_data, is_bulk=True)


# Testing Stuff

@application_test(name='Statistics Test', category='Mechanics')
def statistic_test(username: str, num_increase):
    """
    Makes a few increases on a given users statistics.

    Requires a valid `username` and a number `num_increase` that increments the statistics
    """

    response = GameResponse()
    num_increase = float(num_increase)

    user = load_user(user_id=username)
    if not user:
        response.add_fail_msg(f"Username {username} not found.")
        return response

    statistics_to_test = ['stat.tavern.patrons_served', 'stat.tavern.alcohol_sold', 'stat.base.recipes_executed', 'stat.market.revenue']
    for game_id in statistics_to_test:
        response.log(f"updating {game_id}:")
        user.update(game_id, num_increase)

    for game_id in statistics_to_test:
        response.log(f"retrieving {game_id}: {user.get(game_id)}")

    #response.log(str(user.get('stat', bulk=['', ])))

    return response
