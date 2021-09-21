"""
Storage Module
"""

from flask import render_template

from gnomebrew.game.user import html_generator, User, frontend_id_resolver

@html_generator('html.storage.content')
def render_storage_content(user: User):
    return render_template('snippets/_storage_content.html',
                           content=user.get('data.storage.content'))


@frontend_id_resolver(r'^data\.storage\.*')
def show_storage_updates_in_general(user: User, data: dict, game_id: str):
    user.frontend_update('update', data)
