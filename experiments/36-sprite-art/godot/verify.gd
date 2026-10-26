extends SceneTree

func _initialize() -> void:
	call_deferred("_verify")

func _verify() -> void:
	var scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	var actor: Node3D = scene.get_node("Static2DCat")
	var sprites := actor.find_children("*", "Sprite3D", true, false)
	var mesh_nodes := actor.find_children("*", "MeshInstance3D", true, false)
	var skeletons := actor.find_children("*", "Skeleton3D", true, false)
	assert(sprites.size() == 1)
	assert(mesh_nodes.size() == 1 and mesh_nodes[0].name == "IndependentGroundShadow")
	assert(skeletons.is_empty())
	var sprite: Sprite3D = sprites[0]
	assert(not sprite.no_depth_test)
	assert(not sprite.shaded)
	assert(sprite.alpha_cut == SpriteBase3D.ALPHA_CUT_DISCARD)
	assert(sprite.texture.get_width() == 1448 and sprite.texture.get_height() == 1086)
	assert(scene.cam.projection == Camera3D.PROJECTION_ORTHOGONAL)
	assert(scene.meshes.RoomBed.position.is_equal_approx(scene.bed_original_position))
	var result := {
		"status": "pass", "observed_cat_sprite_count": sprites.size(),
		"observed_character_meshes_excluding_shadow": mesh_nodes.size() - 1,
		"observed_skeleton_count": skeletons.size(), "shadow_is_separate_mesh": true,
		"depth_test_enabled": not sprite.no_depth_test,
		"unshaded_sprite": not sprite.shaded, "orthographic_camera": true,
		"bed_restored_for_default_view": true,
		"art_identity_grounding_animation_automation": "Not established by these structural checks."
	}
	FileAccess.open("res://../runtime-integrity.json", FileAccess.WRITE).store_string(JSON.stringify(result, "\t"))
	print(JSON.stringify(result))
	quit()
