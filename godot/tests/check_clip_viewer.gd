extends SceneTree
## Clip Viewer check (M2.6). Loads the main scene, selects library clips in
## the library panel and drives the viewer bar: play/pause, frame stepping,
## timeline scrub, speed range, loop on and off, camera follow, clip switch
## time, and the frame/time readout.
##
##   godot --headless --path godot --script tests/check_clip_viewer.gd
##
## Needs the local library (git-ignored) with at least two clips that have a
## motion.glb. Exits 1 on any failed check.

## A clip switch must fit in one 60 fps frame.
const MAX_SWITCH_MS := 16.0

var failed := false
var main: Node
var panel: LibraryPanel
var viewer: ClipViewer
var player: ClipPlayer
var cam: Node


func _initialize() -> void:
	main = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	panel = main.get_node("UI/LibraryPanel")
	viewer = main.get_node("UI/ClipViewer")
	player = main.get_node("Character")
	cam = main.get_node("Camera3D")
	_run()


func _run() -> void:
	await process_frame
	_expect(viewer.clip_label.text == "Select a clip in the library", "idle: %s" % viewer.clip_label.text)
	_expect(viewer.play_button.disabled and not viewer.timeline.editable, "idle: transport disabled")

	var playable: Array[String] = []
	var unplayable := ""
	for entry in panel.entries:
		if entry.playable:
			playable.append(entry.id)
		elif unplayable == "":
			unplayable = entry.id
	if playable.size() < 2:
		_expect(false, "need two playable clips under %s, found %s" % [panel.library_root(), playable])
		return _finish()
	var first := playable[0]
	var second := playable[1]

	# Selecting a clip plays it.
	_row(first).select(0)
	_expect(player.clip_id == first and player.is_playing(), "select %s: playing" % first)
	var clip := player.current_clip()
	_expect(clip.frame_count > 1 and is_equal_approx(clip.fps, 30.0), "%s: %d frames at %.2f fps" % [first, clip.frame_count, clip.fps])
	_expect(viewer.timeline.max_value == clip.frame_count - 1, "timeline spans the clip's frames")
	var t0 := player.get_time()
	for i in 10:
		await process_frame
	_expect(player.get_time() > t0, "time advances while playing (%.3f -> %.3f s)" % [t0, player.get_time()])

	# Pause holds the frame.
	viewer.play_button.pressed.emit()
	_expect(not player.is_playing(), "play button pauses")
	var held := player.get_frame()
	for i in 5:
		await process_frame
	_expect(player.get_frame() == held, "paused: frame holds at %d" % held)
	_expect(viewer.play_button.text == "Play", "button reads Play when paused")

	# Frame stepping, with and without loop.
	player.seek_frame(10)
	viewer.forward_button.pressed.emit()
	_expect(player.get_frame() == 11, "step forward: frame %d" % player.get_frame())
	viewer.back_button.pressed.emit()
	viewer.back_button.pressed.emit()
	_expect(player.get_frame() == 9, "step back twice: frame %d" % player.get_frame())
	player.seek_frame(0)
	player.step(-1)
	_expect(player.get_frame() == clip.frame_count - 1, "loop on: step back from 0 wraps to %d" % player.get_frame())
	viewer.loop_check.button_pressed = false
	_expect(not player.loop and clip.animation.loop_mode == Animation.LOOP_NONE, "loop toggle off")
	player.step(1)
	_expect(player.get_frame() == clip.frame_count - 1, "loop off: step past the end stays on the last frame")
	player.seek_frame(0)
	player.step(-1)
	_expect(player.get_frame() == 0, "loop off: step before the start stays on 0")

	# Scrub: the timeline moves the pose.
	await process_frame
	var hips_start := player.focus_position()
	viewer.timeline.value = clip.frame_count / 2
	_expect(player.get_frame() == clip.frame_count / 2, "timeline scrub to frame %d" % player.get_frame())
	await process_frame
	var hips_mid := player.focus_position()
	_expect(hips_start.distance_to(hips_mid) > 0.001, "scrub changes the pose (hips moved %.3f m)" % hips_start.distance_to(hips_mid))
	await process_frame
	var readout := "frame %d / %d   %.2f / %.2f s" % [clip.frame_count / 2, clip.frame_count - 1, player.get_time(), clip.animation.length]
	_expect(viewer.position_label.text == readout, "readout: '%s'" % viewer.position_label.text)

	# Speed range.
	viewer.speed_slider.value = 0.1
	_expect(is_equal_approx(player.player.speed_scale, 0.1), "speed 0.1x")
	viewer.speed_slider.value = 2.0
	_expect(is_equal_approx(player.player.speed_scale, 2.0), "speed 2x")
	player.speed = 5.0
	_expect(is_equal_approx(player.speed, 2.0), "speed clamps to 2x")
	player.speed = 0.0
	_expect(is_equal_approx(player.speed, 0.1), "speed clamps to 0.1x")
	await process_frame
	_expect(is_equal_approx(viewer.speed_slider.value, 0.1) and viewer.speed_label.text == "0.10x", "speed bar follows the player: %s" % viewer.speed_label.text)
	viewer.speed_slider.value = 2.0

	# Loop off: play to the end, stop on the last frame, play again restarts.
	player.seek_frame(clip.frame_count - 4)
	player.set_playing(true)
	for i in 30:
		await process_frame
	_expect(not player.is_playing() and player.get_frame() == clip.frame_count - 1, "loop off: stops on the last frame")
	player.set_playing(true)
	_expect(player.is_playing() and player.get_frame() == 0, "play at the end restarts from frame 0")
	viewer.loop_check.button_pressed = true
	_expect(player.loop and clip.animation.loop_mode == Animation.LOOP_LINEAR, "loop toggle on")
	player.seek_frame(clip.frame_count - 4)
	player.set_playing(true)
	for i in 30:
		await process_frame
	_expect(player.is_playing() and player.get_frame() < clip.frame_count - 4, "loop on: wraps to frame %d" % player.get_frame())

	# Camera follow tracks the hips on the ground plane.
	viewer.follow_check.button_pressed = true
	_expect(cam.follow, "follow toggle")
	var y: float = cam.target.y
	for i in 3:
		await process_frame
	var hips := player.focus_position()
	await process_frame
	var hips_now := player.focus_position()
	var off := Vector2(cam.target.x - hips_now.x, cam.target.z - hips_now.z).length()
	_expect(off < 0.05 and cam.target.y == y, "follow: orbit centre on the hips (%.3f m off), height kept" % off)
	_expect(hips.distance_to(hips_now) > 0.0, "hips moving while following")
	viewer.follow_check.button_pressed = false
	_expect(not cam.follow, "follow off")

	# Switching clips.
	var start := Time.get_ticks_usec()
	_row(second).select(0)
	var cold := (Time.get_ticks_usec() - start) / 1000.0
	_expect(player.clip_id == second and player.is_playing(), "switch to %s" % second)
	_expect(viewer.clip_label.text.begins_with(second), "clip label: %s" % viewer.clip_label.text)
	start = Time.get_ticks_usec()
	_row(first).select(0)
	var warm := (Time.get_ticks_usec() - start) / 1000.0
	_expect(cold < MAX_SWITCH_MS and warm < MAX_SWITCH_MS, "switch time %.2f ms first load, %.2f ms cached" % [cold, warm])
	_expect(player.get_frame() <= 1, "switch starts the clip at frame 0")

	if unplayable != "":
		_row(unplayable).select(0)
		_expect(player.clip_id == first and viewer.clip_label.text.contains("no motion.glb"), "unplayable %s: %s" % [unplayable, viewer.clip_label.text])
	_finish()


func _finish() -> void:
	print("FAIL" if failed else "PASS")
	quit(1 if failed else 0)


func _row(id: String) -> TreeItem:
	for item in panel.tree.get_root().get_children():
		if item.get_metadata(0) == id:
			return item
	return null


func _expect(ok: bool, what: String) -> void:
	if not ok:
		failed = true
	print(("  ok    " if ok else "  FAIL  ") + what)
