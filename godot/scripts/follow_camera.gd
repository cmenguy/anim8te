class_name FollowCamera
extends Node3D
## Third-person follow camera for the grey-box character (M2.13). The rig sits
## at the target's chest height and follows it smoothly; a SpringArm3D pulls
## the camera in when a prop is in the way. The mouse turns it while captured
## (click to capture, Esc to release), the wheel zooms. The rig's yaw is what
## the player's WASD is relative to.

@export var target_path: NodePath
@export var height := 1.4
@export var distance := 4.0
@export var min_distance := 1.5
@export var max_distance := 8.0
@export var mouse_sensitivity := 0.004
@export var follow_sharpness := 10.0
@export var capture_mouse := true

var yaw := 0.0
var pitch := -0.3

var _target: Node3D
@onready var _arm: SpringArm3D = $SpringArm3D


func _ready() -> void:
	top_level = true
	_target = get_node_or_null(target_path)
	if _target is CollisionObject3D:
		_arm.add_excluded_object(_target.get_rid())
	if _target:
		global_position = _target.global_position + Vector3.UP * height
	if capture_mouse and DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_apply()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= event.relative.x * mouse_sensitivity
		pitch = clampf(pitch - event.relative.y * mouse_sensitivity, -1.2, 0.5)
	elif event is InputEventMouseButton and event.pressed:
		match event.button_index:
			MOUSE_BUTTON_WHEEL_UP:
				distance = maxf(min_distance, distance * 0.9)
			MOUSE_BUTTON_WHEEL_DOWN:
				distance = minf(max_distance, distance / 0.9)
			MOUSE_BUTTON_LEFT:
				Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _physics_process(delta: float) -> void:
	if _target:
		var goal := _target.global_position + Vector3.UP * height
		global_position = global_position.lerp(goal, 1.0 - exp(-follow_sharpness * delta))
	_apply()


func snap() -> void:
	if _target:
		global_position = _target.global_position + Vector3.UP * height
	_apply()


func _apply() -> void:
	rotation = Vector3(pitch, yaw, 0)
	_arm.spring_length = distance
