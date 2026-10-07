@tool
extends Node3D
## Grey-box calibration level (GDD §6.1): a 40 x 40 m metric ground and props
## sized to standard parkour metrics, each with collision and a size label.
## One unit is one metre. Props are built in code so their sizes live in one
## place; @tool makes them show up in the editor too.

const GROUND_SIZE := 40.0
const GRID_SHADER := preload("res://assets/shaders/grid.gdshader")

const PROP_COLOR := Color(0.58, 0.6, 0.63)
const ACCENT_COLOR := Color(0.85, 0.62, 0.35)

var _prop_material: StandardMaterial3D
var _accent_material: StandardMaterial3D


func _ready() -> void:
	_prop_material = _material(PROP_COLOR)
	_accent_material = _material(ACCENT_COLOR)
	var old := get_node_or_null("Props")
	if old:
		remove_child(old)
		old.free()
	var props := Node3D.new()
	props.name = "Props"
	add_child(props)
	_build_ground(props)
	_build_boxes(props)
	_build_vault_block(props)
	_build_ledge(props)
	_build_gaps(props)
	_build_ramps(props)
	_build_stairs(props)
	_build_beam(props)


func _build_ground(parent: Node3D) -> void:
	var body := StaticBody3D.new()
	body.name = "Ground"
	parent.add_child(body)
	var mesh := PlaneMesh.new()
	mesh.size = Vector2(GROUND_SIZE, GROUND_SIZE)
	var mat := ShaderMaterial.new()
	mat.shader = GRID_SHADER
	mesh.material = mat
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	body.add_child(mi)
	var shape := BoxShape3D.new()
	shape.size = Vector3(GROUND_SIZE, 1.0, GROUND_SIZE)
	var col := CollisionShape3D.new()
	col.shape = shape
	col.position.y = -0.5  # top face at y = 0
	body.add_child(col)


# Step, vault and climb-up heights.
func _build_boxes(parent: Node3D) -> void:
	for i in 3:
		var h := 0.5 * (i + 1)
		var box := _box(parent, "Box%03dcm" % int(h * 100), Vector3(1.0, h, 1.0), Vector3(-7.0 + 2.0 * i, 0, -6.0))
		_label(box, "box %.1f m" % h, h)


# A deeper 0.5 m block, sized like the one in the vault-m05 take: she lands
# on it and shuffles about 0.8 m forward, more than the 1 m boxes leave.
func _build_vault_block(parent: Node3D) -> void:
	var block := _box(parent, "VaultBlock", Vector3(1.5, 0.5, 2.0), Vector3(-12.0, 0, -6.0))
	_label(block, "vault block 0.5 m, 2 m deep", 0.5)


# Hang / climb wall.
func _build_ledge(parent: Node3D) -> void:
	var wall := _box(parent, "LedgeWall", Vector3(4.0, 2.2, 0.5), Vector3(4.0, 0, -6.0))
	_label(wall, "ledge 2.2 m", 2.2)


# Four 2 x 2 m platforms, 1 m high, with 1.5, 2.5 and 3.5 m gaps along +X.
func _build_gaps(parent: Node3D) -> void:
	var size := Vector3(2.0, 1.0, 2.0)
	var gaps := [1.5, 2.5, 3.5]
	var x := -8.0
	for i in gaps.size() + 1:
		var p := _box(parent, "GapPlatform%d" % (i + 1), size, Vector3(x + size.x / 2.0, 0, -13.0))
		_label(p, "platform 1.0 m", size.y)
		if i < gaps.size():
			var gap: float = gaps[i]
			var marker := Node3D.new()
			marker.name = "Gap%03dcm" % int(gap * 100)
			marker.position = Vector3(x + size.x + gap / 2.0, 0, -13.0)
			parent.add_child(marker)
			_label(marker, "gap %.1f m" % gap, size.y + 0.3)
			x += size.x + gap


# Wedges rising 1.5 m along -X; the run follows from the angle.
func _build_ramps(parent: Node3D) -> void:
	var rise := 1.5
	var x := -6.0
	for deg in [20, 35]:
		var run := rise / tan(deg_to_rad(deg))
		var mesh := PrismMesh.new()
		mesh.left_to_right = 0.0  # right-angle wedge, high side at -X
		mesh.size = Vector3(run, rise, 2.0)
		mesh.material = _prop_material
		var body := StaticBody3D.new()
		body.name = "Ramp%ddeg" % deg
		body.position = Vector3(x, rise / 2.0, 6.0)
		parent.add_child(body)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		body.add_child(mi)
		var col := CollisionShape3D.new()
		col.shape = mesh.create_convex_shape()
		body.add_child(col)
		var anchor := Node3D.new()
		anchor.position = Vector3(0, -rise / 2.0, 0)
		body.add_child(anchor)
		_label(anchor, "ramp %d° (rise 1.5 m, run %.2f m)" % [deg, run], rise)
		x += run + 3.0


# Eight steps with 0.18 m risers and 0.30 m treads, climbing along +X.
func _build_stairs(parent: Node3D) -> void:
	var riser := 0.18
	var tread := 0.30
	var steps := 8
	var stairs := Node3D.new()
	stairs.name = "Stairs"
	stairs.position = Vector3(4.0, 0, 6.0)
	parent.add_child(stairs)
	for i in steps:
		var h := riser * (i + 1)
		_box(stairs, "Step%d" % (i + 1), Vector3(tread, h, 1.5), Vector3(tread * (i + 0.5), 0, 0))
	var anchor := Node3D.new()
	anchor.position = Vector3(tread * steps / 2.0, 0, 0)
	stairs.add_child(anchor)
	_label(anchor, "stairs 0.18 m risers, 0.30 m treads", riser * steps)


# Balance beam: 6 m long, 0.15 m wide, top 0.3 m above the ground.
func _build_beam(parent: Node3D) -> void:
	var beam := _box(parent, "Beam", Vector3(6.0, 0.3, 0.15), Vector3(0, 0, 13.0), _accent_material)
	_label(beam, "beam 0.3 m high, 0.15 m wide", 0.3)


## A box resting on `base` (its bottom face centre), with matching collision.
func _box(parent: Node3D, box_name: String, size: Vector3, base: Vector3, mat: Material = null) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = box_name
	body.position = base
	parent.add_child(body)
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = mat if mat else _prop_material
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.position.y = size.y / 2.0
	body.add_child(mi)
	var shape := BoxShape3D.new()
	shape.size = size
	var col := CollisionShape3D.new()
	col.shape = shape
	col.position.y = size.y / 2.0
	body.add_child(col)
	return body


func _label(parent: Node3D, text: String, top: float) -> void:
	var label := Label3D.new()
	label.name = "Label"
	label.text = text
	label.position.y = top + 0.35
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.pixel_size = 0.008
	label.font_size = 40
	label.outline_size = 10
	label.modulate = Color(1, 1, 1)
	label.outline_modulate = Color(0.1, 0.1, 0.1)
	parent.add_child(label)


func _material(color: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = 0.85
	return m
