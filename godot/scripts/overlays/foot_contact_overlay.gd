class_name FootContactOverlay
extends DebugOverlay
## Foot-contact markers (M2.8): a disk on the ground under each foot joint
## (LeftFoot, RightFoot, LeftToes, RightToes) while `features.json` has it in
## contact; green when the joint is planted, red when it slides, that is when
## its horizontal speed relative to the ground (the treadmill belt, for
## treadmill clips) is over `slide_mps`.

const PLANTED := Color(0.2, 0.9, 0.3)
const SLIDING := Color(1.0, 0.2, 0.15)
const GROUND_Y := 0.003

## Slip speed above which a planted joint counts as sliding: 0.3 m/s is 1 cm
## per frame at 30 fps.
@export var slide_mps := 0.3


func _init() -> void:
	super()
	overlay_id = "foot_contacts"
	title = "Foot contacts"


func _draw_frame(f: ClipFeatures, frame: int) -> void:
	if f.contacts.is_empty():
		note = "no contacts (filter off)"
		return
	for bone in ClipFeatures.CONTACT_BONES:
		if not f.in_contact(frame, bone):
			continue
		var j := f.joint(bone)
		var p := f.position(frame, j)
		var slip := f.slip_speed(frame, j)
		var sliding := slip > slide_mps
		var radius := 0.06 if bone.ends_with("Foot") else 0.04
		disk(Vector3(p.x, GROUND_Y, p.z), radius, SLIDING if sliding else PLANTED)
		shapes.append({"kind": "contact", "bone": bone, "sliding": sliding, "slip_mps": slip})
