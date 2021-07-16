//Minimal File to ensure stations can integrate their own JS code to be executed later.

_has_booted = false;
_BOOT_LIST = []

function add_startup(startup_fun) {
    if(!_has_booted) {
        _BOOT_LIST.push(startup_fun);
    } else {
        startup_fun();
    }
}

function fire_boot_list() {
    _BOOT_LIST.forEach(function (item, index) {
        item();
    })
    _has_booted = true;
}