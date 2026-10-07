extends SceneTree
## Video playback check (M2.9). Plays a library clip's `selected.ogv` and
## `gvhmr/overlay.ogv` (the Ogg Theora copies `anim8te extract` writes) in a
## VideoStreamPlayer: each loads, reports its length, advances while playing,
## seeks, and decodes frames of the source's size.
##
##   godot --headless --path godot --script tests/check_video_playback.gd [-- --clip=<id>]
##
## Needs the local library (git-ignored) with a clip that has both files
## (`anim8te transcode <id>` writes them for clips extracted before M2.9).
## Exits 1 on any failed check.

const FILES: PackedStringArray = ["selected.ogv", "gvhmr/overlay.ogv"]
var failed := false


func _initialize() -> void:
	_run()


func _run() -> void:
	await process_frame  # nodes can only play once the tree is running
	var root_dir := LibraryScanner.resolve_root()
	var clip := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--clip="):
			clip = arg.trim_prefix("--clip=")
	if clip == "":
		for entry in LibraryScanner.scan(root_dir):
			if _has_all(entry.path):
				clip = entry.id
				break
	if clip == "":
		_expect(false, "no clip under %s has %s (run anim8te transcode <id>)" % [root_dir, FILES])
		return _finish()
	print("  clip %s" % clip)
	for rel in FILES:
		await _check_file(root_dir.path_join("clips").path_join(clip).path_join(rel))
	_finish()


func _has_all(dir: String) -> bool:
	for rel in FILES:
		if not FileAccess.file_exists(dir.path_join(rel)):
			return false
	return true


func _check_file(path: String) -> void:
	var stream := VideoStreamTheora.new()
	stream.file = path
	var player := VideoStreamPlayer.new()
	player.stream = stream
	player.volume_db = -80.0
	root.add_child(player)
	player.play()
	await process_frame
	var name := path.get_file()
	var length := player.get_stream_length()
	_expect(player.is_playing(), "%s: playing" % name)
	_expect(length > 4.0 and length < 6.0, "%s: length %.2f s (5 s take)" % [name, length])

	# Plays in real time: about half a second of frames.
	var t0 := Time.get_ticks_msec()
	while Time.get_ticks_msec() - t0 < 500:
		await process_frame
	var pos := player.stream_position
	_expect(pos > 0.3 and pos < 0.8, "%s: position advances (%.2f s after 0.5 s)" % [name, pos])

	var tex := player.get_video_texture()
	var size := tex.get_size() if tex else Vector2.ZERO
	var want := Vector2(768, 960) if name == "selected.ogv" else Vector2(768, 480)
	_expect(size == want, "%s: frames are %s (source %s)" % [name, size, want])

	# Seek, as Compare mode's shared timeline will.
	player.paused = true
	player.stream_position = 3.0
	await process_frame
	await process_frame
	_expect(absf(player.stream_position - 3.0) < 0.1, "%s: seek to 3.0 s lands at %.2f s" % [name, player.stream_position])

	# Plays to the end and stops.
	player.paused = false
	player.stream_position = length - 0.3
	t0 = Time.get_ticks_msec()
	while player.is_playing() and Time.get_ticks_msec() - t0 < 3000:
		await process_frame
	_expect(not player.is_playing(), "%s: stops at the end" % name)
	player.queue_free()
	await process_frame


func _expect(ok: bool, what: String) -> void:
	print(("  ok   " if ok else "  FAIL ") + what)
	if not ok:
		failed = true


func _finish() -> void:
	print("FAILED" if failed else "PASSED")
	quit(1 if failed else 0)
