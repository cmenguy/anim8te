class_name LibraryPanel
extends PanelContainer
## Library panel, simplest form (M2.5, GDD §7.2): the library path, a refresh
## button and the clip list (name, tags, status, QC badge) from
## LibraryScanner. Scans on start and on refresh. Partial clips stay in the
## list, greyed, with what is missing in the status column and the tooltip.
## Built in code; `clip_selected` is for the Clip Viewer (M2.6).

signal clip_selected(clip_id: String, playable: bool)
signal scanned(entries: Array[Dictionary])

## Library root; empty resolves `--library=<path>`, ANIM8TE_LIBRARY, then `<repo>/library`.
@export var library_path := ""

const QC_COLORS := {
	"ok": Color(0.35, 0.8, 0.4),
	"warn": Color(0.95, 0.7, 0.2),
	"fail": Color(0.95, 0.3, 0.3),
	"pending": Color(0.6, 0.6, 0.6),
	LibraryScanner.QC_NONE: Color(0.45, 0.45, 0.45),
}
const QC_TEXT := {"ok": "ok", "warn": "!", "fail": "x", "pending": "...", LibraryScanner.QC_NONE: "-"}
const PARTIAL_COLOR := Color(0.55, 0.55, 0.55)

var entries: Array[Dictionary] = []
var path_edit: LineEdit
var refresh_button: Button
var summary: Label
var tree: Tree


func _ready() -> void:
	custom_minimum_size = Vector2(380, 0)
	var margin := MarginContainer.new()
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 8)
	add_child(margin)
	var box := VBoxContainer.new()
	margin.add_child(box)
	var title := Label.new()
	title.text = "LIBRARY"
	box.add_child(title)
	var row := HBoxContainer.new()
	box.add_child(row)
	path_edit = LineEdit.new()
	path_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	path_edit.placeholder_text = "library path"
	path_edit.text_submitted.connect(func(text): set_library_path(text))
	row.add_child(path_edit)
	refresh_button = Button.new()
	refresh_button.text = "Refresh"
	refresh_button.pressed.connect(refresh)
	row.add_child(refresh_button)
	summary = Label.new()
	box.add_child(summary)
	tree = Tree.new()
	tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tree.hide_root = true
	tree.columns = 4
	tree.column_titles_visible = true
	for i in 4:
		tree.set_column_title(i, ["Clip", "Tags", "Status", "QC"][i])
		tree.set_column_expand(i, i < 2)
	tree.set_column_custom_minimum_width(2, 90)
	tree.set_column_custom_minimum_width(3, 40)
	tree.item_selected.connect(_on_item_selected)
	box.add_child(tree)
	refresh()


## Library root in use (absolute path).
func library_root() -> String:
	return LibraryScanner.resolve_root(library_path)


## Points the panel at another library and rescans.
func set_library_path(path: String) -> void:
	library_path = path.strip_edges()
	refresh()


## Rescans the library and rebuilds the list, keeping the selection if it is still there.
func refresh() -> void:
	var root := library_root()
	var selected := _selected_id()
	path_edit.text = root
	path_edit.tooltip_text = root
	entries = LibraryScanner.scan(root)
	tree.clear()
	var tree_root := tree.create_item()
	var partial := 0
	for entry in entries:
		var item := tree.create_item(tree_root)
		item.set_metadata(0, entry.id)
		item.set_text(0, entry.name)
		item.set_text(1, ", ".join(entry.tags))
		var complete: bool = entry.problems.is_empty()
		item.set_text(2, entry.status if complete else "partial")
		item.set_text(3, QC_TEXT.get(entry.qc, entry.qc))
		item.set_text_alignment(3, HORIZONTAL_ALIGNMENT_CENTER)
		item.set_custom_color(3, QC_COLORS.get(entry.qc, QC_COLORS[LibraryScanner.QC_NONE]))
		var tip := "%s\nstatus: %s\nQC: %s" % [entry.id, entry.status, entry.qc]
		if not complete:
			partial += 1
			tip += "\n" + "\n".join(entry.problems)
			for c in 3:
				item.set_custom_color(c, PARTIAL_COLOR)
		for c in 4:
			item.set_tooltip_text(c, tip)
		if entry.id == selected:
			item.select(0)
	if not DirAccess.dir_exists_absolute(root.path_join("clips")):
		summary.text = "no clips/ folder here"
	else:
		summary.text = "%d clips, %d partial" % [entries.size(), partial]
	scanned.emit(entries)


func _selected_id() -> String:
	var item := tree.get_selected() if tree else null
	return item.get_metadata(0) if item else ""


func _on_item_selected() -> void:
	var id := _selected_id()
	for entry in entries:
		if entry.id == id:
			clip_selected.emit(id, entry.playable)
			return
