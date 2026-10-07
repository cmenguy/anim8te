class_name VelocityOverlay
extends DebugOverlay
## Velocity vectors (M2.8): the root velocity (`root_velocity`) as an arrow
## from the Hips, and the hands' and feet's velocities (finite differences of
## `joint_positions`), each `seconds_per_mps` long per m/s.

const ROOT := Color(0.2, 0.9, 1.0)
const LIMB := Color(1.0, 0.85, 0.2)
const LIMBS: PackedStringArray = ["LeftHand", "RightHand", "LeftFoot", "RightFoot"]

## Arrow length per m/s, metres (0.2: a 1 m/s velocity draws 20 cm).
@export var seconds_per_mps := 0.2


func _init() -> void:
	super()
	overlay_id = "velocity"
	title = "Velocity vectors"


func _draw_frame(f: ClipFeatures, frame: int) -> void:
	var hips := f.root_position[frame]
	var v := f.root_velocity[frame]
	arrow(hips, hips + v * seconds_per_mps, ROOT)
	shapes.append({"kind": "velocity", "bone": "Hips", "velocity": v})
	for bone in LIMBS:
		var j := f.joint(bone)
		if j < 0:
			continue
		var p := f.position(frame, j)
		var lv := f.velocity(frame, j)
		arrow(p, p + lv * seconds_per_mps, LIMB)
		shapes.append({"kind": "velocity", "bone": bone, "velocity": lv})
