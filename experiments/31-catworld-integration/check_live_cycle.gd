extends SceneTree
## Observe normal engine processing at movie FPS, without manually advancing clips.
var room: Node3D
var elapsed := 0.0
var states: Array[int] = []
var changes: Array[Dictionary] = []
var previous := -1

func _initialize() -> void:
	start.call_deferred()

func start() -> void:
	room = load("res://main.tscn").instantiate()
	root.add_child(room)

func _process(delta: float) -> bool:
	if room == null:
		return false
	elapsed += delta
	var pet: Node3D = room.personalized_cat
	if pet.state != previous:
		previous = pet.state
		states.append(previous)
		changes.append({"time":elapsed,"state":previous,"position":str(pet.position),"clip":str(pet.anim.current_animation)})
	if elapsed >= 18.0:
		var passed := states == [0, 1, 2, 3, 0]
		var result := {"pass":passed,"states":states,"changes":changes,"end_distance":pet.position.distance_to(pet.target),"end_speed":pet._speed,"duration":elapsed,"fixed_fps":30}
		FileAccess.open(get_script().resource_path.get_base_dir()+"/live-cycle.json",FileAccess.WRITE).store_string(JSON.stringify(result,"  "))
		print("LIVE_CYCLE ",JSON.stringify(result))
		quit(0 if passed else 1)
	return false
