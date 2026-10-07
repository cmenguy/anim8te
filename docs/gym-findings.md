# Gym findings: M0 and M1 clips (M2.11, 2026-10-07)

All five library clips, reviewed in the Gym's Clip Viewer and Compare mode with the debug overlays on, after the M0 clips were re-run through `extract`, `clean` and `export` (see "How the clips were made"). The numbers come from each clip's `features.json` and `clean/motion.npz`, with the overlays' definitions, so each one can be checked by seeking the Gym to the timestamp given:

- **Foot skate:** a foot or toe joint in contact (`contacts`) whose horizontal speed relative to the ground (the belt on a treadmill, `contact_thresholds.ground_velocity`) is over 0.3 m/s. This is overlay 1's red disk. The percentage is sliding frames over contact frames, across the four contact joints.
- **Ground penetration:** a joint more than 5 mm under y = 0, with foot joints measured at the sole (`rest_heights_above_sole`). This is overlay 4.
- **Jitter:** `joint_jerk`, with "red" meaning over 300 m/s³, the top of overlay 6's scale. Also the share of pelvis-relative joint-velocity power above 6 Hz, the M0.7 measure.
- **Root drift:** the Hips' horizontal displacement over the clip (overlay 2). The loop seam is the root gap plus the mean pelvis-relative joint distance between the last and first frames.
- **Limb flips:** the largest local-rotation change of any bone between two frames.

Every clip is 155 frames at 30 fps (5.13 s), on the default filters (`smooth` savgol 9/3, `ground` p5, `contacts` 4 cm / 0.8 m/s / 3 frames, ground velocity auto). Timestamps are clip time, which is also video time in Compare. Frames are 0-based.

Capture: `docs/captures/m2.11-gym-review.jpg`. Top left: jog-m05 at 2.83 s, right toes under the ground. Top right: vault-m05 at 1.63 s, the 40 mm penetration in the run-up. Bottom left: the same frame in Compare. Bottom right: vault-m05 at 3.50 s, crouched on the block, with no contacts drawn.

## Summary

| Clip | Take | Foot skate (sliding / contact) | Penetration | Jerk p95 (max), red joint-frames | Power >6 Hz | Root drift | Loop seam (root / pose) | Max rotation step |
|---|---|---|---|---|---|---|---|---|
| `idle-m05` | 2 | 0 / 620 (0 %) | none | 12 (21) m/s³, 0 % | 0.2 % | 0.13 m | 0.13 m / 3.2 cm | 1.4° |
| `walk-ur7zdb` | 1 | 124 / 359 (35 %) | none (4 mm max) | 142 (335), 0.1 % | 0.2 % | 0.08 m | 0.08 m / 4.3 cm | 11.3° |
| `jog-qa61r5` | 2 | 110 / 197 (56 %) | 2 frames, 8 mm | 261 (492), 1.9 % | 0.1 % | 0.03 m | 0.03 m / 11.5 cm | 15.1° |
| `jog-m05` | 3 | 95 / 162 (59 %) | 2 frames, 9 mm | 298 (472), 4.8 % | 0.3 % | 0.09 m | 0.09 m / 11.0 cm | 15.3° |
| `vault-m05` | 2 | 38 / 139 (27 %) | 3 frames, 40 mm | 397 (1457), 10.7 % | 0.6 % (legs, run-up: 1.2 % smoothed, 17.3 % raw) | 5.13 m travel | n/a (one-shot) | 17.7° |

No clip has a limb flip: the largest rotation step is 17.7°, against 45° for a flip, and none goes over 30°. The visible defects are foot skate on every moving clip, the vault run-up's leg swaps, missing loops and missing root motion.

## Per clip

### `idle-m05` (take 2, standing, weight shifts)

- **Foot skate:** none. All four contact joints are planted in all 155 frames, and they creep at 0.05 m/s median (0.12 max), under the 0.3 m/s slide line. In the Gym the disks stay green throughout. M0.7's 5 to 8 cm/s creep is still there, just below the overlay's threshold: an idle loop of a few seconds shows it as a slow shuffle.
- **Ground penetration:** none. Soles sit 1.4 to 1.6 cm above the ground (median), and their lowest point is 0.1 cm.
- **Jitter:** none. Jerk p95 is 12 m/s³ and power above 6 Hz is 0.2 %.
- **Root drift:** the Hips wander 13 cm (+0.13 m x) over the clip, with a 16 cm maximum excursion. For a loop that is a 13 cm jump at the seam.
- **Limb flips:** none (1.4° max step).
- **Needs:** foot lock, to pin the creep, and a loop with root drift removed (`root_motion: none` has to mean the Hips' XZ drift is cancelled, not kept).

### `walk-ur7zdb` (take 1, treadmill walk)

- **Foot skate:** 35 % of contact frames slide. It starts at 0.00-0.57 s (f0-17), then appears in short bursts at about every foot plant: 0.93-1.03 s (f28-31), 1.97-2.10 s (f59-63), 2.33-2.43 s (f70-73), 2.53-2.57 s (f76-77), and so on to the end. Slip in contact is 0.21 to 0.26 m/s median, up to 0.80 m/s, worst on the right toes (38 of 94 frames).
- **Ground penetration:** none over 5 mm (4 mm on the right foot at 0.83 s).
- **Jitter:** low. Three red joint-frames on the toes, at 3.13-3.17 s (f94-95) and 4.27 s (f128), at toe-off.
- **Root drift:** 8 cm over the clip. It stays on the spot, as a treadmill clip should until root motion (M3.2).
- **Limb flips:** none (11.3° max, right knee at 4.10 s).
- **Needs:** foot lock, root motion (synthesized), loop (4.3 cm pose gap at the seam).

### `jog-qa61r5` (take 2, treadmill jog)

- **Foot skate:** 56 % of contact frames slide, the most visible defect in the Gym. It covers 0.00-0.50 s (f0-15), 1.10-1.23 s (f33-37), 1.50-1.70 s (f45-51), 2.20-2.23 s (f66-67), plus 14 more short runs. It is worst on the left foot: 35 of 53 contact frames, 0.47 m/s median slip.
- **Ground penetration:** right toes 8 mm under at 2.87-2.90 s (f86-87).
- **Jitter:** jerk turns red on the lower legs at foot strike. That is 26 frames on the right knee and 12 on the left, for example 1.87-2.03 s (f56-61), 3.10-3.30 s (f93-99) and 3.67-3.73 s (f110-112). Power above 6 Hz is only 0.1 %, so this is the impact itself, not noise: smoothing more would round off the foot strike.
- **Root drift:** 3 cm, on the spot.
- **Limb flips:** none (15.1° max, right knee at 5.03 s).
- **Needs:** foot lock first, then root motion and a loop. The seam pose gap is 11.5 cm, the largest of the cycles, because 5.13 s is not a whole number of strides.

### `jog-m05` (take 3, treadmill jog, M0 take)

- **Foot skate:** 59 % of contact frames slide: 0.43-1.00 s (f13-30), 1.50-1.73 s (f45-52), 2.43-2.47 s (f73-74), plus 13 more runs. The left foot slides most (25 of 36 frames, 0.45 m/s median).
- **Ground penetration:** right toes 9 mm under at 2.80-2.83 s (f84-85). See the capture, top left.
- **Jitter:** 4.8 % red joint-frames, the most of the cycles. They fall on the knees (40 and 34 frames) and the hands (20 and 18) at each strike, from 1.83 s to 3.10 s (f55-93). Power above 6 Hz is 0.3 %, so this too is impact rather than noise.
- **Root drift:** 9 cm, on the spot.
- **Limb flips:** none (15.3° max).
- **Needs:** the same as `jog-qa61r5`. The two jogs come out nearly the same (56 and 59 % skate, 8 and 9 mm toe penetration at almost the same frame), so these faults belong to GVHMR and the filters, not to one take. Keep one jog for the starter set.

### `vault-m05` (take 2, side-on run-up and vault onto a block, M0 v3 take)

- **Leg swaps in the run-up**, the worst defect of the five clips. Between 1.47 s and 2.53 s (f44-76) jerk is red on the feet and toes in nearly every frame (365 red joint-frames, 10.7 %; 1457 m/s³ on the left toes at 2.20 s). This is where M0.7 saw the mesh legs out of phase with hers (its frames 40 and 56 at 24 fps are 1.67 s and 2.33 s here). In Compare, step through 1.4 to 2.6 s and watch the GVHMR overlay's legs against the take.
- **Smoothing hides the swaps from the frequency measure but not from the eye.** With `smooth` on, the run-up's leg power above 6 Hz is 1.2 %. Re-cleaned with `--no-smooth`, it is 17.3 % (5.5 % after 2.5 s), the M0.7 picture. M3.20's "from 12 to 13 % to under 3 %" target has to be measured with smoothing off, or it passes before any repair.
- **Ground penetration:** 40 mm on the left toes at 1.60-1.67 s (f48-50), with the left foot and right toes also under. It sits on the swap. Without smoothing it is 19 mm: the savgol filter overshoots the fast foot plant downward. Smoothing has to run before contacts, foot lock and ground alignment (the M3.6 order already does), or a clamp has to follow it.
- **Ground alignment:** the clip was lowered 12.0 cm, against -3.2 to +1.3 cm for the others. GVHMR's ground tilts along her path (M0.7 saw it on take 3), and the 5th-percentile sole height lands in the run-up.
- **Foot skate:** 27 % of contact frames, at 0.40-0.53 s (f12-16), 1.00-1.40 s (f30-42) and 2.50-2.73 s (f75-82, the take-off). The ground velocity was auto-estimated at (0.08, -0.10) m/s, which is noise: there is no belt. For non-treadmill templates the contacts filter should use 0.
- **Contacts on the block:** the last contact is at 2.67 s (f80). After 3 s her soles sit at 0.67 to 0.72 m (median; the block is about 0.53 m, and the 12 cm lowering and the tilt add the rest), so nothing counts as contact, so the crouch on top gets no disks and foot lock would not hold her feet there. See the capture, bottom right. Contacts are measured against y = 0 only.
- **Root drift:** 5.13 m of travel (+5.08 x, -0.68 z), the Hips rising 0.70 to 1.34 m, ending 0.25 m higher. M0.7 measured the image-based travel at about 3.8 m, so this is about 35 % too long.
- **Limb flips:** none over 30° (17.7° max, left knee at 3.03 s). The swaps are whole-leg exchanges spread over several frames, not single-frame flips.
- **Needs:** leg-swap repair and travel rescale (M3.20), root motion from the Hips (M3.2), contacts that work on raised surfaces, segmentation (approach, vault, land; M3.4).

### Other things seen in the Gym

- Both jogs are listed as "jog" in the library panel and only the order tells them apart. The panel shows `meta.json` `name`, not the clip id. This is minor until the library grows; the M3 library screen should show the id or keep names unique.
- The vault takes are landscape (1344×768, side-on framing), so Compare's source pane letterboxes them. `check_video_playback.gd` assumed portrait takes and now reads the source size instead.

## Ranking: what the cleanup filters should fix first (order of M3.A)

1. **Foot lock (M3.1).** Foot skate is the largest and most visible defect: 27 to 59 % of contact frames on every moving clip, plus a slow creep on the idle. It also fixes most of the penetration, which is small and sits on foot plants (8 to 9 mm on the jogs). Two additions from this review: contacts on raised surfaces (the vault's crouch on the block), and ground velocity 0 for non-treadmill templates.
2. **Root motion (M3.2).** All three locomotion clips run on the spot (3 to 9 cm drift), and the vault travels 5.13 m. Nothing is usable in the grey box (M2.13) without it, and `none` has to cancel the idle's 13 cm wander.
3. **Leg-swap repair and travel rescale (M3.20).** This is the worst single defect (the vault run-up, 1.47 to 2.53 s), but it affects only side-on dynamic clips, and it depends on the 2D keypoints (M1.9). Measure its target with smoothing off.
4. **Trim and auto-loop (M3.3).** Every cycle has a visible seam: 11 cm pose gap on the jogs, 4.3 cm on the walk, 3.2 cm plus 13 cm root gap on the idle.
5. **Segmentation (M3.4).** Only the vault needs it so far.
6. **Smoothing and ground alignment** (already in `clean`): leave them as they are, apart from the order. Jitter after smoothing is 0.1 to 0.6 % above 6 Hz on every clip, and the red jerk on the jogs is impact, which more smoothing would only blur. The order matters, though: smoothing pushes the vault's toes 21 mm further down, and the 5th-percentile ground is thrown off by tilted ground (vault, 12 cm). Both are handled by running foot lock and ground alignment after smoothing, as M3.6 already orders them.

Limb-flip handling does not need a filter yet: no clip has a step over 30°.

## How the clips were made

`walk-ur7zdb` and `jog-qa61r5` are the M1 clips, as they were. The three M0 clips only held their feasibility outputs (`takes/`, `feasibility/`). Each got a `meta.json` built from `takes/log.jsonl` (performer `perf01`; idle `custom`, `loop`, root motion `none`; jog `locomotion`, `loop`, `synthesize`; vault `traversal`, `extract`), and then went through the pipeline on its best still-camera take from M0.7:

```bash
uv run anim8te extract idle-m05 --take 2   # 41 s on the Mac worker
uv run anim8te extract jog-m05 --take 3    # 37 s
uv run anim8te extract vault-m05 --take 2  # 38 s
uv run anim8te clean <id> && uv run anim8te export <id>
```

The numbers above come from a scratch script that reads `features.json` with the overlays' definitions. The capture comes from a scratch Godot script that drives `main.tscn` (Compare on or off, overlays 1, 2, 4, 5, 6, seek, then save the viewport), using its own settings file.
