class_name RuntimeClip
extends RefCounted
## Loads a library clip (`motion.glb`) at runtime with GLTFDocument and puts it
## on the humanoid profile's rest, so RetargetModifier3D can drive any model
## imported on SkeletonProfileHumanoid (M2.4; gotchas in godot/README.md).
##
## motion.glb rests are SMPL-X's A-pose with identity rotations. The editor
## importer fixes that with "Overwrite Axis" and "fix silhouette"; at runtime
## nothing does, and RetargetModifier3D transfers rotations relative to rest,
## so the A/T-pose difference would land on the target (about 18 degrees on
## the upper arms). `load_clip` re-expresses the clip on a rest whose bone
## frames are the profile's reference pose (a T-pose, +Y along each bone):
## each bone gets a constant frame change B, the keys become
## B_parent^-1 * key * B and the rest offsets B_parent^-1 * offset, so the
## posed skeleton is unchanged and only the rest moves.

## Child that gives a bone its direction when it has several (or none listed).
## Skeleton path the rewritten tracks point at, relative to the player's root
## node (ClipPlayer builds `Armature/Skeleton3D` to match).
const TRACK_SKELETON := "Armature/Skeleton3D"

const _DIRECTION_CHILD := {
	"Hips": "Spine",
	"UpperChest": "Neck",
}
## Canonical chain: bone -> its single canonical child. Models carry more
## bones (fingers, eyes, twist bones), so the child is looked up by name.
const _CHAIN_CHILD := {
	"Spine": "Chest", "Chest": "UpperChest", "Neck": "Head",
	"LeftShoulder": "LeftUpperArm", "LeftUpperArm": "LeftLowerArm", "LeftLowerArm": "LeftHand",
	"RightShoulder": "RightUpperArm", "RightUpperArm": "RightLowerArm", "RightLowerArm": "RightHand",
	"LeftUpperLeg": "LeftLowerLeg", "LeftLowerLeg": "LeftFoot", "LeftFoot": "LeftToes",
	"RightUpperLeg": "RightLowerLeg", "RightLowerLeg": "RightFoot", "RightFoot": "RightToes",
}

var id: String
var animation: Animation
## Bone name -> rest Transform3D on the profile frames, in the clip's units.
var rests: Dictionary
## Rest hip height; the source skeleton's motion_scale.
var motion_scale: float
## Bone names and parent names, in skeleton order.
var bone_names: PackedStringArray
var bone_parents: PackedStringArray


## Reference rest for `load_clip`, taken from a model's own skeleton: bone
## name -> [global rest rotation, bone direction (towards the canonical child,
## or ZERO for a leaf)]. Using the driven model's rest rather than the
## profile's reference pose also absorbs the bends it keeps after "fix
## silhouette" (about 3 degrees at the elbows and 6 at the knees on the
## mannequin), so the target's bones follow the clip's directions exactly.
static func reference_from_skeleton(skeleton: Skeleton3D) -> Dictionary:
	var reference := {}
	for i in skeleton.get_bone_count():
		var name := skeleton.get_bone_name(i)
		var rot := skeleton.get_bone_global_rest(i).basis.get_rotation_quaternion()
		var child := _canonical_child(skeleton, i)
		var direction := Vector3.ZERO
		if child >= 0:
			direction = skeleton.get_bone_global_rest(child).origin - skeleton.get_bone_global_rest(i).origin
		reference[name] = [rot, direction.normalized()]
	return reference


## Reference rest from the profile's reference pose (+Y along each bone).
static func reference_from_profile(profile: SkeletonProfile) -> Dictionary:
	var reference := {}
	for i in profile.bone_size:
		var name := String(profile.get_bone_name(i))
		var parent := String(profile.get_bone_parent(i))
		var rot := profile.get_reference_pose(i).basis.get_rotation_quaternion()
		if reference.has(parent):
			rot = reference[parent][0] * rot
		reference[name] = [rot, rot * Vector3.UP]
	return reference


## Loads `path` onto `reference` (see above), or returns null and pushes an error.
static func load_clip(path: String, reference: Dictionary) -> RuntimeClip:
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_file(path, state)
	if err != OK:
		push_error("RuntimeClip: cannot read %s (%s)" % [path, error_string(err)])
		return null
	var scene := doc.generate_scene(state)
	if scene == null:
		push_error("RuntimeClip: no scene in %s" % path)
		return null
	var skeletons := scene.find_children("*", "Skeleton3D", true, false)
	var players := scene.find_children("*", "AnimationPlayer", true, false)
	if skeletons.is_empty() or players.is_empty():
		push_error("RuntimeClip: %s has no Skeleton3D or no AnimationPlayer" % path)
		scene.free()
		return null
	var skeleton: Skeleton3D = skeletons[0]
	var player: AnimationPlayer = players[0]
	var names := player.get_animation_list()
	if names.is_empty():
		push_error("RuntimeClip: %s has no animation" % path)
		scene.free()
		return null
	var clip := RuntimeClip.new()
	clip.id = names[0]
	# Duplicate so the clip outlives the generated scene.
	clip.animation = player.get_animation(names[0]).duplicate(true)
	var skeleton_path := String(scene.get_path_to(skeleton))
	var ok := clip._fix_rest(skeleton, skeleton_path, reference)
	scene.free()
	return clip if ok else null


func _fix_rest(skeleton: Skeleton3D, skeleton_path: String, reference: Dictionary) -> bool:
	var count := skeleton.get_bone_count()
	var ref_global := {}
	for name in reference:
		ref_global[name] = reference[name][0]
	# B per bone: the reference frame, swung so the reference bone follows the
	# clip's A-pose bone.
	var frame := {}
	for i in count:
		var name := skeleton.get_bone_name(i)
		if not reference.has(name):
			push_error("RuntimeClip: bone %s is not in the reference rest" % name)
			return false
		if not skeleton.get_bone_rest(i).basis.is_equal_approx(Basis.IDENTITY):
			push_error("RuntimeClip: bone %s has a non-identity rest; expected an anim8te motion.glb" % name)
			return false
		var ref: Quaternion = ref_global[name]
		var ref_direction: Vector3 = reference[name][1]
		var parent := skeleton.get_bone_parent(i)
		var direction := _clip_direction(skeleton, i)
		var swing := Quaternion.IDENTITY
		if direction != Vector3.ZERO and ref_direction != Vector3.ZERO:
			swing = Quaternion(ref_direction, direction)
		elif parent >= 0:
			# Leaf (Head, hands, toes): follow the parent's swing.
			var parent_frame: Quaternion = frame[skeleton.get_bone_name(parent)]
			var parent_ref: Quaternion = ref_global[skeleton.get_bone_name(parent)]
			swing = parent_frame * parent_ref.inverse()
		frame[name] = swing * ref
	# New rests and keys. The clip's rests are global-identity, so a bone's
	# old local offset is already in skeleton space.
	bone_names = PackedStringArray()
	bone_parents = PackedStringArray()
	for i in count:
		var name := skeleton.get_bone_name(i)
		var parent := skeleton.get_bone_parent(i)
		var parent_name := skeleton.get_bone_name(parent) if parent >= 0 else ""
		var parent_frame: Quaternion = frame[parent_name] if parent >= 0 else Quaternion.IDENTITY
		var parent_ref: Quaternion = ref_global[parent_name] if parent >= 0 else Quaternion.IDENTITY
		var ref: Quaternion = ref_global[name]
		var rest := Transform3D(
			Basis(parent_ref.inverse() * ref),
			parent_frame.inverse() * skeleton.get_bone_rest(i).origin
		)
		rests[name] = rest
		bone_names.append(name)
		bone_parents.append(parent_name)
	motion_scale = skeleton.get_bone_rest(0).origin.y
	var prefix := skeleton_path + ":"
	for t in animation.get_track_count():
		var path := String(animation.track_get_path(t))
		if not path.begins_with(prefix):
			continue
		var name := path.substr(prefix.length())
		if not frame.has(name):
			continue
		# Retarget the track onto the player's own skeleton path.
		animation.track_set_path(t, NodePath(TRACK_SKELETON + ":" + name))
		if animation.track_get_type(t) == Animation.TYPE_POSITION_3D:
			# The mixer multiplies bone position tracks by the skeleton's
			# motion_scale, so store them divided by it (as the importer's
			# "normalize position tracks" does).
			for k in animation.track_get_key_count(t):
				var p: Vector3 = animation.track_get_key_value(t, k)
				animation.track_set_key_value(t, k, p / motion_scale)
			continue
		if animation.track_get_type(t) != Animation.TYPE_ROTATION_3D:
			continue
		var b: Quaternion = frame[name]
		var parent := skeleton.get_bone_parent(skeleton.find_bone(name))
		var bp: Quaternion = frame[skeleton.get_bone_name(parent)] if parent >= 0 else Quaternion.IDENTITY
		var bp_inv := bp.inverse()
		for k in animation.track_get_key_count(t):
			var q: Quaternion = animation.track_get_key_value(t, k)
			animation.track_set_key_value(t, k, (bp_inv * q * b).normalized())
	return true


## Direction of bone i in the clip's rest (skeleton space), or ZERO for a leaf.
static func _clip_direction(skeleton: Skeleton3D, i: int) -> Vector3:
	var child := _canonical_child(skeleton, i)
	return skeleton.get_bone_rest(child).origin.normalized() if child >= 0 else Vector3.ZERO


## The child that gives bone i its direction, among the 22 canonical bones,
## or -1 for a canonical leaf (Head, hands, toes).
static func _canonical_child(skeleton: Skeleton3D, i: int) -> int:
	var name := skeleton.get_bone_name(i)
	if _DIRECTION_CHILD.has(name):
		return skeleton.find_bone(_DIRECTION_CHILD[name])
	if name not in _CHAIN_CHILD:
		return -1
	return skeleton.find_bone(_CHAIN_CHILD[name])
