// List of all IDs that are represented in cents rather than in usual values:
cent_list = ['data.storage.content.gold'];
cent_regexes = [/data[.]market[.]inventory[.][\w]+[.]price/i]

function is_cent_id(id) {
    if(cent_list.includes(id)) {
        return true;
    }
    for(var regex of cent_regexes) {
        if(regex.test(id)) {
            return true;
        }
    }
    return false;
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
        return Math.floor(val/60) + ' m, ' + shorten_time(val % 60);
    } else if(val <= 60*60*24) { //hours
        return Math.floor(val/(60*60)) + ' h, ' + shorten_time(val % (60*60));
    } else {
        return Math.floor(val/(60*60*24)) + ' days, ' + shorten_time(val % (60*60*24));
    }
}

/* LOADING BAR */

// Called when a UI update requires a slot being occupied
function occupy_slot(response) {
    var slot_num = 1;
    while(true) {
        var slot = document.getElementById(response.station + '-slot-' + slot_num);
        if(slot==null) {
            error_msg('station.' + response.station + '-warning', 'I did not manage to find a free slot. This should not have happened');
            break;
        }
        //Check if slot is free
        if(slot.dataset.state === 'free') {
            //Slot is free, we can fill it.
            slot.dataset.due = response.due;
            slot.dataset.since = response.since;
            slot.dataset.state = 'occupied';
            animate_slot(slot);
            break;
        }
        slot_num++;
    }
}

// Called when a UI update requires a duetime being updated
function animate_due_time(response) {
    console.log('Animating duetime: ' + response)
    var target = document.getElementById(response.target);
    target.dataset.due = response.due;
    animate_countdown(target);
}

// Animates a slot, assuming data values have been set correctly. Input is local system time
function animate_slot(slot) {
    var due_time_server = Date.parse(slot.dataset.due);
    var since_time_server = Date.parse(slot.dataset.since);
    var progress_bar = slot.children[0]; // We know the location
    var progress_desc = slot.children[1];
    var animation = setInterval(function() {
        var now = Date.now() - time_difference;
        if(now > due_time_server) {
            // We are finished! Stop animation.
            progress_bar.style.width = '0%';
            progress_desc.innerHTML = '...';
            slot.dataset.state = 'free';
            clearInterval(animation);
            return;
        }
        // Set % width based on time passed
        progress_bar.style.width = (((now-since_time_server)/(due_time_server-since_time_server))*100) + '%';
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

/* ERROR LOGGING */

function global_error(error_msg) {
    console.error(error_msg);
}

function error_msg(target_id, message) {
    if(target_id === null) {
        global_error(message);
        return;
    }
    var target = document.getElementById(target_id);
    if(target.style.opacity > 0) {
        // A fadeout is already running. Only append and leave be.
        target.innerHTML += "<br>" + message;
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
        }
    }, 100);
}