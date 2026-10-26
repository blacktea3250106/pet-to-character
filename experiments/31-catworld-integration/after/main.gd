extends Node3D
## Rectangular low-poly window room. Overview fits every corner at any aspect ratio.
## Explicit zoom follows the cat; -- --shot /path.png [--edit] [--portrait] [--clean].
const CatScript := preload("res://cat.gd")
const TripoCatScript := preload("res://tripo_cat.gd")
const PersonalizedCatScript := preload("res://personalized_cat.gd")
const DecorationScript := preload("res://decoration.gd")
const VIEW_DIR := Vector3(-1.05, 1.05, 1.40)
const ROOM_BOUNDS := AABB(Vector3(-0.08, -0.10, -2.85), Vector3(3.80, 2.06, 2.89))
const MAX_ZOOM := 4.5
var cam: Camera3D
var cat: Node3D
var tripo_cat: Node3D
var personalized_cat: Node3D
var active_cat: Node3D
var _cat_button: Button
var room: Node3D
var decoration: Node
var zoom := 1.0
var touches := {}
var _overview_size := 5.0
var _overview_focus := Vector3(1.8, 0.7, -1.25)
var _hud: Control
var _name_panel: PanelContainer
var _edit_button: Button
var _overview_button: Button
var _edit_panel: PanelContainer
var _hint: Label
var _selection_label: Label
var _clean := false
var _frame_points: Array[Vector3] = []

func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	_clean = args.has("--clean")
	if args.has("--portrait"):
		get_window().size = Vector2i(720, 1280)
		get_window().content_scale_size = Vector2i(720, 1280)
	get_viewport().msaa_3d = Viewport.MSAA_4X
	_setup_environment()
	room = load("res://models/room_v7.glb").instantiate()
	room.name = "WindowRoom"
	add_child(room)
	_apply_room_materials()
	_collect_frame_points()
	cat = CatScript.new()
	cat.name = "Cat"
	cat.position = Vector3(1.30, 0.0, -0.90)
	cat.rotation.y = 3.0
	cat.scale = Vector3.ONE * 1.3
	cat.bounds = Rect2(0.25, -1.92, 3.05, 1.66)
	cat.spots.assign([
		{"pos": Vector2(1.30, -0.90), "rest": [1, 8, 1]},
		{"pos": Vector2(0.65, -1.65), "rest": [4, 5, 1]},
		{"pos": Vector2(2.10, -0.60), "rest": [2, 6, 2]},
		{"pos": Vector2(1.75, -1.72), "rest": [3, 6, 1]},
	])
	add_child(cat)
	cat.anim.play("lie", 0.0)
	cat.anim.advance(0.0)
	cat.wait = 18.0
	tripo_cat = TripoCatScript.new()
	tripo_cat.name = "TripoCat"
	tripo_cat.position = Vector3(2.45, 0.0, -0.55)
	tripo_cat.rotation.y = PI
	tripo_cat.scale = Vector3.ONE * 1.3
	add_child(tripo_cat)
	personalized_cat = PersonalizedCatScript.new()
	personalized_cat.name = "PersonalizedCat"
	personalized_cat.position = Vector3(1.60, 0.0, -0.48)
	personalized_cat.rotation.y = 3.0
	add_child(personalized_cat)
	active_cat = personalized_cat
	cam = Camera3D.new()
	cam.name = "RoomCamera"
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.keep_aspect = Camera3D.KEEP_HEIGHT
	cam.near = 0.05
	cam.far = 60.0
	add_child(cam)
	cam.look_at_from_position(_overview_focus + VIEW_DIR.normalized() * 15.0, _overview_focus)
	cam.make_current()
	decoration = DecorationScript.new()
	decoration.name = "Decoration"
	add_child(decoration)
	var layout_arg := args.find("--layout-file")
	if layout_arg >= 0 and layout_arg + 1 < args.size():
		decoration.layout_path = args[layout_arg + 1]
	decoration.setup(cam, room, cat)
	_build_hud()
	decoration.editing_changed.connect(_on_editing_changed)
	decoration.selection_changed.connect(_on_selection_changed)
	decoration.save_failed.connect(_on_save_failed, CONNECT_DEFERRED)
	get_viewport().size_changed.connect(_update_layout)
	_update_layout()
	var z := args.find("--zoom")
	if z >= 0 and z + 1 < args.size():
		zoom = clampf(float(args[z + 1]), 1.0, MAX_ZOOM)
	if args.has("--edit"):
		decoration.toggle_editing()
	_place_camera(1.0)
	var i := args.find("--shot")
	if i >= 0 and i + 1 < args.size():
		_screenshot(args[i + 1])

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

func _build_hud() -> void:
	var layer := CanvasLayer.new()
	layer.name = "RoomInterface"
	layer.layer = 10
	add_child(layer)
	_hud = Control.new()
	_hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hud.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var theme := Theme.new()
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["PingFang TC", "Noto Sans CJK TC", "sans-serif"])
	theme.default_font = font
	theme.default_font_size = 22
	theme.set_color("font_color", "Label", Color("594331"))
	theme.set_color("font_color", "Button", Color("594331"))
	theme.set_color("font_hover_color", "Button", Color("3f5537"))
	theme.set_color("font_pressed_color", "Button", Color("3f5537"))
	theme.set_stylebox("normal", "Button", _panel_style(Color("fff6e7")))
	theme.set_stylebox("hover", "Button", _panel_style(Color("f2ecd7")))
	theme.set_stylebox("pressed", "Button", _panel_style(Color("dce4c5")))
	theme.set_stylebox("focus", "Button", _panel_style(Color(0, 0, 0, 0), false))
	_hud.theme = theme
	layer.add_child(_hud)
	_hud.visible = not _clean
	_name_panel = PanelContainer.new()
	_name_panel.add_theme_stylebox_override("panel", _panel_style(Color("fff6e7")))
	_name_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var name_label := Label.new()
	name_label.text = "小花的家"
	name_label.add_theme_font_size_override("font_size", 29)
	_name_panel.add_child(name_label)
	_hud.add_child(_name_panel)
	_edit_button = _button("佈置小窩", func(): decoration.toggle_editing())
	_overview_button = _button("全景", func(): zoom = 1.0)
	_cat_button = _button("目前：你的貓", _cycle_cat)
	_hint = Label.new()
	_hint.text = "點地板叫你的貓過來 · 滾輪或雙指縮放"
	_hint.add_theme_font_size_override("font_size", 17)
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hud.add_child(_hint)
	_edit_panel = PanelContainer.new()
	_edit_panel.add_theme_stylebox_override("panel", _panel_style(Color("fff6e7")))
	_hud.add_child(_edit_panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	_edit_panel.add_child(column)
	_selection_label = Label.new()
	_selection_label.text = "選擇家具，再拖曳到喜歡的位置"
	_selection_label.add_theme_font_size_override("font_size", 17)
	column.add_child(_selection_label)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	column.add_child(row)
	for item in [
		["地毯", func(): decoration.select_item("RoomRug")],
		["貓窩", func(): decoration.select_item("RoomBed")],
		["旋轉", func(): decoration.rotate_selected()],
		["還原", func(): decoration.restore_defaults()],
	]:
		var b := Button.new()
		b.text = item[0]
		b.custom_minimum_size = Vector2(80, 48)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.pressed.connect(item[1])
		row.add_child(b)
	_edit_panel.visible = false

func _button(caption: String, action: Callable) -> Button:
	var b := Button.new()
	b.text = caption
	b.custom_minimum_size = Vector2(92, 48)
	b.pressed.connect(action)
	_hud.add_child(b)
	return b

func _panel_style(color: Color, shadow := true) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = color
	box.corner_radius_top_left = 18
	box.corner_radius_top_right = 18
	box.corner_radius_bottom_left = 18
	box.corner_radius_bottom_right = 18
	box.content_margin_left = 20
	box.content_margin_right = 20
	box.content_margin_top = 11
	box.content_margin_bottom = 11
	if shadow:
		box.shadow_color = Color(0.28, 0.18, 0.08, 0.12)
		box.shadow_size = 7
		box.shadow_offset = Vector2(0, 3)
	return box

func _on_editing_changed(editing: bool) -> void:
	tripo_cat.process_mode = Node.PROCESS_MODE_DISABLED if editing else Node.PROCESS_MODE_INHERIT
	personalized_cat.process_mode = Node.PROCESS_MODE_DISABLED if editing else Node.PROCESS_MODE_INHERIT
	zoom = 1.0
	touches.clear()
	_edit_panel.visible = editing
	_edit_button.text = "完成" if editing else "佈置小窩"
	_hint.visible = not editing
	_update_layout()

func _cycle_cat() -> void:
	var cats := [personalized_cat, cat, tripo_cat]
	active_cat = cats[(cats.find(active_cat) + 1) % cats.size()]
	var caption: String = {personalized_cat: "你的貓", cat: "小花", tripo_cat: "花花"}[active_cat]
	_cat_button.text = "目前：" + caption
	_hint.text = "點地板叫%s過來 · 滾輪或雙指縮放" % caption
	touches.clear()

func _on_selection_changed(item_name: String) -> void:
	if item_name.is_empty():
		_selection_label.text = "選擇家具，再拖曳到喜歡的位置"
		return
	var label := "地毯" if item_name == "RoomRug" else "貓窩"
	_selection_label.text = "拖曳%s · 完成後會自動記住位置" % label

func _on_save_failed(_reason: String) -> void:
	if decoration.is_editing:
		_selection_label.text = "佈置尚未儲存，請稍後再試"
	else:
		_hint.text = "佈置尚未儲存，請稍後再試"
		_hint.show()

func _update_layout() -> void:
	if cam == null:
		return
	var viewport_size := get_viewport().get_visible_rect().size
	var margin := clampf(viewport_size.x * 0.026, 18.0, 32.0)
	_name_panel.position = Vector2(margin, margin)
	_name_panel.size = Vector2(188, 61)
	_cat_button.size = Vector2(188, 48)
	_cat_button.position = Vector2(margin, margin + 71.0)
	_cat_button.visible = not decoration.is_editing
	_edit_button.size = Vector2(152, 54)
	_edit_button.position = Vector2(viewport_size.x - margin - 152.0, margin)
	_overview_button.size = Vector2(92, 48)
	_overview_button.position = Vector2(viewport_size.x - margin - 92.0, viewport_size.y - margin - 48.0)
	_hint.position = Vector2(margin, viewport_size.y - margin - 41.0)
	_hint.size = Vector2(maxf(100.0, viewport_size.x - 2.0 * margin - 112.0), 38.0)
	_edit_panel.position = Vector2(margin, viewport_size.y - margin - 126.0)
	_edit_panel.size = Vector2(viewport_size.x - 2.0 * margin, 126.0)
	_overview_button.visible = not decoration.is_editing
	var top := margin + 135.0 if not _clean else margin
	var bottom := margin + (156.0 if decoration.is_editing else 67.0) if not _clean else margin
	var area := Rect2(Vector2(margin, top), Vector2(viewport_size.x - margin * 2.0, maxf(100, viewport_size.y - top - bottom)))
	_fit_overview(area, viewport_size)
	_place_camera(1.0)

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

func _process(delta: float) -> void:
	if cam:
		_place_camera(minf(1.0, delta * 8.0))

func _place_camera(blend: float) -> void:
	cam.size = lerpf(cam.size, _overview_size / zoom, blend)
	var follow := clampf((zoom - 1.0) / 1.5, 0.0, 1.0)
	var focus := _overview_focus.lerp(active_cat.global_position + Vector3(0, 0.16, 0), follow)
	var current := cam.global_position - VIEW_DIR.normalized() * 15.0
	focus = current.lerp(focus, blend) if blend < 1.0 else focus
	cam.look_at_from_position(focus + VIEW_DIR.normalized() * 15.0, focus, Vector3.UP)

func _zoom_by(factor: float) -> void:
	zoom = clampf(zoom * factor, 1.0, MAX_ZOOM)

func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch and not event.pressed:
		touches.erase(event.index)

func _unhandled_input(event: InputEvent) -> void:
	if decoration != null and decoration.is_editing:
		return
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_zoom_by(1.12); return
		if event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_zoom_by(1.0 / 1.12); return
	if event is InputEventMagnifyGesture:
		_zoom_by(event.factor); return
	if event is InputEventPanGesture:
		_zoom_by(pow(1.04, -event.delta.y)); return
	if event is InputEventKey and event.pressed:
		if event.keycode in [KEY_EQUAL, KEY_PLUS, KEY_KP_ADD]:
			_zoom_by(1.25); return
		if event.keycode in [KEY_MINUS, KEY_KP_SUBTRACT]:
			_zoom_by(1.0 / 1.25); return
		if event.keycode == KEY_HOME:
			zoom = 1.0; return
	if event is InputEventScreenTouch:
		if event.pressed:
			touches[event.index] = event.position
		else:
			touches.erase(event.index)
	if event is InputEventScreenDrag:
		if touches.size() == 2 and touches.has(event.index):
			var other_index: int = touches.keys().filter(func(k): return k != event.index)[0]
			var other: Vector2 = touches[other_index]
			var before := other.distance_to(touches[event.index])
			var after := other.distance_to(event.position)
			if before > 1.0:
				_zoom_by(after / before)
		touches[event.index] = event.position
		return
	var pos: Vector2
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		pos = event.position
	elif event is InputEventScreenTouch and event.pressed and touches.size() == 1:
		pos = event.position
	else:
		return
	var hit: Variant = Plane(Vector3.UP, 0.0).intersects_ray(cam.project_ray_origin(pos), cam.project_ray_normal(pos))
	if hit != null and hit.x >= 0.15 and hit.x <= 3.45 and hit.z >= -2.0 and hit.z <= -0.15:
		active_cat.go_to(hit)

func _screenshot(path: String) -> void:
	# A screenshot launch must not inherit desktop wheel/trackpad gestures.
	set_process_input(false)
	set_process_unhandled_input(false)
	decoration.set_process_input(false)
	decoration.set_process_unhandled_input(false)
	_hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var args := OS.get_cmdline_user_args()
	var p := args.find("--pose")
	cat.wait = 1e9
	cat.anim.play(args[p + 1] if p >= 0 and p + 1 < args.size() else "lie", 0.0)
	cat.anim.advance(0.0)
	for frame in 12:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var err := get_viewport().get_texture().get_image().save_png(path)
	print("Room screenshot: ", path, " -> ", error_string(err))
	if is_equal_approx(zoom, 1.0):
		for vertex in _frame_points:
			var point := cam.unproject_position(vertex)
			assert(get_viewport().get_visible_rect().has_point(point), "Room corner outside viewport")
		print("Room frame validation passed: ", get_viewport().get_visible_rect().size)
	get_tree().quit(0 if err == OK else 1)
