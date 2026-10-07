extends SceneTree
## Library scanner and panel check (M2.5). Builds a throwaway library under
## user:// with complete, partial and broken clips, scans it with
## LibraryScanner, fills a LibraryPanel from it, and checks every entry.
## Then scans the real library (if any) and prints its list.
##
##   godot --headless --path godot --script tests/check_library_scanner.gd
##
## Exits 1 on any mismatch.

const META := {
	"schema_version": 1, "id": "%s", "name": "%s", "tags": ["locomotion"],
	"status": "exported",
}
## id -> files to write ("bad" writes unparseable JSON).
const FIXTURE := {
	"walk-aaaaaa": {"meta.json": "ok", "qc.json": "ok", "motion.glb": "glb"},
	"jog-bbbbbb": {"meta.json": "ok", "motion.glb": "glb"},
	"vault-cccccc": {"meta.json": "ok", "qc.json": "fail"},
	"idle-dddddd": {"motion.glb": "glb"},
	"run-eeeeee": {"meta.json": "bad", "qc.json": "bad", "motion.glb": "glb"},
	"empty-ffffff": {},
}
## id -> expected [name, status, qc, playable, problems].
const EXPECTED := {
	"walk-aaaaaa": ["walk", "exported", "ok", true, []],
	"jog-bbbbbb": ["jog", "exported", "none", true, []],
	"vault-cccccc": ["vault", "exported", "fail", false, ["no motion.glb"]],
	"idle-dddddd": ["idle-dddddd", "unknown", "none", true, ["no meta.json"]],
	"run-eeeeee": ["run-eeeeee", "unknown", "none", true, ["unreadable meta.json", "unreadable qc.json"]],
	"empty-ffffff": ["empty-ffffff", "unknown", "none", false, ["no meta.json", "no motion.glb"]],
}

var failed := false
var lib := ProjectSettings.globalize_path("user://check_library_scanner")
var panel: LibraryPanel
var selected := []


func _initialize() -> void:
	_build(lib)
	var entries := LibraryScanner.scan(lib)
	_expect(entries.size() == EXPECTED.size(), "%d entries (expected %d)" % [entries.size(), EXPECTED.size()])
	for entry in entries:
		var want: Array = EXPECTED.get(entry.id, [])
		if want.is_empty():
			_expect(false, "unexpected entry %s" % entry.id)
			continue
		var got := [entry.name, entry.status, entry.qc, entry.playable, Array(entry.problems)]
		_expect(got == want, "%s: %s (expected %s)" % [entry.id, got, want])
	_expect(entries[0].name == "empty-ffffff" and entries[-1].name == "walk", "sorted by name")
	_expect(Array(entries[-1].tags) == ["locomotion"], "tags read")
	_expect(LibraryScanner.scan(lib.path_join("nowhere")).is_empty(), "missing root scans empty")

	# The panel; it builds its nodes in _ready, so check it on the first frame.
	panel = LibraryPanel.new()
	panel.library_path = lib
	panel.clip_selected.connect(func(id, playable): selected.append([id, playable]))
	get_root().add_child(panel)


func _process(_delta: float) -> bool:
	# On the fixture, then on a missing lib, then back.
	_expect(_rows(panel).size() == EXPECTED.size(), "panel lists %d rows" % _rows(panel).size())
	_expect(panel.summary.text == "6 clips, 4 partial", "panel summary: %s" % panel.summary.text)
	var vault := _row(panel, "vault-cccccc")
	_expect(vault and vault.get_text(2) == "partial" and vault.get_text(3) == "x", "vault row shows partial and fail badge")
	vault.select(0)
	_expect(selected == [["vault-cccccc", false]], "selection signal: %s" % [selected])
	panel.refresh()
	_expect(panel.tree.get_selected() and panel.tree.get_selected().get_metadata(0) == "vault-cccccc", "refresh keeps the selection")
	panel.set_library_path(lib.path_join("nowhere"))
	_expect(_rows(panel).is_empty() and panel.summary.text == "no clips/ folder here", "missing root: %s" % panel.summary.text)
	# A clip added on disk shows up on refresh.
	panel.set_library_path(lib)
	_write(lib.path_join("clips/new-gggggg/motion.glb"), "glb")
	panel.refresh()
	_expect(_row(panel, "new-gggggg") != null, "refresh picks up a new clip")

	print("real library: %s" % LibraryScanner.resolve_root())
	for entry in LibraryScanner.scan(LibraryScanner.resolve_root()):
		print("  %-14s %-20s %-12s qc=%-7s %s" % [entry.name, entry.id, entry.status, entry.qc, ", ".join(entry.problems)])
	print("FAIL" if failed else "PASS")
	quit(1 if failed else 0)
	return true


func _build(root: String) -> void:
	_remove(lib)
	for id in FIXTURE:
		var dir := lib.path_join("clips").path_join(id)
		DirAccess.make_dir_recursive_absolute(dir)
		var files: Dictionary = FIXTURE[id]
		for file in files:
			var kind: String = files[file]
			var text := "{not json"
			if kind == "glb":
				text = "glb"
			elif file == "meta.json" and kind == "ok":
				var meta := META.duplicate()
				meta.id = id
				meta.name = id.get_slice("-", 0)
				text = JSON.stringify(meta)
			elif file == "qc.json" and kind != "bad":
				text = JSON.stringify({"schema_version": 1, "status": kind, "metrics": {}, "flags": []})
			_write(dir.path_join(file), text)


func _write(path: String, text: String) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(text)


func _remove(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	for d in DirAccess.get_directories_at(path):
		_remove(path.path_join(d))
	for f in DirAccess.get_files_at(path):
		DirAccess.remove_absolute(path.path_join(f))
	DirAccess.remove_absolute(path)


func _rows(panel: LibraryPanel) -> Array[TreeItem]:
	return panel.tree.get_root().get_children()


func _row(panel: LibraryPanel, id: String) -> TreeItem:
	for item in _rows(panel):
		if item.get_metadata(0) == id:
			return item
	return null


func _expect(ok: bool, what: String) -> void:
	if not ok:
		failed = true
	print(("  ok    " if ok else "  FAIL  ") + what)
