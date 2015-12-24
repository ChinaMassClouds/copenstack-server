horizon.addInitFunction(function () {
	/** for control_center **/
	var filed_obj = '.workflow #add_control_center__set_control_center_info';
	var source_domain_obj = filed_obj + ' #id_domain_name';
	var takeOverOptions = function(){
		var all_hosts_str = $(source_domain_obj).closest('td').find('#id_all_hosts').val();
		if(all_hosts_str){
			var all_hosts_dic = $.parseJSON(all_hosts_str);
			var domain = $(source_domain_obj).val();
			var ops = all_hosts_dic[domain];
			$(source_domain_obj).closest('td').find('#id_hostname option').remove();
			if(ops){
				for(var i = 0;i < ops.length;i ++ ){
					var html = '<option value="'+ops[i]+'">'+ops[i]+'</option>';
					$(source_domain_obj).closest('td').find('#id_hostname').append($(html));
				}
			}
		}
	};
	$(document).on('change', source_domain_obj,takeOverOptions);
	$(document).on('focus', filed_obj + ' #id_name',takeOverOptions);
});