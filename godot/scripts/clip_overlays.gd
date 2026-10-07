class_name ClipOverlays
extends Node3D
## The Gym's debug overlays (M2.8, GDD §6.4). A child of the ClipPlayer, so
## it shares the clip's space; one DebugOverlay node per overlay, built in
## `_ready`. On every clip change it reads the clip's `features.json` (once
## per clip, cached) and each frame hands the visible overlays the player's
## current frame.
##
## Which overlays are on is kept across clip changes (it is not touched by
## them) and across sessions in a ConfigFile at `settings_path`, section
## "overlays", one bool per overlay id.

signal overlays_changed

const SECTION := "overlays"

@export var clip_player: NodePath = ^".."
## Where the toggles persist; tests point it elsewhere.
@export var settings_path := "user://gym_settings.cfg"

var player: ClipPlayer
## Overlay id -> DebugOverlay, in panel order.
var overlays := {}
## Features of the current clip, or null (no clip or no readable features.json).
var features: ClipFeatures
## Why there are no features for the current clip, or "".
var status := ""
var _cache := {}


func _ready() -> void:
	player = get_node_or_null(clip_player) as ClipPlayer
	for overlay: DebugOverlay in [
		FootContactOverlay.new(), RootTrajectoryOverlay.new(), VelocityOverlay.new(),
		GroundPenetrationOverlay.new(), SkeletonOverlay.new(), JerkHeatmapOverlay.new(),
	]:
		overlay.name = overlay.overlay_id.to_pascal_case()
		overlay.visible = false
		add_child(overlay)
		overlays[overlay.overlay_id] = overlay
	_load_settings()
	if player:
		player.clip_changed.connect(_on_clip_changed)
		if player.current_clip():
			_on_clip_changed(player.clip_id)


func ids() -> PackedStringArray:
	return PackedStringArray(overlays.keys())


func is_enabled(id: String) -> bool:
	return overlays.has(id) and overlays[id].visible


## Shows or hides an overlay and saves the choice.
func set_enabled(id: String, on: bool) -> void:
	if not overlays.has(id) or overlays[id].visible == on:
		return
	overlays[id].visible = on
	_save_settings()
	refresh()
	overlays_changed.emit()


## Redraws the visible overlays for the player's current frame.
func refresh() -> void:
	var frame := player.get_frame() if player and player.current_clip() else 0
	for overlay: DebugOverlay in overlays.values():
		if overlay.visible:
			overlay.show_frame(features, frame)


func _process(_delta: float) -> void:
	refresh()


func _on_clip_changed(id: String) -> void:
	features = _cache.get(id)
	status = ""
	if features == null:
		var path := player.library_root().path_join("clips").path_join(id).path_join("features.json")
		if not FileAccess.file_exists(path):
			status = "no features.json (run anim8te clean)"
		else:
			features = ClipFeatures.load_file(path)
			if features == null:
				status = "unreadable features.json"
			else:
				_cache[id] = features
	var clip := player.current_clip()
	if features and clip and features.num_frames != clip.frame_count:
		status = "features.json has %d frames, motion.glb %d: re-run clean and export" % [features.num_frames, clip.frame_count]
	refresh()
	overlays_changed.emit()


func _load_settings() -> void:
	var config := ConfigFile.new()
	if config.load(settings_path) != OK:
		return
	for id in overlays:
		overlays[id].visible = bool(config.get_value(SECTION, id, false))


func _save_settings() -> void:
	var config := ConfigFile.new()
	config.load(settings_path)  # keep other sections
	for id in overlays:
		config.set_value(SECTION, id, overlays[id].visible)
	var err := config.save(settings_path)
	if err != OK:
		push_error("ClipOverlays: cannot save %s (%s)" % [settings_path, error_string(err)])
