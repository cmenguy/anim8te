"""M0.7 throwaway: motion metrics for the M0.10 GVHMR feasibility takes.

Run with the GVHMR fork's venv (it has torch, smplx and the body-model code), from the repo root:

    unset VIRTUAL_ENV
    export GVHMR_CHECKPOINTS=~/motion-ai-checkpoints GVHMR_BODY_MODELS=~/motion-ai-checkpoints/body_models
    ~/motion-ai-tools/gvhmr/.venv/bin/python docs/scratch/judge_takes.py

Reads library/clips/<clip>/feasibility/<take>/hmr4d_results.pt, poses the SMPL-X body the same way the
demo's world render does (Y up, metres, floor at the clip's lowest vertex), and prints per take:
foot sliding in contact, joint jitter (acceleration and power above 6 Hz), root and feet height over time, horizontal drift, body shape,
large per-frame joint rotations (limb-flip candidates) and frame counts of the overlays. Writes
metrics.json and heights.png next to each take's results (git-ignored). Not part of motionai/.
"""

import json
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path.home() / "motion-ai-tools" / "gvhmr"))
from gvhmr.utils.smplx_utils import make_smplx  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CLIPS = ROOT / "library" / "clips"
TAKES = [("idle-m05", "2"), ("idle-m05", "3"), ("jog-m05", "1"), ("jog-m05", "2"), ("jog-m05", "3"),
         ("vault-m05", "2"), ("vault-m05", "3")]
FPS = 24  # H3 Max output, M0.5

# SMPL-X body joint indices
PELVIS, L_ANKLE, R_ANKLE, L_FOOT, R_FOOT, HEAD = 0, 7, 8, 10, 11, 15
JOINT_NAMES = ["pelvis", "l_hip", "r_hip", "spine1", "l_knee", "r_knee", "spine2", "l_ankle", "r_ankle",
               "spine3", "l_foot", "r_foot", "neck", "l_collar", "r_collar", "head", "l_shoulder",
               "r_shoulder", "l_elbow", "r_elbow", "l_wrist", "r_wrist"]
STATIC_IDS = [L_ANKLE, L_FOOT, R_ANKLE, R_FOOT, 20, 21]  # order of GVHMR's static_conf head
CONTACT_HEIGHT = 0.05  # m above that foot joint's own lowest point in the clip
CONTACT_SPEED = 0.6  # m/s, 3D; a planted foot should be near zero, a swinging one is well above
HF_HZ = 6.0  # Hz; Nyquist at 24 fps is 12 Hz
FLIP_DEG = 45.0  # per-frame change of one joint's local rotation that marks a flip candidate


def axis_angle_to_matrix(aa):
    return torch.as_tensor(cv2_rodrigues_batch(aa.reshape(-1, 3).numpy())).reshape(*aa.shape[:-1], 3, 3)


def cv2_rodrigues_batch(aa):
    return np.stack([cv2.Rodrigues(a.astype(np.float64))[0] for a in aa])


def rot_angle_deg(r1, r2):
    rel = np.einsum("...ji,...jk->...ik", r1, r2)
    cos = np.clip((np.trace(rel, axis1=-2, axis2=-1) - 1) / 2, -1, 1)
    return np.degrees(np.arccos(cos))


def frame_count(path):
    cap = cv2.VideoCapture(str(path))
    n = 0
    while cap.grab():
        n += 1
    cap.release()
    return n


def stature(smplx, betas):
    """Standing height (head top to sole) of the rest-pose body for one betas vector."""
    out = smplx(betas=betas[None], body_pose=torch.zeros(1, 63), global_orient=torch.zeros(1, 3),
                transl=torch.zeros(1, 3))
    y = out.vertices[0, :, 1]
    return float(y.max() - y.min())


def judge(smplx, clip, take):
    folder = CLIPS / clip / "feasibility" / take
    pred = torch.load(folder / "hmr4d_results.pt", map_location="cpu", weights_only=False)
    params = pred["smpl_params_global"]
    with torch.no_grad():
        out = smplx(**params)
    verts = out.vertices.numpy()  # (L, V, 3), Y up
    joints = out.joints[:, :22].numpy()
    n = len(joints)
    floor = verts[:, :, 1].min()
    verts[:, :, 1] -= floor
    joints[:, :, 1] -= floor
    dt = 1.0 / FPS

    # Foot contact: geometric (low and slow) and GVHMR's own static_conf head (sigmoid > 0.8, as its post-process).
    vel = np.linalg.norm(np.diff(joints, axis=0), axis=-1) / dt  # (L-1, 22) m/s
    hvel = np.linalg.norm(np.diff(joints[:, :, [0, 2]], axis=0), axis=-1)  # (L-1, 22) m per frame
    conf = torch.sigmoid(pred["net_outputs"]["static_conf_logits"][0]).numpy()  # (L, 6)
    slide = {}
    for side, ids in (("left", (L_ANKLE, L_FOOT)), ("right", (R_ANKLE, R_FOOT))):
        for j in ids:
            h = joints[1:, j, 1] - joints[:, j, 1].min()
            geo = (h < CONTACT_HEIGHT) & (vel[:, j] < CONTACT_SPEED)
            gv = conf[1:, STATIC_IDS.index(j)] > 0.8
            name = JOINT_NAMES[j]
            slide[name] = {
                "contact_frames_geo": int(geo.sum()),
                "slide_cm_per_frame_geo": round(float(hvel[geo, j].mean() * 100), 2) if geo.any() else None,
                "slide_cm_per_frame_geo_p95": round(float(np.percentile(hvel[geo, j], 95) * 100), 2) if geo.any() else None,
                "contact_frames_gvhmr": int(gv.sum()),
                "slide_cm_per_frame_gvhmr": round(float(hvel[gv, j].mean() * 100), 2) if gv.any() else None,
            }

    # Jitter: second difference of joint positions, in mm per frame^2, root-relative so travel does not count.
    rel = joints - joints[:, [PELVIS]]
    acc = np.linalg.norm(rel[2:] - 2 * rel[1:-1] + rel[:-2], axis=-1) * 1000  # (L-2, 22)
    root_acc = np.linalg.norm(np.diff(joints[:, PELVIS], n=2, axis=0), axis=-1) * 1000
    worst_joint = int(acc.mean(0).argmax())
    # Share of root-relative joint velocity power above HF_HZ: human motion sits mostly below it, jitter does not.
    v = np.diff(rel, axis=0) - np.diff(rel, axis=0).mean(0)
    spec = np.abs(np.fft.rfft(v, axis=0)) ** 2
    freqs = np.fft.rfftfreq(len(v), d=1.0 / FPS)
    hf_ratio = float(spec[freqs > HF_HZ].sum() / spec.sum())

    # Heights: pelvis over the floor, and the lowest vertex per frame (rises when standing on the block).
    pelvis_h = joints[:, PELVIS, 1]
    feet_h = verts[:, :, 1].min(axis=1)
    head_h = verts[:, :, 1].max(axis=1)

    # Horizontal drift of the pelvis (treadmill check for the jog, travel for the vault).
    xz = joints[:, PELVIS][:, [0, 2]]
    disp = float(np.linalg.norm(xz[-1] - xz[0]))
    path = float(np.linalg.norm(np.diff(xz, axis=0), axis=-1).sum())
    feet_xz = joints[:, [L_FOOT, R_FOOT]][:, :, [0, 2]].mean(1)
    feet_disp = float(np.linalg.norm(feet_xz[-1] - feet_xz[0]))

    # Limb-flip candidates: big per-frame change of a joint's local rotation.
    local = torch.cat([params["global_orient"], params["body_pose"]], dim=1).reshape(n, 22, 3)
    rmats = axis_angle_to_matrix(local).numpy()
    dang = rot_angle_deg(rmats[:-1], rmats[1:])  # (L-1, 22)
    flips = [{"frame": int(f + 1), "joint": JOINT_NAMES[j], "deg": round(float(dang[f, j]), 1)}
             for f, j in zip(*np.nonzero(dang > FLIP_DEG))]

    # Body shape: per-frame betas spread, and stature of the averaged shape.
    betas = params["betas"]
    bpf = pred["betas_per_frame"].numpy()
    mean_betas = betas.mean(0)

    frames = {name: frame_count(folder / f"{name}.mp4") for name in ("0_input_video", "1_incam", "2_global")}
    kp_conf = pred["kp2d"][:, :, 2].numpy()

    m = {
        "clip": clip, "take": take, "frames_results": n, "frames_video": frames,
        "kp2d_low_conf_frames": int((kp_conf.mean(1) < 0.5).sum()),
        "foot_slide": slide,
        "jitter_mm_per_frame2_mean": round(float(acc.mean()), 2),
        "jitter_mm_per_frame2_p95": round(float(np.percentile(acc, 95)), 2),
        "jitter_hf_power_share": round(hf_ratio, 4),
        "jitter_worst_joint": JOINT_NAMES[worst_joint],
        "jitter_worst_joint_mean": round(float(acc.mean(0)[worst_joint]), 2),
        "root_accel_mm_per_frame2_mean": round(float(root_acc.mean()), 2),
        "pelvis_h_start": round(float(pelvis_h[:5].mean()), 3),
        "pelvis_h_min": round(float(pelvis_h.min()), 3),
        "pelvis_h_max": round(float(pelvis_h.max()), 3),
        "pelvis_h_end": round(float(pelvis_h[-5:].mean()), 3),
        "feet_h_start": round(float(feet_h[:5].mean()), 3),
        "feet_h_max": round(float(feet_h.max()), 3),
        "feet_h_end": round(float(feet_h[-5:].mean()), 3),
        "head_h_start": round(float(head_h[:5].mean()), 3),
        "pelvis_disp_m": round(disp, 3),
        "pelvis_path_m": round(path, 3),
        "pelvis_drift_m_per_s": round(disp / (n * dt), 3),
        "feet_disp_m": round(feet_disp, 3),
        "flip_candidates": flips,
        "max_joint_rot_deg_per_frame": round(float(dang.max()), 1),
        "max_joint_rot_joint": JOINT_NAMES[int(np.unravel_index(dang.argmax(), dang.shape)[1])],
        "betas_mean": [round(float(b), 3) for b in mean_betas],
        "betas_per_frame_std_mean": round(float(bpf.std(0).mean()), 3),
        "betas_constant_in_results": bool(torch.allclose(betas, betas[0:1].expand_as(betas))),
        "stature_m": round(stature(smplx, mean_betas), 3),
    }
    (folder / "metrics.json").write_text(json.dumps(m, indent=2))

    t = np.arange(n) / FPS
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.plot(t, pelvis_h, label="pelvis")
    ax.plot(t, feet_h, label="lowest vertex (soles)")
    ax.plot(t, joints[:, L_FOOT, 1], ":", label="l_foot joint")
    ax.plot(t, joints[:, R_FOOT, 1], ":", label="r_foot joint")
    ax.set(xlabel="s", ylabel="height above floor (m)", title=f"{clip}/{take}")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(folder / "heights.png", dpi=110)
    plt.close(fig)
    return m


def main():
    smplx = make_smplx("supermotion")
    results = [judge(smplx, c, t) for c, t in TAKES]
    print(f"{'take':14} {'frames r/in/inc/glob':22} {'slide geo L/R cm/f':20} {'slide gvhmr L/R':16} "
          f"{'jitter mean/p95':16} {'pelvis start/min/max/end':26} {'soles max/end':14} {'drift m (m/s)':14} "
          f"{'flips':6} {'stature':7}")
    for m in results:
        fs = m["foot_slide"]
        fv = m["frames_video"]
        print(f"{m['clip'] + '/' + m['take']:14} "
              f"{m['frames_results']}/{fv['0_input_video']}/{fv['1_incam']}/{fv['2_global']:<10} "
              f"{fs['l_foot']['slide_cm_per_frame_geo']}/{fs['r_foot']['slide_cm_per_frame_geo']:<14} "
              f"{fs['l_foot']['slide_cm_per_frame_gvhmr']}/{fs['r_foot']['slide_cm_per_frame_gvhmr']:<10} "
              f"{m['jitter_mm_per_frame2_mean']}/{m['jitter_mm_per_frame2_p95']:<10} "
              f"{m['pelvis_h_start']}/{m['pelvis_h_min']}/{m['pelvis_h_max']}/{m['pelvis_h_end']:<6} "
              f"{m['feet_h_max']}/{m['feet_h_end']:<8} "
              f"{m['pelvis_disp_m']} ({m['pelvis_drift_m_per_s']})   "
              f"{len(m['flip_candidates']):<6} {m['stature_m']}  hf>6Hz {m['jitter_hf_power_share']}")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
