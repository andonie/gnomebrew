"""
Storage Module
"""

from flask import render_template

from gnomebrew_server.game.user import html_generator, User

@html_generator('html.storage.content')
def render_storage_content(user: User):
    return render_template('snippets/_storage_content.html',
                           content=user.get('data.storage.content'))
