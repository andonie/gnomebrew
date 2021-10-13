"""
This file manages the basic '/' view and generic views
"""

from gnomebrew import app, forms
from flask import render_template, send_from_directory, redirect, url_for, flash, request
from flask_login import login_required, current_user
from os.path import isfile, join
from gnomebrew.game.user import IDBuffer
from gnomebrew.logging import log_execution_time

supported_browsers = ['firefox', 'chrome']

@app.route('/')
def index():
    browser = request.user_agent.browser
    if browser not in supported_browsers:
        flash("Currently, Gnomebrew is optimized for Firefox and Chrome and it's suggested to use either. Your browser might still work.")
    if current_user.is_authenticated:
        playscreen = log_execution_time(lambda: render_template('playscreen.html', buffer=IDBuffer()), 'html', 'playscreen rendered', f"usr:{current_user.get_id()}")
        return playscreen
    else:
        return render_template('public_page.html')


@app.route('/res/<res>')
def static_res(res):
    """
    Returns a static resource
    :param res: Resource name. Can be a path
    :return: Resource or 404
    """
    return send_from_directory(app.config['STATIC_DIR'], res)


@app.route('/ico/<game_id>')
def get_icon(game_id: str):
    """
    Returns the most fitting icon for a given game id
    :param game_id: ID of the entity to get the icon for
    """
    splits = game_id.split('.')
    target_directory = join(app.config['ICO_DIR'], splits[0])

    for possible_image_name in [f"{'.'.join(splits[1:x])}.png" for x in range(len(splits), 1, -1)]:
        if isfile(join(target_directory, possible_image_name)):
            return send_from_directory(target_directory, possible_image_name)

    # No image match found. Use best possible default.
    if isfile(join(target_directory, 'default.png')):
        return send_from_directory(target_directory, 'default.png')
    else:
        # If Icon does not exist (yet), send default img
        return send_from_directory(app.config['ICO_DIR'], 'default.png')


@app.route('/favicon.ico')
def favicon_forward():
    return redirect(url_for('static_res', res='favicon.ico'))


@app.route('/fonts/<font_name>')
def get_font(font_name: str):
    return send_from_directory(app.config['FONT_DIR'], font_name)


@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html', pw_form=forms.PasswordResetForm())


@app.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback():
    form = forms.FeedbackForm()
    if form.validate_on_submit():
        # Valid Form Submitted
        print(f"I RECEIVED {form.feedback=} {form.about=}")
        flash("Thank you for your feedback! It is recorded.")
        return redirect(url_for('index'))
    else:
        # Show Register Page
        return render_template('single_form.html', form=form, title="Feedback")
