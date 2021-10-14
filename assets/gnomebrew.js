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
    $(element).find('.gb-filter').on("keyup", function() {
        var value = $(this).val().toLowerCase();
        var to_filter = $(this).data('filters');
        $(to_filter).filter(function() {
            return ! $(this).data('filter-match').toLowerCase().includes(value);
        }).hide();
        $(to_filter).filter(function() {
            return $(this).data('filter-match').toLowerCase().includes(value);
        }).show();
    });
    $(element).find('#storage-close-button').on('click', function(event) {
        $('.gb-sidebar').addClass('sb-toggle');
    });
    $(element).find('.gb-toggle-view').on('click', function(event) {
        var target = $($(this).data('toggles'));
        target.toggleClass('gb-toggle-hidden');
        var display_target = $($(this).data('display'));
        var is_hidden = $($(this).data('toggles')).hasClass('gb-toggle-hidden');

        // UPDATE CSS CLASSES

        var attr = $(this).attr('data-inform');
        // For some browsers, `attr` is undefined; for others,
        // `attr` is false.  Check for both.
        if (typeof attr !== 'undefined' && attr !== false) {
            console.log($(this).data('toggles'));
            var classname = 'toggle-'+ $(this).data('toggles').substring(1)
            console.log(classname);
            var info_target = $($(this).data('inform'));
            console.log(info_target);
            if(is_hidden) {
                info_target.removeClass(classname);
            } else {
                info_target.addClass(classname);
            }
        }

        if (is_hidden) {
            display_target.removeClass('gb-toggle-view-active');
        } else {
            display_target.addClass('gb-toggle-view-active');
        }
        rescale_ui();

        // IF REQUESTED ATTEMPT TO SYNC DATA:


         var sync_id = $(this).attr('data-sync');
        if (typeof sync_id !== 'undefined' && sync_id !== false) {
            // We have data to sync requested.
            // By default, the engine stores `True` for visible/open, not for hidden, so invert the bit.
            // Attempt to send selection to server.
            sync_selection(sync_id, !is_hidden);
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
    // After everything is set up, re-update the masonry grid to make sure everything looks nice
    rescale_ui();
}

$(document).ready(startup_script);


/* SERVER INTERACTION / CALLBACKS */

var time_difference = null;
socket = io();

// Invoked when game data is updated
function handle_update(data) {
    console.log(data);
    switch(data.update_type) {
        case 'inc': // Increment update
            for (var key in data.updated_elements) {
                var data_selector = '.' + key;
                var val_old = $(data_selector).data('value');
                update_value_at(data_selector, val_old + data.updated_elements[key]['data'], data.updated_elements[key]['display_fun']);
            }
            break;
        case 'set': // Hard-Set update
            for (var key in data.updated_elements) {
                var data_selector = '.' + key;
                var val_old = $(data_selector).data('value');
                update_value_at(data_selector, data.updated_elements[key]['data'], data.updated_elements[key]['display_fun']);
            }
            break;
        case 'change_attributes': //Change attributes
            data.attribute_change_data.forEach( job => {
                console.log(job['selector']);
                $(job['selector']).attr(job['attr'], job['value'])
            });
            break;
    }
    rescale_ui();
}

function update_value_at(data_selector, new_val, display_fun_name) {
    $(data_selector).data('value', new_val);
    // Decide how shorten numbers of this type
    target_fun = styling_functions[display_fun_name];
    $(data_selector).html(target_fun(new_val));
}

// Invoked when a UI element is supposed to be updated.
function handle_ui_req(data) {
    console.log(data);
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
        case 'remove_element':
            $(data.selector).remove();
            break;
        case 'append_element':
            $(data.selector).append(data.element);
            break;
        case 'prompt':
            display_prompt(data.prompt_html);
            break;
        case 'add_station':
            add_station(data.station);
            break;
        case 'player_info':
            display_info(data.target, data.content, data.duration);
            break;
        case 'update_class':
            console.log("YEAH");
            console.log(data);
            if (data.action === 'add_class' ) {
                $(data.target).addClass(data.class_data);
            }
            if (data.action === 'remove_class' ) {
                $(data.target).removeClass(data.class_data);
            }
            break;
    }
    // After any UI update, Masonry gets card blanche to update the grid
    rescale_ui();
}

function update_time_difference(success_callback) {
    var t_c1 = Date.now();
    $.post('/play/request', {request_type: 'time_sync'}).done(function(response) {
        var t_c2 = Date.now();
        time_difference = t_c1 - (Date.parse(response.now) - ((t_c2-t_c1)/2));
        console.log('set time difference to: ' + time_difference);
        success_callback();
    }).fail(function(response){
        global_error('Could not synchronize time with server.')
    });
}

function reload_station(station_name) {
    $.post('/play/game_id/html.station.' + station_name).done(function(response) {
        station_element = document.getElementById('station.' + station_name);
        //Parse Response to DOM and retrieve innerHTML
        var outer = document.createElement('div');
        outer.innerHTML = response;
        station_element.innerHTML = outer.children[0].innerHTML;
        animate_whole_ui(station_element);
        rescale_ui();
    }).fail(function(response){
        global_error('Error while connecting to server!');
    });
}

function reload_element(element_name) {
    $.post('/play/game_id/html.' + element_name).done(function(response) {
        element_to_reload = document.getElementById(element_name);
        element_to_reload.innerHTML = response;
        animate_whole_ui(element_to_reload);
        rescale_ui();
    }).fail(function(response){
        global_error('Error while connecting to server!');
    });
}

function add_station(station_name) {
    console.log('adding station: ' + station_name);
    $.post('/play/game_id/html.' + station_name).done(function(response) {
        element = $(response);
        animate_whole_ui(element);
        $('.gb-grid').append(element);
    }).fail(function(response){
        global_error('Error while connecting to server!');
    });
}

/* INGAME EVENT */

function display_prompt(prompt_html) {
    document.getElementById('gb_prompt_container').innerHTML = prompt_html
    show_event_modal();
}

function show_event_modal() {
    $('#gb-event-modal').modal({
        backdrop: 'static',
        keyboard: false
    });
}

// Complete frontend shutdown logic for an ingame event modal
function close_event_modal() {
    var button = document.getElementById('gb-event-modal-button');
    var button_text = button.innerHTML;

    var request_object = {
        request_type: 'prompt',
        target_id: $('#gb-event-modal').data('target'),
        input: {}
    };

    console.log(request_object);

    // If applicable, collect any and all inputs set by user
    $('#gb-event-modal input').each(function(index){
        console.log('HI');
        var id = $(this).data('input-id');
        var val = $(this).val();
        request_object.input[id] = val;
    });

    console.log(request_object);

    console.log('I have this request at the Ready: ' + JSON.stringify(request_object));

    $.post('/play/request', request_object).done(function(response) {
        console.log('PROMPT RESPONSE RECEIVED:');
        console.log(response);
        if(response.type != 'success') {
            error_msg('gb-event-modal-warning', response.fail_msg);
            button.innerHTML = button_text;
            return;
        }
        // Success!
        // We take the up-to-date notification info from the server and apply it to the message buttons.
        for (var prompt_selector in response['prompt_states']) {
            console.log(response['prompt_states'][prompt_selector]);
            console.log($(prompt_selector));
            if(response['prompt_states'][prompt_selector]) {
                console.log($(prompt_selector));
                $(prompt_selector).removeClass('gb-navbar-hidden')
            } else {
                console.log($(prompt_selector));
                $(prompt_selector).addClass('gb-navbar-hidden')
            }
        }
        // We now want to close the modal now
        button.innerHTML = button_text;
        $('#gb-event-modal').modal('hide');
    }).fail(function(response) {
        error_msg('gb-event-modal-warning', 'Failed trying to connect to Gnomebrew server.');
        button.innerHTML = button_text;
    });
}

/* GAMEPLAY */

// Wrapper for all Game Requests that do not require a direct reaction to the response
function one_way_game_request(request_data, error_target, trigger_element) {
    var reset_element = null;
    if(trigger_element) {
        trigger_element.disabled = true;
        $(trigger_element).addClass('gb-pending');

        reset_element = function(){
            trigger_element.disabled = false;
            $(trigger_element).removeClass('gb-pending');
        };
    }

    $.post('/play/request', request_data).done(function(response){
        if(reset_element) {
            reset_element();
        }
    }).fail(function() {
        error_msg(error_target, 'Could not connect to Gnomebrew Server!');
        if(reset_element) {
            reset_element();
        }
    });
}

// Wrapper for all Game requests that do print output
function two_way_game_request(request_data, trigger_element, output_id, success_logic) {
    trigger_element.disabled = true;
    $(trigger_element).addClass('gb-pending');

    var reset_element = function(){
        trigger_element.disabled = false;
        $(trigger_element).removeClass('gb-pending');
    };

    $.post('/play/request', request_data).done(function(response){
        success_logic(response);
        reset_element();
    }).fail(function(e) {
        console.log(e);
        reset_element();
    });
}

// Request a prompt ID to be shown
function request_prompt(prompt_type, trigger_element) {
    console.log({
        request_type: 'give_prompt',
        prompt_type: prompt_type
    });
    one_way_game_request({
        request_type: 'give_prompt',
        prompt_type: prompt_type
    }, null, trigger_element);
}

// Execute Recipe by ID and update the UI
function execute_recipe(recipe_id, error_target, trigger_element) {
    one_way_game_request({
        request_type: 'recipe',
        action: 'execute',
        recipe_id: recipe_id
    }, error_target, trigger_element);
}

function cancel_recipe(event_id, error_target, trigger_element) {
    one_way_game_request({
        request_type: 'recipe',
        action: 'cancel',
        event_id: event_id
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
        request_type: 'market_buy',
        item_id: item_id,
        amount: amount
    }, error_target, trigger_element);
}

function serve_next(action, error_target, trigger_element) {
    one_way_game_request({
        request_type: 'serve_next',
        what_do: action
    }, error_target, trigger_element);
}

function set_price(item_id, error_target, trigger_element) {
    one_way_game_request({
        request_type: 'set_price',
        item: item_id,
        price: Math.round(parseFloat(document.getElementById('data.tavern.prices.' + item_id).value).toFixed(2)*100)
    }, error_target, trigger_element)
}

function sync_selection(game_id, value) {
    one_way_game_request({
        request_type: 'select',
        target_id:  game_id,
        value: value,
    }, null, null);
}
