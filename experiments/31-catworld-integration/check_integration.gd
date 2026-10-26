extends SceneTree

var report := {"checks": [], "states": [], "motion_samples": []}
var room: Node3D
var pet: Node3D
var failed := false

func _initialize() -> void:
	run.call_deferred()

func check(condition: bool, label: String) -> void:
	report.checks.append({"check": label, "pass": condition})
	if not condition:
		failed = true
		push_error(label)

func run() -> void:
	room = load("res://main.tscn").instantiate()
	root.add_child(room)
	await process_frame
	pet = room.personalized_cat
	check(room.has_node("Cat") and room.has_node("TripoCat") and room.has_node("PersonalizedCat"), "all_three_cats_present")
	check(pet.ready_for_play, "new_cat_ready")
	check(room.active_cat == pet, "new_cat_selected_by_default")
	check(pet.anim.get_animation_list().size() == 4, "four_clips_only")
	var skeleton: Skeleton3D = pet.model.find_children("*", "Skeleton3D", true, false)[0]
	check(skeleton.get_bone_count() == 56, "56_bones_preserved")
	var triangles := 0
	var eight_weights := true
	for mesh: MeshInstance3D in pet.model.find_children("*", "MeshInstance3D", true, false):
		for surface in mesh.mesh.get_surface_count():
			triangles += mesh.mesh.surface_get_array_index_len(surface) / 3
			eight_weights = eight_weights and bool(mesh.mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
	check(triangles == 3500, "3500_base_triangles_preserved")
	check(eight_weights, "eight_skin_weights_preserved")
	report["rest_bounds"] = {"position":str(pet.rest_bounds.position), "size":str(pet.rest_bounds.size)}
	report["normalization"] = {"scale":str(pet.normalization.scale),"position":str(pet.normalization.position)}
	check(absf(pet.rest_bounds.size.y * pet.normalization.scale.y - pet.standing_height) < 0.0001, "height_derived_from_rest_bounds")
	room._cat_button.pressed.emit()
	check(room.active_cat == room.cat, "selector_switches_to_original_cat")
	room._cat_button.pressed.emit()
	check(room.active_cat == room.tripo_cat, "selector_switches_to_tripo_cat")
	room._cat_button.pressed.emit()
	check(room.active_cat == pet, "selector_returns_to_personalized_cat")
	# Avoid writing the player's furniture layout during a pause/resume test.
	var user_layout: String = room.decoration.layout_path
	room.decoration.layout_path = output_dir() + "/test-room-layout.json"
	room.decoration.set_editing(true)
	check(pet.process_mode == Node.PROCESS_MODE_DISABLED and room.cat.process_mode == Node.PROCESS_MODE_DISABLED and room.tripo_cat.process_mode == Node.PROCESS_MODE_DISABLED, "editing_pauses_all_cats")
	room.decoration.set_editing(false)
	check(pet.process_mode == Node.PROCESS_MODE_INHERIT and room.cat.process_mode == Node.PROCESS_MODE_INHERIT and room.tripo_cat.process_mode == Node.PROCESS_MODE_INHERIT, "editing_resumes_all_cats")
	room.decoration.layout_path = user_layout
	# Deterministic fixed-step test of the real controller and imported curves.
	for cat in [room.cat, room.tripo_cat, pet]:
		cat.set_process(false)
		cat.anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	pet.waypoints.clear()
	pet.wait = 1e9
	var destination := pet.position + Vector3(0.35, 0, -0.32)
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = room.cam.unproject_position(destination)
	room._unhandled_input(click)
	check(pet.target.distance_to(destination) < 0.0001, "floor_click_routes_to_selected_cat")
	var movement_in_transition := 0.0
	var max_bone_change := 0.0
	var pose_before: Array[Quaternion] = []
	for bone in skeleton.get_bone_count():
		pose_before.append(skeleton.get_bone_pose_rotation(bone))
	for frame in 900:
		var state_before: int = pet.state
		var pos_before: Vector3 = pet.position
		pet._process(1.0/60.0)
		pet.anim.advance(1.0/60.0)
		if state_before in [pet.State.RISING, pet.State.LOWERING]:
			movement_in_transition = maxf(movement_in_transition, pet.position.distance_to(pos_before))
		if not report.states.has(pet.state):
			report.states.append(pet.state)
		for bone in skeleton.get_bone_count():
			max_bone_change = maxf(max_bone_change, pose_before[bone].angle_to(skeleton.get_bone_pose_rotation(bone)))
		if frame % 60 == 0:
			report.motion_samples.append({"frame":frame,"state":pet.state,"position":str(pet.position),"clip":str(pet.anim.current_animation)})
	check(report.states.has(pet.State.RISING) and report.states.has(pet.State.WALKING) and report.states.has(pet.State.LOWERING) and report.states.has(pet.State.SITTING), "complete_sit_rise_walk_lower_sit_cycle")
	check(movement_in_transition < 0.000001, "root_stationary_during_transitions")
	check(pet.position.distance_to(destination) <= pet.ARRIVAL_DISTANCE, "reaches_clicked_destination")
	check(pet.state == pet.State.SITTING, "ends_sitting")
	check(max_bone_change > 0.00001, "imported_bone_animation_changes_pose")
	# A new destination during lowering must wait for lowering to finish.
	pet.state = pet.State.WALKING
	pet._lower()
	pet.go_to(pet.position + Vector3(-0.3,0,0))
	check(pet.state == pet.State.LOWERING, "retarget_during_lowering_does_not_interrupt_pose")
	for frame in 150:
		pet._process(1.0/60.0)
		pet.anim.advance(1.0/60.0)
	check(pet.state == pet.State.WALKING, "queued_destination_rises_then_walks")
	room.zoom = 3.0
	room._place_camera(1.0)
	var focus: Vector3 = room.cam.global_position - room.VIEW_DIR.normalized()*15.0
	check(focus.distance_to(pet.global_position+Vector3(0,0.16,0)) < 0.0001, "zoom_follows_selected_cat")
	report["godot_version"] = Engine.get_version_info().string
	report["max_bone_rotation_change_radians"] = max_bone_change
	report["pass"] = not failed
	report["animation_quality_pass"] = false
	report["scope"] = "Godot import and integration behavior; does not repair existing deformation/contact defects or validate new cats."
	var file := FileAccess.open(output_dir()+"/integration-check.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"  "))
	print("INTEGRATION_CHECK ", JSON.stringify(report.checks))
	quit(1 if failed else 0)

func output_dir() -> String:
	return get_script().resource_path.get_base_dir()
