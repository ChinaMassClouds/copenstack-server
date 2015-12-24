horizon.addInitFunction(function () {
	var fieldsetId1 = 'add_alarm_policy__policy_base_info';
	var fieldsetId2 = 'add_alarm_policy__target';
	var fieldsetId3 = 'add_alarm_policy__policy_point';
	var getSourceType = function(){
		return $('#'+fieldsetId1+' #id_source_type').val();
	};
	var changeTargets = function(event){
		event.preventDefault();
		if(!$('a[data-target="#'+fieldsetId2+'"]').closest('li').is('.active')){
			return;
		}
		var zone = $('#'+fieldsetId1+' #id_zone').val();
		var source_type = getSourceType();
		var allHostsAndVms = $('#'+fieldsetId1+' #id_allHostsAndVms').val();
		allHostsAndVms = JSON.parse(allHostsAndVms);
		$('.button-previous').attr('disabled',true);
		for(var i = 0; i < allHostsAndVms.length; i ++ ){
			var obj = allHostsAndVms[i];
			if(obj['zone'] != zone || obj['type'] != source_type){
				$('#' + fieldsetId2 + ' li[data-target-id="id_target_'+obj['id']+'"]').closest('ul').remove();
			}
		}
	};
	var changeThreshold = function(event){
		event.preventDefault();
		if(!$('a[data-target="#'+fieldsetId3+'"]').closest('li').is('.active')){
			return;
		}
		var source_type = getSourceType();
		if(source_type == 'vm'){
			$('#'+fieldsetId3+' #id_disk_point').closest('div.form-group').remove();
		}
	};
	$(document).on('click', '.button-next',function(event){
		changeTargets(event);
		changeThreshold(event);
	});
	$(document).on('click', 'a[data-target="#'+fieldsetId2+'"]',function(event){
		changeTargets(event);
		changeThreshold(event);
	});
});