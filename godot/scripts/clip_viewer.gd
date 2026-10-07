class_name ClipViewer
extends PanelContainer
## Clip Viewer mode (M2.6, GDD §6.3): a transport bar for the ClipPlayer.
## Selecting a clip in the library panel plays it on the mannequin; the bar
## has play/pause, frame step back and forward, a timeline to scrub (by
## frame), speed from 0.1x to 2x, a loop toggle and the camera follow toggle,
## and shows the current frame and time. Built in code. The Compare toggle
## (M2.10) shows the CompareView, which follows the same transport.
##
## Keys: Space plays or pauses, Left / Right (or , / .) step one frame,
## L toggles loop, V toggles Compare; the orbit camera handles C (follow)
## and F (focus).

@export var clip_player: NodePath
@export var library_panel: NodePath
@export var camera: NodePath
@export var compare_view: NodePath

var player: ClipPlayer
var panel: LibraryPanel
var cam: Camera3D
var compare: CompareView
var play_button: Button
var back_button: Button
var forward_button: Button
var timeline: HSlider
var position_label: Label
var clip_label: Label
var speed_slider: HSlider
var speed_label: Label
var loop_check: CheckBox
var follow_check: CheckBox
var compare_check: CheckBox
var _resume_after_scrub := false


func _ready() -> void:
	player = get_node_or_null(clip_player) as ClipPlayer
	panel = get_node_or_null(library_panel) as LibraryPanel
	cam = get_node_or_null(camera) as Camera3D
	compare = get_node_or_null(compare_view) as CompareView
	_build()
	if panel:
		panel.clip_selected.connect(select)
	if player:
		player.clip_changed.connect(func(_id): _sync())
	_sync()


## Plays `id` (the library panel's selection); unplayable clips are named, not played.
func select(id: String, playable: bool = true) -> void:
	if player == null:
		return
	if not playable:
		clip_label.text = "%s: no motion.glb, nothing to play" % id
		return
	if panel:
		player.library_path = panel.library_path
	if not player.play(id):
		clip_label.text = "%s: could not load (see the log)" % id
		return
	_sync()


func _process(_delta: float) -> void:
	if player == null:
		return
	var clip := player.current_clip()
	if clip:
		var frame := player.get_frame()
		if not timeline.has_meta("dragging"):
			timeline.set_value_no_signal(frame)
		position_label.text = "frame %d / %d   %.2f / %.2f s" % [frame, clip.frame_count - 1, player.get_time(), clip.animation.length]
	play_button.text = "Pause" if player.is_playing() else "Play"
	# Speed and loop can change from code or keys too.
	if not is_equal_approx(speed_slider.value, player.speed):
		speed_slider.set_value_no_signal(player.speed)
		speed_label.text = "%.2fx" % player.speed
	loop_check.set_pressed_no_signal(player.loop)
	if cam and "follow" in cam:
		follow_check.set_pressed_no_signal(cam.follow)
	if compare:
		compare_check.set_pressed_no_signal(compare.is_active())


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed) or player == null:
		return
	if get_viewport().gui_get_focus_owner() is LineEdit:
		return
	match event.keycode:
		KEY_SPACE:
			if not event.echo:
				player.set_playing(not player.is_playing())
		KEY_LEFT, KEY_COMMA:
			player.step(-1)
		KEY_RIGHT, KEY_PERIOD:
			player.step(1)
		KEY_L:
			if not event.echo:
				player.loop = not player.loop
		KEY_V:
			if not event.echo and compare:
				compare.set_active(not compare.is_active())
		_:
			return
	get_viewport().set_input_as_handled()


func _sync() -> void:
	var clip := player.current_clip() if player else null
	for control in [play_button, back_button, forward_button, timeline]:
		control.set("disabled", clip == null)
	timeline.editable = clip != null
	if clip == null:
		clip_label.text = "Select a clip in the library"
		position_label.text = ""
		return
	clip_label.text = "%s   %d frames at %.0f fps" % [clip.id, clip.frame_count, clip.fps]
	timeline.max_value = clip.frame_count - 1
	speed_slider.set_value_no_signal(player.speed)
	speed_label.text = "%.2fx" % player.speed
	loop_check.set_pressed_no_signal(player.loop)


func _build() -> void:
	custom_minimum_size = Vector2(0, 76)
	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 8)
	add_child(margin)
	var box := VBoxContainer.new()
	margin.add_child(box)

	var top := HBoxContainer.new()
	box.add_child(top)
	back_button = _button("|<", "Previous frame (Left)", func(): player.step(-1))
	top.add_child(back_button)
	play_button = _button("Play", "Play / pause (Space)", func(): player.set_playing(not player.is_playing()))
	play_button.custom_minimum_size.x = 64
	top.add_child(play_button)
	forward_button = _button(">|", "Next frame (Right)", func(): player.step(1))
	top.add_child(forward_button)
	timeline = HSlider.new()
	timeline.step = 1
	timeline.focus_mode = Control.FOCUS_NONE
	timeline.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	timeline.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	timeline.value_changed.connect(func(v): player.seek_frame(int(v)))
	timeline.drag_started.connect(_on_scrub_started)
	timeline.drag_ended.connect(_on_scrub_ended)
	top.add_child(timeline)
	position_label = Label.new()
	position_label.custom_minimum_size.x = 210
	top.add_child(position_label)

	var bottom := HBoxContainer.new()
	box.add_child(bottom)
	clip_label = Label.new()
	clip_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	clip_label.clip_text = true
	bottom.add_child(clip_label)
	var speed_title := Label.new()
	speed_title.text = "Speed"
	bottom.add_child(speed_title)
	speed_slider = HSlider.new()
	speed_slider.min_value = 0.1
	speed_slider.max_value = 2.0
	speed_slider.step = 0.05
	speed_slider.value = 1.0
	speed_slider.custom_minimum_size.x = 140
	speed_slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	speed_slider.focus_mode = Control.FOCUS_NONE
	speed_slider.value_changed.connect(_on_speed_changed)
	bottom.add_child(speed_slider)
	speed_label = Label.new()
	speed_label.custom_minimum_size.x = 48
	speed_label.text = "1.00x"
	bottom.add_child(speed_label)
	var reset := _button("1x", "Normal speed", func(): speed_slider.value = 1.0)
	bottom.add_child(reset)
	loop_check = CheckBox.new()
	loop_check.text = "Loop"
	loop_check.tooltip_text = "Loop the clip (L)"
	loop_check.focus_mode = Control.FOCUS_NONE
	loop_check.button_pressed = player.loop if player else true
	loop_check.toggled.connect(func(on): player.loop = on)
	bottom.add_child(loop_check)
	follow_check = CheckBox.new()
	follow_check.text = "Follow"
	follow_check.tooltip_text = "Camera follows the character (C)"
	follow_check.focus_mode = Control.FOCUS_NONE
	follow_check.toggled.connect(func(on): if cam: cam.follow = on)
	bottom.add_child(follow_check)
	compare_check = CheckBox.new()
	compare_check.text = "Compare"
	compare_check.tooltip_text = "Source take, GVHMR overlay and 3D side by side (V)"
	compare_check.focus_mode = Control.FOCUS_NONE
	compare_check.disabled = compare == null
	compare_check.toggled.connect(func(on): if compare: compare.set_active(on))
	bottom.add_child(compare_check)


func _button(text: String, tip: String, action: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.tooltip_text = tip
	b.focus_mode = Control.FOCUS_NONE
	b.pressed.connect(action)
	return b


func _on_speed_changed(value: float) -> void:
	player.speed = value
	speed_label.text = "%.2fx" % player.speed


func _on_scrub_started() -> void:
	timeline.set_meta("dragging", true)
	_resume_after_scrub = player.is_playing()
	player.set_playing(false)


func _on_scrub_ended(_changed: bool) -> void:
	timeline.remove_meta("dragging")
	if _resume_after_scrub:
		player.set_playing(true)
