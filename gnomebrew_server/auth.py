"""
Manages authentication and user creation (login/logout/create)
"""

from gnomebrew_server import app, forms
from gnomebrew_server.game import user
from flask_login import login_user, current_user, logout_user, login_required
from flask import render_template, flash, redirect, url_for, request
from werkzeug.urls import url_parse


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = forms.LoginForm()
    if form.validate_on_submit():
        # Do Login
        _usr = user.load_user(form.username.data)
        if _usr is None:
            flash(f'No user with name {form.username.data} found')
            return redirect(url_for('login'))
        if not _usr.check_pw(form.password.data):
            flash('Username and password did not match.')
            return redirect(url_for('login'))

        # Login correct.
        login_user(_usr, remember=form.remember_me.data)
        flash(f'Welcome back, {_usr.get_name()}')

        # Next redirect
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)

    else:
        # Show Login Page
        return render_template('login.html', form=form)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = forms.RegistrationForm()
    if form.validate_on_submit():
        # Valid Form Submitted
        flash("You're successfully registered.")
        pass
    else:
        # Show Register Page
        return render_template('register.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/settings')
@login_required
def settings():
    return 'settings.'
