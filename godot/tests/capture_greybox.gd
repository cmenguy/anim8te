extends SceneTree
## Plays a scripted run through the grey box (M2.13) by pressing the player's
## input actions, for the capture: walk, jog into the 1.5 m box, walk back,
## jog along the boxes to the vault block, vault onto it and walk off.
## Record it with Movie Maker:
##
##   godot --path godot --write-movie /tmp/greybox.avi --fixed-fps 30 \
##     --script tests/capture_greybox.gd
##   ffmpeg -i /tmp/greybox.avi -an -vf scale=960:-2 -c:v libx264 -crf 30 \
##     -preset slow -pix_fmt yuv420p docs/captures/m2.13-greybox-play.mp4
##
## `-- --stills=<dir>` also saves a PNG at a few moments.

const SCENE := "res://scenes/greybox_play.tscn"

var _player: GreyboxPlayer
var _camera: FollowCamera
var _stills := ""
var _t := 0.0


func _init() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--stills="):
			_stills = arg.trim_prefix("--stills=")
	_run.call_deferred()


func _run() -> void:
	var scene: Node = load(SCENE).instantiate()
	root.add_child(scene)
	_player = scene.get_node("Player")
	_camera = scene.get_node("CameraRig")
	_camera.capture_mouse = false
	_player.global_transform = Transform3D(Basis(Vector3.UP, PI), Vector3(-3, 0, 1))
	_player.spawn = _player.global_transform
	_camera.yaw = 0.0
	_camera.pitch = -0.25
	_camera.snap()

	await _wait(1.0, "idle")
	await _hold(["move_forward"], 2.0, "walk")
	await _hold(["move_forward", "sprint"], 2.7, "jog-into-box")
	await _wait(0.6)
	await _hold(["move_back"], 2.2, "walk-back")
	await _turn_camera(PI / 2.0, 1.0)
	await _hold(["move_forward", "sprint"], 4.0, "jog-to-block")
	await _wait(0.4)
	await _turn_camera(0.0, 1.0)
	await _hold(["move_forward"], 0.3)
	await _wait(0.3)
	await _hold(["vault"], 0.1)
	await _wait(2.4, "vault-runup")
	await _wait(1.0, "vault-onto")
	await _wait(2.0, "vault-on-block")
	await _wait(1.0)
	await _hold(["move_forward"], 1.6, "walk-off")
	await _wait(1.0)
	quit()


func _turn_camera(to: float, seconds: float) -> void:
	var from := _camera.yaw
	var n := int(seconds * Engine.physics_ticks_per_second)
	for i in n:
		_camera.yaw = lerpf(from, to, smoothstep(0.0, 1.0, float(i + 1) / n))
		await physics_frame


func _hold(actions: Array, seconds: float, still := "") -> void:
	for a in actions:
		Input.action_press(a)
	await _wait(seconds, still)
	for a in actions:
		Input.action_release(a)


func _wait(seconds: float, still := "") -> void:
	for i in int(seconds * Engine.physics_ticks_per_second):
		await physics_frame
	_t += seconds
	if still != "" and _stills != "":
		await process_frame
		var image := root.get_texture().get_image()
		image.save_png(_stills.path_join("%05.1f-%s.png" % [_t, still]))
