// Simple UI Utilities available to all Gnomebrew pages.

$('.gb-tabs').children().on('click', function(e) {
    $(this).siblings().removeClass('gb-tab-selected');
    $(this).addClass('gb-tab-selected');
    $(this).parent().parent().find('.gb-tab').hide();
    $($(this).data('target')).show();
    console.log(e);
});