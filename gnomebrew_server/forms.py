"""tf
This
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from gnomebrew_server.game.user import load_user


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
