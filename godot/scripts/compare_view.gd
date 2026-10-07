class_name CompareView
extends PanelContainer
## Compare mode (M2.10, GDD §6.3): the clip's source take (`selected.ogv`),
## GVHMR's overlay render (`gvhmr/overlay.ogv`) and the 3D clip side by side,
## all on the ClipPlayer's clock. Built in code; hidden until shown (the Clip
## Viewer's Compare toggle, key V).
##
##   [ source take ] [ 3D clip       ]
##                   [ GVHMR overlay ]
##
## The ClipPlayer's animation time is the master clock: the Clip Viewer's
## transport (play/pause, scrub, step, speed, loop) acts on it as in Clip
## Viewer mode, and every frame the two VideoStreamPlayers follow it. Clip
## time t is video time t: GVHMR resamples the take to 30 fps without
## trimming it.
##
## A VideoStreamPlayer advances by the frame's process delta times its
## `speed_scale`, as the AnimationPlayer does, so at the same speed the two
## stay together on their own. A Theora seek costs 10 to 35 ms, so while
## playing the videos only seek on a jump (a loop, a scrub, a step) or a gap
## over `SEEK_TOLERANCE`; while paused they seek whenever the player's time
## moves, which is frame-exact. A video is also held (paused) on its last
## frame: running there, the decoder finds no next frame, stops and rewinds
## to frame 0. `play()` and unpausing re-enable a VideoStreamPlayer's
## processing too late for that frame, which leaves it a frame behind, so
## after either the video is seeked once more on the next frame.
##
## The order matters: this node processes after the ClipPlayer (earlier in
## the tree) and before its own VideoStreamPlayer children, so it sees this
## frame's clip time and the videos' positions before their update, and
## compares the clip with where that update will put them. A seek makes the
## video skip its next update, so a seek here lands exactly on the clip's
## time.
##
## The 3D pane is a SubViewport sharing the main world, with its own orbit
## camera following the character, so debug overlays show there too.

## Video files per pane, relative to the clip directory.
const FILES: PackedStringArray = ["selected.ogv", "gvhmr/overlay.ogv"]
const TITLES: PackedStringArray = ["Source take", "GVHMR overlay"]
## Largest video-to-clip gap while playing before a corrective seek, in
## seconds: half a frame at 30 fps.
const SEEK_TOLERANCE := 0.5 / 30.0
## Smallest gap that re-seeks a paused video.
const PAUSED_TOLERANCE := 1e-3
## Seeks land this far past the clip's time: a Theora seek to the exact
## start of frame k (k / fps, the clip's frame times) shows frame k - 1.
const SEEK_PAST := 1e-4

@export var clip_player: NodePath

var player: ClipPlayer
## The source and overlay players, in FILES order; a null stream when the
## clip has no such file.
var videos: Array[VideoStreamPlayer] = []
var titles: Array[Label] = []
var frames: Array[AspectRatioContainer] = []
var viewport: SubViewport
var camera: Camera3D
## Corrective seeks made while playing, per video (for the check script).
var resyncs: Array[int] = [0, 0]
## Per video: started or unpaused last frame, so seek again this frame.
var _settle: Array[bool] = [false, false]
## Per video: one frame's duration in seconds, from its Theora header.
var _frame_time: Array[float] = [1.0 / 30.0, 1.0 / 30.0]
var _clip_dir := ""


func _ready() -> void:
	player = get_node_or_null(clip_player) as ClipPlayer
	_build()
	if player:
		player.clip_changed.connect(func(_id): _load_videos())
	visibility_changed.connect(_on_visibility_changed)
	_on_visibility_changed()


## Shows or hides the view; hidden, the videos stop and the 3D pane stops rendering.
func set_active(on: bool) -> void:
	visible = on


func is_active() -> bool:
	return visible


func _on_visibility_changed() -> void:
	if not visible:
		for v in videos:
			v.stop()
		return
	_load_videos()


func _load_videos() -> void:
	if not visible:
		return
	var clip := player.current_clip() if player else null
	var dir := player.library_root().path_join("clips").path_join(clip.id) if clip else ""
	if dir == _clip_dir:
		return
	_clip_dir = dir
	resyncs = [0, 0]
	_settle = [false, false]
	_frame_time = [1.0 / 30.0, 1.0 / 30.0]
	for i in videos.size():
		var v := videos[i]
		v.stop()
		v.stream = null
		var path := dir.path_join(FILES[i]) if dir != "" else ""
		if path != "" and FileAccess.file_exists(path):
			var stream := VideoStreamTheora.new()
			stream.file = path
			v.stream = stream
			_frame_time[i] = 1.0 / theora_fps(path)
			titles[i].text = "%s   %s" % [TITLES[i], FILES[i]]
			frames[i].visible = true
		else:
			titles[i].text = "%s: no %s (run anim8te transcode %s)" % [TITLES[i], FILES[i], clip.id] if clip else TITLES[i]
			frames[i].visible = false
	_sync_videos()


func _process(_delta: float) -> void:
	if visible:
		_sync_videos()


## Puts both videos on the player's time, speed and play state.
func _sync_videos() -> void:
	var clip := player.current_clip() if player else null
	if clip == null:
		return
	var playing := player.is_playing()
	var t := player.get_time()
	var delta := get_process_delta_time()
	for i in videos.size():
		var v := videos[i]
		if v.stream == null:
			continue
		var tex := v.get_video_texture()
		if tex and tex.get_width() > 0:
			frames[i].ratio = float(tex.get_width()) / tex.get_height()
		var length := v.get_stream_length()
		var target := minf(t, length)
		# Runs while the clip plays, short of the video's last frame.
		var run := playing and target < length - _frame_time[i]
		var jumped := _settle[i]
		_settle[i] = false
		if not v.is_playing():
			v.play()  # never started, or the decoder hit the end of the stream
			jumped = true
			_settle[i] = run
		if v.paused == run:
			v.paused = not run
			jumped = true
			_settle[i] = run
		v.speed_scale = player.speed
		# Where the video will be once its own update this frame has run.
		var at := v.stream_position + (delta * v.speed_scale if run else 0.0)
		if jumped or absf(at - target) > (SEEK_TOLERANCE if run else PAUSED_TOLERANCE):
			v.stream_position = minf(target + SEEK_PAST, length)
			if run and not jumped:
				resyncs[i] += 1


## Frame rate of an Ogg Theora file, from its identification header (FRN
## and FRD, big-endian, 22 bytes into the packet); 30 if it is not found.
static func theora_fps(path: String) -> float:
	var file := FileAccess.open(path, FileAccess.READ)
	var head := file.get_buffer(512) if file else PackedByteArray()
	var at := head.hex_encode().find("807468656f7261")  # 0x80 "theora"
	if at < 0 or at % 2 == 1 or at / 2 + 30 > head.size():
		return 30.0
	var p := at / 2 + 22
	var num := (head[p] << 24) | (head[p + 1] << 16) | (head[p + 2] << 8) | head[p + 3]
	var den := (head[p + 4] << 24) | (head[p + 5] << 16) | (head[p + 6] << 8) | head[p + 7]
	return float(num) / den if num > 0 and den > 0 else 30.0


func _build() -> void:
	# Opaque, so the main view behind it does not show through.
	var background := StyleBoxFlat.new()
	background.bg_color = Color(0.13, 0.14, 0.16)
	add_theme_stylebox_override("panel", background)
	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 6)
	add_child(margin)
	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 6)
	margin.add_child(columns)

	var left := _pane(0)
	left.size_flags_stretch_ratio = 0.8
	columns.add_child(left)
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	columns.add_child(right)

	# 3D on top, where the overlay panel (top right of the screen) sits over it.
	var title := Label.new()
	title.text = "3D clip"
	right.add_child(title)
	var container := SubViewportContainer.new()
	container.stretch = true
	container.size_flags_vertical = Control.SIZE_EXPAND_FILL
	container.size_flags_stretch_ratio = 1.6
	right.add_child(container)
	viewport = SubViewport.new()
	container.add_child(viewport)
	camera = Camera3D.new()
	camera.set_script(load("res://scripts/orbit_camera.gd"))
	camera.distance = 3.5
	camera.target = Vector3(0, 0.9, 0)
	camera.follow = true
	viewport.add_child(camera)
	if player:
		camera.focus_target = camera.get_path_to(player)
	camera.current = true
	right.add_child(_pane(1))


## A titled pane holding video `i` at its own aspect ratio.
func _pane(i: int) -> VBoxContainer:
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var title := Label.new()
	title.text = TITLES[i]
	title.clip_text = true
	box.add_child(title)
	titles.append(title)
	var frame := AspectRatioContainer.new()
	frame.ratio = 0.8 if i == 0 else 1.6  # H3 Max 768P take, GVHMR render; set from the video once it plays
	frame.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(frame)
	frames.append(frame)
	var video := VideoStreamPlayer.new()
	video.expand = true
	video.volume_db = -80.0
	video.loop = false
	frame.add_child(video)
	videos.append(video)
	return box
