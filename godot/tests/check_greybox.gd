extends SceneTree
## Checks the playable grey box (M2.13) by pressing its input actions:
## WASD relative to the camera, the blend speed for walk and jog, collision
## with a box, and the vault onto the vault block. Exits 1 on a failed check.
##
##   godot --headless --path godot --script tests/check_greybox.gd
##
## With a renderer and `--write-movie <file.avi>` it also records the run
## (the M2.13 capture).

const SCENE := "res://scenes/greybox_play.tscn"

var _failures := 0
var _player: GreyboxPlayer
var _camera: FollowCamera


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	var scene: Node = load(SCENE).instantiate()
	root.add_child(scene)
	_player = scene.get_node("Player")
	_camera = scene.get_node("CameraRig")
	await _frames(10)

	# Camera-relative movement: forward goes where the camera looks.
	_place(Vector3(0, 0, 2), PI, 0.0)
	var start := _player.global_position
	await _hold(["move_forward"], 1.5)
	var moved := _player.global_position - start
	_check(moved.z < -1.0 and absf(moved.x) < 0.05, "W with the camera looking -Z moves -Z (moved %s)" % moved)
	_check(absf(_player.blend_speed() - _player.walk_speed) < 0.05, "walking blends at the walk speed (%.2f m/s)" % _player.blend_speed())
	_check(_facing().dot(Vector3.FORWARD) > 0.99, "the model faces where it walks (%s)" % _facing())
	await _hold(["move_forward", "sprint"], 1.5)
	_check(absf(_player.blend_speed() - _player.jog_speed) < 0.05, "sprint blends at the jog speed (%.2f m/s)" % _player.blend_speed())
	await _frames(90)
	_check(_player.blend_speed() < 0.05, "released, it settles to idle (%.2f m/s)" % _player.blend_speed())

	_place(Vector3(0, 0, 2), PI, PI / 2.0)  # camera turned to look -X
	start = _player.global_position
	await _hold(["move_forward"], 1.0)
	moved = _player.global_position - start
	_check(moved.x < -0.6 and absf(moved.z) < 0.05, "W with the camera looking -X moves -X (moved %s)" % moved)
	_place(Vector3(0, 0, 2), PI, PI / 2.0)
	start = _player.global_position
	await _hold(["move_right"], 1.0)
	moved = _player.global_position - start
	_check(moved.z < -0.6 and absf(moved.x) < 0.05, "D with the camera looking -X moves -Z (moved %s)" % moved)

	# Collision: jog into the 1.5 m box (x -3, z -6.5 to -5.5).
	_place(Vector3(-3, 0, -3), PI, 0.0)
	await _hold(["move_forward", "sprint"], 3.0)
	var p := _player.global_position
	_check(p.z > -5.25 and p.z < -5.1 and absf(p.y) < 0.01, "jogging into the 1.5 m box stops at its face (z %.3f, y %.3f)" % [p.z, p.y])
	_check(_player.blend_speed() < 0.1, "against the box the blend drops to idle (%.2f m/s)" % _player.blend_speed())

	# Vault onto the vault block (x -12.75 to -11.25, z -7 to -5, top 0.5 m)
	# from 2.2 m away.
	_place(Vector3(-12, 0, -2.8), PI, 0.0)
	await _frames(5)
	await _hold(["vault"], 0.1)
	_check(_player.is_vaulting(), "E starts the vault")
	var peak := 0.0
	while _player.is_vaulting():
		await physics_frame
		peak = maxf(peak, _player.global_position.distance_to(Vector3(-12, 0, -2.8)))
	await _frames(40)
	p = _player.global_position
	_check(absf(p.y - 0.5) < 0.02 and p.z < -5.0 and p.z > -7.0 and absf(p.x + 12) < 0.6, "the vault ends standing on the block (%s, travel %.2f m)" % [p, peak])
	_check(_player.is_on_floor(), "on the box, the body is on the floor")
	var visual: Node3D = _player.get_node("Visual")
	_check(absf(visual.position.y) < 0.01, "the model is back on the body (%.3f m)" % visual.position.y)

	# Walking off the box and back to the ground.
	await _hold(["move_forward"], 1.5)
	_check(absf(_player.global_position.y) < 0.02, "walking off the box lands on the ground (y %.3f)" % _player.global_position.y)

	print("check_greybox: %s" % ("OK" if _failures == 0 else "%d FAILED" % _failures))
	quit(1 if _failures else 0)


func _place(pos: Vector3, yaw: float, camera_yaw: float) -> void:
	_player.global_transform = Transform3D(Basis(Vector3.UP, yaw), pos)
	_player.velocity = Vector3.ZERO
	_camera.yaw = camera_yaw
	_camera.snap()


func _facing() -> Vector3:
	return _player.global_basis.z


func _hold(actions: Array, seconds: float) -> void:
	for a in actions:
		Input.action_press(a)
	await _frames(int(seconds * Engine.physics_ticks_per_second))
	for a in actions:
		Input.action_release(a)


func _frames(n: int) -> void:
	for i in n:
		await physics_frame


func _check(ok: bool, what: String) -> void:
	print(("  ok    " if ok else "  FAIL  ") + what)
	if not ok:
		_failures += 1
