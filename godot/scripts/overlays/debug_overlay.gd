class_name DebugOverlay
extends MeshInstance3D
## Base of the Gym's debug overlays (M2.8, GDD §6.4). Each overlay is its own
## node under ClipOverlays, which hands it the clip's ClipFeatures (parsed
## from `features.json`) and the current frame; the overlay redraws an
## ImmediateMesh in the clip's space (the ClipPlayer's), unshaded and drawn
## over the character so it stays visible.
##
## Subclasses set `overlay_id` and `title` and implement `_draw_frame`. Drawn
## state is kept in `shapes` (one entry per marker, line or label) so tests
## can check what is shown without reading the mesh.

## Key in the settings file and the panel; stable across sessions.
var overlay_id := ""
var title := ""
## Why nothing is drawn for this clip (missing data), or "".
var note := ""
## What the last frame drew: Array of Dictionaries with at least `kind`.
var shapes: Array[Dictionary] = []
## Line width in metres: lines are drawn as ribbons facing the camera (plain
## one-pixel lines when there is no camera).
var line_width := 0.008

var _mesh := ImmediateMesh.new()
var _line_points := PackedVector3Array()
var _line_colors := PackedColorArray()
var _tri_points := PackedVector3Array()
var _tri_colors := PackedColorArray()
var _labels: Array[Label3D] = []
var _label_count := 0


func _init() -> void:
	mesh = _mesh
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	material.vertex_color_is_srgb = true
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.no_depth_test = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.render_priority = 1
	material_override = material


## Redraws for `frame` of `features` (null clears).
func show_frame(features: ClipFeatures, frame: int) -> void:
	_mesh.clear_surfaces()
	shapes.clear()
	_label_count = 0
	note = ""
	if features != null:
		_draw_frame(features, frame)
	_ribbons()
	_flush(Mesh.PRIMITIVE_TRIANGLES, _tri_points, _tri_colors)
	_flush(Mesh.PRIMITIVE_LINES, _line_points, _line_colors)
	# Packed arrays are passed by value: clear the members here.
	_tri_points.clear()
	_tri_colors.clear()
	_line_points.clear()
	_line_colors.clear()
	for i in _labels.size():
		_labels[i].visible = i < _label_count


## Draws one frame; override.
func _draw_frame(_features: ClipFeatures, _frame: int) -> void:
	pass


func line(a: Vector3, b: Vector3, color: Color) -> void:
	lines([a, b], color)


## Segments between consecutive points.
func polyline(points: PackedVector3Array, color: Color) -> void:
	if points.size() < 2:
		return
	var pairs := PackedVector3Array()
	for i in points.size() - 1:
		pairs.append(points[i])
		pairs.append(points[i + 1])
	lines(pairs, color)


## Line segments, two points each.
func lines(pairs: PackedVector3Array, color: Color) -> void:
	for p in pairs:
		_line_points.append(p)
		_line_colors.append(color)


## Filled disk on the ground plane (y = height) with an outline.
func disk(center: Vector3, radius: float, color: Color, segments := 20) -> void:
	var fill := Color(color, color.a * 0.7)
	for i in segments:
		_triangle(center, center + _ring(i, segments, radius), center + _ring(i + 1, segments, radius), fill)
	var ring := PackedVector3Array()
	for i in segments + 1:
		ring.append(center + _ring(i, segments, radius))
	polyline(ring, color)


## Small filled octahedron, a joint marker.
func marker(center: Vector3, size: float, color: Color) -> void:
	var x := Vector3(size, 0, 0)
	var y := Vector3(0, size, 0)
	var z := Vector3(0, 0, size)
	for sy in [y, -y]:
		for pair in [[x, z], [z, -x], [-x, -z], [-z, x]]:
			_triangle(center + sy, center + pair[0], center + pair[1], color)


## Line with a two-stroke head at `to`.
func arrow(from: Vector3, to: Vector3, color: Color) -> void:
	var d := to - from
	if d.length() < 1e-4:
		return
	var side := d.cross(Vector3.UP)
	if side.length() < 1e-4:
		side = d.cross(Vector3.RIGHT)
	side = side.normalized() * minf(0.04, d.length() * 0.25)
	var back := to - d.normalized() * minf(0.08, d.length() * 0.4)
	lines([from, to, to, back + side, to, back - side], color)


## Text facing the camera at `at`.
func label(at: Vector3, text: String, color: Color) -> void:
	if _label_count == _labels.size():
		var l := Label3D.new()
		l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		l.no_depth_test = true
		l.fixed_size = true
		l.pixel_size = 0.0006
		l.font_size = 28
		l.outline_size = 8
		add_child(l)
		_labels.append(l)
	var l := _labels[_label_count]
	l.position = at
	l.text = text
	l.modulate = color
	_label_count += 1


func _triangle(a: Vector3, b: Vector3, c: Vector3, color: Color) -> void:
	_tri_points.append_array([a, b, c])
	_tri_colors.append_array([color, color, color])


## Turns the line segments into camera-facing quads, when there is a camera.
func _ribbons() -> void:
	var cam := get_viewport().get_camera_3d() if is_inside_tree() else null
	if cam == null or _line_points.is_empty():
		return
	var eye := global_transform.affine_inverse() * cam.global_position
	for i in range(0, _line_points.size(), 2):
		var a := _line_points[i]
		var b := _line_points[i + 1]
		var side := (b - a).cross(eye - (a + b) * 0.5)
		if side.length() < 1e-6:
			continue
		side = side.normalized() * line_width * 0.5
		var c := _line_colors[i]
		_triangle(a - side, a + side, b + side, c)
		_triangle(a - side, b + side, b - side, c)
	_line_points.clear()
	_line_colors.clear()


func _flush(primitive: Mesh.PrimitiveType, points: PackedVector3Array, colors: PackedColorArray) -> void:
	if not points.is_empty():
		_mesh.surface_begin(primitive)
		for i in points.size():
			_mesh.surface_set_color(colors[i])
			_mesh.surface_add_vertex(points[i])
		_mesh.surface_end()


static func _ring(i: int, segments: int, radius: float) -> Vector3:
	var a := TAU * i / segments
	return Vector3(cos(a) * radius, 0, sin(a) * radius)
