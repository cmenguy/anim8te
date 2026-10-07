class_name JerkHeatmapOverlay
extends DebugOverlay
## Joint-jerk heatmap (M2.8): a marker on every joint coloured by its jerk
## (`joint_jerk`, m/s^3) on a fixed scale, so clips compare: blue at 0, green,
## yellow, red at `max_jerk` and above. On the M1 treadmill clips the median
## is about 30 (walk) and 95 (jog), the 99th percentile 220 and 325.

## Jerk that maps to full red, m/s^3.
@export var max_jerk := 300.0

const RAMP: Array[Color] = [Color(0.2, 0.4, 1.0), Color(0.2, 0.9, 0.4), Color(1.0, 0.9, 0.2), Color(1.0, 0.15, 0.1)]


func _init() -> void:
	super()
	overlay_id = "jerk_heatmap"
	title = "Joint jerk heatmap"


func _draw_frame(f: ClipFeatures, frame: int) -> void:
	var jerk := f.joint_jerk[clampi(frame, 0, f.num_frames - 1)]
	for j in f.bone_names.size():
		var c := color_for(jerk[j])
		marker(f.position(frame, j), 0.035, c)
		shapes.append({"kind": "jerk", "bone": f.bone_names[j], "jerk": jerk[j], "color": c})


## Colour of a jerk value on the ramp.
func color_for(jerk: float) -> Color:
	var t := clampf(jerk / max_jerk, 0.0, 1.0) * (RAMP.size() - 1)
	var i := mini(floori(t), RAMP.size() - 2)
	return RAMP[i].lerp(RAMP[i + 1], t - i)
