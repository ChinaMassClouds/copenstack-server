horizon.monitor_overview = {
	draw: function(param){
		var url = param && param['url'];
		var div_class_name = param && param['div_class_name'];
		var x_offset = param && param['x_offset'];
		var y_offset = param && param['y_offset'];
		var y_label_postfix = param && param['y_label_postfix'];
		$.ajax({
			url: url,
			datatype:'json',
			success: function(res){
				var x_labels = res && res['x_labels'];
				var y_series = res && res['y_series'];
				if(!x_labels || !y_series) return;
				if(!x_labels.length || x_labels.length == 0){
					$('.' + div_class_name).parent().hide();
				}else{
					$('.' + div_class_name).parent().show();
					new Chartist.Bar('.' + div_class_name, {
						labels: x_labels,
						series: [y_series]
					}, {
						axisX: {
					    	offset: x_offset || 20
					  	},
					  	axisY: {
					  		offset: y_offset || 30,
					  		labelInterpolationFnc: function(value) {
					  			return value + (y_label_postfix || '%')
					  		},
					  		scaleMinSpace: 15
					  	}
					});
				}
			},
			error: function(){
				horizon.clearErrorMessages();
				horizon.alert('error', gettext('Error to get monitor info.'));
			}
		});
	},
	cpu_monitor: function(target_type){
		param = {};
		param['div_class_name'] = target_type + '_cpu_monitor';
		param['url'] = '/dashboard/admin/monitoroverview/cpu_monitor/' + target_type;
		horizon.monitor_overview.draw(param);
	},
	mem_monitor: function(target_type){
		param = {};
		param['div_class_name'] = target_type + '_mem_monitor';
		param['url'] = '/dashboard/admin/monitoroverview/mem_monitor/' + target_type;
		horizon.monitor_overview.draw(param);
	},
	disk_monitor: function(target_type){
		param = {};
		param['div_class_name'] = target_type + '_disk_monitor';
		param['url'] = '/dashboard/admin/monitoroverview/disk_monitor/' + target_type;
		horizon.monitor_overview.draw(param);
	},
	net_monitor: function(target_type){
		param = {};
		param['div_class_name'] = target_type + '_net_monitor';
		param['url'] = '/dashboard/admin/monitoroverview/net_monitor/' + target_type;
		param['y_label_postfix'] = 'kB';
		horizon.monitor_overview.draw(param);
	},
	loaddata: function(target_type){
		if(!($('#ceilometer_overview a').is(':visible'))) return;
		horizon.monitor_overview.cpu_monitor(target_type);
		horizon.monitor_overview.mem_monitor(target_type);
		horizon.monitor_overview.disk_monitor(target_type);
		horizon.monitor_overview.net_monitor(target_type);
		setTimeout(function(){
			horizon.monitor_overview.loaddata(target_type);
		}, 120000);
		$('#ceilometer_overview a').on('click',function(){
			if($(this).attr('data-target') == '#ceilometer_overview__host'){
				horizon.monitor_overview.loaddata('host');
			}else{
				horizon.monitor_overview.loaddata('vm');
			}
		});
	}
};