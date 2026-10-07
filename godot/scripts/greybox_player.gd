class_name GreyboxPlayer
extends CharacterBody3D
## Playable grey-box character (M2.13): the mannequin on a CharacterBody3D,
## moved with WASD relative to the follow camera. An AnimationTree blends
## idle, walk and jog by speed and plays the vault as a one-shot on top.
##
## The clips come through the editor import path (`assets/sample_clips/`,
## canonical bone map), so their tracks are `%GeneralSkeleton:<Bone>` and the
## Hips position is normalized by the skeleton's `motion_scale`. They are
## prepared once in `_ready`:
## - idle, walk and jog are made in place: the Hips' horizontal drift over the
##   clip is removed (treadmill clips, 3 to 13 cm), and code moves the body.
## - the vault (filmed side-on, running along +X) is turned to run along +Z,
##   the model's front, and its horizontal Hips travel is taken out of the
##   track and applied to the body while it plays (manual root motion). Its
##   height stays in the animation; once she is on the block the model is
##   lowered so her soles land on whatever surface is under the body.
## Hand-built and tuned by eye; M5.3 is the real controller.

const HIPS := "%GeneralSkeleton:Hips"
const CLIPS := {
	"idle": preload("res://assets/sample_clips/idle-m05.glb"),
	"walk": preload("res://assets/sample_clips/walk-ur7zdb.glb"),
	"jog": preload("res://assets/sample_clips/jog-qa61r5.glb"),
	"vault": preload("res://assets/sample_clips/vault-m05.glb"),
}
## Keys, by physical position (WASD on any layout).
const KEYS := {
	"move_forward": [KEY_W, KEY_UP],
	"move_back": [KEY_S, KEY_DOWN],
	"move_left": [KEY_A, KEY_LEFT],
	"move_right": [KEY_D, KEY_RIGHT],
	"sprint": [KEY_SHIFT],
	"vault": [KEY_E, KEY_SPACE],
	"reset": [KEY_R],
}

## Walking speed (m/s), and the walk's place in the blend space. The treadmill
## walk's belt runs at 0.79 m/s, so the feet slide a little above that.
@export var walk_speed := 1.1
## Speed with the sprint key held (m/s), the jog's place in the blend space.
## The jog's belt runs at 0.89 m/s; `jog_anim_rate` speeds its cadence up.
@export var jog_speed := 2.2
@export var jog_anim_rate := 1.3
@export var acceleration := 6.0
@export var turn_sharpness := 10.0
@export var camera_path: NodePath
## The vault travels 5.13 m, about 35 % more than the take shows (M2.11), so
## its root motion is scaled down: she is on the block after about 2.8 m and
## ends 3.8 m from where she started.
@export var vault_travel_scale := 0.75
## Time in the vault clip from which her feet are on the block (M2.11: after
## 3 s), and her sole height there in the clip's frame (0.67 to 0.72 m).
@export var vault_landing_time := 3.0
@export var vault_clip_sole := 0.70
@export var vault_fade_in := 0.2
@export var vault_fade_out := 0.4

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var spawn: Transform3D

var _camera: Node3D
var _visual: Node3D
var _tree: AnimationTree
var _vaulting := false
var _vault_t := 0.0
var _vault_length := 0.0
var _vault_origin := Vector3.ZERO
var _vault_basis := Basis.IDENTITY
var _vault_times := PackedFloat32Array()
var _vault_travel := PackedVector2Array()
var _vault_surface := NAN
var _visual_drop_rate := 0.0


func _ready() -> void:
	_ensure_actions()
	spawn = global_transform
	_camera = get_node_or_null(camera_path)
	_visual = $Visual
	var skeleton: Skeleton3D = _visual.find_child("GeneralSkeleton", true, false)
	var lib := AnimationLibrary.new()
	for key in ["idle", "walk", "jog"]:
		lib.add_animation(key, _in_place(_clip(key)))
	lib.add_animation("vault", _prepare_vault(_clip("vault"), skeleton.motion_scale))
	var player: AnimationPlayer = $AnimationPlayer
	player.add_animation_library("", lib)
	_tree = $AnimationTree
	_tree.tree_root = _build_tree()
	_tree.anim_player = _tree.get_path_to(player)
	_tree.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_PHYSICS
	_tree.active = true


func _physics_process(delta: float) -> void:
	if Input.is_action_just_pressed("reset"):
		reset()
	if _vaulting:
		_vault_step(delta)
		return
	_visual.position.y = move_toward(_visual.position.y, 0.0, _visual_drop_rate * delta)

	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var dir := _camera_relative(input)
	var target_speed := jog_speed if Input.is_action_pressed("sprint") else walk_speed
	var horizontal := Vector3(velocity.x, 0, velocity.z)
	horizontal = horizontal.move_toward(dir * target_speed, acceleration * delta)
	velocity.x = horizontal.x
	velocity.z = horizontal.z
	velocity.y = 0.0 if is_on_floor() else velocity.y - gravity * delta
	move_and_slide()
	if dir.length() > 0.1:
		var weight := 1.0 - exp(-turn_sharpness * delta)
		rotation.y = lerp_angle(rotation.y, atan2(dir.x, dir.z), weight)

	# The blend follows the speed the body really has, so walking into a prop
	# settles to idle instead of running on the spot.
	var real := get_real_velocity()
	set_blend_speed(Vector2(real.x, real.z).length())

	if Input.is_action_just_pressed("vault") and is_on_floor():
		start_vault()


## Blend position and cadence for a ground speed in m/s.
func set_blend_speed(speed: float) -> void:
	_tree.set("parameters/locomotion/blend_position", speed)
	var t := clampf((speed - walk_speed) / (jog_speed - walk_speed), 0.0, 1.0)
	_tree.set("parameters/rate/scale", lerpf(1.0, jog_anim_rate, t))


func blend_speed() -> float:
	return _tree.get("parameters/locomotion/blend_position")


func is_vaulting() -> bool:
	return _vaulting


func start_vault() -> void:
	_vaulting = true
	_vault_t = 0.0
	_vault_origin = global_position
	_vault_basis = Basis(Vector3.UP, rotation.y)
	_vault_surface = NAN
	velocity = Vector3.ZERO
	_tree.set("parameters/vault/request", AnimationNodeOneShot.ONE_SHOT_REQUEST_FIRE)


func reset() -> void:
	if _vaulting:
		_tree.set("parameters/vault/request", AnimationNodeOneShot.ONE_SHOT_REQUEST_ABORT)
		_vaulting = false
	global_transform = spawn
	velocity = Vector3.ZERO
	_visual.position = Vector3.ZERO


func _vault_step(delta: float) -> void:
	_vault_t += delta
	var travel := _vault_travel_at(_vault_t)
	global_position = _vault_origin + _vault_basis * Vector3(travel.x, 0, travel.y)
	if _vault_t >= vault_landing_time:
		if is_nan(_vault_surface):
			_vault_surface = _surface_below()
		# Lower (or raise) the model so the clip's soles sit on that surface.
		var target := _vault_surface - _vault_origin.y - vault_clip_sole
		_visual.position.y = move_toward(_visual.position.y, target, 3.0 * delta)
	if _vault_t >= _vault_length - vault_fade_out:
		# The one-shot fades back to locomotion over `vault_fade_out`; put the
		# body on the surface now and let the model come up to it over the fade.
		_vaulting = false
		var visual_y := _visual.global_position.y
		var surface := _surface_below()
		global_position.y = surface
		_visual.global_position.y = visual_y
		_visual_drop_rate = absf(_visual.position.y) / vault_fade_out
		velocity = Vector3.ZERO


func _surface_below() -> float:
	var from := global_position + Vector3.UP * 3.0
	var query := PhysicsRayQueryParameters3D.create(from, global_position + Vector3.DOWN * 2.0)
	query.exclude = [get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return hit.position.y if hit else _vault_origin.y


func _vault_travel_at(t: float) -> Vector2:
	var n := _vault_times.size()
	if t <= _vault_times[0]:
		return _vault_travel[0]
	for i in range(1, n):
		if t <= _vault_times[i]:
			var w := (t - _vault_times[i - 1]) / (_vault_times[i] - _vault_times[i - 1])
			return _vault_travel[i - 1].lerp(_vault_travel[i], w)
	return _vault_travel[n - 1]


## Input vector (x right, y back) to a ground direction from the camera's yaw.
func _camera_relative(input: Vector2) -> Vector3:
	var basis := _camera.global_basis if _camera else global_basis
	var forward := Vector3(-basis.z.x, 0, -basis.z.z).normalized()
	var right := Vector3(basis.x.x, 0, basis.x.z).normalized()
	var dir := right * input.x - forward * input.y
	return dir.limit_length(1.0)


func _clip(key: String) -> Animation:
	var lib: AnimationLibrary = CLIPS[key]
	return lib.get_animation(lib.get_animation_list()[0]).duplicate(true)


## Removes the Hips' horizontal drift (a ramp from the first key to the last),
## so a loop neither wanders nor jumps at the seam.
func _in_place(anim: Animation) -> Animation:
	var track := anim.find_track(HIPS, Animation.TYPE_POSITION_3D)
	var n := anim.track_get_key_count(track)
	var first: Vector3 = anim.track_get_key_value(track, 0)
	var last: Vector3 = anim.track_get_key_value(track, n - 1)
	for i in n:
		var p: Vector3 = anim.track_get_key_value(track, i)
		var drift := first.lerp(last, float(i) / float(n - 1))
		anim.track_set_key_value(track, i, Vector3(p.x - drift.x, p.y, p.z - drift.z))
	return anim


## Turns the vault to run along +Z and moves its horizontal Hips travel from
## the track into `_vault_travel` (metres, model space, scaled).
func _prepare_vault(anim: Animation, motion_scale: float) -> Animation:
	anim.loop_mode = Animation.LOOP_NONE
	_vault_length = anim.length
	var pos := anim.find_track(HIPS, Animation.TYPE_POSITION_3D)
	var rot := anim.find_track(HIPS, Animation.TYPE_ROTATION_3D)
	var n := anim.track_get_key_count(pos)
	var first: Vector3 = anim.track_get_key_value(pos, 0)
	var landing: Vector3 = anim.track_get_key_value(pos, anim.track_find_key(pos, vault_landing_time))
	var heading := atan2(landing.x - first.x, landing.z - first.z)
	# The skeleton's Root bone has identity rest, so a yaw on the Hips (rotation
	# and position) turns the whole body about the model origin.
	var turn := Quaternion(Vector3.UP, -heading)
	for i in anim.track_get_key_count(rot):
		var q: Quaternion = anim.track_get_key_value(rot, i)
		anim.track_set_key_value(rot, i, turn * q)
	var start := turn * first
	_vault_times.resize(n)
	_vault_travel.resize(n)
	for i in n:
		var p: Vector3 = turn * (anim.track_get_key_value(pos, i) as Vector3)
		_vault_times[i] = anim.track_get_key_time(pos, i)
		_vault_travel[i] = Vector2(p.x - start.x, p.z - start.z) * motion_scale * vault_travel_scale
		anim.track_set_key_value(pos, i, Vector3(start.x, p.y, start.z))
	return anim


## Locomotion blend space (idle, walk, jog by speed), its cadence, and the
## vault as a one-shot over it.
func _build_tree() -> AnimationNodeBlendTree:
	var space := AnimationNodeBlendSpace1D.new()
	space.min_space = 0.0
	space.max_space = jog_speed
	for entry in [["idle", 0.0], ["walk", walk_speed], ["jog", jog_speed]]:
		var node := AnimationNodeAnimation.new()
		node.animation = entry[0]
		space.add_blend_point(node, entry[1], -1, entry[0])
	var vault := AnimationNodeAnimation.new()
	vault.animation = "vault"
	var shot := AnimationNodeOneShot.new()
	shot.fadein_time = vault_fade_in
	shot.fadeout_time = vault_fade_out
	var tree := AnimationNodeBlendTree.new()
	tree.add_node("locomotion", space)
	tree.add_node("rate", AnimationNodeTimeScale.new())
	tree.add_node("vault_clip", vault)
	tree.add_node("vault", shot)
	tree.connect_node("rate", 0, "locomotion")
	tree.connect_node("vault", 0, "rate")
	tree.connect_node("vault", 1, "vault_clip")
	tree.connect_node("output", 0, "vault")
	return tree


static func _ensure_actions() -> void:
	for action in KEYS:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		for key in KEYS[action]:
			var event := InputEventKey.new()
			event.physical_keycode = key
			InputMap.action_add_event(action, event)
