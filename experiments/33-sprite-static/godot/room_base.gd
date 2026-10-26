extends Node3D
# Environment, room materials and camera fitting copied from the read-only source.
const VIEW_DIR := Vector3(-1.05, 1.05, 1.40)
const ROOM_BOUNDS := AABB(Vector3(-0.08, -0.10, -2.85), Vector3(3.80, 2.06, 2.89))
var room: Node3D
var cam: Camera3D
var _frame_points: Array[Vector3] = []
var _overview_size := 5.0
var _overview_focus := Vector3(1.8, 0.7, -1.25)

func _apply_room_materials() -> void:
	# This imported GLB contains linear COLOR_0, but Godot leaves the shared
	# material's vertex-color flag off. Enable it on runtime duplicates.
	var materials := {}
	for mesh in room.find_children("*", "MeshInstance3D", true, false):
		for surface in mesh.mesh.get_surface_count():
			var source: Material = mesh.get_active_material(surface)
			if source is StandardMaterial3D:
				if not materials.has(source):
					var material: StandardMaterial3D = source.duplicate()
					material.vertex_color_use_as_albedo = true
					material.vertex_color_is_srgb = false
					material.roughness = 0.92
					materials[source] = material
				mesh.set_surface_override_material(surface, materials[source])

func _collect_frame_points() -> void:
	# Project the visible geometry rather than the empty top/front corners of an
	# enclosing box. This makes the room larger without ever clipping its edges.
	_frame_points.clear()
	for mesh in room.find_children("*", "MeshInstance3D", true, false):
		for surface in mesh.mesh.get_surface_count():
			var vertices: PackedVector3Array = mesh.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			for vertex in vertices:
				_frame_points.append(mesh.to_global(vertex))

func _setup_environment() -> void:
	var layer := CanvasLayer.new()
	layer.name = "SoftBackground"
	layer.layer = -10
	add_child(layer)
	var backdrop := ColorRect.new()
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var material := ShaderMaterial.new()
	material.shader = preload("res://shaders/soft_garden.gdshader")
	backdrop.material = material
	layer.add_child(backdrop)
	var env := Environment.new()
	env.background_mode = Environment.BG_CANVAS
	env.background_canvas_max_layer = -1
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(1.0, 0.94, 0.84)
	env.ambient_light_energy = 0.58
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var world := WorldEnvironment.new()
	world.environment = env
	add_child(world)
	var sunlight := DirectionalLight3D.new()
	sunlight.name = "WindowSunlight"
	sunlight.light_color = Color(1.0, 0.91, 0.76)
	sunlight.light_energy = 1.7
	sunlight.shadow_enabled = true
	sunlight.shadow_bias = 0.10
	sunlight.shadow_normal_bias = 0.45
	sunlight.directional_shadow_max_distance = 10.0
	sunlight.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	sunlight.light_angular_distance = 2.0
	add_child(sunlight)
	sunlight.look_at_from_position(Vector3(-1.0, 3.6, -5.0), Vector3(1.7, 0.0, -0.7))
	var fill := DirectionalLight3D.new()
	fill.name = "SoftRoomFill"
	fill.light_color = Color(0.91, 0.94, 1.0)
	fill.light_energy = 0.35
	add_child(fill)
	fill.look_at_from_position(Vector3(-3.0, 4.0, 5.0), Vector3(1.8, 0.3, -1.2))

func _fit_overview(area: Rect2, viewport_size: Vector2) -> void:
	var right := cam.global_basis.x
	var up := cam.global_basis.y
	var min_x := INF
	var max_x := -INF
	var min_y := INF
	var max_y := -INF
	for point in _frame_points:
		min_x = minf(min_x, point.dot(right))
		max_x = maxf(max_x, point.dot(right))
		min_y = minf(min_y, point.dot(up))
		max_y = maxf(max_y, point.dot(up))
	var unit := maxf((max_x - min_x) / area.size.x, (max_y - min_y) / area.size.y) * 1.025
	_overview_size = unit * viewport_size.y
	var center := right * (min_x + max_x) * 0.5 + up * (min_y + max_y) * 0.5
	center += VIEW_DIR.normalized() * ROOM_BOUNDS.get_center().dot(VIEW_DIR.normalized())
	var offset := area.get_center() - viewport_size * 0.5
	_overview_focus = center - right * offset.x * unit + up * offset.y * unit
