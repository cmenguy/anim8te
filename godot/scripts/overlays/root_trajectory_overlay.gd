class_name RootTrajectoryOverlay
extends DebugOverlay
## Root trajectory (M2.8): the Hips track projected on the ground, the past
## `seconds` in blue and the next `seconds` (the clip's own upcoming frames;
## the controller's prediction is M5) in orange, with the current position
## and facing. Treadmill clips stay on the spot until root motion (M3.2).

const PAST := Color(0.3, 0.6, 1.0)
const FUTURE := Color(1.0, 0.6, 0.15)
const GROUND_Y := 0.004

@export var seconds := 1.0


func _init() -> void:
	super()
	overlay_id = "root_trajectory"
	title = "Root trajectory"


func _draw_frame(f: ClipFeatures, frame: int) -> void:
	var span := roundi(seconds * f.fps)
	var first := maxi(frame - span, 0)
	var last := mini(frame + span, f.num_frames - 1)
	var past := PackedVector3Array()
	for i in range(first, frame + 1):
		past.append(_ground(f.root_position[i]))
	var future := PackedVector3Array()
	for i in range(frame, last + 1):
		future.append(_ground(f.root_position[i]))
	polyline(past, PAST)
	polyline(future, FUTURE)
	var here := _ground(f.root_position[frame])
	disk(here, 0.05, Color.WHITE, 12)
	# Facing: the hips' left-to-right axis turned a quarter about Y (+Z front).
	var across := f.position(frame, f.joint("RightUpperLeg")) - f.position(frame, f.joint("LeftUpperLeg"))
	var facing := Vector3(across.z, 0, -across.x).normalized()
	if facing != Vector3.ZERO:
		arrow(here, here + facing * 0.25, Color.WHITE)
	shapes.append({"kind": "trajectory", "past": past.size(), "future": future.size(), "facing": facing})


static func _ground(p: Vector3) -> Vector3:
	return Vector3(p.x, GROUND_Y, p.z)
