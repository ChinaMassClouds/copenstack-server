horizon.alarmmsg_search = {
	AlarmMsg : {
		source_type_enum: {
			'host':gettext('Host'),
			'vm':gettext('VM')
		},
		status_enum : {
			'untreated':gettext('Untreated'),
			'treated':gettext('Treated')
		},
		create_html : function(enums){
			var html = '';
			html += '<select class="form-control myselectfilter" style="width:200px">';
			for(var key in enums){
				html += '<option value="' + key + '">' + enums[key] + '</option>';
			}
			html += '</select>';
			return html;
		},
		hide_input:function(){
			$('div#alarmmsg .table_search input[name="alarmmsg__filter__q"]').hide();
		},
		show_input:function(){
			$('div#alarmmsg .table_search input[name="alarmmsg__filter__q"]').show();
		},
		remove_my_selects:function(){
			$('div#alarmmsg .table_search .myselectfilter').remove();
		},
		replace_input_with_select:function(select_html){
			this.hide_input();
			this.remove_my_selects();
			$('div#alarmmsg .table_search input').after($(select_html));
		},
		replace_select_with_input:function(){
			this.remove_my_selects();
			this.show_input();
		},
		change_filter_filed:function(){
			var flag = $('div#alarmmsg select[name="alarmmsg__filter__q_field"]').val();
			if(flag == 'source_type'){
				var select_html = this.create_html(this.source_type_enum);
				this.replace_input_with_select(select_html);
			}else if(flag == 'name'){
				this.replace_select_with_input();
			}else if(flag == 'zone'){
				this.replace_select_with_input();
			}else if(flag == 'status'){
				var select_html = this.create_html(this.status_enum);
				this.replace_input_with_select(select_html);
			}
		}
	},
	init : function(){
		AlarmMsg_obj = this.AlarmMsg;
		AlarmMsg_obj.change_filter_filed();
		$('div#alarmmsg select[name="alarmmsg__filter__q_field"]').off('change');
		$('div#alarmmsg select[name="alarmmsg__filter__q_field"]').on('change',function(){
			AlarmMsg_obj.change_filter_filed();
		});
	},
};