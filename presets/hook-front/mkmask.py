#!/usr/bin/env python3
"""hook-front: the masks for the proof line, which sits on the top layer but reads as if it were on the wall.

Two sheets, one 1080 x BAND.height band per output frame of this effect's window:
  knock.png  where the speaker is NOT (the cutout's alpha, inverted): the line is knocked out wherever they are, so it
             sits behind them like type on the wall would, and never lands on the head as they move up into it
  masks.png  where the picture under the line is light: the ink copy shows through it, the light copy everywhere else,
             so the small mono line splits light/dark against the room, no outline
Both are read the way the composition shows the picture: the camera's opening settle (edit.CAMERA["open"], a scale
about the camera origin eased power2.out) is applied to each frame first, because this line is outside the camera.
For frame 0 (where this layer can carry a big line one behind the head: a cutout window can't start on frame 0) it
also writes, in the camera's own space (fx.js scales them with the camera):
  knock0.png  the room on frame 0: line one is knocked out wherever the speaker is (and, with OPEN_FROM, behind
              whatever hangs in front of that hook's wall: its front.png)
  wall.png    where frame 0 is light, for line one's ink copy: read off frame 0 itself on the MASK ramp, or with
              OPEN_FROM a copy of that hook effect's own wall mask (fx/<OPEN_FROM>/mask.png), so the split matches
Its settings come from this folder's fx.js (preset.py writes them): BAND (top, height), MASK (lo, hi, blur), OPEN_FROM.

Run: PY fx/<id>/mkmask.py <project> [<id>] [--at S --end S] [--blank]
  reads   the FX entry <id> in <project>/edit.py (or --at / --end), CAMERA open and CAM_ORIGIN there, public/clean.mp4,
          public/subject.webm (and with OPEN_FROM: fx/<OPEN_FROM>/mask.png and front.png)
  --blank neutral sheets without reading footage: nothing knocked out, no ink split (one band, repeated by the CSS)
<id> defaults to this script's folder name. Rerun it whenever the window, the cut, the camera or the footage changes.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, FH, FPS = 1080, 1920, 30


def preset_constants():
    """the PRESET CONSTANTS block of this folder's fx.js: name -> value"""
    text = open(os.path.join(HERE, "fx.js"), encoding="utf-8").read()
    a = text.index("// PRESET CONSTANTS START")
    b = text.index("// PRESET CONSTANTS END", a)
    dec, out = json.JSONDecoder(), {}
    for m in re.finditer(r"(?m)^\s*var\s+([A-Za-z_]\w*)\s*=\s*", text[a:b]):
        out[m.group(1)] = dec.raw_decode(text, a + m.end())[0]
    return out


def frames(src, f0, n, alpha=False):
    args = ["ffmpeg", "-v", "error"] + (["-c:v", "libvpx-vp9"] if alpha else []) + ["-i", src, "-vf",
            f"select=between(n\\,{f0}\\,{f0 + n - 1})", "-fps_mode", "passthrough", "-frames:v", str(n),
            "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24", "-"]
    raw = subprocess.run(args, capture_output=True, check=True).stdout
    got = np.frombuffer(raw, np.uint8).reshape(-1, FH, W, 4 if alpha else 3)
    if len(got) == 0:
        sys.exit(f"{src}: no frames at {f0}..{f0 + n - 1}")
    if len(got) < n:
        got = np.concatenate([got, np.repeat(got[-1:], n - len(got), axis=0)])
    return got


def load(project):
    spec = importlib.util.spec_from_file_location("edit", os.path.join(project, "edit.py"))
    E = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(E)
    return E


def window(E, project, fid):
    for F in getattr(E, "FX", []):
        if F["id"] == fid:
            end = F["end"]
            if end == "end":
                end = json.load(open(os.path.join(project, "timeline.json")))["total"]
            return float(F["at"]), float(end)
    sys.exit(f"no FX entry with id {fid!r} in {project}/edit.py (or pass --at and --end)")


def cam_scale(E, t):
    """the camera's opening settle at output time t: scale s0 -> 1 over d seconds, power2.out (the kit default)"""
    s0, d = (getattr(E, "CAMERA", {}) or {}).get("open", (1.04, 0.45))
    if d <= 0 or t >= d:
        return 1.0
    p = t / d
    return s0 + (1.0 - s0) * (1 - (1 - p) ** 2)


def save(a, path):
    Image.fromarray(a, "RGBA").save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project")
    ap.add_argument("id", nargs="?", default=os.path.basename(HERE))
    ap.add_argument("--at", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--blank", action="store_true")
    args = ap.parse_args()
    if os.path.exists(os.path.join(HERE, "preset.json")):
        sys.exit(f"{HERE} is the preset library: make an instance (pipeline/preset.py add) and run its copy")
    project, fid = os.path.abspath(os.path.expanduser(args.project)), args.id
    C = preset_constants()
    y0, H = int(C["BAND"]["top"]), int(C["BAND"]["height"])
    lo, hi, blur = C["MASK"]["lo"], C["MASK"]["hi"], C["MASK"].get("blur", 1.0)
    hook = C.get("OPEN_FROM") or ""                                # null: no hook effect to copy line one's split from
    out_dir = os.path.join(project, "fx", fid)
    hook_mask, hook_front = ((os.path.join(project, "fx", hook, f) if hook else "") for f in ("mask.png", "front.png"))
    if args.blank:
        band = np.zeros((H, W, 4), np.uint8)
        save(band, os.path.join(out_dir, "masks.png"))             # no ink copy
        band[..., 3] = 255
        save(band, os.path.join(out_dir, "knock.png"))             # nothing knocked out
        k0 = np.zeros((FH, W, 4), np.uint8)
        k0[..., 3] = 255
        save(k0, os.path.join(out_dir, "knock0.png"))
        if hook and os.path.exists(hook_mask):
            shutil.copy(hook_mask, os.path.join(out_dir, "wall.png"))
        else:
            save(np.zeros((FH, W, 4), np.uint8), os.path.join(out_dir, "wall.png"))
        print(f"{out_dir}: neutral masks (no knock-out, no ink split){' + the wall mask of ' + hook if hook and os.path.exists(hook_mask) else ''}")
        return
    E = load(project)
    at, end = (args.at, args.end) if args.at is not None and args.end is not None else window(E, project, fid)
    f0 = round(at * FPS)
    n = max(1, round(end * FPS) - f0)
    clean = frames(os.path.join(project, "public", "clean.mp4"), f0, n)
    subj = frames(os.path.join(project, "public", "subject.webm"), f0, n, alpha=True)
    ox, oy = getattr(E, "CAM_ORIGIN", None) or (540, 760)
    xs = np.arange(W, dtype=np.float32)
    ys = np.arange(y0, y0 + H, dtype=np.float32)
    sheet = np.zeros((n * H, W, 4), np.uint8)
    knock = np.zeros((n * H, W, 4), np.uint8)
    for k in range(n):
        s = cam_scale(E, (f0 + k) / FPS)
        sx = np.clip(np.round(ox + (xs - ox) / s), 0, W - 1).astype(int)      # where each band pixel samples the footage
        sy = np.clip(np.round(oy + (ys - oy) / s), 0, FH - 1).astype(int)
        rgb = clean[k][sy][:, sx].astype(np.float32)
        luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        m = np.clip((luma - lo) / (hi - lo), 0, 1)
        band = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur)))
        sheet[k * H:(k + 1) * H, :, 3] = band
        knock[k * H:(k + 1) * H, :, 3] = 255 - subj[k][sy][:, sx][..., 3]           # the room only: the speaker knocks it out
    save(sheet, os.path.join(out_dir, "masks.png"))
    save(knock, os.path.join(out_dir, "knock.png"))
    k0 = np.zeros((FH, W, 4), np.uint8)                                    # frame 0, camera space, full frame
    k0[..., 3] = 255 - subj[0][..., 3]
    if hook and os.path.exists(hook_front):                                # that hook's foreground, in front of its type too
        k0[..., 3] = (k0[..., 3].astype(np.uint16) * np.asarray(Image.open(hook_front))[..., 3] // 255).astype(np.uint8)
    save(k0, os.path.join(out_dir, "knock0.png"))
    if hook:
        if not os.path.exists(hook_mask):
            sys.exit(f"{hook_mask} is missing: run fx/{hook}/mkmask.py first (or set OPEN_FROM to null)")
        shutil.copy(hook_mask, os.path.join(out_dir, "wall.png"))
    else:                                                                  # line one splits against frame 0 itself
        rgb = clean[0].astype(np.float32)                                  # camera space: the footage's own pixels
        luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        m = np.clip((luma - lo) / (hi - lo), 0, 1)
        wall = np.zeros((FH, W, 4), np.uint8)
        wall[..., 3] = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur)))
        save(wall, os.path.join(out_dir, "wall.png"))
    print(f"{out_dir}/masks.png + knock.png: {n} bands of {W}x{H} (frames {f0}-{f0 + n - 1}), "
          f"ink {sheet[..., 3].mean() / 255:.3f}, room {knock[..., 3].mean() / 255:.3f}; wall.png "
          f"{'from fx/' + hook + '/mask.png' if hook else 'read off frame ' + str(f0)}")


if __name__ == "__main__":
    main()
