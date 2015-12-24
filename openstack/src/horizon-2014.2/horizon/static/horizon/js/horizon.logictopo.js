horizon.logic_topo = {
	/** data-level : 0123456 ; */
	/** data-type : ['openstack','zone','plat','datacenter','cluster','host','vm','computer'] ; */
	row_height: [60,110,110,110,110,110,120],
	svg_offset_x: -255,
	svg_offset_y: -131,
    width_per_node: 80,
	height_per_node: 77,
    vm_count_per_row: 10,
	get_canvas_height: function(){
		var height = 0;
		var arr = horizon.logic_topo.row_height;
		for(var i = 0; i < arr.length; i ++ ){
			height += arr[i];
		}
		return height;
	},
	get_top: function(level,index,obj){
		if(level == 0) return 0;
		var node_type = $(obj).attr('data-type');
		var top = 0;
		var arr = horizon.logic_topo.row_height;
		for(var i = 0; i < level; i ++ ){
			top += arr[i];
		}
		top += arr[level] / 2;
		if(node_type == 'vm'){
			var vmindex = Number($(obj).attr('data-vmindex'));
			var z = Math.floor(vmindex / horizon.logic_topo.vm_count_per_row);
			top += z * horizon.logic_topo.height_per_node;
		}
		return top;
	},
	get_max_left: function(selector){
		var max_left = -Infinity;
		$(selector).each(function(index,obj){
			var left = Number($(obj).css('left').replace('px',''));
			if(!left) left = 0;
			if(left > max_left) max_left = left;
		});
		return max_left;
	},
    get_canvas_width: function(){
		var max_left = horizon.logic_topo.get_max_left('#logic-topo > div');
		return max_left + horizon.logic_topo.width_per_node;
	},
	get_level_nodes: function(level){
		var $arr = $('#logic-topo > div[data-level="'+level+'"]');
		return $arr;
	},
	get_left: function(level,index,obj){
		if(false && Number(level) == 0){
			var max_left = horizon.logic_topo.get_max_left('#logic-topo > div');
			return ((max_left + horizon.logic_topo.width_per_node) / 2) + 'px';
		}else{
			var child = JSON.parse($(obj).attr('data-child'));
			var node_type = $(obj).attr('data-type');
			if(child && child.length > 0){
				var min_left = Infinity;
				var max_left = -Infinity;
				for(var i = 0; i < child.length; i ++ ){
					var $c_obj = $('#logic-topo > div[data-no="' + child[i] + '"]');
					var c_left = Number($c_obj.css('left').replace('px',''));
					if(!c_left){
						c_left = 0;
					}
					if(c_left > max_left){
						max_left = c_left;
					}
					if(c_left < min_left){
						min_left = c_left;
					}
				}
				if(node_type == 'host' || node_type == 'computer'){
					if(child.length > horizon.logic_topo.vm_count_per_row){
						max_left = min_left + (horizon.logic_topo.vm_count_per_row - 1) * horizon.logic_topo.width_per_node;
					}
				}
				return ((min_left + max_left) / 2) + 'px';
			}else if(node_type == 'vm'){
				var vmindex = Number($(obj).attr('data-vmindex'));
				if(vmindex == 0){
					var max_left = horizon.logic_topo.get_max_left('#logic-topo > div[data-level="' + level + '"]');
					return (max_left + horizon.logic_topo.width_per_node) + 'px';
				}else{
					var vm0no = Number($(obj).attr('data-vm0no'));
					var vm0left = Number($('#logic-topo > div[data-no="'+vm0no+'"]').css('left').replace('px',''));
					var t = vmindex % horizon.logic_topo.vm_count_per_row;
					return (vm0left + t * horizon.logic_topo.width_per_node) + 'px';
				}
			}else{
				var selector = '#logic-topo > div[data-level="' + level + '"]';
				var $brother = $(selector);
				if($brother.length == 1){
					return '0';
				}else{
					var max_left = horizon.logic_topo.get_max_left(selector);
					return (max_left + horizon.logic_topo.width_per_node) + 'px';
				}
			}
		}
	},
	connect_line: function(){
		jsPlumb.ready(function () {

		    var instance = window.jsp = jsPlumb.getInstance({
		        DragOptions: { cursor: 'pointer', zIndex: 2000 },
		        Container: "logic-topo"
		    });
			
		    var basicType = {
 		        connector: "StateMachine",
 		        paintStyle: { strokeStyle: "red", lineWidth: 4 },
 		        hoverPaintStyle: { strokeStyle: "blue" },
 		        overlays: [
 		            "Arrow"
 		        ]
 		    };
 		    instance.registerConnectionType("basic", basicType);
			
			// this is the paint style for the connecting lines..
		    var connectorPaintStyle = {
		           		            lineWidth: 2,
		           		            strokeStyle: "#61B7CF",
		           		            joinstyle: "round",
		           		            outlineColor: "white",
		           		            outlineWidth: 2
		           		        },

			// the definition of source endpoints (the small blue ones)
		        sourceEndpoint = {
		      		            endpoint: "Blank",
		      		            isSource: true,
		      		            connector: 'Straight',
		      		            connectorStyle: connectorPaintStyle,
		      		            dragOptions: {},
		      		            overlays: [
		      		                [ "Label", {
		      		                    location: [0.5, 1.5],
		      		                    label: "",
		      		                    cssClass: "endpointSourceLabel"
		      		                } ]
		      		            ]
		      		        },
			// the definition of target endpoints (will appear when the user drags a connection)
		        targetEndpoint = {
		      		            endpoint: "Dot",
		      		            paintStyle: { fillStyle: "#7AB02C", radius: 1 },
		      		            maxConnections: -1,
		      		            dropOptions: { hoverClass: "hover", activeClass: "active" },
		      		            isTarget: true,
		      		            overlays: [
		      		                [ "Label", { location: [0.5, -0.5], label: "", cssClass: "endpointTargetLabel" } ]
		      		            ]
		      		        },
			    init = function (connection) {
			        connection.getOverlay("label").setLabel(connection.sourceId.substring(15) + "-" + connection.targetId.substring(15));
			    };
			
			var _addEndpoints = function (toId, sourceAnchors, targetAnchors) {
			    for (var i = 0; i < sourceAnchors.length; i++) {
			        var sourceUUID = toId + sourceAnchors[i];
			        instance.addEndpoint("flowchart" + toId, sourceEndpoint, {
			            anchor: sourceAnchors[i], uuid: sourceUUID
			        });
			    }
			    for (var j = 0; j < targetAnchors.length; j++) {
			        var targetUUID = toId + targetAnchors[j];
			        instance.addEndpoint("flowchart" + toId, targetEndpoint, { anchor: targetAnchors[j], uuid: targetUUID });
			    }
			};
			
			// suspend drawing and initialise.
			instance.batch(function () {
		    	var $all_nodes = $('#logic-topo > div');
		    	instance.bind("connection", function (connInfo, originalEvent) {
		            init(connInfo.connection);
		        });
			
			    // make all the window divs draggable
			    instance.draggable(jsPlumb.getSelector(".flowchart-demo .window"), { grid: [20, 20] });

				$all_nodes.each(function(index,obj){
					var parent_no = $(obj).attr('data-no');
					var child = JSON.parse($(obj).attr('data-child'));
					for(var i = 0; i < child.length; i ++ ){
						var vmindex = $('#logic-topo > div[data-no="' + child[i] + '"]').attr('data-vmindex');
						if(!vmindex || vmindex < horizon.logic_topo.vm_count_per_row){
				    		_addEndpoints(parent_no, ["BottomCenter"], []);
							_addEndpoints(child[i], [], ["TopCenter"]);
							instance.connect({uuids: [parent_no + "BottomCenter", child[i] + "TopCenter"], editable: true});
						}
					}
				});
			});
			
			jsPlumb.fire("jsPlumbDemoLoaded", instance);
			
		});
	},
	partition_vm_rows: function(){
		var $all = $('#logic-topo > div[data-type="host"],#logic-topo > div[data-type="computer"]');
		$all.each(function(index,obj){
			var child_nos = JSON.parse($(obj).attr('data-child'));
			if(child_nos.length > 0){
				var vm_0_no = child_nos[0];
				for(var i = 0; i < child_nos.length; i ++ ){
					var row_no = Math.floor(i / horizon.logic_topo.vm_count_per_row);
					$('#logic-topo > div[data-no="' + child_nos[i] + '"]').attr('data-vm0no',vm_0_no);
					$('#logic-topo > div[data-no="' + child_nos[i] + '"]').attr('data-vmindex',i);
				}
			}
		});
	},
	init: function(){
		horizon.logic_topo.partition_vm_rows();
	
		var canvas_height = horizon.logic_topo.get_canvas_height();
		var $canvas_div = $('#logic-topo');
		$canvas_div.css('height',canvas_height);
		
		for(var level = horizon.logic_topo.row_height.length - 1; level >= 0; level -- ){
			var $level_nodes = horizon.logic_topo.get_level_nodes(level);
			$level_nodes.each(function(index, obj){
				var top = horizon.logic_topo.get_top(level,index,obj);
				var left = horizon.logic_topo.get_left(level,index,obj);
				$(obj).css('top',top);
				$(obj).css('left',left);
			});
		}
		
		var canvas_width = horizon.logic_topo.get_canvas_width();
		$canvas_div.css('width',canvas_width);
		
		horizon.logic_topo.connect_line();
		
		$canvas_div.show();
	},
};
