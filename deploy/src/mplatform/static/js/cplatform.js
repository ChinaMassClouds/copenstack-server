	$(function(){
			/*** 定义常量 ********/
			var NODENUM_EVERYPAGE = 5; //每页展示的节点数
			var REGEXP_IPADDRESSWITHMASK = /^(?:(?:[01]?\d{1,2}|2[0-4]\d|25[0-5])\.){3}(?:[01]?\d{1,2}|2[0-4]\d|25[0-5])(?:\/(?:[012]?\d|3[012]))$/;
			var REGEXP_IPADDRESS = /^(?:(?:[01]?\d{1,2}|2[0-4]\d|25[0-5])\.){3}(?:[01]?\d{1,2}|2[0-4]\d|25[0-5])$/;
			var REGEXP_INTEGER = /^\d+$/;
			/*
			节点类型与网卡类型对应关系（可选的网卡类型）：
			网络节点包含的网络：数据网络，存储网络，管理网络和外部网络
			计算节点包含的网络：数据网络，存储网络，管理网络
			其他节点：管理网络
			*/
			var NODETYPE_NETTYPE = {
                    'Controller':['managenet'],
					'Compute':['managenet','storagenet','datanet'],
					'Database':['managenet'],
					'RabbitMQ':['managenet'],
					'Neutron':['managenet','storagenet','datanet','outernet'],
					'Storage-Cinder':['managenet'] };
			/**
			 * 该常量与后台view保持一致
			 * -------------------
			节点类型与网卡类型对应关系（必须的网卡类型）：
			网络节点包含的网络：数据网络，存储网络，管理网络和外部网络
			计算节点包含的网络：数据网络，存储网络，管理网络
			其他节点：管理网络
			*/
			var NODETYPE_NETTYPE_NESSESARY = {
                    'Controller':['managenet'],
					'Compute':['managenet','datanet'],
					'Database':['managenet'],
					'RabbitMQ':['managenet'],
					'Neutron':['managenet','datanet'],
					'Storage-Cinder':['managenet'] };
			
			// 需要占用独立网卡的网络配置
			var NEED_ONE_CARD = {'gre':['outernet'],
			                     'vlan':['datanet','outernet'],
			                     'vxlan':['outernet']};
			// 网络类型名称对照
			var NET_KEY_NAME = {'managenet':'管理网络',
								'storagenet':'存储网络',
								'datanet':'数据网络',
								'outernet':'外部网络'};
			// 淡入淡出效果持续时间 （毫秒）
			var FADE_TIME = 200; 
				
	
	
			/*** 可变的全局变量 *****************/
			var g_checkedNodes = [];// 被选中的节点
			var g_nodeConfig = {}; // 节点配置，未保存的新数据
			var g_nodeInfo = []; // 后台返回的节点信息，未被修改的旧数据
			var g_timer_installStatus = null; // 安装进度状态刷新定时器
			var g_timer_log = null; // 日志展示刷新定时器
			var g_timer_deployStatus = null; // 部署状态刷新定时器
			
			/** 创建Uploader对象 **/
			var createUploader = function(serverPath,pickObjId,multiple){
				return WebUploader.create({
				    server: serverPath,
				    pick: '#' + pickObjId,
				    formData:{'fileUUID':''},
				    resize: false,// 不压缩image, 默认如果是jpeg，文件上传前会压缩一把再上传！
				    chunked: true, //分片上传
				    chunkSize: 52428800, //每个分片50M
				    chunkRetry: 10, //如果某个分片由于网络问题出错，允许自动重传10次
				    multiple: multiple //是否允许选取多个文件
				});
			};
			
			var global_license_uploader = createUploader('/cplatform/uploadLicense/','file_license',false);
	
	
			/*** 表单序列化 ***************/
			$.fn.serializeObject = function() {
				var o = {};
				var a = this.serializeArray();
				$.each(a, function() {
					if (o[this.name] !== undefined) {
						if (!o[this.name].push) {
							o[this.name] = [o[this.name]];
						}
						o[this.name].push(this.value || '');
					} else {
						o[this.name] = this.value || '';
					}
				});
				return o;
			};
			
			/** 从全局变量中删除无效的节点，以 g_nodeInfo 为准 */
			var deleteInvalidNodeFromGlobalVar = function(node){
				var validNode = [];
				for(var i = 0;i < g_nodeInfo.length; i ++ ){
					var nodename = g_nodeInfo[i]['nodename'];
					validNode.push(nodename);
				}
				
				var new_g_checkedNodes = [];
				for(var i = 0;i < g_checkedNodes.length; i ++ ){
					if(validNode.indexOf(g_checkedNodes[i]) > -1){
						new_g_checkedNodes.push(g_checkedNodes[i]);
					}
				}
				g_checkedNodes = new_g_checkedNodes;
				
				var new_g_nodeConfig = {};
				for(var i in g_nodeConfig){
					if(validNode.indexOf(i) > -1){
						new_g_nodeConfig[i] = g_nodeConfig[i];
					}
				}
				g_nodeConfig = new_g_nodeConfig;
			};
				
			/** 获取指定对象的 ScrollTop 值，参数 selectStr 是选择器表达式 */
			var getScrollTop = function(selectStr){
				var scrollTop = $(selectStr).scrollTop();
				if(!scrollTop){ // 考虑浏览器的兼容性
					scrollTop = document.documentElement.scrollTop;
				}
				return scrollTop;
			};
			
			/** 锁住body使其不可滚动 */
			var lockDocumentBody = function(){
				$('.overlay').css('top',getScrollTop('body'));
				$('body').addClass('overflow_hidden');
			};
			
			/** 解锁body使其可以滚动 */
			var unlockDocumentBody = function(){
				$('body').removeClass('overflow_hidden');
			};
			
			/** 检验session，失效时自动跳到登录页面 */
			var checkSession = function(res){
				if(res.indexOf('<!-- page for login -->') == 0){
					window.location = '/';
				}
			};
			
			/****
				function : 检验文件扩展名
				@param fileinput:对象，fileinput对象
				@param accepttype:字符串，接受的文件扩展名，不区分大小写，多个用逗号隔开，中间不要带空格
			**/
			function checkFileExtName(fileinput, accepttype){
				var filename = fileinput.files[0].name;
				accepttypereg = accepttype.replace(/,/g,'|').replace(/\./g,'\\.');
				var reg = new RegExp('^.+\\.(' + accepttypereg + ')$','i');
				if(reg.test(filename)){
					return true;
				}
				fileinput.value = '';
				alert('只能上传'+accepttype+'文件！');
				return false;
			}
			/**
            	生成32位随机字符串
            **/
            function createUUID(){
            	var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
            	var maxPos = chars.length;
            	var len = 32;
            	var uuid = '';
            	for(var i = 0;i < len;i ++){
            		uuid += chars.charAt(Math.floor(Math.random() * maxPos));
            	}
            	return uuid;
            }
            
    		$('.close_btn,.cancel').on('click', function(e){
    			e.preventDefault();
    			$('.overlay').hide();
    			unlockDocumentBody();
    		});

    		$('.guideBottom .next').on('click', function(){
    			if($('.guide_main .manage_network').is(':visible')){
    				$('#guide_network_form').submit();
    				var list = $('#guide_network_form .error');
    				for(var i = 0; i < list.length; i ++){
    					if($(list[i]).html()){
    						return;
    					}
    				}
    			}
    				
    			if($('.guide_nav .active').index() + 2 < $('.guide_nav .item').length){
    				$('.guide_nav .active').removeClass('active').addClass('configed').next().addClass('active');

    				$('.guide_main .main_item').eq($('.guide_nav .active').index()).show().siblings().hide();
    				return false;
    			}else if($('.guide_nav .active').index() + 2 === $('.guide_nav .item').length){
    				$(this).addClass('create');
    				$('.guide_nav .active').removeClass('active').addClass('configed').next().addClass('active');

    				$('.guide_main .main_item').eq($('.guide_nav .active').index()).show().siblings().hide();
    				return false;
    			}
    		});

    		$('.back').on('click', function(){
    			$('.next').removeClass('create');
    			if($('.guide_nav .active').index() !== 0){
    				$('.guide_nav .active').removeClass('active').prev().addClass('active');

    				$('.guide_main .main_item').eq($('.guide_nav .active').index()).show().siblings().hide();
    			}
    			else{
    				return false;
    			}
    		});

			$('.deploy_mode .icon:not(.disable), .network .icon').on('click', function(e){
				e.preventDefault;
				var $this = $(this);
				if($this.hasClass('selected')) {
					return;
				}
				$this.closest('.main_item').find('.selected').removeClass('selected');
				$this.addClass('selected');
			});

			$('.storage .icon:not(.disable)').on('click', function(e){
				e.preventDefault;
				var $this = $(this);
				if($this.hasClass('selected')) {
					return;
				}
				$this.closest('.subitems').find('.selected').removeClass('selected');
				$this.addClass('selected');
			});

			$('.takeover_platform .icon').on('click', function(e){
				e.preventDefault;
				var $this = $(this);
				$this.toggleClass('selected');
			});


			$('.guide').on('click', '.create', function(e){
				e.preventDefault;
				$('.guide_div').hide();
				unlockDocumentBody();
				$('.wait_div').show();
				lockDocumentBody();
				
				var customdata = {};
				customdata['colud_evn_name'] = $('.guide_main #colud_evn_name').val();//云环境名称
				customdata['deploy_mode'] = $('.guide_main .deploy_mode a.selected').attr('data-val');//部署模式
				var selectedObjs = $('.guide_main .takeover_platform a.selected');
				var takeover_platform = '';
				if(selectedObjs && selectedObjs.length > 0){
					for(var i = 0;i< selectedObjs.length;i++){
						if(i > 0) takeover_platform += ',';
						takeover_platform += $(selectedObjs[i]).attr('data-val');
					}
				}
				customdata['takeover_platform'] = takeover_platform;//接管平台
				customdata['network'] = $('.guide_main .network a.selected').attr('data-val');//数据网络
				customdata['cidr'] = $('.guide_main .manage_network #cidr1').val();//管理网络-CIDR
				customdata['ip_range_min'] = $('.guide_main .manage_network #ip_range1').val();//管理网络-开始IP
				customdata['ip_range_max'] = $('.guide_main .manage_network #ip_range_max1').val();//管理网络-结束IP
				customdata['gateway'] = $('.guide_main .manage_network #gateway1').val();//管理网络-网关
				customdata['dns1'] = $('.guide_main .manage_network #dns1').val();//管理网络-DNS1
				customdata['storage_vminstance'] = $('.guide_main .storage .vminstance a.selected').attr('data-val');//存储-虚机实例
				customdata['storage_vmimage'] = $('.guide_main .storage .vmimage a.selected').attr('data-val');//存储-虚机镜像
				customdata['storage_userdisk'] = $('.guide_main .storage .userdisk a.selected').attr('data-val');//存储-用户磁盘
				
				$.ajax({
					url:'/cplatform/create/',
					type:'post',
					data:customdata,
					success:function(res){
						if(res == 'success'){
							alert('创建云环境成功！');
							$('.guide_div').hide();
							unlockDocumentBody();
							$('body > .content').show();
							query_node(1);
							showNodeRoleInRight();
						}else{
							alert('创建云环境失败！');
							window.location = '/';
						}
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(){
						alert('创建云环境失败！');
						window.location = '/';
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			});
			
			var openTimerInstallStatus = function(){
				// 安装进度刷新定时器
				if(!g_timer_installStatus){
					g_timer_installStatus = setInterval(function(){
						$.ajax({
							url: '/cplatform/installStatus/',
							success:function(res){
								checkSession(res);
								$('.setup_process').hide();
								if(res){
									var res_json = JSON.parse(res);
									for(var k in res_json){
										if(res_json[k])
											$('.setup_process[data-node="' + k + '"]').html(res_json[k]).show();
									}
								}
							}
						});
					},1000);
				}
			};
			var closeTimerInstallStatus = function(){
				if(g_timer_installStatus){
					clearInterval(g_timer_installStatus);
					g_timer_installStatus = null;
				}
			};
			var openTimerLog = function(){
				// 日志刷新定时器
				if(!g_timer_log){
					g_timer_log = setInterval(function(){
						$.ajax({
							url: '/cplatform/logshow/',
							success:function(res){
								checkSession(res);
								if(res){
									$('.wait_div').fadeOut(FADE_TIME);
									unlockDocumentBody();
									$('.log_content textarea').css('height',screen.height - 340);
									$('.log_content textarea').val(res).show();
									//$('.log_content textarea').scrollTop (99999999); // 滚动条自动滚动到最下方
								}
							}
						});
					},1000);
				}
			};
			var closeTimerLog = function(){
				if(g_timer_log){
					clearInterval(g_timer_log);
					g_timer_log = null;
				}
			};
			var showDeployStatus = function(){
				$.ajax({
					url: '/cplatform/getDeployStatus/',
					success:function(res){
						checkSession(res);
						if(res == 'deploying'){
							$('.deployStatus').html('');
						}else if(res && res.indexOf('deployover') == 0){
							var c_ip = res.split(',')[1];
							$('.deployStatus').html('云平台环境部署完成，请在浏览器中输入IP ' + c_ip + ' 登陆到云平台Dashborad。');
						}else if(res == 'deployfail'){
							$('.deployStatus').html('云平台环境部署失败。');
						}else{
							$('.deployStatus').html('');
						}
					}
				});
			};
			var openTimerDeployStatus = function(){
				// 部署状态刷新定时器
				if(!g_timer_deployStatus){
					g_timer_deployStatus = setInterval(showDeployStatus,10000);
				}
			};
			//显示硬件信息
			var showHardwareInfo = function(){
				$.ajax({
					url:'/cplatform/getHardInfo/',
					success:function(res){
						$('.license_content .hardware_info').html(res);
					},
					error:function(){
						$('.license_content .hardware_info').html('获取硬件信息出错！');
					}
				});
			};
			//显示授权信息
			var showLicenseInfo = function(){
				$.ajax({
					url:'/cplatform/getLicenseInfo/',
					success:function(res){
						if(res && res.indexOf('probation:') == 0){
							$('.license_content .license_info').html('试用期至 ' + res.replace('probation:',''));
							$('.license_content .license_info').css('height', '50px');
						}else {
							$('.license_content .license_info').html(res || '没有可用的授权文件！');
							$('.license_content .license_info').css('height', res ? '280px' : '50px');
						}
					},
					error:function(){
						$('.license_content .license_info').html('获取授权信息出错！');
					}
				});
			};
			//main area event
			$('.tab li').on('click', function(e){
				e.preventDefault;
				var $this = $(this);
				$this.addClass('active').siblings().removeClass('active');

				$('.main_wrapper > div').eq($this.index()).show().siblings().hide();
				//定时器切换
				if($('.tab .node').is('.active')){
					openTimerInstallStatus();
				}else{
					closeTimerInstallStatus();
				}
				if($('.tab .log').is('.active')){
					$('.wait_div').show();
					lockDocumentBody();
					openTimerLog();
				}else{
					closeTimerLog();
				}
				if($('.tab .upgrade').is('.active')){
					showUploadedFiles('basic_iso');
					showUploadedFiles('unit_rpm');
				}
				if($('.tab .license').is('.active')){
					showHardwareInfo();
					showLicenseInfo();
				}
			});
			//网络设置页面初始化数据
			$('.tab .net').on('click',function(){
				$.ajax({
					url:'/cplatform/forNetConfig/',
					success:function(res){
						checkSession(res);
						var res_json = JSON.parse(res);
						for(var k in res_json){
							$('.net_content input[name="' + k + '"]').val(res_json[k]);
						}
						//动态加载DNS
						var func = function(keyword){
							var i = 1;
							while(res_json[keyword + i]){
								if(i > $('.net_content input[name="' + keyword + '"]').length){
									var lastDom = $($('.net_content input[name="' + keyword + '"]')[i-2]);
									var $clone = lastDom.clone().val('').removeClass('required');
									lastDom.after($clone);
								}
								$($('.net_content input[name="' + keyword + '"]')[i-1]).val(res_json[keyword + i]);
								i ++;
							}
						};
						func('manage_dns');
						func('storage_dns');
					},
					error:function(){
						alert('获取网络配置信息失败！');
					}
				});
			});
			//云环境设置页面初始化数据
			$('.tab .setup').on('click',function(){
				$.ajax({
					url:'/cplatform/forEnvConfig/',
					success:function(res){
						checkSession(res);
						var res_json = JSON.parse(res);
						$('.setup_content input[name="setup_name"]').val(res_json['env_name']);
						$('.setup_content .network .icon').removeClass('selected');
						$('.setup_content .network .icon[data-val="'+res_json['networktype']+'"]').addClass('selected');
						$('.setup_content .storage .vminstance .icon').removeClass('selected');
						$('.setup_content .storage .vminstance .icon[data-val="'+res_json['storage_vminstance']+'"]').addClass('selected');
						$('.setup_content .storage .vmimage .icon').removeClass('selected');
						$('.setup_content .storage .vmimage .icon[data-val="'+res_json['storage_vmimage']+'"]').addClass('selected');
						$('.setup_content .storage .userdisk .icon').removeClass('selected');
						$('.setup_content .storage .userdisk .icon[data-val="'+res_json['storage_userdisk']+'"]').addClass('selected');
					},
					error:function(){
						alert('获取云环境配置信息失败！');
					}
				});
			});

			//node set up
			$('.node_list').on('click', '.icon', function(e){
				e.preventDefault;
				var $this = $(this);
				if(g_checkedNodes.length == 0 
						|| $this.next().find('.node_tip').html().replace('(','').replace(')','')
						== g_nodeConfig[g_checkedNodes[0]].join(',')){
					$this.toggleClass('selected');
					setNodeListCss();
					if($this.hasClass('selected')){
						g_checkedNodes.push($this.attr('data-val'));
					}else{
						for(var i = 0;i < g_checkedNodes.length; i++){
							if(g_checkedNodes[i] == $this.attr('data-val')){
								g_checkedNodes.splice(i,1);
								break;
							}
						}
					}
					showNodeRoleInRight();
				}else{
					alert('只有配置相同的节点才能同时选中！');
				}
			});
			

			$(document).on('click','.net_config_style', function(e){
				e.preventDefault();
				$(this).next('.net_config_list').toggle();
			});

			$(document).on('click','.net_config_list li', function(e){
				e.preventDefault();
				if($(this).find('div').hasClass('checkbox')){
					$(this).find('div').removeClass('checkbox').addClass('checkbox_checked');
				}else{
					$(this).find('div').removeClass('checkbox_checked').addClass('checkbox');
				}
			});
			
			$(document).on('click','.disk_nodes li span', function(e){
				e.preventDefault();
				if($(this).hasClass('checkbox')){
					$(this).removeClass('checkbox').addClass('checkbox_checked');
				}else{
					$(this).removeClass('checkbox_checked').addClass('checkbox');
				}
			});
			// 节点设置
			$('.main_wrapper').on('click', '.node_setup', function(e){
				e.stopPropagation();
				var nodeRole = $(this).parent().parent().find('.node_tip').html();
				var nodeRoleArr = [];
				if(nodeRole){
					nodeRoleArr = nodeRole.replace('(','').replace(')','').split(',');
				}
				var nodeName = $(this).attr('data-name');
				$.ajax({
					url:'/cplatform/fornodecfg/' + nodeName + '/',
					type:'post',
					data:{'node_role':nodeRole},
					datatype:'json',
					success:function(res){
						checkSession(res);
						if(res){
							var res_json = JSON.parse(res);
							//显示网卡列表
							var netList = htmlRender($('#template_nodeeth').html(),res_json['net']);
							$('.config_wrapper .net_nodes').html('');
							for(var i = 0; i < netList.length; i ++){
								$('.config_wrapper .net_nodes').append($(netList[i]));
							}
							//显示磁盘列表
							var diskList = htmlRender($('#template_nodedisk').html(),res_json['disk']);
							$('.config_wrapper .disk_nodes').html('');
							for(var i = 0; i < diskList.length; i ++){
								$('.config_wrapper .disk_nodes').append($(diskList[i]));
							}
							//node名称
							$('.config_wrapper .node_name').val(nodeName);
							$('.config_wrapper .node_role').val(nodeRole);
							$('.config_wrapper .net_type').val(res_json['net_type']);
							
							var netUl = $('.config_wrapper .net_nodes .node');
							//网络设置的可选与禁选（由节点类型决定）
							for(var i = 0; i < nodeRoleArr.length; i ++ ){
								var role = nodeRoleArr[i];
								var avalibleNet = NODETYPE_NETTYPE[role];
								for(var v = 0; v < avalibleNet.length; v ++ ){
									netUl.find('div[data-val="'+avalibleNet[v]+'"]').parent()
											.css('display','inline-block');
								}
							}
							//显示网络设置
							for(var i=0;i<netUl.length;i++){
								var netType = $(netUl[i]).find('.netType').html();
								if(netType){
									var netTypeArr = netType.split(',');
									for(var t = 0; t < netTypeArr.length; t ++ ){
										$(netUl[i]).find('div[data-val="'+netTypeArr[t]+'"]').removeClass('checkbox')
												.addClass('checkbox_checked');
										$(netUl[i]).find('div[data-val="'+netTypeArr[t]+'"]').parent()
												.css('display','inline-block');
									}
								}
							}
							
							var diskUl = $('.config_wrapper .disk_nodes .node');
							//判断磁盘挂载选择框是否展示
							var ext_list = [];
							if(nodeRole.indexOf('Controller') > -1){
								ext_list.push({'key':'nfs','value':'扩展NFS存储空间'});
							}
							if(nodeRole.indexOf('Storage-Cinder') > -1){
								ext_list.push({'key':'cinder','value':'扩展cinder卷空间'});
							}
							if(ext_list.length == 2){
								diskUl.find('.diskext_checkbox').remove();
								diskUl.find('.diskext_select[data-sys="xfs"]').remove();
							}else if(ext_list.length == 1){
								diskUl.find('span').attr('data-val',ext_list[0]['key']);
								diskUl.find('span').html(ext_list[0]['value']);
								diskUl.find('.diskext_select').remove();
								diskUl.find('.diskext_checkbox[data-sys="xfs"]').remove();
							}else{
								diskUl.find('.diskext_checkbox').remove();
								diskUl.find('.diskext_select').remove();
							}
							//显示磁盘的挂载情况
							for(var i=0;i<diskUl.length;i++){
								if($(diskUl[i]).find('.diskext_select').length > 0){
									var a = $(diskUl[i]).find('.diskext_select').attr('data-type');
									$(diskUl[i]).find('.diskext_select').val(a);
								}else if($(diskUl[i]).find('.diskext_checkbox').length > 0){
									var a = $(diskUl[i]).find('.diskext_checkbox').attr('data-type');
									$(diskUl[i]).find('.diskext_checkbox[data-val="'+a+'"]').removeClass('checkbox').addClass('checkbox_checked');
								}
							}
						}
					},
					error:function(){
						alert('获取节点信息出错！');
					}
				});

				$('.config_wrapper .config_area').parent().show();
				$('.config_wrapper .config_area_ipset input').val('');
				$('.config_wrapper .config_area_ipset').parent().hide();
				$('.config_wrapper').show().parent().show();
				lockDocumentBody();
			});

			//net_content的添加input功能
			$('.net_content').on('click','.add_icon', function(e){
				e.preventDefault();
				var $this = $(this);
				var $clone = $this.prev().clone().val('').removeClass('required');
				$this.before($clone);
			});

			
			//net content validation
			$.validator.addMethod("ipaddressWithMask", function(value) {
				return REGEXP_IPADDRESSWITHMASK.test(value);
			}, '请输入合法地址');

			$.validator.addMethod("ipaddress", function(value) {
				return REGEXP_IPADDRESS.test(value);
			}, '请输入合法地址');
			
			
			$('#guide_network_form').validate({
				rules: {
					cidr1:"ipaddressWithMask",
					ip_range1: "ipaddress",
					ip_range_max1: "ipaddress",
					gateway1: "ipaddress",
					dns1: "ipaddress"
				},
				errorPlacement: function(error, element) {
					element.parent().find(".error_message").html(error);
				},
				submitHandler: function () {
                	
            	}
			});


			$('#setup_content_form').validate({
				rules: {
					setup_name: {
						required: true
					},
					old_pwd: {
						required: true
					},
					new_pwd: {
						required: true
					},
					confirm_pwd: {
						required: true
					}
				},
				messages: {
					setup_name: {
						required: "请输入对应名称"
					},
					old_pwd: {
						required: "密码不能为空"
					},
					new_pwd: {
						required: "密码不能为空"
					},
					confirm_pwd: {
						required: "密码不能为空"
					}
				},
				errorPlacement: function(error, element) {
					element.parent().find(".error_message").html(error);
				},
				submitHandler: function (form) {
                	form.ajaxSubmit(function(){
					alert("ok");
					});
            	}
			});
			
			/*** 由ajax返回的数据及html模板合成最终html代码段 *****/
			var htmlRender = function(html_template,json_str){
				var res_json = null;
				if(typeof(json_str) == 'string') 
					res_json = JSON.parse(json_str);
				else
					res_json = json_str;
						
				var createHtml = function(jsonObj){
					var html = html_template;
					for(var key in jsonObj){
						var reg = RegExp('@@@'+key+'@@@','g');
						html = html.replace(reg,jsonObj[key]);
					}
					return html;
				};
				if(res_json.length != undefined){// res_json是对象列表
					var html_arr = [];
					for(var i=0;i<res_json.length;i++){
						html_arr.push(createHtml(res_json[i]));
					}
					return html_arr;
				}else {// res_json是单个对象
					return createHtml(res_json);
				}
			};
			/*** 设置节点列表的样式 *******/
			var setNodeListCss = function(){
				var nodeDoms = $('.node_list li');
				//清除原有的颜色
				nodeDoms.removeClass('done').removeClass('error');
				for(var i = 0;i < nodeDoms.length; i++){
					if($(nodeDoms[i]).find('.selected') && $(nodeDoms[i]).find('.selected').length > 0){//选中的显示蓝色
						$(nodeDoms[i]).addClass('done');
					}else{
						if(!$(nodeDoms[i]).find('.node_tip').html()){//未被选中的，根据角色配置显示红色或绿色
							$(nodeDoms[i]).addClass('error');
						}
					}
				}
			};
			/*** 显示列表上各节点的角色（缓存） *******/
			var setNodeListRole = function(){
				for(var node in g_nodeConfig){
					var roles = g_nodeConfig[node];
					var roles_str = '';
					if(roles.length > 0){
						roles_str = '(' + roles.join(',') + ')';
					}
					$('.node_list span[data-val="'+node+'"]').next().find('.node_tip').html(roles_str);
				}
			};
			/*** 在右侧显示选中节点的角色（缓存） ********/
			var showNodeRoleInRight = function(){
				if(g_checkedNodes.length == 0){
					$('.right').hide();
				}else{
					var firstCheckedNode = g_checkedNodes[0];
					var roles_str = $('.node_list span[data-val="'+firstCheckedNode+'"]').next().find('.node_tip').html();
					roles_str = roles_str.replace('(','').replace(')','');
					var roles = roles_str.split(',');
					$('.right a').removeClass('selected');
					for(var i =0;i<roles.length;i++){
						$('.right a[data-val="'+roles[i]+'"]').addClass('selected');
					}
					$('.right').show();
				}
			};
			/*** 展示当页数据 ******/
			var showPageData = function(targetPage){
				if(!targetPage) targetPage = 1;
				var lis = g_nodeInfo.slice((targetPage - 1) * NODENUM_EVERYPAGE, targetPage * NODENUM_EVERYPAGE);
				var pageLis = htmlRender($('#template_node').html(),lis);
				$('.node_list').html('');
				for(var i = 0; i < pageLis.length; i ++){
					$('.node_list').append($(pageLis[i]));
				}
				//当前页标志
				$('.page_area .num').removeClass('cur');
				$('.page_area .num').eq(targetPage-1).addClass('cur');
				//被选中的，打勾
				for(var i = 0; i < g_checkedNodes.length; i ++){
					$('.node_list span[data-val="'+g_checkedNodes[i]+'"]').addClass('selected');
				}
				//显示列表上各节点的角色
				setNodeListRole();
				//根据配置情况设置样式
				setNodeListCss();
				
			};
			var reciveResult = function(res,is_find){
				if(res){
					//把节点信息存入全局变量
					var res_json = JSON.parse(res);
					if(res_json['error']){
						if(res_json['error'] == 'BROADCAST_ERROR'){
							alert('发送广播消息出错！');
						}else if(res_json['error'] == 'READ_ERROR'){
							alert('读取节点信息出错！');
						}else{
							alert('未知错误！');
						}
					}else{
						g_nodeInfo = JSON.parse(res_json['nodes']);
						for(var i = 0; i < g_nodeInfo.length; i++){
							if(g_nodeInfo[i]['roles'])
								g_nodeConfig[g_nodeInfo[i]['nodename']] = g_nodeInfo[i]['roles'].split(',');
							else
								g_nodeConfig[g_nodeInfo[i]['nodename']] = []
						}
						//页码
						var nodenum = res_json['nodenum'];
						var totalPageNum = Math.ceil(nodenum / NODENUM_EVERYPAGE);
						$('#totalPageNum').html(totalPageNum);
						$('.page_area .num').remove();
						for(var i = totalPageNum; i > 0; i --){
							$('.page_area').prepend($('<span class="num">' + i + '</span>'));
						}

						$('.page_area .num').on('click',function(){
							showPageData($(this).html());
						});
						//显示第一页的数据
						showPageData(1);
						//显示节点数
						$('#node_num').html(nodenum);
						
						if(is_find && Number(nodenum) == 0){
							alert('未发现任何节点！');
						}
						if(Number(nodenum) > 0){
							$('.node_content_main .left').show();
							$('.node_content_main .no_node').hide();
							openTimerInstallStatus();
						}else{
							$('.node_content_main .left').hide();
							$('.node_content_main .no_node').show();
						}
					}
				}
			};
			/*** 发现节点 *****/
			var find_node = function(){
				$.ajax({
					url:'/cplatform/findnodes/',
					datatype:'json',
					success:function(res){
						checkSession(res);
						reciveResult(res,true);
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(e){
						alert('发现节点失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			};
			/*** 从后台获取节点信息列表 *******/
			var query_node = function(targetPage){
				$.ajax({
					url:'/cplatform/listnodes/'+targetPage+'/',
					datatype:'json',
					success:function(res){
						checkSession(res);
						reciveResult(res);
						deleteInvalidNodeFromGlobalVar();
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(){
						alert('加载节点信息失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			};

			/*** 发现节点 **********/
			$(document).on('click','.find_node',function(){
				$('.wait_div').show();
				lockDocumentBody();
				find_node();
			});
			/*** 上一页 **********/
			$(document).on('click','.page_area .last',function(){
				var currPage = $('.page_area .cur').html();
				if(Number(currPage) == 1) return;
				showPageData(currPage - 1);
			});
			/*** 下一页 **********/
			$(document).on('click','.page_area .next',function(){
				var currPage = $('.page_area .cur').html();
				if(Number(currPage) == Number($('#totalPageNum').html())) return;
				showPageData(Number(currPage) + 1);
			});
			/*** 到第n页 ***********/
			$(document).on('click','.page_area .confirm input[type="button"]',function(){
				var targetPage = $('.page_area .to_page input').val();
				if(Number(targetPage) < 1 || Number(targetPage) > Number($('#totalPageNum').html())) return;
				showPageData(targetPage);
			});
			/*** 右侧配置 *******************/
			$(document).on('click','.right a',function(){
				$(this).toggleClass('selected');
				var checkedRole = [];
				var checkedRoleDom = $('.right .selected');
				for(var i = 0; i < checkedRoleDom.length; i++){
					checkedRole.push($(checkedRoleDom[i]).attr('data-val'));
				}
				for(var i = 0; i < g_checkedNodes.length; i++){
					g_nodeConfig[g_checkedNodes[i]] = checkedRole;
				}
				setNodeListRole();
			});
			/*** 节点列表，点击大方框 ***/
			$(document).on('click','.node_list .node_item_main',function(){
				$('.node_list .selected').removeClass('selected');
				$(this).prev().addClass('selected');
				setNodeListCss();
				g_checkedNodes.length = 0;
				g_checkedNodes.push($(this).prev().attr('data-val'));
				showNodeRoleInRight();
			});
			/*** 部署变更  **********/
			$(document).on('click','.deploy_change',function(){
				var checkNewNodes = function(){ // 新增节点只能作为计算节点
					var error_nodes = [];
					for(var i = 0; i < g_nodeInfo.length; i ++ ){
						if(g_nodeInfo[i]['is_new'] == '1'){
							var node_name = g_nodeInfo[i]['nodename'];
							if(g_nodeConfig[node_name]){
								for(var j=0;j<g_nodeConfig[node_name].length;j++){
									if(g_nodeConfig[node_name][j] != 'Compute'){
										error_nodes.push(node_name);
										break;
									}
								}
							}
						}
					}
					if(error_nodes.length > 0){
						alert('节点' + error_nodes + '是新增节点，只能作为计算节点部署，请修改！');
						return false;
					}
					return true;
				};
				if(!checkNewNodes()) return;

				var startDeploy = function(){ // 正式开始部署
					$.ajax({
						url:'/cplatform/deployChange/',
						type:'post',
						data:{'nodeConfig':JSON.stringify(g_nodeConfig)},
						success:function(res){
							if(res == 'deploying'){
								alert('部署变更已经开始，请勿重复点击！');
							}else if(res == 'netinfoloss_gre'){
								alert('gre网络未设置！');
							}else if(res == 'netinfoloss_vlan'){
								alert('vlan网络未设置！');
							}else if(res == 'netinfoloss_vxlan'){
								alert('vxlan网络未设置！');
							}else if(res && res.indexOf('success') == 0){
								//var ip = res.split(',')[1];
								//alert('openstack部署完成，访问IP ' + ip + ' 登陆Dashborad。');
								//query_node(1);
							}else{
								//alert('部署变更失败！');
							}
							//$('.wait_div').fadeOut(FADE_TIME);
						},
						error:function(){
							/*
							alert('部署变更失败！');
							$('.wait_div').fadeOut(FADE_TIME);
							*/
						}
					});
				};
				var getNodeCpuno = function(node){ // 获取某个节点的cpu个数
					for(var i = 0; i < g_nodeInfo.length; i++){
						if(g_nodeInfo[i]['nodename'] == node){
							return Number(g_nodeInfo[i]['physicalprocessorcount']);
						}
					}
					return 0;
				};
				var getComputeCpuno = function(){ // 获取所有计算节点的cpu个数之和
					var a = g_nodeInfo;
					var total_cpuno = 0;
					for(var node in g_nodeConfig){
						for(var i = 0; i < g_nodeConfig[node].length; i ++ ){
							if('Compute' == g_nodeConfig[node][i]){
								total_cpuno += getNodeCpuno(node);
								break;
							}
						}
					}
					return total_cpuno;
				};
				
				if(!confirm('确定部署变更吗？')) return;
				$.ajax({
					url:'/cplatform/getLicenseCpuNo/',
					success:function(res){
						if(res == 'probation'){
							startDeploy();
						}else if(res == 'outdate'){
							alert('授权日期已过，请上传新的授权文件！');
						}else if(res == 'error'){
							alert('尚未授权，无法开启部署！');
						}else{
							var max_cpuno = Number(res);
							var computeCpuno = getComputeCpuno();
							if(computeCpuno > max_cpuno){
								var msg = '计算节点的 CPU 个数为 '+computeCpuno+'，'
										+'超过了授权所允许的 '+max_cpuno+' 个，请减少计算节点或者购买新的授权！';
								alert(msg);
								return;
							}
							startDeploy();
						}
					},
					error:function(){
						alert('查询授权信息出错，无法开启部署！')
					}
				});
			});
			/*** 节点配置保存 *******/
			var nodecfg_nodename = '';
			var nodecfg_netJson = {};
			var nodecfg_diskJson = {};
			$(document).on('click','.config_wrapper .save',function(){
				var node_role = $('.config_wrapper .node_role').val();
				if(!node_role){
					alert('请先设置节点类型！');
					return;
				}
				$('.config_wrapper .config_area_ipset .error_message').html('');
				var check_netcard = function(){ //检查必须的网卡类型是否齐全
					for(var role in NODETYPE_NETTYPE_NESSESARY){
						if(node_role.indexOf(role) > -1){
							var nessesary_arr = NODETYPE_NETTYPE_NESSESARY[role];
							for(var i = 0; i < nessesary_arr.length; i ++ ){
								if($('.config_wrapper .net_nodes .net_config_list .checkbox_checked[data-val="'+nessesary_arr[i]+'"]').length == 0){
									alert('请选择一块网卡作为'+NET_KEY_NAME[nessesary_arr[i]]+'！');
									return false;
								}
							}
						}
					}
					return true;
				}; 
				var check_netcard2 = function(){ // 每种网卡类型只需要一块网卡
					for(var role in NODETYPE_NETTYPE){
						if(node_role.indexOf(role) > -1){
							var arr = NODETYPE_NETTYPE[role];
							for(var i = 0; i < arr.length; i ++ ){
								if($('.config_wrapper .net_nodes .net_config_list .checkbox_checked[data-val="'+arr[i]+'"]').length > 1){
									alert('每种网卡类型只需要一块网卡！');
									return false;
								}
							}
						}
					}
					return true;
				};
				var nType = $('.net_type').val();// gre vlan vxlan 
				var getNetJson = function(){
					var res = {};
					var netDoms = $('.config_wrapper .net_nodes .node');
					
					var one_list = NEED_ONE_CARD[nType];
					
					for( var i = 0; i < netDoms.length; i ++ ){
						var card = $(netDoms[i]).find('.icon').html();
						var mac = $(netDoms[i]).find('.mac').html();
						var ip = $(netDoms[i]).find('.ip').html();
						var netType_arr = $(netDoms[i]).find('.checkbox_checked');
						var netType = '';
						for( var j = 0; j < netType_arr.length; j ++ ){
							if(j > 0)
								netType += ',';
							netType += $(netType_arr[j]).attr('data-val');
						}
						//检查网卡配置-开始-------------------------------------NEED_ONE_CARD
						for(var t = 0; t < one_list.length; t++){
							if(netType.indexOf(one_list[t]) > -1 && netType != one_list[t]){
								alert(NET_KEY_NAME[one_list[t]] + '需要单独占用一块网卡！');
								return;
							}
						}
						//检查网卡配置-结束-------------------------------------
						res[card] = {'mac':mac,'netType':netType,'ip':ip};
					}
					return res;
				};
				
				var getDiskJson = function(){
					var res = {};
					var diskDoms = $('.config_wrapper .disk_nodes .node');
					for( var i = 0; i < diskDoms.length; i ++ ){
						var diskname = $(diskDoms[i]).find('label').html();
						var mountType = '';
						
						if($(diskDoms[i]).find('.diskext_select').length > 0){
							mountType = $(diskDoms[i]).find('.diskext_select').val();
						}else if($(diskDoms[i]).find('.diskext_checkbox').length > 0){
							var o = $(diskDoms[i]).find('.diskext_checkbox');
							if (o.is('.checkbox_checked')){
								mountType = o.attr('data-val');
							}
						}
						res[diskname] = mountType;
					}
					return res;
				};
				var getNoIpCard = function(){
					var res = [];
					for(var k in nodecfg_netJson){
						if(nodecfg_netJson[k]['netType'] && !nodecfg_netJson[k]['ip']){
							res.push(k);
						}
					}
					return res;
				};
				var saveData = function(){
					$.ajax({
						url:'/cplatform/configNode/',
						type:'post',
						data:{'node_name':nodecfg_nodename,'net':JSON.stringify(nodecfg_netJson),'disk':JSON.stringify(nodecfg_diskJson)},
						success:function(res){
							if(res == 'success'){
								alert('保存成功！');
								$('.config_div').hide();
								unlockDocumentBody();
							}else{
								alert('保存失败！');
							}
						},
						error:function(){
							alert('保存失败！');
						}
					});
				};
				if($('.config_wrapper .config_area').is(':visible')){
					if(!check_netcard()) return;
					if(!check_netcard2()) return;
					nodecfg_nodename = $('.config_wrapper .node_name').val();
					nodecfg_netJson = getNetJson();
					nodecfg_diskJson = getDiskJson();
					var noIpCard = getNoIpCard();
					if(noIpCard.length > 0){
						$('.config_wrapper .config_area_ipset').html('');
						var ihtml = '';
						for(var i =0;i<noIpCard.length;i++){
							ihtml += '<div class="config_title">请设置网卡 '+noIpCard[i]+' 的 IP 地址</div>';
							ihtml += '<div class="config_content dd">';
							ihtml += '<label>IP地址：</label>';
							ihtml += '<div class="message">';
							ihtml += '    <input class="netset_ip" data-card="'+noIpCard[i]+'">';
							ihtml += '    <span class="error_message"></span>';
							ihtml += '</div>';
							ihtml += '<br/>';
							ihtml += '<label>子网掩码：</label>';
							ihtml += '<div class="message">';
							ihtml += '    <input class="netset_mask">';
							ihtml += '    <span class="error_message"></span>';
							ihtml += '</div>';
							ihtml += '<br/>';
							if(nType == 'vlan'){
								ihtml += '<label>DNS：</label>';
								ihtml += '<div class="message">';
								ihtml += '    <input class="netset_dns">';
								ihtml += '    <span class="error_message"></span>';
								ihtml += '</div>';
								ihtml += '<br/>';
							}
							ihtml += '</div>';
						}
						$('.config_wrapper .config_area_ipset').html(ihtml);
						$('.config_wrapper .config_area').parent().hide();
						$('.config_wrapper .config_area_ipset').parent().show();
					}else{
						saveData();
					}
				}else if($('.config_wrapper .config_area_ipset').is(':visible')){
					// 用户为网卡设置ip，然后保存--zhangdebo 2015年10月25日
					var ip_list = $('.config_wrapper .config_area_ipset .config_content .netset_ip');
					var mask_list = $('.config_wrapper .config_area_ipset .config_content .netset_mask');
					var dns_list = $('.config_wrapper .config_area_ipset .config_content .netset_dns');
					var has_err = false;
					for(var i = 0; i < ip_list.length; i ++ ){
						if(!REGEXP_IPADDRESS.test($(ip_list[i]).val())){
							$(ip_list[i]).next().html('请输入合法地址');
							$(ip_list[i]).next().show();
							has_err = true;
						}
					}
					for(var i = 0; i < mask_list.length; i ++ ){
						if(!REGEXP_IPADDRESS.test($(mask_list[i]).val())){
							$(mask_list[i]).next().html('请输入合法地址');
							$(mask_list[i]).next().show();
							has_err = true;
						}
					}
					for(var i = 0; i < dns_list.length; i ++ ){
						if(!REGEXP_IPADDRESS.test($(dns_list[i]).val())){
							$(dns_list[i]).next().html('请输入合法地址');
							$(dns_list[i]).next().show();
							has_err = true;
						}
					}
					if(has_err) return;
					for(var i = 0; i < ip_list.length; i ++ ){
						var card = $(ip_list[i]).attr('data-card');
						var ip = $(ip_list[i]).val();
						var mask = (mask_list && mask_list[i]) ? $(mask_list[i]).val() : '';
						var dns = (dns_list && dns_list[i]) ? $(dns_list[i]).val() : '';
						nodecfg_netJson[card]['ip'] = ip;
						nodecfg_netJson[card]['netmask'] = mask;
						nodecfg_netJson[card]['dns'] = dns;
					}
					saveData();
				}
			});
			
			/*** 网络设置-保存 ***/
			$(document).on('click','.net_content .save_setup',function(){
				// 数据校验
				$('#net_content_form .error_message').html('');
				var error = '请输入合法地址';
				var inputList = $('#net_content_form input');
				var hasError = false;
				var networktype = $('#net_content_form input[name="networktype"]').val();
				if(networktype == 'gre'){
					$('#net_content_form input[name="gre_cidr"]').addClass('required');
				}else if(networktype == 'vlan'){
					$('#net_content_form input[name="vlan_ipstart"]').addClass('required');
					$('#net_content_form input[name="vlan_ipend"]').addClass('required');
					$('#net_content_form input[name="vlan_cidr"]').addClass('required');
				}else if(networktype == 'vxlan'){
					$('#net_content_form input[name="vxlan_ipstart"]').addClass('required');
					$('#net_content_form input[name="vxlan_ipend"]').addClass('required');
					$('#net_content_form input[name="vxlan_cidr"]').addClass('required');
				}
				for(var i = 0;i < inputList.length; i++){
					if($(inputList[i]).is('.required') && !$(inputList[i]).val()){
						$(inputList[i]).parent().find('.error_message').html(error);
						hasError = true;
						continue;
					}
					if($(inputList[i]).is('.regexp_ipaddresswithmask') && $(inputList[i]).val() 
							&& !REGEXP_IPADDRESSWITHMASK.test($(inputList[i]).val())){
						$(inputList[i]).parent().find('.error_message').html(error);
						hasError = true;
						continue;
					}
					if($(inputList[i]).is('.regexp_ipaddress') && $(inputList[i]).val() 
							&& !REGEXP_IPADDRESS.test($(inputList[i]).val())){
						$(inputList[i]).parent().find('.error_message').html(error);
						hasError = true;
						continue;
					}
					if($(inputList[i]).is('.regexp_integer') && $(inputList[i]).val() 
							&& !REGEXP_INTEGER.test($(inputList[i]).val())){
						$(inputList[i]).parent().find('.error_message').html(error);
						hasError = true;
						continue;
					}
				}
				if(hasError) return;
				var formData = $('#net_content_form').serializeObject();
				$.ajax({
					url:'/cplatform/netConfig/',
					type:'post',
					data: {'form_data':JSON.stringify(formData)},
					success:function(res){
						if(res == 'success'){
							alert('保存成功！');
						}else{
							alert('保存失败！');
						}
					},
					error:function(){
						alert('保存失败！');
					}
				});
			});
			/*** 云环境设置 保存 ******/
			$(document).on('click','.setup_content .save_setup',function(){
				var formData = $('#setup_content_form').serializeObject();
				if(formData['new_pwd'] && !formData['old_pwd']){
					$('.setup_content #old_pwd').next().html('请输入旧密码！');
					return;
				}else{
					$('.setup_content #old_pwd').next().html('');
				}
				if(formData['confirm_pwd'] != formData['new_pwd']){
					$('.setup_content #confirm_pwd').next().html('密码不一致！');
					return;
				}else{
					$('.setup_content #confirm_pwd').next().html('');
				}
				formData['network'] = $('.setup_content .network .selected').attr('data-val');
				formData['storage_vminstance'] = $('.setup_content .storage .vminstance .selected').attr('data-val');
				formData['storage_vmimage'] = $('.setup_content .storage .vmimage .selected').attr('data-val');
				formData['storage_userdisk'] = $('.setup_content .storage .userdisk .selected').attr('data-val');
				$.ajax({
					url:'/cplatform/envConfig/',
					type:'post',
					data: {'form_data':JSON.stringify(formData)},
					success:function(res){
						if(res == 'success'){
							alert('保存成功！');
						}else if(res == 'passwd_error'){
							alert('密码修改失败！');
						}else{
							alert('保存失败！');
						}
					},
					error:function(){
						alert('保存失败！');
					}
				});
			});
			//注销
			$(document).on('click','.logout_item',function(){
				window.location = '/accounts/logout/';
			});
			//打开DHCP
			$(document).on('click','.open_dhcp',function(){
				if(!confirm('确定打开DHCP吗？')) return;
				$.ajax({
					url:'/cplatform/openDhcp/',
					success:function(res){
						if(res == 'success'){
							$('.open_dhcp').hide();
							$('.close_dhcp').show();
							alert('打开DHCP成功！');
						}else{
							alert('打开DHCP失败！');
						}
					},
					error:function(){
						alert('打开DHCP失败！');
					}
				});
			});
			//关闭DHCP
			$(document).on('click','.close_dhcp',function(){
				if(!confirm('确定关闭DHCP吗？')) return;
				$.ajax({
					url:'/cplatform/closeDhcp/',
					success:function(res){
						if(res == 'success'){
							$('.open_dhcp').show();
							$('.close_dhcp').hide();
							alert('关闭DHCP成功！');
						}else{
							alert('关闭DHCP失败！');
						}
					},
					error:function(){
						alert('关闭DHCP失败！');
					}
				});
			});
			//删除云环境
			$(document).on('click','.del_env',function(){
				if(!confirm('确定删除当前云环境吗？该操作不可恢复！')) return;
				$.ajax({
					url:'/cplatform/deleteEnv/',
					success:function(){
						alert('删除云环境成功！');
						window.location.reload();
					},
					error:function(){
						alert('删除云环境失败！');
					}
				});
			});
			//删除节点
			$(document).on('click','.delete_node',function(){
				var node_role = $(this).parent().find('.node_role').val();
				if(node_role.indexOf('Controller') > -1){
					alert('控制节点不允许删除！');
					return;
				}
				if(!confirm('确定删除该节点吗？')) return;
				var node_name = $(this).parent().find('.node_name').val();
				$.ajax({
					url: '/cplatform/deleteNode/',
					type: 'post',
					data: {'node_name':node_name},
					success: function(res){
						if(res == 'success'){
							$('.overlay').hide();
							unlockDocumentBody();
							query_node(1);
						}else{
							alert('删除节点失败！');
						}
					},
					error: function(){
						alert('删除节点失败！');
					}
				});
			});
			
			/** 升级模块：列出已上传的文件 **/
			var showUploadedFiles = function(flag){
				$('.wait_div').show();
				lockDocumentBody();
				var url = '';
				var dom_class = '';
				var package_name = '';
				var html = '';
				if(flag == 'basic_iso'){
					url = '/cplatform/listBasicIsos/';
					dom_class = 'file_basic_list';
					package_name = '基础升级包';
					html += '<tr>';
					html += '<td>';
					html += '@@@filename@@@';
					html += '</td>';
					html += '<td>';
					html += '	<a class="del">删除</a>';
					html += '</td>';
					html += '</tr>';
				}else if(flag == 'unit_rpm'){
					url = '/cplatform/listUnitRpms/';
					dom_class = 'file_unit_list';
					package_name = '组件升级包';
					html += '<tr>';
					html += '<td>';
					html += '<input type="checkbox">';
					html += '</td>';
					html += '<td>';
					html += '@@@filename@@@';
					html += '</td>';
					html += '<td>';
					html += '	<a class="del">删除</a>';
					html += '</td>';
					html += '</tr>';
				}
				if(!url || !dom_class) return;
				$.ajax({
					'url' : url,
					success:function(res){
						if(res){
							res = JSON.parse(res);
							$('.'+dom_class).find('tr:not(:first-child)').remove();
							if(res.length == 0){
								$('.'+dom_class).hide();
							}else{
								for(var i = 0 ;i < res.length; i ++){
									thtml = html.replace('@@@filename@@@',res[i]['name'])
									$('.'+dom_class).append($(thtml));
								}
								$('.'+dom_class).show();
							}
						}
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(){
						alert('查询' + package_name + '列表出错！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			}
			
	
			/** 基础升级--开始 */
			var basicUploader = createUploader('/cplatform/uploadBasicIso/','file_basic',false);
			var showUploadProgress = function( file, percentage ) {
				percentage = Math.round(percentage * 100);
				if(percentage > 99){
					percentage = 99;
				}
				document.getElementById('progressNumber').innerHTML = percentage + '%';
			    $('.progress-bar').css( 'width', percentage + '%' );
			};

			var uploadSuccess = function( file,ret ) {
			    document.getElementById('progressNumber').innerHTML = '100%';
			    $('.progress-bar').css( 'width', '100%' );
			    $('.uploading_div').fadeOut(FADE_TIME);
			    unlockDocumentBody();
			};
			var resetProgressBar = function(){
				document.getElementById('progressNumber').innerHTML = '0%';
			    $('.progress-bar').css( 'width', '0' );
			};
			// 文件上传过程中创建进度条实时显示。
			basicUploader.on( 'uploadProgress', showUploadProgress);
			basicUploader.on( 'uploadSuccess', function( file,ret ) {
			    basicUploader.reset();
				uploadSuccess(file,ret);
			    $('#file_basic input[type="file"]')[0].value = '';
			    showUploadedFiles('basic_iso');
			});
			basicUploader.on( 'uploadError', function( file ,reason) {
				basicUploader.reset();
				alert('上传出错：' + reason);
				$('.uploading_div').fadeOut(FADE_TIME);
				unlockDocumentBody();
			});
			$('#basic_upload').on('click',function(){
				if($('.file_basic_list').find('tr').length > 1){
					alert('最多只能上传一个ISO文件！');
					return;
				}
				if(!$('#file_basic input[type="file"]')[0].value){
					alert('请选择要上传的ISO文件！');
					return;
				}
				resetProgressBar();
				if(!checkFileExtName($('#file_basic input[type="file"]')[0],'iso')) return;
				$('.uploading_div').show();
				lockDocumentBody();
				var fileUUID = createUUID();
				basicUploader.options.formData['fileUUID'] = fileUUID;
				basicUploader.upload();
			});
			$(document).on('click','.file_basic_list .del',function(){
				if(!confirm('确定删除该文件吗？')) return;
				$('.wait_div').show();
				lockDocumentBody();
				var filename = $(this).parent().prev().html();
				$.ajax({
					url:'/cplatform/delBasicIso/',
					type:'post',
					data:{'filename':filename},
					success:function(res){
						if(res == 'success') showUploadedFiles('basic_iso'); 
						else alert('删除失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(){
						alert('删除失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			});
			$(document).on('click','#basic_upgrade',function(){
				if($('.file_basic_list').find('tr').length <= 1){
					alert('没有可用的ISO文件！');
					return;
				}
				if(!confirm('确定开始基础升级吗？')) return;
				$('.wait_div').show();
				lockDocumentBody();
				$.ajax({
					url:'/cplatform/basicUpgrade/',
					success:function(res){
						if(res == 'success'){
							alert('基础升级完成！');
						}else{
							alert('基础升级失败！');
						}
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(){
						alert('基础升级失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			});
			/** 基础升级--结束 */
				
				
	
	
			/** 组件升级--开始 */
			var unitUploader = createUploader('/cplatform/uploadUnitRpm/','file_unit',true);

			// 检查队列文件是否都已经上传完毕
			var allFileUploaded = function(){
				var fList = unitUploader.getFiles();
				for(var i = 0; i < fList.length; i ++ ){
					if(fList[i].getStatus() != 'complete')
						return false;
				}
				return true;
			};
			// 文件上传过程中创建进度条实时显示。
			unitUploader.on( 'uploadProgress', showUploadProgress);
			unitUploader.on( 'uploadSuccess', function( file,ret ) {
				if(allFileUploaded()){
					$.ajax({
						url:'/cplatform/ajaxCreateRepo/',
						success:function(res){
							if(res == 'success'){
								//alert('重建yum源成功！');
							}else{
								alert('重建yum源出错！');
							}
							unitUploader.reset();
							uploadSuccess(file,ret);
						    $('#file_unit input[type="file"]')[0].value = '';
						    showUploadedFiles('unit_rpm');
						},
						error:function(){
							alert('重建yum源出错！');
						}
					});
				}
			});
			unitUploader.on( 'uploadError', function( file ,reason) {
				unitUploader.reset();
				alert('上传出错：' + reason);
				$('.uploading_div').fadeOut(FADE_TIME);
				unlockDocumentBody();
			});
			$('#unit_upload').on('click',function(){
				if(!$('#file_unit input[type="file"]')[0].value){
					alert('请选择要上传的RPM文件！');
					return;
				}
				resetProgressBar();
				if(!checkFileExtName($('#file_unit input[type="file"]')[0],'rpm')) return;
				$('.uploading_div').show();
				lockDocumentBody();
				var fileUUID = createUUID();
				unitUploader.options.formData['fileUUID'] = fileUUID;
				unitUploader.upload();
			});
			$(document).on('click','.file_unit_list .del',function(){
				if(!confirm('确定删除该文件吗？')) return;
				$('.wait_div').css('top',$('body').scrollTop());
				$('.wait_div').show();
				lockDocumentBody();
				var filename = $(this).parent().prev().html();
				$.ajax({
					url:'/cplatform/delUnitRpm/',
					type:'post',
					data:{'filename':JSON.stringify([filename])},
					success:function(res){
						if(res == 'success') {
							showUploadedFiles('unit_rpm');
						}else if(res == 'createRepo_fail'){
							alert('重建yum源出错！');
							showUploadedFiles('unit_rpm');
						}else {
							alert('删除失败！');
						}
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(){
						alert('删除失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			});
			$(document).on('click','.file_unit_list input[name="checkall"]',function(){
				var arr = $('.file_unit_list').find('input:not([name="checkall"])');
				for(var i = 0; i < arr.length; i ++){
					arr[i].checked = $(this).is(':checked');
				}
			});
			$(document).on('click','#unit_del',function(){
				var objArr = $('.file_unit_list input[type="checkbox"]:not([name="checkall"]):checked');
				if(objArr.length == 0){
					alert('请选择要删除的文件！');
					return;
				}
				if(!confirm('确定删除所选文件吗？')) return;
				$('.wait_div').show();
				lockDocumentBody();
				var fileArr = [];
				for(var i = 0;i<objArr.length;i++){
					fileArr.push($(objArr[i]).parent().next().html());
				}
				$.ajax({
					url:'/cplatform/delUnitRpm/',
					type:'post',
					data:{'filename':JSON.stringify(fileArr)},
					success:function(res){
						if(res == 'success') showUploadedFiles('unit_rpm');
						else alert('删除失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(){
						alert('删除失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			});
			$(document).on('click','#unit_upgrade',function(){
				if($('.file_unit_list').find('tr').length <= 1){
					alert('没有可用的RPM文件！');
					return;
				}
				if(!confirm('确定开始组件升级吗？')) return;
				$('.wait_div').show();
				lockDocumentBody();
				$.ajax({
					url:'/cplatform/unitUpgrade/',
					success:function(res){
						if(res == 'success'){
							alert('组件升级完成！');
						}else{
							alert('组件升级失败！');
						}
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					},
					error:function(){
						alert('组件升级失败！');
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
					}
				});
			});
			/** 组件升级--结束 */
				
			// 下载硬件信息
			$(document).on('click','.license_content .btn_download_hardinfo',function(){
				window.location = '/cplatform/downloadHardinfo/';
			});
			var clearLicenseFileInput = function(){
				$('.upd_license_div #file_license input[type="file"]').val('');
				global_license_uploader.reset();
			};
			// 上传授权信息
			$(document).on('click','.license_content .btn_upload_license',function(){
				clearLicenseFileInput();
				$('.upd_license_div textarea').html('');
				$('.upd_license_div').show();
				lockDocumentBody();
			});
			global_license_uploader.on( 'uploadSuccess', function( file,ret ) {
				$('.upd_license_div textarea').html(ret['_raw'] || '授权文件无效');
				clearLicenseFileInput();
			});
			global_license_uploader.on( 'uploadError', function( file ,reason) {
				clearLicenseFileInput();
			});
			global_license_uploader.on( 'fileQueued', function() {
				var file = $('.upd_license_div #file_license input[type="file"]')[0].files[0];
				if(file && file.size > 2000){
					alert('文件过大，请上传正确的授权文件！');
					clearLicenseFileInput();
					return;
				}
				var fileUUID = createUUID();
				global_license_uploader.options.formData['fileUUID'] = fileUUID;
				global_license_uploader.upload();
			});
			$(document).on('click','.upd_license_div .updlicense_wrapper .oper_area .save',function(){
				var lincenseInfo = $('.upd_license_div .updlicense_wrapper .content textarea').html();
				if(!lincenseInfo){
					alert('请选择授权文件!');
					return;
				}else if(lincenseInfo == '授权文件无效'){
					alert('授权文件无效!');
					return;
				}
				if( ! confirm('确定使用该授权文件吗？') )  return;
				$('.upd_license_div').hide();
				$('.wait_div').show();
				lockDocumentBody();
				$.ajax({
					url:'/cplatform/licenseok/',
					success:function(res){
						if(res == 'success'){
							alert('授权文件已生效！');
							$('.wait_div').fadeOut(FADE_TIME);
							unlockDocumentBody();
							showLicenseInfo();
						}else{
							$('.wait_div').fadeOut(FADE_TIME);
							unlockDocumentBody();
							alert('授权文件出错！');
						}
					},
					error:function(){
						$('.wait_div').fadeOut(FADE_TIME);
						unlockDocumentBody();
						alert('授权文件出错！');
					}
				});
			});
					
			/************************/
			if($('#to_new').val() == '1'){
				$('body > .content').hide();
				$('.guide_div').show();
			}else{
				$('.wait_div').show();
				lockDocumentBody();
				$('body > .content').show();
				$('.guide_div').hide();
				query_node(1);
			}
			
			if($('#dhcpIsActive').val() == 'True'){
				$('.open_dhcp').hide();
				$('.close_dhcp').show();
			}else{
				$('.open_dhcp').show();
				$('.close_dhcp').hide();
			}
			showDeployStatus();
			openTimerDeployStatus();
			
    	});
