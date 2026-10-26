extends "res://baseline.gd"

var variant := "A"
var variant_label: Label
var lighting_report := {"changed_property": "Sprite3D.shaded", "captures": []}

func _ready() -> void:
	super._ready()
	var layer := CanvasLayer.new()
	add_child(layer)
	variant_label = Label.new()
	variant_label.position = Vector2(28, 128)
	variant_label.add_theme_font_size_override("font_size", 23)
	variant_label.add_theme_color_override("font_color", Color("62492f"))
	layer.add_child(variant_label)
	_set_variant("A")
	if OS.get_cmdline_user_args().has("--lighting-capture"):
		_capture_lighting.call_deferred()

func _set_variant(value: String) -> void:
	variant = value
	sprite.shaded = value == "B"
	variant_label.text = ("A 原版：圖片自身明暗" if value == "A" else "B 本階段：接受房間燈光") + "　[A / B 切換]"

func _unhandled_input(event: InputEvent) -> void:
	super._unhandled_input(event)
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_A:
			_set_variant("A")
		elif event.keycode == KEY_B:
			_set_variant("B")

func _capture_lighting() -> void:
	# Keep every UI pixel identical in the raw ablation frames.
	variant_label.hide()
	for close in [true, false]:
		_set_test("rug", close)
		for value in ["A", "B"]:
			_set_variant(value)
			var file_name: String = ("close-" if close else "overview-") + value
			await _save_capture(file_name)
			lighting_report.captures.append({
				"file": file_name + ".png", "shaded": sprite.shaded,
				"position": [actor.position.x, actor.position.y, actor.position.z],
				"camera_size": cam.size, "pixel_size": sprite.pixel_size,
				"offset": [sprite.offset.x, sprite.offset.y],
				"shadow_visible": ground_shadow.visible,
				"alpha_cut": sprite.alpha_cut, "no_depth_test": sprite.no_depth_test,
				"texture": sprite.texture.resource_path,
			})
	FileAccess.open("res://../lighting-check.json", FileAccess.WRITE).store_string(JSON.stringify(lighting_report, "\t"))
	get_tree().quit()
