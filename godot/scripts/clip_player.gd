class_name ClipPlayer
extends Node3D
## Plays library clips (`library/clips/<id>/motion.glb`, loaded at runtime) on
## a humanoid model through RetargetModifier3D (M2.4). Node layout, built in
## `_ready` (see "Runtime retargeting" in godot/README.md):
##
##   ClipPlayer
##     Armature
##       Skeleton3D             canonical source: 22 bones, profile rest, no mesh
##         RetargetModifier3D   SkeletonProfileHumanoid, local pose
##           <model skeleton>   the model's Skeleton3D, moved here with its meshes
##     AnimationPlayer          root_node = ClipPlayer, one track set per loaded clip
##
## RetargetModifier3D only drives Skeleton3D nodes that are its direct
## children, so the model's skeleton is taken out of the model scene.

signal clip_changed(clip_id: String)

## Model to drive; any scene imported with a BoneMap on SkeletonProfileHumanoid.
@export var model_scene: PackedScene = preload("res://assets/mannequin/Superhero_Male_FullBody.gltf")
## Clip to play on ready; empty plays nothing. A `--clip=<id>` user argument
## (after `--` on the command line) overrides it.
@export var clip_id := ""
## Library root; empty resolves `--library=<path>`, ANIM8TE_LIBRARY, then `<repo>/library`.
@export var library_path := ""
@export var loop := true

var profile := SkeletonProfileHumanoid.new()
var source: Skeleton3D
var retarget: RetargetModifier3D
var target: Skeleton3D
var player: AnimationPlayer
var _clips := {}


func _ready() -> void:
	var armature := Node3D.new()
	armature.name = "Armature"
	add_child(armature)
	source = Skeleton3D.new()
	source.name = "Skeleton3D"
	armature.add_child(source)
	retarget = RetargetModifier3D.new()
	retarget.profile = profile
	retarget.use_global_pose = false
	source.add_child(retarget)
	player = AnimationPlayer.new()
	player.name = "AnimationPlayer"
	add_child(player)
	player.root_node = player.get_path_to(self)
	player.add_animation_library("", AnimationLibrary.new())
	if model_scene:
		set_model(model_scene.instantiate())
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--clip="):
			clip_id = arg.trim_prefix("--clip=")
	if clip_id != "":
		play(clip_id)


## Resolved library root (absolute path).
func library_root() -> String:
	return LibraryScanner.resolve_root(library_path)


## Drives `model` (a scene instance) from now on; its Skeleton3D and meshes
## move under the retarget modifier and the rest of the scene is freed.
func set_model(model: Node) -> void:
	var skeletons := model.find_children("*", "Skeleton3D", true, false)
	if skeletons.is_empty():
		push_error("ClipPlayer: model %s has no Skeleton3D" % model.name)
		model.free()
		return
	if target:
		target.queue_free()
	target = skeletons[0]
	var xform := _transform_in(target, model)
	_clear_owner(target, model)
	target.get_parent().remove_child(target)
	retarget.add_child(target)
	target.transform = xform
	model.free()
	# Clips are put on the driven model's rest; reload them for the new one.
	_clips.clear()
	var library := player.get_animation_library("")
	for name in library.get_animation_list():
		library.remove_animation(name)
	if source.get_bone_count() > 0 and clip_id != "":
		play(clip_id)


## Loads a clip from the library (cached) and returns it, or null.
func load_clip(id: String) -> RuntimeClip:
	if _clips.has(id):
		return _clips[id]
	var path := library_root().path_join("clips").path_join(id).path_join("motion.glb")
	if not FileAccess.file_exists(path):
		push_error("ClipPlayer: no motion.glb for clip %s at %s" % [id, path])
		return null
	var reference := RuntimeClip.reference_from_skeleton(target) if target else RuntimeClip.reference_from_profile(profile)
	var clip := RuntimeClip.load_clip(path, reference)
	if clip == null:
		return null
	if source.get_bone_count() == 0:
		_build_source(clip)
	elif not _same_bones(clip):
		push_error("ClipPlayer: clip %s is not on the canonical skeleton" % id)
		return null
	clip.animation.loop_mode = Animation.LOOP_LINEAR if loop else Animation.LOOP_NONE
	player.get_animation_library("").add_animation(clip.id, clip.animation)
	_clips[id] = clip
	return clip


## Loads (if needed) and plays a clip from its start.
func play(id: String) -> bool:
	var clip := load_clip(id)
	if clip == null:
		return false
	# Rests differ per performer (bone offsets); rotations are the profile's.
	for name in clip.bone_names:
		source.set_bone_rest(source.find_bone(name), clip.rests[name])
	source.reset_bone_poses()
	source.motion_scale = clip.motion_scale
	player.play(clip.id)
	player.seek(0.0, true)
	clip_id = id
	clip_changed.emit(id)
	return true


func _build_source(clip: RuntimeClip) -> void:
	for name in clip.bone_names:
		source.add_bone(name)
	for i in clip.bone_names.size():
		var parent := clip.bone_parents[i]
		if parent != "":
			source.set_bone_parent(i, source.find_bone(parent))
		source.set_bone_rest(i, clip.rests[clip.bone_names[i]])
	source.reset_bone_poses()


func _same_bones(clip: RuntimeClip) -> bool:
	if clip.bone_names.size() != source.get_bone_count():
		return false
	for i in clip.bone_names.size():
		if source.get_bone_name(i) != clip.bone_names[i]:
			return false
	return true


static func _transform_in(node: Node3D, ancestor: Node) -> Transform3D:
	var xform := node.transform
	var p := node.get_parent()
	while p != ancestor and p is Node3D:
		xform = (p as Node3D).transform * xform
		p = p.get_parent()
	return xform


static func _clear_owner(node: Node, scene_root: Node) -> void:
	if node.owner == scene_root:
		node.owner = null
	for child in node.get_children():
		_clear_owner(child, scene_root)
