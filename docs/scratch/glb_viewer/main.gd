# Throwaway M1.11 viewer: loads a skeleton-only motion.glb at runtime, draws each bone as a
# capsule, plays its animation and frames it from a front three-quarter view.
# Usage: godot --path <this dir> [--write-movie out.avi --fixed-fps 30] -- <motion.glb>
extends Node3D

var skel: Skeleton3D
var bones := {}  # bone index -> MeshInstance3D
var label: Label3D

func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var path: String = args[0]
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_file(path, state)
	assert(err == OK, "cannot load %s" % path)
	var scene := doc.generate_scene(state)
	add_child(scene)
	skel = scene.find_children("*", "Skeleton3D", true, false)[0]
	var player: AnimationPlayer = scene.find_children("*", "AnimationPlayer", true, false)[0]
	var anim_name: StringName = player.get_animation_list()[0]
	player.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
	player.play(anim_name)
	player.advance(0.0)
	print("loaded %s: %d bones, animation %s (%.2f s)" % [path.get_file(), skel.get_bone_count(), anim_name, player.get_animation(anim_name).length])

	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.85, 0.55, 0.25)
	for i in skel.get_bone_count():
		if skel.get_bone_parent(i) < 0:
			continue
		var mi := MeshInstance3D.new()
		var cap := CapsuleMesh.new()
		cap.radius = 0.035
		mi.mesh = cap
		mi.material_override = mat
		add_child(mi)
		bones[i] = mi
	var head := skel.find_bone("Head")
	if head >= 0:
		var hm := MeshInstance3D.new()
		var sphere := SphereMesh.new()
		sphere.radius = 0.1
		sphere.height = 0.2
		hm.mesh = sphere
		hm.material_override = mat
		add_child(hm)
		bones[-head - 1] = hm

	var floor := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(4, 4)
	floor.mesh = plane
	var fm := StandardMaterial3D.new()
	fm.albedo_color = Color(0.3, 0.32, 0.35)
	floor.material_override = fm
	add_child(floor)
	for k in range(-4, 5):
		_line(Vector3(k * 0.5, 0.001, -2), Vector3(k * 0.5, 0.001, 2))
		_line(Vector3(-2, 0.001, k * 0.5), Vector3(2, 0.001, k * 0.5))

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	sun.shadow_enabled = true
	add_child(sun)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.12, 0.13, 0.15)
	env.environment.ambient_light_color = Color(0.5, 0.5, 0.55)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	add_child(env)
	var cam := Camera3D.new()
	add_child(cam)
	cam.position = Vector3(1.4, 1.25, 1.9)
	cam.look_at(Vector3(0, 0.8, 0))

	label = Label3D.new()
	label.text = "%s  (Godot %s)" % [path.get_file().get_basename() if path.get_file() != "motion.glb" else path.get_base_dir().get_file(), Engine.get_version_info().string]
	label.pixel_size = 0.0015
	label.position = Vector3(0, 1.9, 0)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	add_child(label)

func _line(a: Vector3, b: Vector3) -> void:
	var mi := MeshInstance3D.new()
	var im := ImmediateMesh.new()
	im.surface_begin(Mesh.PRIMITIVE_LINES)
	im.surface_add_vertex(a)
	im.surface_add_vertex(b)
	im.surface_end()
	mi.mesh = im
	add_child(mi)

func _process(_dt: float) -> void:
	for i in bones:
		var mi: MeshInstance3D = bones[i]
		if i < 0:
			var g := skel.global_transform * skel.get_bone_global_pose(-i - 1)
			mi.global_position = g.origin + g.basis.y.normalized() * 0.1
			continue
		var a := (skel.global_transform * skel.get_bone_global_pose(skel.get_bone_parent(i))).origin
		var b := (skel.global_transform * skel.get_bone_global_pose(i)).origin
		var d := b - a
		var len := d.length()
		var cap: CapsuleMesh = mi.mesh
		cap.height = max(len + 0.07, 0.08)
		mi.global_position = (a + b) * 0.5
		if len > 1e-4:
			var y := d / len
			var x := y.cross(Vector3.FORWARD if abs(y.z) < 0.9 else Vector3.RIGHT).normalized()
			mi.global_basis = Basis(x, y, x.cross(y))
