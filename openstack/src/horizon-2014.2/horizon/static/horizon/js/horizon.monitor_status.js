horizon.addInitFunction(function () {
	var MonitorStatus = {
		timer : null,
		defSetting : {
			'auto_resize': false,
			'auto_size': false
		},
		getSettings: function(is_init,flag){
			var settings = $.extend({},MonitorStatus.defSetting);
			settings['loading_effect'] = !! is_init;
//			settings['axes_x'] = false;
			if(flag == 'cpu'){
				settings['yMin'] = 0;
				settings['yMax'] = 100;
			}
			return settings;
		},
		showChartAndTitle: function(){
			$('.chart_container .chart_title').show();
			$('.chart_container div[data-chart-type="line_chart"]').show();
			$('div.disk_monitor').show();
		},
		hideChartAndTitle: function(){
			$('.chart_container .chart_title').hide();
			$('.chart_container div[data-chart-type="line_chart"]').hide();
			$('div.disk_monitor').hide();
		},
		domain_hosts_url : function(param){
			var func_name = param['source'] == 'host' ? 'domain_hosts':'domain_vms';
			return '/dashboard/admin/controlcenter/'
					+ param['domain_id'] + '/'
					+ func_name + '/';
		},
		clearTarget: function(){
			$('#ceilometer-stats #select_target option').remove();
		},
		addTarget: function(option_html){
			$('#ceilometer-stats #select_target').append($(option_html));
		},
		showErrorMsg:function(msg){
			horizon.clearErrorMessages();
            horizon.alert('error', gettext(msg));
		},
		startTimer: function(){
			if(!MonitorStatus.timer){
				MonitorStatus.timer = setInterval(MonitorStatus.refreshChart,60000);
			}
		},
		stopTimer: function(){
			if(MonitorStatus.timer){
				clearInterval(MonitorStatus.timer);
				MonitorStatus.timer = null;
			}
			$("div[data-chart-type='line_chart']").html('');
			$("div[data-chart-type='line_chart']").parent().find('#legend').html('');
			MonitorStatus.hideChartAndTitle();
		},
		getDomainAndSource:function(){
			var domain_id = $('#ceilometer-stats #select_domain').val();
			var source = $('#ceilometer-stats #select_source').val();
			if(domain_id && source){
				return {'domain_id':domain_id,'source':source};
			}else{
				MonitorStatus.stopTimer();
				return null;
			}
		},
		getWholeParam:function(){
			var das = MonitorStatus.getDomainAndSource();
			if(!das) return null;
			var target = $('#ceilometer-stats #select_target').val();
			if(!target) return null;
			das['target'] = target;
			return das;
		},
		reloadTarget : function(){
			MonitorStatus.clearTarget();
			MonitorStatus.stopTimer();
			horizon.clearErrorMessages();
			var param = MonitorStatus.getDomainAndSource();
			if(!param) return;
			$.ajax({
				url: MonitorStatus.domain_hosts_url(param),
				datatype:'json',
				success:function(res){
					var res_json = JSON.parse(res);
					for(var i = 0; i < res_json.length; i ++ ){
						var option_html = '';
						if(res_json[i] && typeof(res_json[i]) == 'object' && res_json[i]['id']){
							option_html = '<option value="'
									+ res_json[i]['id'] + '">'
									+ res_json[i]['name'] + '</option>';
							MonitorStatus.addTarget(option_html);
						}else if(res_json[i] && typeof(res_json[i]) == 'string'){
							option_html = '<option value="'
									+ res_json[i] + '">'
									+ res_json[i] + '</option>';
							MonitorStatus.addTarget(option_html);
						}
					}
				},
				error: function(){
					MonitorStatus.showErrorMsg('Error to get host or vm list.');
				}
			});
		},

		initChart: function(){
			MonitorStatus.showChartAndTitle();
			var source = $('#ceilometer-stats #select_source').val();
			horizon.d3_line_chart.init("div.cpu_monitor",MonitorStatus.getSettings(true,'cpu'));
			horizon.d3_line_chart.init("div.mem_monitor",MonitorStatus.getSettings(true,'mem'));
			if(source == 'vm'){
				horizon.d3_line_chart.init("div.disk_monitor",MonitorStatus.getSettings(true,'disk'));
				$('.disk_monitor').parent().show();
			}else{
				$('.disk_monitor').parent().hide();
			}
			horizon.d3_line_chart.init("div.net_monitor",MonitorStatus.getSettings(true,'net'));
		},
		refreshChart: function(){
			var source = $('#ceilometer-stats #select_source').val();
		    horizon.d3_line_chart.refresh("div.cpu_monitor",MonitorStatus.getSettings(false,'cpu'));
		    horizon.d3_line_chart.refresh("div.mem_monitor",MonitorStatus.getSettings(false,'mem'));
		    if(source == 'vm'){
		    	horizon.d3_line_chart.refresh("div.disk_monitor",MonitorStatus.getSettings(false,'disk'));
		    	$('.disk_monitor').parent().show();
		    }else{
		    	$('.disk_monitor').parent().hide();
		    }
		    horizon.d3_line_chart.refresh("div.net_monitor",MonitorStatus.getSettings(false,'net'));
		}
	};
	$(document).on('change','#ceilometer-stats #select_domain',MonitorStatus.reloadTarget);
	$(document).on('change','#ceilometer-stats #select_source',MonitorStatus.reloadTarget);
	$(document).on('click','#ceilometer-stats #monitor_status_ok',function(){
		var param = MonitorStatus.getWholeParam();
		if(!param) return;
		MonitorStatus.initChart();
		MonitorStatus.startTimer();
	});
});