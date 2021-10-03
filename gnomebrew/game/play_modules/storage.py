"""
Storage Module
"""
from os.path import join

from flask import render_template

from gnomebrew.game.user import html_generator, User, frontend_id_resolver

@html_generator('html.storage.content')
def render_storage_content(game_id: str, user: User, **kwargs):
    return render_template(join('snippets', '_storage_content.html'),
                           content=user.get('data.storage.content'))


@frontend_id_resolver(r'^data\.storage\.*')
def show_storage_updates_in_general(user: User, data: dict, game_id: str, **kwargs):
    if 'command' in kwargs and kwargs['command'] == '$set':
        user.frontend_update('update', data)
    else:
        user.frontend_update('ui', {
            'type': 'reload_element',
            'element': 'storage.content'
        })
