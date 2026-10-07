class_name OverlayPanel
extends PanelContainer
## Toggles for the debug overlays (M2.8): one check box per overlay, keys 1 to
## 6 in the same order, and a line saying when the clip has no usable
## features.json or an overlay has nothing to draw. Built in code.

@export var clip_overlays: NodePath

var overlays: ClipOverlays
## Overlay id -> CheckBox.
var checks := {}
var status_label: Label


func _ready() -> void:
	overlays = get_node_or_null(clip_overlays) as ClipOverlays
	_build()
	if overlays:
		overlays.overlays_changed.connect(_sync)
	_sync()


func _build() -> void:
	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 8)
	add_child(margin)
	var box := VBoxContainer.new()
	margin.add_child(box)
	var heading := Label.new()
	heading.text = "Overlays"
	box.add_child(heading)
	if overlays == null:
		return
	var key := 1
	for id in overlays.ids():
		var overlay: DebugOverlay = overlays.overlays[id]
		var check := CheckBox.new()
		check.text = "%d  %s" % [key, overlay.title]
		check.tooltip_text = "%s (%d)" % [overlay.title, key]
		check.focus_mode = Control.FOCUS_NONE
		check.toggled.connect(func(on): overlays.set_enabled(id, on))
		box.add_child(check)
		checks[id] = check
		key += 1
	status_label = Label.new()
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.custom_minimum_size.x = 200
	status_label.modulate = Color(1.0, 0.75, 0.4)
	box.add_child(status_label)


func _process(_delta: float) -> void:
	# Overlay notes depend on the frame's data; keep the line current.
	if overlays:
		status_label.text = _status_text()


func _input(event: InputEvent) -> void:
	if overlays == null or not (event is InputEventKey and event.pressed and not event.echo):
		return
	if get_viewport().gui_get_focus_owner() is LineEdit:
		return
	var index: int = event.keycode - KEY_1
	var ids := overlays.ids()
	if index < 0 or index >= ids.size():
		return
	overlays.set_enabled(ids[index], not overlays.is_enabled(ids[index]))
	get_viewport().set_input_as_handled()


func _sync() -> void:
	if overlays == null:
		return
	for id in checks:
		checks[id].set_pressed_no_signal(overlays.is_enabled(id))
	status_label.text = _status_text()


func _status_text() -> String:
	if overlays.status != "":
		return overlays.status
	var notes := PackedStringArray()
	for overlay: DebugOverlay in overlays.overlays.values():
		if overlay.visible and overlay.note != "":
			notes.append("%s: %s" % [overlay.title, overlay.note])
	return "\n".join(notes)
