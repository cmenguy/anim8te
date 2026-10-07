extends Camera3D
## Orbit camera for the Gym. Right or left drag orbits, middle drag (or
## shift + drag) pans, the wheel zooms, F focuses on the character, C toggles
## follow (the orbit centre tracks the character on the ground plane, so the
## view does not bob with the hips). A focus target with a `focus_position()`
## method (ClipPlayer: its hips) is followed through that, otherwise through
## its origin plus `focus_height`. A click or wheel over a GUI control (a
## panel, Compare's 3D pane) is left to the control: wheel events pass
## through even a stopping control.

@export var focus_target: NodePath
@export var focus_height := 1.0  # metres above the target's origin (about hip height)
@export var target := Vector3(0, 1, 0)
@export var distance := 6.0
@export_range(-180, 180) var yaw_deg := 30.0
@export_range(-89, 89) var pitch_deg := -20.0
@export var min_distance := 0.5
@export var max_distance := 60.0
@export var orbit_speed := 0.3  # degrees per pixel
@export var zoom_step := 1.1
@export var follow := false

var _orbiting := false
var _panning := false


func _ready() -> void:
	_apply()


func _process(_delta: float) -> void:
	if not follow:
		return
	var point = focus_point()
	if point != null and (point.x != target.x or point.z != target.z):
		target.x = point.x
		target.z = point.z
		_apply()


## What the camera focuses on and follows, or null without a focus target.
func focus_point() -> Variant:
	var node := get_node_or_null(focus_target) as Node3D
	if node == null:
		return null
	if node.has_method("focus_position"):
		return node.focus_position()
	return node.global_position + Vector3.UP * focus_height


func focus() -> void:
	var point = focus_point()
	if point != null:
		target = point
		distance = 4.0
		_apply()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and get_viewport().gui_get_hovered_control():
		return
	if event is InputEventMouseButton:
		match event.button_index:
			MOUSE_BUTTON_LEFT, MOUSE_BUTTON_RIGHT:
				_orbiting = event.pressed and not event.shift_pressed
				_panning = event.pressed and event.shift_pressed
			MOUSE_BUTTON_MIDDLE:
				_panning = event.pressed
			MOUSE_BUTTON_WHEEL_UP:
				if event.pressed:
					distance = clampf(distance / zoom_step, min_distance, max_distance)
			MOUSE_BUTTON_WHEEL_DOWN:
				if event.pressed:
					distance = clampf(distance * zoom_step, min_distance, max_distance)
		_apply()
	elif event is InputEventMouseMotion:
		if _orbiting:
			yaw_deg = wrapf(yaw_deg - event.relative.x * orbit_speed, -180.0, 180.0)
			pitch_deg = clampf(pitch_deg - event.relative.y * orbit_speed, -89.0, 89.0)
			_apply()
		elif _panning:
			var k := distance * 0.0015
			target += (-global_basis.x * event.relative.x + global_basis.y * event.relative.y) * k
			_apply()
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F:
			focus()
		elif event.keycode == KEY_C:
			follow = not follow


func _apply() -> void:
	var rot := Basis.from_euler(Vector3(deg_to_rad(pitch_deg), deg_to_rad(yaw_deg), 0))
	var eye := target + rot * Vector3(0, 0, distance)
	if is_inside_tree():
		look_at_from_position(eye, target, Vector3.UP)
	else:
		transform = Transform3D(rot, eye)
