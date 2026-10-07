class_name GroundPenetrationOverlay
extends DebugOverlay
## Ground-penetration highlight (M2.8): a red marker, a red disk on the
## ground and the depth in millimetres for every joint under the ground. Foot
## joints count by their sole (their height minus `rest_heights_above_sole`,
## as in ground alignment), the other joints by their own position.

const COLOR := Color(1.0, 0.1, 0.35)
const GROUND_Y := 0.005

## Depth under which a sole counts as penetrating, metres.
@export var tolerance_m := 0.005


func _init() -> void:
	super()
	overlay_id = "ground_penetration"
	title = "Ground penetration"


func _draw_frame(f: ClipFeatures, frame: int) -> void:
	if f.rest_heights_above_sole.is_empty():
		note = "features.json has no rest_heights_above_sole; re-run anim8te clean"
	for j in f.bone_names.size():
		var bone := f.bone_names[j]
		var p := f.position(frame, j)
		var depth := -p.y
		if bone in ClipFeatures.CONTACT_BONES:
			var sole := f.sole_height(frame, bone)
			if is_nan(sole):
				continue
			depth = -sole
		if depth <= tolerance_m:
			continue
		marker(p, 0.025, COLOR)
		disk(Vector3(p.x, GROUND_Y, p.z), 0.05 + depth, COLOR, 16)
		label(Vector3(p.x, GROUND_Y + 0.08, p.z), "%d mm" % roundi(depth * 1000.0), COLOR)
		shapes.append({"kind": "penetration", "bone": bone, "depth_m": depth})
