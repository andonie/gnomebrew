import datetime

from gnomebrew_server import app
from flask_login import login_required, current_user
from gnomebrew_server import forms, mongo
from flask import flash, render_template, jsonify
from gnomebrew_server.game import user
import gnomebrew_server.game.event as event
from gnomebrew_server.core_modules.market import market_update

@app.route('/test/form', methods=['GET', 'POST'])
def form_test():
    form = forms.LoginForm()
    if form.validate_on_submit():
        flash(f'Login received for {form.username.data}, password was {form.password.data}')
        return render_template('index.html')
    else:
        return render_template('formtest_1.html', form=form)


@app.route('/test/db')
def db_test():
    res = mongo.db.users.find_one({"username": 'mike'})
    print(res)
    return f"I found {res['tavern_name']}"



@app.route('/test/json', methods=['GET', 'POST'])
@login_required
def send_json():
    test = {
        'fuck': 'me',
        'hello': ['world']
    }
    return jsonify(test)


@app.route('/test/s/<path:subpath>')
def test_paththing(subpath):
    return subpath


@app.route('/test/button')
def js_test_1():
    return render_template('interactiontest_1.html')


@app.route('/test/inventory/<uname>')
def show_inventory(uname):
    return f'inventory is {user.load_user(uname).get_inventory()}'


@app.route('/test/inventory')
@login_required
def your_inventory():
    return f'your inventory is\n{current_user.get_inventory()}'



@app.route('/test/eval/<id>')
@login_required
def evaluate(id: str):
    return str(current_user.get(id))


@app.route('/test/cheat')
@login_required
def cheat():
    current_user.update('data.storage.content', {'gold': 4000})
    return 'cheated!'


@app.route('/test/event')
@login_required
def test_event():
    e = event.Event.generate_event_from_recipe_data(current_user.get_id(), {'gold': 5000},
                                                    due_time=datetime.datetime.utcnow() + datetime.timedelta(seconds=12),
                                                    slots=1)
    e.enqueue()
    return 'enqueued (I think)'


@app.route('/test/recipe/<rid>')
@login_required
def test_recipe(rid):
    return current_user.get(rid).check_and_execute(current_user).to_json()


@app.route('/test/market_update')
@login_required
def update_inventory():
    print(str(market_update))
    market_update(current_user, {})
    return 'hope that worked..'
