extends "res://room_base.gd"

var actor: Node3D
var sprite: Sprite3D
var ground_shadow: MeshInstance3D
var profile: Dictionary
var shot_label: Label
var caption: Label
var positions: Dictionary = {}
var meshes: Dictionary = {}
var zoomed := true
var current_test := "rug"
var report := {}
var auto_capture := false
var bed_original_position: Vector3
var bed_test_position: Vector3

func _ready() -> void:
	profile = JSON.parse_string(FileAccess.get_file_as_string("res://profile.json"))
	auto_capture = OS.get_cmdline_user_args().has("--capture")
	get_viewport().msaa_3d = Viewport.MSAA_4X
	_setup_environment()
	room = load("res://models/room_v7.glb").instantiate()
	add_child(room)
	_apply_room_materials()
	_collect_frame_points()
	for mesh in room.find_children("*", "MeshInstance3D", true, false):
		meshes[mesh.name] = mesh
	cam = Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.keep_aspect = Camera3D.KEEP_HEIGHT
	cam.near = 0.05
	cam.far = 60.0
	add_child(cam)
	cam.look_at_from_position(_overview_focus + VIEW_DIR.normalized() * 15.0, _overview_focus)
	cam.make_current()
	_fit_overview(Rect2(32, 90, 1216, 794), Vector2(1280, 960))
	_create_cat()
	_make_test_positions()
	_build_interface()
	_set_test("rug", true)
	if OS.get_cmdline_user_args().has("--edge-check"):
		_capture_edge_suite.call_deferred()
	elif auto_capture:
		_capture_suite.call_deferred()

func _create_cat() -> void:
	actor = Node3D.new()
	actor.name = "Static2DCat"
	add_child(actor)
	sprite = Sprite3D.new()
	sprite.name = "CatCutout"
	sprite.texture = load(profile.texture)
	var dimensions := sprite.texture.get_size()
	var box: Array = profile.source_alpha_bbox
	sprite.pixel_size = float(profile.visual_width_world) / float(box[2] - box[0])
	var pivot := Vector2(profile.pivot_normalized[0], profile.pivot_normalized[1]) * dimensions
	sprite.offset = Vector2(dimensions.x * 0.5 - pivot.x, pivot.y - dimensions.y * 0.5)
	sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
	sprite.alpha_scissor_threshold = profile.alpha_scissor_threshold
	sprite.shaded = false
	sprite.no_depth_test = false
	sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	sprite.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	actor.add_child(sprite)
	ground_shadow = MeshInstance3D.new()
	ground_shadow.name = "IndependentGroundShadow"
	var plane := PlaneMesh.new()
	plane.size = Vector2(profile.shadow_size_world[0], profile.shadow_size_world[1])
	ground_shadow.mesh = plane
	ground_shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var shader := Shader.new()
	shader.code = """shader_type spatial;
render_mode unshaded, blend_mix, cull_disabled, depth_draw_never;
uniform float opacity = 0.23;
void fragment() {
  float radius = length((UV - vec2(0.5)) * 2.0);
  ALBEDO = vec3(0.16, 0.105, 0.065);
  ALPHA = (1.0 - smoothstep(0.25, 1.0, radius)) * opacity;
}
"""
	var material := ShaderMaterial.new()
	material.shader = shader
	material.set_shader_parameter("opacity", profile.shadow_opacity)
	ground_shadow.material_override = material
	actor.add_child(ground_shadow)
	ground_shadow.position.y = 0.001
	# One shared shadow direction, aligned with camera right on the floor.
	ground_shadow.rotation.y = atan2(-cam.global_basis.x.z, cam.global_basis.x.x)

func _world_aabb(mesh: MeshInstance3D) -> AABB:
	return mesh.global_transform * mesh.get_aabb()

func _floor_height(point: Vector3) -> float:
	var floor_y := -INF
	for key in ["RoomFloor", "RoomRug"]:
		var bounds := _world_aabb(meshes[key])
		if point.x >= bounds.position.x and point.x <= bounds.end.x and point.z >= bounds.position.z and point.z <= bounds.end.z:
			floor_y = maxf(floor_y, bounds.end.y)
	assert(is_finite(floor_y), "Test point outside supported floor/rug")
	return floor_y

func _make_test_positions() -> void:
	var p: Array = profile.normal_position
	positions.rug = Vector3(p[0], p[1], p[2])
	bed_original_position = meshes.RoomBed.position
	# A shared test layout isolates bed occlusion from the nearby wall and seat.
	bed_test_position = meshes.RoomRug.position
	meshes.RoomBed.position = bed_test_position
	var bed := _world_aabb(meshes.RoomBed)
	var toward := Vector3(VIEW_DIR.x, 0, VIEW_DIR.z).normalized()
	var right := Vector3(cam.global_basis.x.x, 0, cam.global_basis.x.z).normalized()
	var radius := absf(toward.x) * bed.size.x * 0.5 + absf(toward.z) * bed.size.z * 0.5
	var side_radius := absf(right.x) * bed.size.x * 0.5 + absf(right.z) * bed.size.z * 0.5
	positions.bed_front = bed.get_center() + toward * (radius + 0.12)
	positions.bed_behind = bed.get_center() - toward * (radius + 0.06)
	positions.bed_edge = bed.get_center() + toward * 0.02 - right * (side_radius + 0.05)
	for key in positions:
		var point: Vector3 = positions[key]
		point.y = _floor_height(point) + 0.003
		positions[key] = point
	report = {
		"engine": Engine.get_version_info(),
		"camera_projection": "orthographic", "camera_view_dir": [-1.05, 1.05, 1.40],
		"cat_mesh_present": false, "cat_skeleton_present": false,
		"sprite_alpha_cut": sprite.alpha_cut, "sprite_shaded": sprite.shaded,
		"sprite_pixel_size": sprite.pixel_size, "pivot_source": profile.pivot_provenance,
		"ground_shadow_separate": true, "test_positions": {}, "captures": [],
		"scope": "Static pose only; no walking, navigation, collision or new-cat automation acceptance."
	}
	for key in positions:
		var point: Vector3 = positions[key]
		report.test_positions[key] = [point.x, point.y, point.z]
	report.bed_layout = {"original": [bed_original_position.x, bed_original_position.y, bed_original_position.z], "isolated_test": [bed_test_position.x, bed_test_position.y, bed_test_position.z], "reason": "Prevent wall/window-seat occlusion confounding the bed test."}
	meshes.RoomBed.position = bed_original_position

func _build_interface() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(1.0, 0.974, 0.91, 0.94)
	style.set_corner_radius_all(16)
	style.content_margin_left = 20
	style.content_margin_right = 20
	style.content_margin_top = 12
	style.content_margin_bottom = 12
	panel.add_theme_stylebox_override("panel", style)
	panel.position = Vector2(26, 22)
	layer.add_child(panel)
	var stack := VBoxContainer.new()
	panel.add_child(stack)
	shot_label = Label.new()
	shot_label.add_theme_color_override("font_color", Color("62492f"))
	shot_label.add_theme_font_size_override("font_size", 24)
	stack.add_child(shot_label)
	caption = Label.new()
	caption.text = "cat.png 原型 · 靜態趴姿 · Godot 實際畫面"
	caption.add_theme_color_override("font_color", Color("826746"))
	caption.add_theme_font_size_override("font_size", 16)
	stack.add_child(caption)
	var footer := Label.new()
	footer.text = "1 全景　2 近景　3 窩前　4 窩後　5 窩旁　·　滑鼠滾輪縮放"
	footer.position = Vector2(30, 922)
	footer.add_theme_color_override("font_color", Color("62492f"))
	footer.add_theme_font_size_override("font_size", 17)
	layer.add_child(footer)

func _set_test(key: String, close: bool) -> void:
	current_test = key
	zoomed = close
	actor.position = positions[key]
	sprite.no_depth_test = false
	ground_shadow.visible = true
	meshes.RoomBed.position = bed_original_position if key == "rug" else bed_test_position
	caption.text = "cat.png 原型 · 靜態趴姿 · Godot 實際畫面" if key == "rug" else "遮擋測試 · 貓窩暫移開闊處 · 同一張 2D 圖"
	var target := actor.position + Vector3(0, 0.17, 0) if close else _overview_focus
	if close and key != "rug":
		target = target.lerp(_world_aabb(meshes.RoomBed).get_center(), 0.35)
	cam.size = float(profile.close_camera_size) if close else _overview_size
	cam.look_at_from_position(target + VIEW_DIR.normalized() * 15.0, target)
	var titles := {"rug": "近景", "bed_front": "家具前方", "bed_behind": "家具後方", "bed_edge": "家具邊緣"}
	shot_label.text = "2D 貓咪原型 / " + (titles[key] if close else "房間全景")

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		match event.keycode:
			KEY_1: _set_test("rug", false)
			KEY_2: _set_test("rug", true)
			KEY_3: _set_test("bed_front", true)
			KEY_4: _set_test("bed_behind", true)
			KEY_5: _set_test("bed_edge", true)
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			cam.size = clampf(cam.size / 1.1, 0.9, 7.0)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			cam.size = clampf(cam.size * 1.1, 0.9, 7.0)

func _save_capture(name: String) -> void:
	for frame in 12:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var path := ProjectSettings.globalize_path("res://../evidence/" + name + ".png")
	var error := get_viewport().get_texture().get_image().save_png(path)
	assert(error == OK, "Screenshot write failed")
	report.captures.append({"name": name, "no_depth_test": sprite.no_depth_test, "ground_shadow_visible": ground_shadow.visible, "camera_size": cam.size, "test_point": current_test})
	print("CAPTURE ", path)

func _capture_suite() -> void:
	_set_test("rug", false)
	await _save_capture("01-overview")
	_set_test("rug", true)
	await _save_capture("02-close")
	ground_shadow.visible = false
	await _save_capture("02b-close-shadow-off-diagnostic")
	ground_shadow.visible = true
	_set_test("bed_front", true)
	await _save_capture("03-bed-front")
	_set_test("bed_behind", true)
	await _save_capture("04-bed-behind-depth-on")
	sprite.no_depth_test = true
	# Same camera and caption for an isolated depth-test comparison.
	await _save_capture("05-bed-behind-depth-off-diagnostic")
	sprite.no_depth_test = false
	_set_test("bed_edge", true)
	await _save_capture("06-bed-edge")
	FileAccess.open("res://../engine-check.json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	get_tree().quit()

func _capture_edge_suite() -> void:
	_set_test("bed_edge", true)
	await _save_capture("07-bed-edge-depth-on")
	sprite.no_depth_test = true
	await _save_capture("08-bed-edge-depth-off-diagnostic")
	FileAccess.open("res://../edge-check.json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	get_tree().quit()
