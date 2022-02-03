"""
Manages Gnomebrew's forms via `flask_wtf`
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, validators
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from gnomebrew.game.user import load_user


class LoginForm(FlaskForm):
    """
    Login Form
    """
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Register')

    def validate_username(self, username):
        """
        Automatically called because following 'validate_x' nomenclature of WTForms
        :param username:    username field
        :raise:             `ValidationError` if username already exists in database
        """
        user = load_user(username.data)
        if user is not None:
            raise ValidationError('Username already taken. Please choose a different one.')


class PasswordResetForm(FlaskForm):
    old_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired()])
    new_password2 = PasswordField('Repeat New Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Change Password Now')


class FeedbackForm(FlaskForm):
    about = StringField('What is this feedback about?', validators=[validators.required()])
    feedback = TextAreaField('Your Feedback', validators=[validators.required()])
    submit = SubmitField('Send Feedback')
