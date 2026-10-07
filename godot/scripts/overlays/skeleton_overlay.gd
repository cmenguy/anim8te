class_name SkeletonOverlay
extends DebugOverlay
## Skeleton wireframe (M2.8): the canonical skeleton as extracted
## (`joint_positions`), bones as lines and joints as small markers, drawn over
## the mannequin. Differences from the mannequin are the retarget onto its
## own proportions (its stance is a few centimetres wider, for example).

const BONE := Color(0.95, 0.95, 0.95)
const JOINT := Color(0.2, 0.8, 1.0)

var _profile := SkeletonProfileHumanoid.new()


func _init() -> void:
	super()
	overlay_id = "skeleton"
	title = "Skeleton wireframe"


func _draw_frame(f: ClipFeatures, frame: int) -> void:
	var pairs := PackedVector3Array()
	for j in f.bone_names.size():
		var p := f.position(frame, j)
		marker(p, 0.015, JOINT)
		var i := _profile.find_bone(f.bone_names[j])
		var parent := String(_profile.get_bone_parent(i)) if i >= 0 else ""
		var pj := f.joint(parent) if parent != "" else -1
		if pj >= 0:
			pairs.append_array([f.position(frame, pj), p])
	lines(pairs, BONE)
	shapes.append({"kind": "skeleton", "joints": f.bone_names.size(), "bones": pairs.size() / 2})
