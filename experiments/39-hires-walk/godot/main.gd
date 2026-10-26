extends "res://movement.gd"

var animation: Dictionary
var frame_textures: Array = []
var heading := PI / 4
var gait := 0.0
var move_speed := 0.0
var follow_camera := false
var demo := false
var demo_wait := 0.0
var demo_index := 0
var demo_elapsed := 0.0
var seen_frames := {}
var seen_directions := {}
var max_step := 0.0
var previous_direction := 1
var max_heading_step := 0.0
var demo_started := false

func _ready() -> void:
	super._ready()
	animation = JSON.parse_string(FileAccess.get_file_as_string("res://animation.json"))
	for direction in animation.directions:
		var frames: Array = []
		var source: Texture2D = load(direction.texture)
		for info in direction.frames:
			var texture := AtlasTexture.new()
			texture.atlas = source
			texture.region = Rect2(info.region[0], info.region[1], info.region[2], info.region[3])
			texture.filter_clip = true
			frames.append(texture)
		frame_textures.append(frames)
	actor.name = "Walking2DCat"
	shot_label.text = "貓咪房間 · 八方向走路"
	caption.text = "點地板走過去 · 右鍵停下 · 2 跟隨近景"
	for node in find_children("*", "Label", true, false):
		if node is Label and node.text.begins_with("單張趴姿"):
			node.text = "左鍵前往　右鍵停止　1 全景　2 近景　D 自動走動　R 回地毯"
	_show_pose(false)
	if OS.get_cmdline_user_args().has("--autowalk"):
		demo = true
	if OS.get_cmdline_user_args().has("--walk-demo"):
		demo = true
		testing = true

func _show_pose(walking: bool) -> void:
	var direction := posmod(int(round(heading / (PI / 4))), 8)
	var frame := int(floor(gait * 4.0)) % 4 if walking else (0 if fposmod(gait, 1.0) < 0.5 else 2)
	var info: Dictionary = animation.directions[direction].frames[frame]
	sprite.texture = frame_textures[direction][frame]
	sprite.pixel_size = animation.directions[direction].pixel_size
	sprite.offset = Vector2(info.region[2] * 0.5 - info.pivot[0], info.pivot[1] - info.region[3] * 0.5)
	seen_frames[str(frame)] = true
	seen_directions[str(direction)] = true
	previous_direction = direction

func _clear_segment(a: Vector3, b: Vector3) -> bool:
	var count := maxi(1, int(ceil(a.distance_to(b) / (CELL * 0.4))))
	for i in range(1, count + 1):
		if not _supported(a.lerp(b, float(i) / count)): return false
	return true

func _go_to(point: Vector3) -> bool:
	if not super._go_to(point): return false
	# Remove grid zigzags only where the entire padded segment remains clear.
	var simplified: Array[Vector3] = []
	var anchor := actor.position
	while not route.is_empty():
		var furthest := 0
		for i in range(route.size() - 1, -1, -1):
			if _clear_segment(anchor, route[i]):
				furthest = i
				break
		anchor = route[furthest]
		simplified.append(anchor)
		route = route.slice(furthest + 1)
	route = simplified
	return true

func _physics_process(delta: float) -> void:
	if not ready_to_move or animation.is_empty(): return
	if pending_click.x >= 0:
		demo = false
		if not _click(pending_click): caption.text = "這裡不能前往，請點空的地板"
		pending_click = Vector2(-1, -1)
	if demo:
		demo_elapsed += delta
		if route.is_empty():
			demo_wait += delta
			if demo_wait > 0.7:
				demo_wait = 0
				_next_demo_goal()
	var distance_moved := 0.0
	var turn_amount := 0.0
	if not route.is_empty():
		var target := route[0]
		target.y = actor.position.y
		var remaining := actor.position.distance_to(target)
		var direction := (target - actor.position).normalized()
		var screen_direction := Vector2(direction.dot(cam.global_basis.x), -direction.dot(cam.global_basis.y))
		var desired := screen_direction.angle()
		var old_heading := heading
		heading = rotate_toward(heading, desired, 4.0 * delta)
		turn_amount = absf(angle_difference(old_heading, heading))
		max_heading_step = maxf(max_heading_step, turn_amount)
		var error := absf(angle_difference(heading, desired))
		var target_speed := SPEED * clampf(cos(error), 0, 1)
		if route.size() == 1:
			target_speed = minf(target_speed, sqrt(2.0 * 1.8 * remaining))
		move_speed = move_toward(move_speed, target_speed, 1.8 * delta)
		var step := minf(remaining, move_speed * delta)
		# Avoid sideways skating while rotating sharply.
		if error > PI / 3: step = 0
		var next := actor.position + direction * step
		if not _supported(next):
			route.clear()
			move_speed = 0
			marker.hide()
		else:
			next.y = _vertical_hit(next, 1).position.y + 0.003
			actor.position = next
			distance_moved = step
			travel += step
			max_step = maxf(max_step, step)
			if remaining - step < 0.001:
				route.pop_front()
				if route.is_empty(): marker.hide()
		caption.text = "走路中 · 點地板換目標 · 右鍵停下"
	else:
		move_speed = 0
		caption.text = "已停下 · 點地板繼續走　｜　2 近景"
	gait += distance_moved / float(animation.cycle_distance)
	if distance_moved < 0.0001 and not route.is_empty(): gait += turn_amount * 0.12
	_show_pose(distance_moved > 0.0001 or turn_amount > 0.001)
	if follow_camera:
		var target := actor.position + Vector3(0, 0.28, 0)
		cam.look_at_from_position(target + VIEW_DIR.normalized() * 15, target)
	if testing and demo_elapsed > 22:
		FileAccess.open("res://../walk-check.json", FileAccess.WRITE).store_string(JSON.stringify({"distance": travel, "frames_seen": seen_frames.keys(), "directions_seen": seen_directions.keys(), "max_step": max_step, "max_heading_step": max_heading_step, "elapsed": demo_elapsed, "source_frame_size": 627, "animation": "4 distinct walk poses per direction, phase driven by distance", "limitations": "4-frame cadence; rear-left head angle; no dedicated idle pose; AI patch drift"}, "\t"))
		get_tree().quit()

func _next_demo_goal() -> void:
	var desired_angle := demo_index * PI * 0.75
	demo_index += 1
	var best := actor.position
	var score := -INF
	for y in grid.region.size.y:
		for x in grid.region.size.x:
			var id := Vector2i(x, y)
			if grid.is_point_solid(id): continue
			var p := grid.get_point_position(id)
			var candidate := Vector3(p.x, actor.position.y, p.y)
			var offset := candidate - actor.position
			if offset.length() < 0.45: continue
			var screen := Vector2(offset.dot(cam.global_basis.x), -offset.dot(cam.global_basis.y)).normalized()
			var value := screen.dot(Vector2.from_angle(desired_angle)) * 3 + minf(offset.length(), 1.5)
			if value > score and not grid.get_id_path(_cell(actor.position), id).is_empty():
				score = value
				best = candidate
	_go_to(best)

func _unhandled_input(event: InputEvent) -> void:
	super._unhandled_input(event)
	if testing: return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
		demo = false
		move_speed = 0
	if event is InputEventKey and event.pressed:
		match event.keycode:
			KEY_D: demo = not demo
			KEY_R:
				demo = false
				move_speed = 0
			KEY_1:
				follow_camera = false
				cam.size = _overview_size
				cam.look_at_from_position(_overview_focus + VIEW_DIR.normalized() * 15, _overview_focus)
			KEY_2:
				follow_camera = true
				cam.size = 1.8
