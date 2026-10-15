#!/usr/bin/env python3
"""stamp-strike: the light/dark wall mask for the words stamped behind the speaker, and what hangs in front of them.

One alpha mask for the whole frame: where the room behind the speaker is light. The ink copy of the type shows through
it and the light copy everywhere else, so the letters split light/dark against the footage's own brightness instead
of wearing an outline. It reads the room across this effect's window (the median of the frames read) and leaves the
speaker out with the cutout, so a moving head doesn't bleed into it. Made for a locked-off shot: on a handheld one
keep the words over an area that doesn't change, or set SPLIT to false in fx.js.
Its settings are the MASK constant in this folder's fx.js (preset.py writes it): lo / hi (the luma ramp, 0-255),
blur, samples, read (the part of the window to read, s after its start), front ([luma, y]: dark things above y, a
ceiling fan, pass in front of the type; null: nothing in front).

Run: PY fx/<id>/mkmask.py <project> [<id>] [--at S --end S] [--blank]
  reads   the FX entry <id> in <project>/edit.py (or --at / --end), public/clean.mp4, public/subject.webm
  writes  fx/<id>/mask.png and fx/<id>/front.png (1080x1920 alpha masks)
  --blank writes neutral masks without reading any footage: light type only, nothing in front
<id> defaults to this script's folder name. Rerun it whenever the window, the cut or the footage changes.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30


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
    """output frames f0 .. f0+n-1 (rgba when alpha: VP9 with an alpha channel)"""
    args = ["ffmpeg", "-v", "error"] + (["-c:v", "libvpx-vp9"] if alpha else []) + ["-i", src,
            "-vf", f"select=between(n\\,{f0}\\,{f0 + n - 1})", "-fps_mode", "passthrough",
            "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24", "-"]
    raw = subprocess.run(args, capture_output=True, check=True).stdout
    got = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 4 if alpha else 3)
    if len(got) == 0:
        sys.exit(f"{src}: no frames at {f0}..{f0 + n - 1}")
    return got


def fill(a):
    """fill the NaNs (pixels the speaker covers in every frame) from their nearest read neighbours, growing inward"""
    a = a.copy()
    for _ in range(400):
        m = np.isnan(a)
        if not m.any():
            break
        p = np.pad(a, 1, mode="edge")
        nb = np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
        cnt = (~np.isnan(nb)).sum(0)
        avg = np.nansum(nb, axis=0) / np.maximum(cnt, 1)
        a = np.where(m & (cnt > 0), avg, a)
    return np.where(np.isnan(a), 255.0, a)


def window(project, fid):
    spec = importlib.util.spec_from_file_location("edit", os.path.join(project, "edit.py"))
    E = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(E)
    for F in getattr(E, "FX", []):
        if F["id"] == fid:
            end = F["end"]
            if end == "end":
                end = json.load(open(os.path.join(project, "timeline.json")))["total"]
            return float(F["at"]), float(end)
    sys.exit(f"no FX entry with id {fid!r} in {project}/edit.py (or pass --at and --end)")


def save(out, path):
    Image.fromarray(out, "RGBA").save(path, optimize=True)


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
    out_dir = os.path.join(project, "fx", fid)
    if args.blank:                                            # light type only, nothing in front
        z = np.zeros((H, W, 4), np.uint8)
        save(z, os.path.join(out_dir, "mask.png"))
        z[..., 3] = 255
        save(z, os.path.join(out_dir, "front.png"))
        print(f"{out_dir}: neutral mask.png (no ink copy) and front.png (nothing in front)")
        return
    M = preset_constants()["MASK"]
    lo, hi, blur, samples, read, front = M["lo"], M["hi"], M.get("blur", 1.0), M.get("samples", 0), M.get("read"), M.get("front")
    at, end = (args.at, args.end) if args.at is not None and args.end is not None else window(project, fid)
    if read:
        at, end = at + read[0], min(end, at + read[1])
    f0 = round(at * FPS)
    n = max(1, round(end * FPS) - f0)
    pub = os.path.join(project, "public")
    clean = frames(os.path.join(pub, "clean.mp4"), f0, n)
    k = len(clean) if samples <= 0 else min(samples, len(clean))
    pick = np.unique(np.linspace(0, len(clean) - 1, k).round().astype(int))
    rgb = clean[pick].astype(np.float32)
    luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    sub = os.path.join(pub, "subject.webm")
    if os.path.exists(sub):                                   # the room only: drop the samples where the speaker is
        alpha = frames(sub, f0, n, alpha=True)
        alpha = alpha[np.minimum(pick, len(alpha) - 1), ..., 3]
        room = np.where(alpha < 128, luma, np.nan)
        seen = ~np.all(np.isnan(room), axis=0)
        luma = np.where(seen, np.nanmedian(np.where(seen, room, 0), axis=0), np.nan)
        luma = fill(luma)                                     # never seen: the nearest wall around it
    else:
        luma = np.median(luma, axis=0)
    m = np.clip((luma - lo) / (hi - lo), 0, 1)
    a = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur)))
    out = np.zeros((H, W, 4), np.uint8)
    out[..., 3] = a
    fo = np.zeros((H, W, 4), np.uint8)                        # front.png: the room's own foreground (open when null)
    fo[..., 3] = 255
    if front:                                                 # static, read like the wall
        fr = np.where((luma < front[0]) & (np.arange(H)[:, None] < front[1]), 0, 255).astype(np.uint8)
        fo[..., 3] = np.asarray(Image.fromarray(fr).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2)))
    save(fo, os.path.join(out_dir, "front.png"))
    save(out, os.path.join(out_dir, "mask.png"))
    print(f"{out_dir}/mask.png: light {a.mean() / 255:.3f} of the frame, from {len(pick)} frames ({f0}-{f0 + n - 1})")


if __name__ == "__main__":
    main()
