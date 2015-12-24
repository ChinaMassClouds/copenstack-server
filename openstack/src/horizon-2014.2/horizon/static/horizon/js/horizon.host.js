horizon.addInitFunction(function () {
	$('form[action="/dashboard/admin/host/"]').find('td.status_up').each(function(index,obj){
		var val = $(obj).html();
		var styleDic = {'green'	:['#0f0','#050',gettext('The entity is OK.')],
						'yellow':['#ff0','#550',gettext('The entity might have a problem.')],
						'red'	:['#f00','#500',gettext('The entity definitely has a problem.')],
						'gray'	:['#ddd','#555',gettext('The status is unknown.')]};
		var radial_gradient_val = '5px 5px, circle, '+styleDic[val][0]+', '+styleDic[val][1];
		var html = '<div title="'+styleDic[val][2]+'" '
					+ 'style="width:16px;height:16px;border-radius:8px;' 
					+ 'background:-webkit-radial-gradient('+radial_gradient_val+');' 	/** for chrome 	*/
					+ 'background:-moz-radial-gradient('+radial_gradient_val+');' 		/** for firefox */
					+ 'background:-ms-radial-gradient('+radial_gradient_val+');' 		/** for ie 		*/
					+ 'background:radial-gradient('+radial_gradient_val+');'
					+ '"></div>';
		$(obj).html(html);
	});
});