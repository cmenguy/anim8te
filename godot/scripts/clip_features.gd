class_name ClipFeatures
extends RefCounted
## A clip's `features.json` (M2.7; schema `ClipFeatures` in anim8te/library.py),
## parsed for the debug overlays (M2.8). Everything is in the glTF frame, the
## same space as the ClipPlayer's source skeleton (Y-up, metres), one entry
## per frame at `fps`.

## Foot joints that `contacts` and `rest_heights_above_sole` cover.
const CONTACT_BONES: PackedStringArray = ["LeftFoot", "RightFoot", "LeftToes", "RightToes"]

var path: String
var fps := 30.0
var num_frames := 0
var bone_names: PackedStringArray
## Per frame: joint positions in `bone_names` order.
var joint_positions: Array[PackedVector3Array] = []
## Per frame: jerk magnitude per joint, m/s^3.
var joint_jerk: Array[PackedFloat32Array] = []
var root_position: PackedVector3Array
var root_velocity: PackedVector3Array
## Contact bone -> PackedByteArray per frame (1 = contact); empty when the
## contacts filter was off.
var contacts := {}
## Contacts filter thresholds (`height_m`, `speed_mps`), when present.
var contact_height_m := 0.04
## Ground (x, z) velocity the contacts were measured against, m/s.
var ground_velocity := Vector2.ZERO
## Contact bone -> rest height above the soles, metres; empty in files
## written before M2.8 (re-run `anim8te clean`).
var rest_heights_above_sole := {}


## Parses `path`, or returns null and pushes an error.
static func load_file(path: String) -> ClipFeatures:
	var text := FileAccess.get_file_as_string(path)
	if text == "":
		push_error("ClipFeatures: cannot read %s" % path)
		return null
	var json := JSON.new()
	if json.parse(text) != OK or not json.data is Dictionary:
		push_error("ClipFeatures: %s is not a JSON object" % path)
		return null
	var d: Dictionary = json.data
	for key in ["fps", "num_frames", "bone_names", "joint_positions", "joint_jerk", "root_position", "root_velocity"]:
		if not d.has(key):
			push_error("ClipFeatures: %s has no %s" % [path, key])
			return null
	var f := ClipFeatures.new()
	f.path = path
	f.fps = float(d.fps)
	f.num_frames = int(d.num_frames)
	f.bone_names = PackedStringArray(d.bone_names)
	for frame in d.joint_positions:
		var row := PackedVector3Array()
		for p in frame:
			row.append(Vector3(p[0], p[1], p[2]))
		f.joint_positions.append(row)
	for frame in d.joint_jerk:
		f.joint_jerk.append(PackedFloat32Array(frame))
	f.root_position = _vectors(d.root_position)
	f.root_velocity = _vectors(d.root_velocity)
	var contacts: Dictionary = d.get("contacts", {}) if d.get("contacts") is Dictionary else {}
	for bone in contacts:
		var flags := PackedByteArray()
		for c in contacts[bone]:
			flags.append(1 if c else 0)
		f.contacts[bone] = flags
	if d.get("contact_thresholds") is Dictionary:
		var t: Dictionary = d.contact_thresholds
		f.contact_height_m = float(t.get("height_m", f.contact_height_m))
		var gv = t.get("ground_velocity")
		if gv is Array and gv.size() == 2:
			f.ground_velocity = Vector2(gv[0], gv[1])
	if d.get("rest_heights_above_sole") is Dictionary:
		for bone in d.rest_heights_above_sole:
			f.rest_heights_above_sole[bone] = float(d.rest_heights_above_sole[bone])
	if f.joint_positions.size() != f.num_frames or f.root_position.size() != f.num_frames:
		push_error("ClipFeatures: %s has %d frames of positions, expected %d" % [path, f.joint_positions.size(), f.num_frames])
		return null
	return f


func joint(name: String) -> int:
	return bone_names.find(name)


func position(frame: int, j: int) -> Vector3:
	return joint_positions[_clamp(frame)][j]


## Velocity of joint j at `frame`, m/s (central differences, one-sided at the
## ends, as anim8te computes `root_velocity`).
func velocity(frame: int, j: int) -> Vector3:
	if num_frames < 2:
		return Vector3.ZERO
	var a := _clamp(frame - 1)
	var b := _clamp(frame + 1)
	return (joint_positions[b][j] - joint_positions[a][j]) * fps / float(b - a)


## Horizontal speed of joint j relative to the ground, m/s.
func slip_speed(frame: int, j: int) -> float:
	var v := velocity(frame, j)
	return (Vector2(v.x, v.z) - ground_velocity).length()


func in_contact(frame: int, bone: String) -> bool:
	return contacts.has(bone) and contacts[bone][_clamp(frame)] == 1


## Height of a contact bone's sole above the ground, metres, or NAN when its
## rest height is unknown.
func sole_height(frame: int, bone: String) -> float:
	if not rest_heights_above_sole.has(bone):
		return NAN
	return position(frame, joint(bone)).y - rest_heights_above_sole[bone]


func _clamp(frame: int) -> int:
	return clampi(frame, 0, num_frames - 1)


static func _vectors(rows: Array) -> PackedVector3Array:
	var out := PackedVector3Array()
	for p in rows:
		out.append(Vector3(p[0], p[1], p[2]))
	return out
