extends SceneTree
## Runtime retargeting check (M2.4). For each library clip with a motion.glb,
## plays it on the mannequin through ClipPlayer (GLTFDocument +
## RetargetModifier3D) next to the raw clip (the same glb, loaded but not
## converted) and compares, frame by frame:
##   - each canonical bone's direction (bone to child joint), mannequin vs clip;
##   - the hip height change from rest, mannequin vs clip x motion_scale ratio.
## For the walk it also reports the editor import path (assets/sample_clips/,
## M2.3) against the clip, for reference.
##
##   godot --headless --path godot --script tests/check_runtime_retarget.gd [-- --clip=<id>]
##
## Needs the local library (git-ignored). Exits 1 if a bone or the hips drift
## past the thresholds below.

const MAX_DEG := 1.0
const MAX_HIPS_CM := 0.5
const EDITOR_CLIP := "walk-ur7zdb"
const EDITOR_LIBRARY := "res://assets/sample_clips/walk-ur7zdb.glb"
## Bone -> child joint that gives its direction.
const SEGMENTS := {
	"Hips": "Spine", "Spine": "Chest", "Chest": "UpperChest", "UpperChest": "Neck", "Neck": "Head",
	"LeftShoulder": "LeftUpperArm", "LeftUpperArm": "LeftLowerArm", "LeftLowerArm": "LeftHand",
	"RightShoulder": "RightUpperArm", "RightUpperArm": "RightLowerArm", "RightLowerArm": "RightHand",
	"LeftUpperLeg": "LeftLowerLeg", "LeftLowerLeg": "LeftFoot", "LeftFoot": "LeftToes",
	"RightUpperLeg": "RightLowerLeg", "RightLowerLeg": "RightFoot", "RightFoot": "RightToes",
}

var clips: PackedStringArray
var index := -1
var runtime: ClipPlayer
var raw: Skeleton3D
var raw_player: AnimationPlayer
var raw_scene: Node
var editor: Skeleton3D
var editor_player: AnimationPlayer
var frame := 0
var frames := 0
var stats := {}
var failed := false


func _initialize() -> void:
	runtime = ClipPlayer.new()
	root.add_child(runtime)
	var man: Node3D = load("res://assets/mannequin/Superhero_Male_FullBody.gltf").instantiate()
	root.add_child(man)
	editor = man.get_node("%GeneralSkeleton")
	editor_player = AnimationPlayer.new()
	man.add_child(editor_player)
	editor_player.root_node = editor_player.get_path_to(man)
	editor_player.add_animation_library("", load(EDITOR_LIBRARY))
	editor_player.play(EDITOR_CLIP)
	editor_player.pause()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--clip="):
			clips.append(arg.trim_prefix("--clip="))
	if clips.is_empty():
		var dir := runtime.library_root().path_join("clips")
		for id in DirAccess.get_directories_at(dir):
			if FileAccess.file_exists(dir.path_join(id).path_join("motion.glb")):
				clips.append(id)
	if clips.is_empty():
		push_error("no clip with a motion.glb under %s" % runtime.library_root())


func _process(_delta: float) -> bool:
	if index < 0 or frame >= frames:
		if index >= 0:
			_report()
		index += 1
		if index >= clips.size():
			print("FAIL" if failed or clips.is_empty() else "PASS")
			quit(1 if failed or clips.is_empty() else 0)
			return true
		if not _start(clips[index]):
			failed = true
			frames = 0
			return false
	# Modifiers apply during the skeleton update, so read one frame after seeking.
	if frame > 0:
		_compare()
	var t := frame / 30.0
	runtime.player.seek(t, true)
	raw_player.seek(t, true)
	editor_player.seek(t, true)
	frame += 1
	return false


func _start(id: String) -> bool:
	if raw_scene:
		raw_scene.queue_free()
	if not runtime.play(id):
		return false
	runtime.player.pause()
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	doc.append_from_file(runtime.library_root().path_join("clips").path_join(id).path_join("motion.glb"), state)
	raw_scene = doc.generate_scene(state)
	root.add_child(raw_scene)
	raw = raw_scene.find_children("*", "Skeleton3D", true, false)[0]
	raw_player = raw_scene.find_children("*", "AnimationPlayer", true, false)[0]
	raw_player.play(raw_player.get_animation_list()[0])
	raw_player.pause()
	frames = int(runtime.player.current_animation_length * 30.0)
	frame = 0
	stats = {"runtime": {}, "editor": {}, "hips": []}
	return true


func _compare() -> void:
	var with_editor := clips[index] == EDITOR_CLIP
	for bone in SEGMENTS:
		var d := _direction(raw, bone)
		_add(stats["runtime"], bone, rad_to_deg(d.angle_to(_direction(runtime.target, bone))))
		if with_editor:
			_add(stats["editor"], bone, rad_to_deg(d.angle_to(_direction(editor, bone))))
	var ratio := runtime.target.motion_scale / raw.get_bone_rest(0).origin.y
	var raw_dy := raw.get_bone_global_pose(0).origin.y - raw.get_bone_rest(0).origin.y
	var hips := runtime.target.find_bone("Hips")
	var target_dy := runtime.target.get_bone_global_pose(hips).origin.y - runtime.target.get_bone_global_rest(hips).origin.y
	stats["hips"].append(absf(target_dy - raw_dy * ratio) * 100.0)


func _report() -> void:
	var with_editor := clips[index] == EDITOR_CLIP
	print("%s, %d frames: bone direction vs the clip, degrees (median / max)%s" % [clips[index], frames, ", editor path alongside" if with_editor else ""])
	for bone in SEGMENTS:
		var r := _summary(stats["runtime"][bone])
		var bad := r[1] > MAX_DEG
		failed = failed or bad
		var line := "  %-14s runtime %5.2f / %5.2f" % [bone, r[0], r[1]]
		if with_editor:
			var e := _summary(stats["editor"][bone])
			line += "   editor %5.2f / %5.2f" % [e[0], e[1]]
		print(line + ("  FAIL" if bad else ""))
	var h := _summary(stats["hips"])
	var hips_bad := h[1] > MAX_HIPS_CM
	failed = failed or hips_bad
	print("  hip height change vs clip: %.2f / %.2f cm%s" % [h[0], h[1], "  FAIL" if hips_bad else ""])


func _direction(skeleton: Skeleton3D, bone: String) -> Vector3:
	var a := skeleton.get_bone_global_pose(skeleton.find_bone(bone)).origin
	var b := skeleton.get_bone_global_pose(skeleton.find_bone(SEGMENTS[bone])).origin
	return (b - a).normalized()


static func _add(d: Dictionary, key: String, value: float) -> void:
	if not d.has(key):
		d[key] = []
	d[key].append(value)


static func _summary(values: Array) -> Array[float]:
	var v := values.duplicate()
	v.sort()
	return [v[v.size() / 2], v[-1]]
