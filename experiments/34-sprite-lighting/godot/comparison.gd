extends SceneTree

func _initialize() -> void:
	call_deferred("_build")

func _label(parent: Node, content: String, at: Vector2, font_size: int, color: Color) -> void:
	var label := Label.new()
	label.text = content
	label.position = at
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)

func _build() -> void:
	root.size = Vector2i(1440, 690)
	root.title = "第一階段 — 受光 A/B"
	var panel := ColorRect.new()
	panel.color = Color("f3efe6")
	panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(panel)
	_label(panel, "第一階段｜只改角色受光", Vector2(32, 20), 28, Color("43392e"))
	_label(panel, "同一張 PNG、鏡頭、位置、尺寸與地面陰影；下圖為 Godot 實際截圖的相同區域。", Vector2(32, 62), 18, Color("706456"))
	for i in 2:
		var variant := "A" if i == 0 else "B"
		var x := 32 + i * 704
		_label(panel, "A 原版：圖片自身明暗" if i == 0 else "B 本階段：接受房間燈光", Vector2(x, 112), 22, Color("43392e"))
		var original := Image.load_from_file(ProjectSettings.globalize_path("res://../evidence/close-" + variant + ".png"))
		assert(original != null)
		var texture := AtlasTexture.new()
		texture.atlas = ImageTexture.create_from_image(original)
		# Same display crop on both original screenshots; no pixels are repainted.
		texture.region = Rect2(350, 240, 540, 380)
		var view := TextureRect.new()
		view.texture = texture
		view.position = Vector2(x, 152)
		view.size = Vector2(672, 473)
		view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		view.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		panel.add_child(view)
	_label(panel, "觀察：B 的色溫略暖，整體差別很小；尚不足以消除貼紙感。A 保留為基準。", Vector2(32, 648), 20, Color("43392e"))
	for frame in 12:
		await process_frame
	await RenderingServer.frame_post_draw
	var error := root.get_texture().get_image().save_png(ProjectSettings.globalize_path("res://../evidence/comparison.png"))
	assert(error == OK)
	quit()
