extends "res://baseline.gd"

const CELL := 0.075
const SPEED := 0.6
var grid := AStarGrid2D.new()
var origin := Vector2.ZERO
var safe_floor := Rect2()
var radius := 0.0
var route: Array[Vector3] = []
var ready_to_move := false
var destination := Vector3.ZERO
var marker: MeshInstance3D
var pending_click := Vector2(-1, -1)
var travel := 0.0
var testing := false

func _ready() -> void:
	super._ready()
	_set_test("rug", false)
	shot_label.text = "貓咪房間 · 自由移動"
	caption.text = "點地板前往 · 右鍵停止 · 滾輪縮放"
	for node in find_children("*", "Label", true, false):
		if node is Label and node.text.begins_with("1 全景"):
			node.text = "單張趴姿移動測試 · 尚未加入走路動畫　｜　R 回到地毯"
	for mesh in meshes.values():
		var body := StaticBody3D.new()
		body.collision_layer = 1 if mesh.name in ["RoomFloor", "RoomRug"] else 2
		body.collision_mask = 0
		mesh.add_child(body)
		var shape := CollisionShape3D.new()
		shape.shape = mesh.mesh.create_trimesh_shape()
		body.add_child(shape)
	marker = MeshInstance3D.new()
	var ring := TorusMesh.new()
	ring.inner_radius = 0.065
	ring.outer_radius = 0.082
	marker.mesh = ring
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color("f8e6a0")
	marker.material_override = material
	marker.scale.y = 0.1
	marker.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(marker)
	marker.hide()
	_initialize_navigation.call_deferred()

func _vertical_hit(point: Vector3, mask: int) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(Vector3(point.x, 10, point.z), Vector3(point.x, -10, point.z), mask)
	return get_world_3d().direct_space_state.intersect_ray(query)

func _supported(point: Vector3) -> bool:
	if not safe_floor.has_point(Vector2(point.x, point.z)):
		return false
	for i in 17:
		var offset := Vector3.ZERO if i == 16 else Vector3(cos(i * TAU / 16), 0, sin(i * TAU / 16)) * radius
		if not _vertical_hit(point + offset, 2).is_empty():
			return false
	return not _vertical_hit(point, 1).is_empty()

func _initialize_navigation() -> void:
	await get_tree().physics_frame
	await get_tree().physics_frame
	var bounds := _world_aabb(meshes.RoomFloor)
	radius = float(profile.visual_width_world) * 0.5
	safe_floor = Rect2(Vector2(bounds.position.x, bounds.position.z), Vector2(bounds.size.x, bounds.size.z)).grow(-radius)
	origin = safe_floor.position
	grid.region = Rect2i(0, 0, int(safe_floor.size.x / CELL) + 1, int(safe_floor.size.y / CELL) + 1)
	grid.cell_size = Vector2(CELL, CELL)
	grid.offset = origin
	grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	grid.update()
	for y in grid.region.size.y:
		for x in grid.region.size.x:
			var p := grid.get_point_position(Vector2i(x, y))
			grid.set_point_solid(Vector2i(x, y), not _supported(Vector3(p.x, 0, p.y)))
	ready_to_move = true
	_snap_start()
	if OS.get_cmdline_user_args().has("--movement-check"):
		testing = true
		_run_checks.call_deferred()

func _cell(point: Vector3) -> Vector2i:
	return Vector2i(((Vector2(point.x, point.z) - origin) / CELL).round())

func _snap_start() -> void:
	var closest := Vector3.ZERO
	var distance := INF
	for y in grid.region.size.y:
		for x in grid.region.size.x:
			var id := Vector2i(x, y)
			if grid.is_point_solid(id): continue
			var p := grid.get_point_position(id)
			var v := Vector3(p.x, actor.position.y, p.y)
			if v.distance_squared_to(actor.position) < distance:
				distance = v.distance_squared_to(actor.position)
				closest = v
	assert(is_finite(distance), "No walkable floor")
	actor.position = closest
	actor.position.y = _vertical_hit(closest, 1).position.y + 0.003

func _go_to(point: Vector3) -> bool:
	if not ready_to_move or not _supported(point): return false
	var end := _cell(point)
	var start := _cell(actor.position)
	if not grid.is_in_boundsv(end) or grid.is_point_solid(end): return false
	var ids := grid.get_id_path(start, end)
	if ids.is_empty(): return false
	var planned: Array[Vector3] = []
	for id in ids:
		var p := grid.get_point_position(id)
		planned.append(Vector3(p.x, 0, p.y))
	route = planned
	destination = route.back()
	destination.y = _vertical_hit(destination, 1).position.y + 0.003
	marker.position = destination + Vector3(0, 0.007, 0)
	marker.show()
	return true

func _click(screen: Vector2) -> bool:
	var from := cam.project_ray_origin(screen)
	var direction := cam.project_ray_normal(screen)
	var hit := get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(from, from + direction * 60, 3))
	if hit.is_empty() or hit.collider.collision_layer != 1: return false
	return _go_to(hit.position)

func _physics_process(delta: float) -> void:
	if not ready_to_move: return
	if pending_click.x >= 0:
		if not _click(pending_click): caption.text = "這裡不能前往，請點空的地板"
		pending_click = Vector2(-1, -1)
	if route.is_empty(): return
	var target := route[0]
	target.y = actor.position.y
	var next := actor.position.move_toward(target, SPEED * delta)
	if not _supported(next):
		route.clear()
		marker.hide()
		caption.text = "前方無法通行，已停止"
		return
	var hit := _vertical_hit(next, 1)
	travel += Vector2(next.x - actor.position.x, next.z - actor.position.z).length()
	next.y = hit.position.y + 0.003
	actor.position = next
	caption.text = "前往目標中 · 再點地板可更換目標"
	if Vector2(next.x - target.x, next.z - target.z).length() < 0.001:
		route.pop_front()
		if route.is_empty():
			marker.hide()
			caption.text = "已抵達 · 點地板繼續移動"

func _unhandled_input(event: InputEvent) -> void:
	if testing: return
	if event is InputEventMouseButton and event.pressed:
		match event.button_index:
			MOUSE_BUTTON_LEFT: pending_click = event.position
			MOUSE_BUTTON_RIGHT:
				route.clear()
				marker.hide()
				caption.text = "已停止 · 點地板繼續移動"
			MOUSE_BUTTON_WHEEL_UP: cam.size = clampf(cam.size / 1.1, 1.2, 7)
			MOUSE_BUTTON_WHEEL_DOWN: cam.size = clampf(cam.size * 1.1, 1.2, 7)
	if event is InputEventKey and event.pressed and event.keycode == KEY_R and ready_to_move:
		route.clear()
		marker.hide()
		actor.position = positions.rug
		_snap_start()

func _run_checks() -> void:
	var initial := actor.position
	await _save_capture("01-start")
	var reachable: Array[Vector3] = []
	for y in grid.region.size.y:
		for x in grid.region.size.x:
			var id := Vector2i(x, y)
			if grid.is_point_solid(id): continue
			if grid.get_id_path(_cell(initial), id).is_empty(): continue
			var p := grid.get_point_position(id)
			reachable.append(Vector3(p.x, 0, p.y))
	reachable.sort_custom(func(a: Vector3, b: Vector3): return a.distance_squared_to(initial) > b.distance_squared_to(initial))
	assert(not reachable.is_empty())
	var goal := reachable[0]
	goal.y = _vertical_hit(goal, 1).position.y
	assert(_click(cam.unproject_position(goal)), "Actual projected floor click rejected")
	var frames := 0
	var height_error := 0.0
	while not route.is_empty() and frames < 1800:
		await get_tree().physics_frame
		frames += 1
		height_error = maxf(height_error, absf(actor.position.y - (_vertical_hit(actor.position, 1).position.y + 0.003)))
		assert(_supported(actor.position), "Actor crossed blocked area")
		if frames == 80: await _save_capture("02-moving")
	assert(actor.position.distance_to(destination) < 0.005, "Did not arrive")
	await _save_capture("03-arrived")
	assert(not _go_to(Vector3(100, 0, 100)), "Out of bounds accepted")
	assert(not _go_to(_world_aabb(meshes.RoomBed).get_center()), "Bed accepted")
	assert(_go_to(initial))
	await get_tree().physics_frame
	assert(_go_to(actor.position), "Midroute retarget failed")
	route.clear()
	var stopped := actor.position
	for i in 5: await get_tree().physics_frame
	assert(actor.position == stopped)
	var result := {"passed": true, "reachable_cells": reachable.size(), "frames_to_arrive": frames, "distance_traveled": travel, "max_height_error": height_error, "projected_click": true, "reject_bed_and_outside": true, "retarget_and_stop": true, "radius": radius, "cell_size": CELL, "animation": "static lying sprite, no walking frames", "scope": "one fixed room and cat.png prototype"}
	FileAccess.open("res://../movement-check.json", FileAccess.WRITE).store_string(JSON.stringify(result, "\t"))
	get_tree().quit()
