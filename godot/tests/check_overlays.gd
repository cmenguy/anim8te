extends SceneTree
## Debug overlays check (M2.8). Loads the main scene, plays library clips and
## turns on each overlay: every overlay is its own node fed from the clip's
## features.json, what it draws matches the file frame by frame, toggles
## survive a clip change, and a second session (a fresh main scene on the
## same settings file) comes back with the same toggles.
##
##   godot --headless --path godot --script tests/check_overlays.gd
##
## Needs the local library (git-ignored) with two clips that have a
## motion.glb and a features.json from `anim8te clean` (M2.8 or later), and
## at least one contact frame and one sole under the ground across them.
## Uses its own settings file, never the user's. Exits 1 on any failed check.

const SETTINGS := "user://check_overlays.cfg"
const IDS: PackedStringArray = ["foot_contacts", "root_trajectory", "velocity", "ground_penetration", "skeleton", "jerk_heatmap"]

var failed := false
var main: Node
var player: ClipPlayer
var overlays: ClipOverlays
var panel: OverlayPanel


func _initialize() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS))
	_run()


func _open_main() -> void:
	main = load("res://scenes/main.tscn").instantiate()
	main.get_node("Character/Overlays").settings_path = SETTINGS
	root.add_child(main)
	player = main.get_node("Character")
	overlays = main.get_node("Character/Overlays")
	panel = main.get_node("UI/OverlayPanel")


func _run() -> void:
	_open_main()
	await process_frame

	# One node per overlay, all off on a first run.
	_expect(overlays.ids() == IDS, "overlay ids %s" % overlays.ids())
	for id in IDS:
		var node: Node = overlays.overlays[id]
		_expect(node is DebugOverlay and node.get_parent() == overlays, "%s is its own DebugOverlay node (%s)" % [id, node.name])
		_expect(not overlays.is_enabled(id) and not panel.checks[id].button_pressed, "%s off on a first run" % id)

	var clips := _clips_with_features()
	if clips.size() < 2:
		_expect(false, "need two clips with motion.glb and features.json under %s, found %s" % [player.library_root(), clips])
		return _finish()
	var first: String = clips[0]
	var second: String = clips[1]

	var t0 := Time.get_ticks_usec()
	player.play(first)
	print("  %s: play + features.json load %.1f ms" % [first, (Time.get_ticks_usec() - t0) / 1000.0])
	player.set_playing(false)
	var f := overlays.features
	_expect(f != null and overlays.status == "", "%s: features loaded (%s)" % [first, overlays.status])
	if f == null:
		return _finish()
	_expect(f.num_frames == player.current_clip().frame_count, "features frames %d = clip frames %d" % [f.num_frames, player.current_clip().frame_count])

	# Same space as the source skeleton: the root track is the Hips.
	var worst := 0.0
	for frame in [0, f.num_frames / 3, f.num_frames - 1]:
		player.seek_frame(frame)
		await process_frame
		var hips := player.source.global_transform * player.source.get_bone_global_pose(0).origin
		worst = maxf(worst, (hips - overlays.global_transform * f.root_position[frame]).length())
	_expect(worst < 0.002, "root track matches the playing Hips (worst %.4f m)" % worst)

	# Turning each on through the panel draws it.
	for id in IDS:
		panel.checks[id].button_pressed = true
	for id in IDS:
		_expect(overlays.is_enabled(id), "%s on from the panel" % id)
	await _check_clip(first)

	# Toggles survive a clip change; the overlays redraw from the new file.
	panel.checks["velocity"].button_pressed = false
	player.play(second)
	player.set_playing(false)
	await process_frame
	_expect(overlays.features != f and overlays.features.path.contains(second), "features follow the clip (%s)" % second)
	for id in IDS:
		_expect(overlays.is_enabled(id) == (id != "velocity"), "%s kept across the clip change" % id)
	panel.checks["velocity"].button_pressed = true
	await _check_clip(second)

	# Key 2 toggles the second overlay, and the panel follows.
	_press(KEY_2)
	_expect(not overlays.is_enabled("root_trajectory") and not panel.checks["root_trajectory"].button_pressed, "key 2 turns root trajectory off")
	_press(KEY_4)
	_expect(not overlays.is_enabled("ground_penetration"), "key 4 turns ground penetration off")

	# A new session restores the saved toggles.
	main.free()
	await process_frame
	_open_main()
	await process_frame
	for id in IDS:
		var want := id not in ["root_trajectory", "ground_penetration"]
		_expect(overlays.is_enabled(id) == want and panel.checks[id].button_pressed == want, "%s restored as %s in a new session" % [id, want])
	player.play(first)
	await process_frame
	_expect(overlays.overlays["skeleton"].mesh.get_surface_count() > 0, "restored overlays draw")
	main.free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS))
	_finish()


## Steps through every frame of the current clip and checks each overlay
## against features.json.
func _check_clip(id: String) -> void:
	var f := overlays.features
	var o := overlays.overlays
	var contacts := 0
	var sliding := 0
	var penetrations := 0
	var expected_penetrations := 0
	var deepest := 0.0
	var tolerance: float = o["ground_penetration"].tolerance_m
	var slide: float = o["foot_contacts"].slide_mps
	var drew := {}
	var ok := {"contacts": true, "trajectory": true, "velocity": true, "penetration": true, "skeleton": true, "jerk": true}
	for frame in f.num_frames:
		player.seek_frame(frame)
		overlays.refresh()
		for overlay in o.values():
			if overlay.mesh.get_surface_count() > 0:
				drew[overlay.overlay_id] = true
		# Foot contacts: exactly the flagged joints, red when slipping.
		var flagged := 0
		for bone in ClipFeatures.CONTACT_BONES:
			flagged += 1 if f.in_contact(frame, bone) else 0
		var shown: Array = o["foot_contacts"].shapes
		if shown.size() != flagged:
			ok.contacts = false
		for s in shown:
			contacts += 1
			sliding += 1 if s.sliding else 0
			if s.sliding != (f.slip_speed(frame, f.joint(s.bone)) > slide) or not f.in_contact(frame, s.bone):
				ok.contacts = false
		# Root trajectory: up to 1 s either side, clamped at the ends.
		var span := roundi(f.fps)
		var t: Dictionary = o["root_trajectory"].shapes[0]
		if t.past != mini(frame, span) + 1 or t.future != mini(f.num_frames - 1 - frame, span) + 1:
			ok.trajectory = false
		# Velocity: the Hips arrow is root_velocity.
		var v: Dictionary = o["velocity"].shapes[0]
		if v.bone != "Hips" or not v.velocity.is_equal_approx(f.root_velocity[frame]) or o["velocity"].shapes.size() != 5:
			ok.velocity = false
		# Ground penetration: every joint under the ground, and only those.
		var under := 0
		for j in f.bone_names.size():
			var bone := f.bone_names[j]
			var depth := -f.sole_height(frame, bone) if bone in ClipFeatures.CONTACT_BONES else -f.position(frame, j).y
			if depth > tolerance:
				under += 1
				deepest = maxf(deepest, depth)
		expected_penetrations += under
		penetrations += o["ground_penetration"].shapes.size()
		if o["ground_penetration"].shapes.size() != under:
			ok.penetration = false
		# Skeleton: 22 joints, 21 bones.
		var sk: Dictionary = o["skeleton"].shapes[0]
		if sk.joints != 22 or sk.bones != 21:
			ok.skeleton = false
		# Jerk: one marker per joint, coloured from joint_jerk.
		var jerk: Array = o["jerk_heatmap"].shapes
		if jerk.size() != 22:
			ok.jerk = false
		else:
			for j in 22:
				if not is_equal_approx(jerk[j].jerk, f.joint_jerk[frame][j]) or jerk[j].color != o["jerk_heatmap"].color_for(f.joint_jerk[frame][j]):
					ok.jerk = false
	for key in ok:
		_expect(ok[key], "%s: %s overlay matches features.json on all %d frames" % [id, key, f.num_frames])
	_expect(f.rest_heights_above_sole.size() == 4, "%s: features.json has rest_heights_above_sole" % id)
	for overlay_id in IDS:
		var want := overlay_id != "ground_penetration" or expected_penetrations > 0
		_expect(drew.get(overlay_id, false) == want, "%s: %s draws geometry: %s" % [id, overlay_id, want])
	print("  %s: %d contact markers (%d sliding, %.0f %%), %d penetrations (deepest %.1f mm)" % [
		id, contacts, sliding, 100.0 * sliding / maxi(contacts, 1), penetrations, deepest * 1000.0])
	_expect(contacts > 0, "%s: some contact markers" % id)
	_expect(penetrations == expected_penetrations, "%s: penetrations %d = expected %d" % [id, penetrations, expected_penetrations])
	await process_frame


func _clips_with_features() -> Array:
	var out := []
	for entry in LibraryScanner.scan(player.library_root()):
		if entry.playable and FileAccess.file_exists(entry.path.path_join("features.json")):
			out.append(entry.id)
	return out


func _press(key: Key) -> void:
	var event := InputEventKey.new()
	event.keycode = key
	event.pressed = true
	panel._input(event)


func _expect(ok: bool, what: String) -> void:
	print(("  ok   " if ok else "  FAIL ") + what)
	if not ok:
		failed = true


func _finish() -> void:
	print("FAILED" if failed else "PASSED")
	quit(1 if failed else 0)
