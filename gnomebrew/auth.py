"""
Manages authentication and user creation (login/logout/create)
"""

from gnomebrew import app, forms
from gnomebrew.game.user import User, load_user
from flask_login import login_user, current_user, logout_user, login_required
from flask import render_template, flash, redirect, url_for, request
from werkzeug.urls import url_parse

from gnomebrew.logging import log


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = forms.LoginForm()
    if form.validate_on_submit():
        # Do Login
        _usr = load_user(form.username.data)
        if _usr is None:
            flash(f'No user with name {form.username.data} found')
            return redirect(url_for('login'))
        if not _usr.check_pw(form.password.data):
            flash('Username and password did not match.')
            return redirect(url_for('login'))

        # Login correct.
        login_user(_usr, remember=form.remember_me.data)
        flash(f'Welcome back, {_usr.get_name()}')
        log('gb_system', _usr.get_id(), 'login')

        # Next redirect
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)

    else:
        # Show Login Page
        return render_template('single_form.html', form=form, title="Login")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = forms.RegistrationForm()
    if form.validate_on_submit():
        # Valid Form Submitted
        assert form.password.data == form.password2.data
        user = User.create_user(form.username.data, form.password.data)
        login_user(user, remember=form.remember_me.data)
        flash("Welcome to Gnomebrew! You're successfully registered.")
        return redirect(url_for('index'))
    else:
        # Show Register Page
        return render_template('single_form.html', form=form, title="Register")


@app.route('/logout')
def logout():
    username = current_user.get_id()
    logout_user()
    log('gb_system', username, 'logout')
    flash(f"See you later, {username}! Your game continues while you're away.")
    return redirect(url_for('index'))
