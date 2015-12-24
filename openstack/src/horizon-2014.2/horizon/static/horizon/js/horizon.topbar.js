horizon.addInitFunction(function() {
	$('.topbar .context-box > div').on('click',function(){
		$('.topbar .context-box > div').removeClass('active');
		$(this).addClass('active');
	});
});
