extends SceneTree
## Compare mode check (M2.10). Loads the main scene, plays a library clip
## that has `selected.ogv` and `gvhmr/overlay.ogv`, turns Compare on from the
## Clip Viewer bar and checks that the source take, the overlay video and the
## 3D clip stay on one clock: drift under one frame (1/30 s) on every frame
## of a full 5 s play at 1x, at 0.5x and 2x, across a loop and to the end of
## a non-looping clip; timeline scrubs, frame steps and pause seek all three.
##
##   godot --headless --path godot --script tests/check_compare.gd [-- --clip=<id>]
##
## Needs the local library (git-ignored). Drift is the gap between each
## VideoStreamPlayer's `stream_position` and the ClipPlayer's time. Run
## without `--headless` and it also checks the frames on screen: each
## video's texture, every frame of a play at 1x, 2x and 0.5x and on paused
## scrubs, is matched against the file's frames decoded by ffmpeg
## (`ANIM8TE_FFMPEG`, else `ffmpeg` on PATH) and compared with the frame the
## clip's time calls for. Exits 1 on any failed check.

const FRAME := 1.0 / 30.0
## Thumbnail width for the on-screen check's frame matching (aspect kept).
const THUMB_WIDTH := 64
## Frames either side of the expected one that the matching considers; an
## offset at the window's edge fails the check either way.
const MATCH_WINDOW := 4
## A shown frame counts as another frame only when it is closer to that one
## than to the expected frame by this factor: thumbnails of near-still
## frames (the take's first frames) are otherwise a coin toss.
const MATCH_MARGIN := 1.05
## A frame longer than this is a stall: the Theora decoder outputs at most
## one new frame per update, so the frame after a stall can show a stale
## picture (the clock is right; the next update catches up). Samples taken
## right after a stall are reported, not judged.
const STALL_MS := 50
const FILES: PackedStringArray = ["selected.ogv", "gvhmr/overlay.ogv"]

var failed := false
var main: Node
var panel: LibraryPanel
var viewer: ClipViewer
var compare: CompareView
var player: ClipPlayer


func _initialize() -> void:
	main = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	panel = main.get_node("UI/LibraryPanel")
	viewer = main.get_node("UI/ClipViewer")
	compare = main.get_node("UI/CompareView")
	player = main.get_node("Character")
	_run()


func _run() -> void:
	await process_frame
	var id := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--clip="):
			id = arg.trim_prefix("--clip=")
	var others: Array[String] = []
	for entry in panel.entries:
		if entry.playable and _has_videos(entry.path):
			if id == "":
				id = entry.id
			elif entry.id != id:
				others.append(entry.id)
	if id == "":
		_expect(false, "no playable clip under %s has %s (run anim8te transcode <id>)" % [panel.library_root(), FILES])
		return _finish()
	print("  clip %s" % id)

	# Compare starts hidden; the bar's toggle shows it on the playing clip.
	_row(id).select(0)
	_expect(not compare.visible and compare.videos.all(func(v): return not v.is_playing()), "compare hidden, videos idle")
	viewer.compare_check.button_pressed = true
	_expect(compare.visible, "Compare toggle shows the view")
	for i in videos_count():
		var v := compare.videos[i]
		var file: String = v.stream.file if v.stream else ""
		_expect(file.ends_with("clips/%s/%s" % [id, FILES[i]]), "pane %d plays %s" % [i, file.trim_prefix(panel.library_root())])
	_expect(compare.viewport.find_world_3d() == main.get_viewport().find_world_3d(), "3D pane renders the main world")
	_expect(compare.camera.follow and compare.camera.focus_point() != null, "3D pane camera follows the character")
	# The wheel over the 3D pane zooms its camera, not the main one (needs a
	# window: headless lays the UI out in 64x64).
	await process_frame
	await _check_wheel()
	var clip := player.current_clip()

	# Full play at 1x, loop off, from frame 0 to the end.
	viewer.loop_check.button_pressed = false
	viewer.speed_slider.value = 1.0
	player.set_playing(false)
	player.seek_frame(0)
	for i in 5:
		await process_frame  # past the first frames' long deltas (scene load, window)
	player.set_playing(true)
	var run := await _measure(func(): return not player.is_playing(), 8.0)
	_expect(run.max_gap < FRAME, "1x, %d frames over %.2f s of clip: max drift %.1f ms (source), %.1f ms (overlay)" % [run.frames, run.span, run.gaps[0] * 1000, run.gaps[1] * 1000])
	_expect(run.first < 0.2 and run.last >= clip.animation.length - FRAME, "covers the whole clip (%.2f to %.2f s)" % [run.first, run.last])
	_expect(run.resyncs <= 2, "corrective seeks while playing: %d" % run.resyncs)
	await process_frame
	_expect(player.get_frame() == clip.frame_count - 1, "loop off: clip stops on its last frame")
	_expect(_paused_at(player.get_time()), "loop off: videos pause on the clip's last frame (%s)" % _positions())

	# Speed applies to all three.
	for speed in [0.5, 2.0]:
		viewer.speed_slider.value = speed
		player.seek(1.0)
		player.set_playing(true)
		run = await _measure(func(): return player.get_time() > 2.5 or not player.is_playing(), 4.0)
		_expect(run.max_gap < FRAME and run.resyncs <= 2, "%.1fx: max drift %.1f ms over %d frames, %d corrective seeks" % [speed, run.max_gap * 1000, run.frames, run.resyncs])
		var rates_ok: bool = absf(run.clip_rate / speed - 1.0) < 0.1
		for rate in run.video_rates:
			rates_ok = rates_ok and absf(rate / run.clip_rate - 1.0) < 0.02
		_expect(rates_ok, "%.1fx: clip runs %.2fx, videos %.2fx and %.2fx" % [speed, run.clip_rate, run.video_rates[0], run.video_rates[1]])
	viewer.speed_slider.value = 1.0

	# Loop on: across the end and back to the start.
	viewer.loop_check.button_pressed = true
	player.seek(clip.animation.length - 0.5)
	player.set_playing(true)
	var wrapped := [false]
	var last := [player.get_time()]
	run = await _measure(func():
		if player.get_time() < last[0]:
			wrapped[0] = true
		last[0] = player.get_time()
		return wrapped[0] and player.get_time() > 0.5, 3.0)
	_expect(wrapped[0] and run.max_gap < FRAME and run.resyncs <= 2, "loop: wraps with max drift %.1f ms (%d frames, %d corrective seeks)" % [run.max_gap * 1000, run.frames, run.resyncs])

	# Paused: scrub, step and hold.
	player.set_playing(false)
	await process_frame
	for frame in [clip.frame_count / 2, 10, clip.frame_count - 1, 0]:
		viewer.timeline.value = frame
		await process_frame
		_expect(_paused_at(frame / clip.fps), "scrub to frame %d: videos at %s" % [frame, _positions()])
	viewer.timeline.value = 40
	await process_frame
	viewer.forward_button.pressed.emit()
	await process_frame
	_expect(_paused_at(41 / clip.fps), "step forward to 41: videos at %s" % _positions())
	viewer.back_button.pressed.emit()
	viewer.back_button.pressed.emit()
	await process_frame
	_expect(_paused_at(39 / clip.fps), "step back to 39: videos at %s" % _positions())
	for i in 10:
		await process_frame
	_expect(_paused_at(39 / clip.fps), "paused: videos hold at %s" % _positions())

	await _check_screen(id)

	# Another clip with videos swaps the panes' files.
	if not others.is_empty():
		_row(others[0]).select(0)
		await process_frame
		var file: String = compare.videos[0].stream.file
		_expect(file.contains("clips/%s/" % others[0]), "switch to %s: panes follow" % others[0])
		run = await _measure(func(): return player.get_time() > 1.0, 3.0)
		_expect(run.max_gap < FRAME, "%s: max drift %.1f ms" % [others[0], run.max_gap * 1000])

	# Hiding stops the videos.
	viewer.compare_check.button_pressed = false
	await process_frame
	_expect(not compare.visible and compare.videos.all(func(v): return not v.is_playing()), "Compare off: view hidden, videos stopped")
	_finish()


## On-screen check: the frame each video shows, matched by pixels against
## ffmpeg's decode of the file (thumbnails), against floor(t * fps).
func _check_screen(id: String) -> void:
	if DisplayServer.get_name() == "headless":
		print("  skip  on-screen frames (run without --headless)")
		return
	var ffmpeg := OS.get_environment("ANIM8TE_FFMPEG") if OS.has_environment("ANIM8TE_FFMPEG") else "ffmpeg"
	var refs := []
	var fps := []
	var sizes: Array[Vector2i] = []
	for i in videos_count():
		var dir := OS.get_user_data_dir().path_join("check_compare").path_join(str(i))
		DirAccess.make_dir_recursive_absolute(dir)
		for f in DirAccess.get_files_at(dir):
			DirAccess.remove_absolute(dir.path_join(f))
		var src := panel.library_root().path_join("clips").path_join(id).path_join(FILES[i])
		var code := OS.execute(ffmpeg, ["-v", "error", "-i", src, "-vf", "scale=%d:-2" % THUMB_WIDTH, "-start_number", "0", dir.path_join("%04d.png")])
		var frames := []
		while FileAccess.file_exists(dir.path_join("%04d.png" % frames.size())):
			var img := Image.load_from_file(dir.path_join("%04d.png" % frames.size()))
			img.convert(Image.FORMAT_RGB8)
			frames.append(img.get_data())
			if frames.size() == 1:
				sizes.append(img.get_size())
		if code != 0 or frames.is_empty():
			_expect(false, "ffmpeg (%s) decodes %s" % [ffmpeg, FILES[i]])
			return
		refs.append(frames)
		fps.append(CompareView.theora_fps(src))
	print("  on screen: %d and %d frames decoded by ffmpeg" % [refs[0].size(), refs[1].size()])

	viewer.loop_check.button_pressed = false
	for speed in [1.0, 2.0, 0.5]:
		viewer.speed_slider.value = speed
		player.set_playing(false)
		player.seek_frame(0)
		for i in 5:
			await process_frame
		player.set_playing(true)
		# Capture during the play, match after it, so matching does not slow the frames.
		var shots := []
		var last := Time.get_ticks_msec()
		while player.is_playing():
			await process_frame
			var stall := Time.get_ticks_msec() - last > STALL_MS
			last = Time.get_ticks_msec()
			for i in videos_count():
				shots.append([i, _thumb(i, sizes[i]), player.get_time(), stall])
			last = Time.get_ticks_msec()  # the capture's own time is not the app's
		var off := {}
		var stalled := []
		for shot in shots:
			var i: int = shot[0]
			var want := _expected(shot[2], fps[i], refs[i].size())
			var d := _closest(shot[1], refs[i], want) - want
			if shot[3]:
				stalled.append(d)
				continue
			off[d] = off.get(d, 0) + 1
			if absi(d) > 1:
				print("        %s at %.4f s: frame %d shown, %d expected" % [FILES[i], shot[2], want + d, want])
		if not stalled.is_empty():
			print("        %d samples after a stall over %d ms, offsets %s" % [stalled.size(), STALL_MS, stalled])
		var judged := shots.size() - stalled.size()
		var exact: float = off.get(0, 0) / float(judged)
		var within := off.keys().all(func(d): return absi(d) <= 1)
		_expect(within and exact > 0.99, "on screen %.1fx: %.1f %% of %d video frames exact, off by %s" % [speed, exact * 100, judged, off])
	viewer.speed_slider.value = 1.0
	var wrong := 0
	for frame in range(0, player.current_clip().frame_count, 7):
		viewer.timeline.value = frame
		await process_frame
		for i in videos_count():
			var want := _expected(player.get_time(), fps[i], refs[i].size())
			if _closest(_thumb(i, sizes[i]), refs[i], want) != want:
				wrong += 1
	_expect(wrong == 0, "on screen, paused scrubs: %d frames off" % wrong)


## What video `i` shows, as a thumbnail of `size` (RGB8 bytes).
func _thumb(i: int, size: Vector2i) -> PackedByteArray:
	var img := compare.videos[i].get_video_texture().get_image()
	img.convert(Image.FORMAT_RGB8)
	img.resize(size.x, size.y, Image.INTERPOLATE_BILINEAR)
	return img.get_data()


## Index of the decoded frame a thumbnail shows, within MATCH_WINDOW of
## `near` (the expected frame), which wins unless another is clearly closer
## (MATCH_MARGIN). Sums every 5th byte, so all three channels are sampled.
func _closest(data: PackedByteArray, frames: Array, near: int) -> int:
	var best := near
	var best_sum := 1 << 62
	var near_sum := 0
	for j in range(maxi(near - MATCH_WINDOW, 0), mini(near + MATCH_WINDOW + 1, frames.size())):
		var ref: PackedByteArray = frames[j]
		var sum := 0
		for b in range(0, data.size(), 5):
			sum += absi(data[b] - ref[b])
		if j == near:
			near_sum = sum
		if sum < best_sum:
			best_sum = sum
			best = j
	return near if near_sum <= best_sum * MATCH_MARGIN else best


func _expected(t: float, fps: float, count: int) -> int:
	return mini(floori(t * fps + 1e-4), count - 1)


func _check_wheel() -> void:
	if DisplayServer.get_name() == "headless":
		print("  skip  mouse wheel over the 3D pane (run without --headless)")
		return
	var pane: Control = compare.viewport.get_parent()
	var main_cam: Camera3D = main.get_node("Camera3D")
	var before: Array[float] = [compare.camera.distance, main_cam.distance]
	var wheel := InputEventMouseButton.new()
	wheel.button_index = MOUSE_BUTTON_WHEEL_UP
	wheel.pressed = true
	wheel.position = pane.get_global_rect().get_center()
	wheel.global_position = wheel.position
	root.push_input(wheel)
	_expect(compare.camera.distance < before[0] and main_cam.distance == before[1], "wheel over the 3D pane zooms its camera (%.2f -> %.2f m)" % [before[0], compare.camera.distance])


func videos_count() -> int:
	return compare.videos.size()


## Steps frames until `done` returns true (or `limit` seconds pass) and
## returns the largest video-to-clip gap per video, the corrective seeks
## the view made, and the clip's and videos' rates against the wall clock.
## The state read after `process_frame` is the previous frame's, fully
## processed; the first frame (the view catching up with a seek made just
## before) is not measured.
func _measure(done: Callable, limit: float) -> Dictionary:
	var gaps := [0.0, 0.0]
	var frames := 0
	var t_first := -1.0
	var t_last := 0.0
	await process_frame
	compare.resyncs = [0, 0]
	var t0 := player.get_time()
	var v0: Array = compare.videos.map(func(v): return v.stream_position)
	var w0 := Time.get_ticks_usec()
	while (Time.get_ticks_usec() - w0) / 1e6 < limit:
		await process_frame
		if not player.is_playing() and frames > 0 and done.call():
			break
		var t := player.get_time()
		for i in compare.videos.size():
			var v := compare.videos[i]
			gaps[i] = maxf(gaps[i], absf(v.stream_position - minf(t, v.get_stream_length())))
		if t_first < 0.0:
			t_first = t
		t_last = maxf(t_last, t)
		frames += 1
		if done.call():
			break
	var wall := (Time.get_ticks_usec() - w0) / 1e6
	var rates := []
	for i in compare.videos.size():
		rates.append((compare.videos[i].stream_position - v0[i]) / wall)
	return {
		"gaps": gaps, "max_gap": maxf(gaps[0], gaps[1]), "frames": frames, "span": t_last - t_first, "first": t_first, "last": t_last,
		"resyncs": compare.resyncs[0] + compare.resyncs[1], "clip_rate": (player.get_time() - t0) / wall, "video_rates": rates,
	}


func _paused_at(t: float) -> bool:
	for v in compare.videos:
		if not v.paused or absf(v.stream_position - t) > 0.002:
			return false
	return true


func _positions() -> String:
	return "%.3f / %.3f s (clip %.3f s)" % [compare.videos[0].stream_position, compare.videos[1].stream_position, player.get_time()]


func _has_videos(dir: String) -> bool:
	for rel in FILES:
		if not FileAccess.file_exists(dir.path_join(rel)):
			return false
	return true


func _row(id: String) -> TreeItem:
	for item in panel.tree.get_root().get_children():
		if item.get_metadata(0) == id:
			return item
	return null


func _expect(ok: bool, what: String) -> void:
	if not ok:
		failed = true
	print(("  ok    " if ok else "  FAIL  ") + what)


func _finish() -> void:
	print("FAIL" if failed else "PASS")
	quit(1 if failed else 0)
