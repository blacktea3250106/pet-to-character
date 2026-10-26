extends Node3D
## Two behaviors from the selected 3,500-triangle asset: walk and sit.
## Normalization changes only the scene wrapper, never vertices or skin weights.

enum State { SITTING, RISING, WALKING, LOWERING }

@export var model_scene: PackedScene = preload("res://models/personalized_cat.glb")
@export var walk_clip: StringName = &"Walk"
@export var sit_clip: StringName = &"Sitting"
@export var rise_clip: StringName = &"Sitting_to_Idle"
@export var lower_clip: StringName = &"Idle_to_Sit"
@export var standing_height := 0.43
@export var walk_speed := 0.16
@export var rest_seconds := 5.0
@export var bounds := Rect2(0.40, -1.75, 2.50, 1.30)
@export var waypoints: Array[Vector2] = [
	Vector2(1.65, -1.55), Vector2(2.65, -1.25),
	Vector2(2.65, -0.50), Vector2(1.65, -0.50),
]

const ARRIVAL_DISTANCE := 0.025
const TURN_RATE := 2.8
const ACCELERATION := 0.6

var anim: AnimationPlayer
var model: Node3D
var normalization: Node3D
var rest_bounds: AABB
var target := Vector3.ZERO
var moving := false
var wait := 5.0
var state := State.SITTING
var ready_for_play := false
var _speed := 0.0
var _waypoint := 0


func _ready() -> void:
	normalization = Node3D.new()
	normalization.name = "SizeAndGround"
	add_child(normalization)
	model = model_scene.instantiate()
	normalization.add_child(model)
	anim = model.find_child("AnimationPlayer", true, false) as AnimationPlayer
	if anim == null:
		_reject("Personalized cat requires an AnimationPlayer.")
		return
	for clip in [walk_clip, sit_clip, rise_clip, lower_clip]:
		if not anim.has_animation(clip) or anim.get_animation(clip).length <= 0.0:
			_reject("Personalized cat missing required animation: " + str(clip))
			return
	# Keep the imported resource reusable by other instances with different settings.
	var library := anim.get_animation_library("").duplicate(true) as AnimationLibrary
	anim.remove_animation_library("")
	anim.add_animation_library("", library)
	for clip in [walk_clip, sit_clip]:
		anim.get_animation(clip).loop_mode = Animation.LOOP_LINEAR
	for clip in [rise_clip, lower_clip]:
		anim.get_animation(clip).loop_mode = Animation.LOOP_NONE
	var found := false
	for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		var relative := normalization.global_transform.affine_inverse() * mesh.global_transform
		var box: AABB = relative * mesh.get_aabb()
		rest_bounds = rest_bounds.merge(box) if found else box
		found = true
	if not found or rest_bounds.size.y <= 0.0001 or standing_height <= 0.0:
		_reject("Personalized cat has invalid standing bounds.")
		return
	var unit := standing_height / rest_bounds.size.y
	normalization.scale = Vector3.ONE * unit
	var center := rest_bounds.get_center()
	normalization.position = -Vector3(center.x, rest_bounds.position.y, center.z) * unit
	anim.animation_finished.connect(_on_animation_finished)
	target = position
	wait = rest_seconds
	ready_for_play = true
	_play(sit_clip, 0.0)
	anim.advance(0.0)


func _reject(message: String) -> void:
	push_error(message)
	hide()
	set_process(false)


func go_to(point: Vector3) -> void:
	if not ready_for_play:
		return
	target = Vector3(clampf(point.x, bounds.position.x, bounds.end.x), position.y,
		clampf(point.z, bounds.position.y, bounds.end.y))
	moving = position.distance_to(target) > ARRIVAL_DISTANCE
	if moving and state == State.SITTING:
		state = State.RISING
		_play(rise_clip, 0.10)
	elif not moving and state == State.WALKING:
		_lower()


func _play(clip: StringName, blend := 0.10) -> void:
	anim.speed_scale = 1.0
	if anim.current_animation != clip or not anim.is_playing():
		anim.play(clip, blend)


func _hold_standing() -> void:
	if anim.current_animation != rise_clip:
		anim.play(rise_clip, 0.10)
	anim.seek(anim.get_animation(rise_clip).length, true)
	anim.speed_scale = 0.0


func _lower() -> void:
	moving = false
	_speed = 0.0
	state = State.LOWERING
	_play(lower_clip, 0.12)


func _on_animation_finished(clip: StringName) -> void:
	if state == State.RISING and clip == rise_clip:
		state = State.WALKING
		if not moving:
			_lower()
	elif state == State.LOWERING and clip == lower_clip:
		state = State.SITTING
		_play(sit_clip, 0.10)
		wait = rest_seconds
		if moving:
			state = State.RISING
			_play(rise_clip, 0.10)


func _process(delta: float) -> void:
	if not ready_for_play:
		return
	if state == State.SITTING:
		wait -= delta
		if wait <= 0.0 and not waypoints.is_empty():
			var next := waypoints[_waypoint]
			_waypoint = (_waypoint + 1) % waypoints.size()
			go_to(Vector3(next.x, position.y, next.y))
		return
	# The root stays still throughout both pose transitions.
	if state != State.WALKING:
		return
	var offset := target - position
	offset.y = 0.0
	var distance := offset.length()
	if distance <= ARRIVAL_DISTANCE:
		_lower()
		return
	var heading := atan2(-offset.z, offset.x)
	var angle := angle_difference(rotation.y, heading)
	rotation.y += clampf(angle, -TURN_RATE * delta, TURN_RATE * delta)
	if absf(angle) > 0.15:
		_speed = 0.0
		_hold_standing()
		return
	var stopping_speed := sqrt(2.0 * ACCELERATION * maxf(0.0, distance - ARRIVAL_DISTANCE))
	_speed = move_toward(_speed, minf(walk_speed, stopping_speed), ACCELERATION * delta)
	var travel := minf(_speed * delta, distance)
	position += offset / distance * travel
	_play(walk_clip)
	anim.speed_scale = travel / maxf(delta * walk_speed, 0.0001)
