/* BOOTING */

function animate_whole_ui(element) {
    $(element).find('.countdown').each(function(index){
        animate_countdown(this);
    });
    $(element).find('.slot-ext').each(function(index){
        if(this.dataset.state === 'occupied') {
            animate_slot(this);
        }
    });
}

function startup_script() {
    update_time_difference(function(){
        //Callback executed after time difference is set.
        animate_whole_ui(document);
    });
    // Register socket handlers
    socket.on('update', handle_update);
    socket.on('ui', handle_ui_req);

    fire_boot_list();
}

$(document).ready(startup_script);


/* SERVER INTERACTION / CALLBACKS */

var time_difference = null;
socket = io();

// Invoked when game data is updated
function handle_update(data) {
    //console.log('update: ' + JSON.stringify(data));
    for(var id in data) {
        // Pre-Check if ID matches a station that must be reloaded
        // This would be the case for mechanism that come after a heavier data change


        if(typeof data[id] === 'object' && data[id] !== null) {
            // The update is for a complex object.
            // Create new object with extended keys and recursively repeat.
            new_data = {};
            for(var key in data[id]) {
                new_data[id + '.' + key] = data[id][key];
                handle_update(new_data);
            }
        } else {
            // This is a value to be updated in the UI.
            try {
                value = data[id];
                if(typeof value === "number") {
                    value = shorten_num(value);
                }
                document.getElementById(id).innerHTML = value;
            } catch(error) {

                // If any error happens, reload the entire DIV.
                // Errors should NOT happen.

                console.error('Unable to handle: ' + JSON.stringify(data))

                var station_name = id.split('.')[1];
                reload_station(station_name);
                break; // After the reload, updating any additional data is unnecessary
            }
        }
    }
}

// Invoked when a UI element is supposed to be updated.
function handle_ui_req(data) {
    switch(data.type) {
        case 'slot':
            occupy_slot(data);
            break;
        case 'duetime':
            animate_due_time(data);
            break;
        case 'reload_station':
            reload_station(data.station);
            break;
        case 'reload_element':
            reload_element(data.element);
            break;
    }
}

function update_time_difference(success_callback) {
    var t_c1 = Date.now();
    $.post('/play/request', {type: 'time_sync'}).done(function(response) {
        var t_c2 = Date.now();
        time_difference = t_c1 - (Date.parse(response.now) - ((t_c2-t_c1)/2));
        console.log('set time difference to: ' + time_difference);
        success_callback();
    }).fail(function(response){
        global_error('Could not synchronize time with server.')
    });
}

function reload_station(station_name) {
    $.post('/play/game_id/html.' + station_name).done(function(response) {
        station_element = document.getElementById('station.' + station_name);
        //Parse Response to DOM and retrieve innerHTML
        var outer = document.createElement('div');
        outer.innerHTML = response;
        station_element.innerHTML = outer.children[0].innerHTML;
        animate_whole_ui(station_element);
    }).fail(function(response){
        global_error('Error while connecting to server!');
    });
}

function reload_element(element_name) {
    $.post('/play/game_id/html.' + element_name).done(function(response) {
        element_to_reload = document.getElementById(element_name);
        element_to_reload.innerHTML = response;
        animate_whole_ui(station_element);
    }).fail(function(response){
        global_error('Error while connecting to server!');
    });
}

/* GAMEPLAY */

// Wrapper for all Game Requests that do not require a direct reaction to the response, which covers all UI
function one_way_game_request(request_data, error_target, trigger_element) {
    trigger_element.disabled = true;
    var html_before = trigger_element.innerHTML;
    if(html_before.length < 3) {
        trigger_element.innerHTML = '.';
    } else {
        trigger_element.innerHTML = '...';
    }

    var reset_element = function(){
        trigger_element.disabled = false;
        trigger_element.innerHTML = html_before;
    };

    $.post('/play/request', request_data).done(function(response){
        if(response.type != 'success') {
            error_msg(error_target, response.fail_msg);
        }
        reset_element();
    }).fail(function() {
        error_msg(error_target, 'Could not connect to Gnomebrew Server!');
        reset_element();
    });
}

// Execute Recipe by ID and update the UI
function execute_recipe(recipe_id, error_target, trigger_element) {
    one_way_game_request({
        type: 'recipe',
        recipe_id: recipe_id
    }, error_target, trigger_element);
}

// Buy From Market
function market_buy(item_id, error_target, trigger_element, buy_all) {
    var amount = 1;
    if(buy_all) {
        // Buy all section is chosen -> change amount to all that's left.
        var stock_indicator = document.getElementById('data.market.inventory.' + item_id.substring(5) + '.stock')
        amount = parseInt(stock_indicator.innerHTML, 10)
        if (amount == 0) {
            error_msg(error_target, 'Inventory is empty.');
            return;
        }
    }
    one_way_game_request({
        type: 'market_buy',
        item_id: item_id,
        amount: amount
    }, error_target, trigger_element);
}

function serve_next(action, error_target, trigger_element) {
    one_way_game_request({
        type: 'serve_next',
        what_do: action
    }, error_target, trigger_element);
}

function set_price(item_id, error_target, trigger_element) {
    one_way_game_request({
        type: 'set_price',
        item: item_id,
        price: document.getElementById('data.tavern.prices.' + item_id).value
    }, error_target, trigger_element)
}


