function attempt_reset() {
    $.post('/play/request', {
        request_type: 'reset_game_data',
        confirmation: $('#reset-confirmation').val()
    }).done(function(response) {

    });
}