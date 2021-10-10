"""
The divination table module enables the player to view a part of the world map.
"""
from os.path import join
from typing import List, Union

from flask import render_template

from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.objects import WorldLocation
from gnomebrew.game.objects.game_object import render_object
from gnomebrew.game.objects.world import get_world_location
from gnomebrew.game.testing import application_test
from gnomebrew.game.user import User, html_generator, id_update_listener
from gnomebrew.game.util import global_jinja_fun, transpose_matrix, shift_matrix


def get_locations_around(center: str, radius: int) -> List[List[WorldLocation]]:
    """
    Somewhat efficiently generates a quasi-matrix around a given location in the world.
    :param center:      A location to be the center of the location matrix as a fully qualified ID.
    :param radius:      The radius of the location matrix. Is equal to the number of quadratic 'layers'
                        around the `center`
    :return:            A quasi matrix where `result[0][0]` is the center and `result[x][y]` is the location
                        `x` fields horizontally and `y` fields vertically away from the center
    """
    matrix_size = 1 + radius * 2
    # Initiate an empty quasi-matrix
    result: List[List[Union[WorldLocation, None]]] = [[None] * matrix_size for _ in range(matrix_size)]

    # Get parent location
    splits = center.split('.')
    parent_id = '.'.join(splits[:-1])
    parent: WorldLocation = get_world_location(parent_id, None)

    # Get Numerical Center of finest layer defined
    center_x, center_y = WorldLocation.hex_seed_to_num_coordinates(splits[-1])

    for x in range(radius + 1):
        for y in range(radius + 1):
            for c1 in [x, -x] if x != 0 else [x]:
                for c2 in [y, -y] if y != 0 else [y]:
                    next_x, next_y = center_x + c1, center_y + c2
                    if 0 <= next_x < WorldLocation.COORDINATE_LIMIT and 0 <= next_y < WorldLocation.COORDINATE_LIMIT:
                        # All coordinates are within acceptable bounds. Use core parent.
                        next_parent = parent
                    else:
                        # We have crossed a parent boundary
                        parent_x, parent_y = parent.get_finest_coordinates()
                        next_parent = parent.generate_sibling_location(
                            (parent_x + (1 if next_x >= WorldLocation.COORDINATE_LIMIT else -1 if next_x < 0 else 0),
                             parent_y + (1 if next_y >= WorldLocation.COORDINATE_LIMIT else -1 if next_y < 0 else 0)))
                        # Ensure nex_x and next_y are within bounds
                        next_x = next_x % WorldLocation.COORDINATE_LIMIT
                        next_y = next_y % WorldLocation.COORDINATE_LIMIT

                    # print(f"{c2=}, {c2=}")
                    result[c1][c2] = next_parent.generate_sub_location((next_x, next_y))

    return result


@html_generator('html.divination_table.map')
def generate_current_divination_map_html(game_id: str, user: User, **kwargs) -> str:
    """
    Generates HTML for the currently relevant divination map
    based on the given user's `current_focus` and `divination_radius` attribute.
    :param user:    A user.
    :return:        The relevant divination map to be displayed for the user.
    """
    return render_object('render, map', data=generate_current_divination_map(user))


@global_jinja_fun
def generate_current_divination_map(user: User, **kwargs) -> List[List[WorldLocation]]:
    """
    Helper function. Generate a given user's current divination map.
    :param user:    a user. Assumes user has access to the divination table.
    :return:        A user's current divination map as a quasi-matrix
    """
    divination_radius = user.get('attr.divination_table.divination_radius', default=5, **kwargs)
    matrix = get_locations_around(center=user.get('data.divination_table.current_focus', **kwargs),
                                  radius=divination_radius)
    # Shift matrix so that [0][0] is in the center instead of at the technical beginning
    matrix = shift_matrix(matrix, divination_radius, divination_radius)
    return matrix


@global_jinja_fun
def reformat_divination_map_for_display(divination_map: List[List[WorldLocation]]) -> List[List[WorldLocation]]:
    """
    Utility/helper for displaying a location map in game. Location maps in Gnomebrew are centered on (0,0), which
    does not translate well to an HTML table. This function takes such a location map and performs two actions to make
    it easier to display in an HTML table:

    * Shift (0,0) to actual index center of the map
    * Transpose matrix (so that rows are indexed first and columns second)

    :param divination_map:     A valid map to reformat.
    :return:        The transposed and shifted matrix
    """
    # Ensure this matrix is quadratic and of uneven side length
    length = len(divination_map)
    assert length == len(divination_map[0]) and length & 1 == 1
    radius = int((length - 1) / 2)
    return transpose_matrix(shift_matrix(divination_map, radius, radius))


@id_update_listener(r'data\.divination_table\.current_focus')
def reload_map_on_focus_update(user: User, data: dict, game_id: str, **kwargs):
    user.frontend_update('ui', {
        'type': 'reload_element',
        'element': 'gb-divination-map'
    })


@application_test(name='Location Scan', category='Mechanics')
def location_scan_test(center: str, radius: str):
    """
    Lists all locations that are `radius` away from `center`.
    Primitive check that does not require UI.
    """
    response = GameResponse()
    radius = int(radius)

    matrix = get_locations_around(center, radius)

    for y in range(-radius, radius + 1):
        string = ''
        for x in range(-radius, radius + 1):
            string += f"|{'***' if x == 0 and y == 0 else ''} {matrix[x][y].get_full_address().split('.')[-1]} "
        response.log(string + '|')

    return response
