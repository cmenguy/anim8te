class_name LibraryScanner
extends RefCounted
## Reads the clip library from disk (M2.5): one entry per `<root>/clips/<id>/`
## directory, from its `meta.json`, `qc.json` and `motion.glb`. Partial or
## broken clips come back as entries with `problems`, never as errors, so the
## list can show them. The daemon-backed list (M3.10) falls back to this.
##
## Schemas: `ClipMeta` and `QCReport` in anim8te/library.py.

## QC badge values: `qc.json` status, or NONE when there is no readable file.
const QC_NONE := "none"


## Library root (absolute path): `override` if set, else a `--library=<path>`
## user argument (after `--`), else ANIM8TE_LIBRARY, else `<repo>/library`.
static func resolve_root(override := "") -> String:
	if override != "":
		return ProjectSettings.globalize_path(override)
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--library="):
			return arg.trim_prefix("--library=")
	var env := OS.get_environment("ANIM8TE_LIBRARY")
	if env != "":
		return env
	return ProjectSettings.globalize_path("res://").path_join("../library").simplify_path()


## Entries for every clip directory under `root`, sorted by name then id.
## Each entry is a Dictionary:
##   id, name, tags (PackedStringArray), status (meta.json status, or "unknown"),
##   qc (ok / warn / fail / pending, or QC_NONE), has_meta, has_qc, has_glb,
##   playable (motion.glb present), problems (PackedStringArray, empty when complete),
##   path (the clip directory).
static func scan(root: String) -> Array[Dictionary]:
	var entries: Array[Dictionary] = []
	var clips_dir := root.path_join("clips")
	if not DirAccess.dir_exists_absolute(clips_dir):
		return entries
	for id in DirAccess.get_directories_at(clips_dir):
		if id.begins_with("."):
			continue
		entries.append(scan_clip(clips_dir.path_join(id)))
	entries.sort_custom(func(a, b): return [a.name, a.id] < [b.name, b.id])
	return entries


## One entry (see `scan`) for the clip directory at `path`.
static func scan_clip(path: String) -> Dictionary:
	var id := path.get_file()
	var entry := {
		"id": id, "name": id, "tags": PackedStringArray(), "status": "unknown",
		"qc": QC_NONE, "has_meta": false, "has_qc": false, "has_glb": false,
		"playable": false, "problems": PackedStringArray(), "path": path,
	}
	var meta_path := path.path_join("meta.json")
	if FileAccess.file_exists(meta_path):
		var meta := _read_json(meta_path)
		if meta.is_empty():
			entry.problems.append("unreadable meta.json")
		else:
			entry.has_meta = true
			if meta.get("name") is String and meta.name != "":
				entry.name = meta.name
			if meta.get("tags") is Array:
				for tag in meta.tags:
					entry.tags.append(str(tag))
			if meta.get("status") is String:
				entry.status = meta.status
	else:
		entry.problems.append("no meta.json")
	var qc_path := path.path_join("qc.json")
	if FileAccess.file_exists(qc_path):
		var qc := _read_json(qc_path)
		if qc.get("status") is String:
			entry.has_qc = true
			entry.qc = qc.status
		else:
			entry.problems.append("unreadable qc.json")
	entry.has_glb = FileAccess.file_exists(path.path_join("motion.glb"))
	entry.playable = entry.has_glb
	if not entry.has_glb:
		entry.problems.append("no motion.glb")
	return entry


## Parsed JSON object, or {} when the file is unreadable or not an object.
static func _read_json(path: String) -> Dictionary:
	var text := FileAccess.get_file_as_string(path)
	if text == "":
		return {}
	var json := JSON.new()
	if json.parse(text) != OK or not json.data is Dictionary:
		return {}
	return json.data
