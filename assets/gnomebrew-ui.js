// List of all IDs that are represented in cents rather than in usual values:

styling_functions = {
    'shorten_num': shorten_num,
    'shorten_time': shorten_time,
    'shorten_cents': shorten_cents,
    'str': display_string
}

// Cosmetic Function To Make Big and small numbers look nice.
function shorten_num(val) {
    var shortcodes = ['', 'K', 'M', 'MM'];
    var num_level = 0;
    while(val > 1000) {
        val /= 1000;
        num_level++;
    }
    if(num_level>0) {
        val = val.toFixed(2);
    }
    return val + ' ' + shortcodes[num_level];
}

// Cosmetic function to deal with values denoted in cents
function shorten_cents(val) {
    return shorten_num(val/100);
}

// Cosmetic Function To Make Times more digestible
// Assumes val is in seconds
function shorten_time(val) {
    if(val <= 60) { //seconds
        return Math.floor(val) + ' s';
    } else if(val <= 60*60) { //minutes
        return Math.floor(val/60) + ' m ' + shorten_time(val % 60);
    } else if(val <= 60*60*24) { //hours
        return Math.floor(val/(60*60)) + ' h ' + shorten_time(val % (60*60));
    } else {
        return Math.floor(val/(60*60*24)) + ' days ' + shorten_time(val % (60*60*24));
    }
}

function display_string(val) {
    return val;
}

/* GENERAL UI */


function rescale_ui(e) {

}

window.onresize = rescale_ui

/* LOADING BAR */

// Called when a UI update requires a duetime being updated
function animate_due_time(response) {
    var target = document.getElementById(response.target);
    target.dataset.due = response.due;
    animate_countdown(target);
}

// Animates a slot, assuming data values have been set correctly.
function animate_slot(slot) {
    var due_time_server = Date.parse(slot.dataset.due);
    var since_time_server = Date.parse(slot.dataset.since);
    var progress_bar = slot.children[0]; // We know the location within HTML
    var cancel_button = slot.children[1].children[0];
    var icon = slot.children[1].children[1];
    var progress_desc = slot.children[1].children[2];
    var animation = setInterval(function() {
        var now = Date.now() - time_difference;
        if(now > due_time_server) {
            // We are finished! Stop animation and clean up.
            clearInterval(animation);
            $(slot).remove();
            return;
        }
        // Set % width based on time passed
        var inset = 'inset(0 ' + ((1-(now-since_time_server)/(due_time_server-since_time_server))*100) + '% 0px 0px)';
        $(progress_bar).css('clip-path', inset);
        progress_desc.innerHTML = shorten_time(Math.ceil((due_time_server-now)/1000));
    }, 50);
}

//Animates a countdown, assuming the data-due value is set correctly.
function animate_countdown(countdown) {
    var due_time_server = Date.parse(countdown.dataset.due);
    var animation = setInterval(function(){
        var now = Date.now() - time_difference;
        var ms_left = due_time_server-now;
        if(ms_left<=0) {
            countdown.innerHTML = '0 s';
            clearInterval(animation);
            return;
        }
        countdown.innerHTML = shorten_time(ms_left/1000);
    }, 50);
}


/* ZOOM UTILITY */

function zoom_in(target_selector) {
    console.log($(target_selector).data('zoom'));
    var zoom_configs = $(target_selector).data('zoom');
    for (const key in zoom_configs) {
        $(target_selector).find(key).each(function() {
            for(var i = 0; i < zoom_configs[key].length-1; i++) {
                if($(this).hasClass(zoom_configs[key][i])) {
                    $(this).removeClass(zoom_configs[key][i]);
                    $(this).addClass(zoom_configs[key][i+1]);
                    break;
                }
            }
        });
    }
}

function zoom_out(target_selector) {
    var zoom_configs = $(target_selector).data('zoom');
    for (const key in zoom_configs) {
        $(target_selector).find(key).each(function() {
            for(var i = 1; i < zoom_configs[key].length; i++) {
                if($(this).hasClass(zoom_configs[key][i])) {
                    $(this).removeClass(zoom_configs[key][i]);
                    $(this).addClass(zoom_configs[key][i-1]);
                    break;
                }
            }
        });
    }
}


/* SELECT Utility */

// Updates a selection in game.
function select(game_id, selected) {
    two_way_game_request({
        request_type: 'select',
        target_id: game_id,
        value: $(selected).data('select-value')
    }, selected, null, function(response) {
        console.log(response);
        select_selection = !$(selected).hasClass('gb-selected');
        $($(selected).data('peers')).removeClass('gb-selected');
        if (select_selection) {
            // If something was selected already, it is unselected instead.
            $(selected).addClass('gb-selected');
        }
    });
}

function toggle_selection(game_id, toggled) {
    two_way_game_request({
        request_type: 'select',
        target_id: game_id,
        value: '_toggle'
    }, toggled, null, function(response) {
        console.log(response);
    });
}

/* TOGGLE Utility */

function toggle_at_selector(selector, toggle_class) {
    $(selector).toggleClass(toggle_class)
}


/* PLAYER INFO */

var info_cnt = 0;

function display_info(target_selector, info_html, duration) {
    var info = $(info_html);
    var info_id = 'player_info_' + info_cnt;
    info.attr('id', info_id);
    console.log(info);
    info_cnt++;
    $(target_selector).append(info);
    rescale_ui();

    var STEP = 0.1;
    var PRE_CNT = duration;
    var cnt = 0;
    var target = document.getElementById(info_id);
    target.style.opacity = 1;

    var fadeEffect = setInterval(function() {
        if(cnt < PRE_CNT) {
            cnt++;
            return;
        }
        if (target.style.opacity > 0) {
            target.style.opacity -= STEP;
        } else {
            // Animation Done. Clean Up
            $( target ).remove();
            rescale_ui();
            clearInterval(fadeEffect);
        }
    }, 100);
}


/* ERROR LOGGING */

function global_error(error_msg) {
    console.error(error_msg);
}

function error_msg(target_id, message) {
    console.log('Error: ' + target_id + ' --- ' + message);
    if(target_id === null) {
        global_error(message);
        return;
    }
    var target = document.getElementById(target_id);
    if(target.style.opacity > 0) {
        // A fadeout is already running. Only append and leave be.
        target.innerHTML += "<br>" + message;
        rescale_ui();
        return;
    }
    target.innerHTML = message;
    target.style.opacity = 1;
    var STEP = 0.1;
    var PRE_CNT = 20;
    var cnt = 0;
    var fadeEffect = setInterval(function() {
        if(cnt < PRE_CNT) {
            cnt++;
            return;
        }
        if (target.style.opacity > 0) {
            target.style.opacity -= STEP;
        } else {
            // Animation Done. Clean Up
            clearInterval(fadeEffect);
            target.innerHTML = "";
            rescale_ui();
        }
    }, 100);
    rescale_ui();
}