#!/usr/bin/env python3
"""kinetic-hook-front: the light/dark masks for the opening line on top of the speaker.

For every output frame of this effect's window: where the picture under the line's band (y 212-444) is light, an
alpha mask. The dark copy of the line shows through it and the light copy everywhere else, so the type splits
light/dark against the footage's own brightness instead of wearing an outline. With --field <s> (the time
kinetic-hook's dark ground cuts in), frames from then on only count the speaker: the room is under the ground there.

Run: PY fx/<id>/mkmask.py <project> [<id>] [--field <s>]
  reads   <project>/edit.py (the FX entry <id>: at, end), <project>/public/clean.mp4,
          <project>/public/subject.webm (only with --field)
  writes  <project>/fx/<id>/masks.png: one 1080x232 band per frame of the window, stacked top to bottom
<id> defaults to this script's folder name. Rerun it whenever the window, the cut or the footage changes.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

Y0, H = 212, 232            # the line's band on the 1080x1920 frame (fx.html: #<id>-band)
LO, HI = 140, 170           # luma ramp (0-255): below LO the line stays light, above HI it turns dark
BLUR = 1.2                  # soften the split a hair (px)
W, FH, FPS = 1080, 1920, 30


def frames(src, f0, n, alpha=False):
    """output frames f0 .. f0+n-1 of a 1080x1920 video as arrays (rgba when alpha: VP9 with an alpha channel)"""
    args = ["ffmpeg", "-v", "error"] + (["-c:v", "libvpx-vp9"] if alpha else []) + ["-i", src,
            "-vf", f"select=between(n\\,{f0}\\,{f0 + n - 1})", "-fps_mode", "passthrough", "-frames:v", str(n),
            "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24", "-"]
    raw = subprocess.run(args, capture_output=True, check=True).stdout
    c = 4 if alpha else 3
    got = np.frombuffer(raw, np.uint8).reshape(-1, FH, W, c)
    if len(got) == 0:
        sys.exit(f"{src}: no frames at {f0}..{f0 + n - 1}")
    if len(got) < n:                                   # past the end: hold the last frame
        got = np.concatenate([got, np.repeat(got[-1:], n - len(got), axis=0)])
    return got


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
    sys.exit(f"no FX entry with id {fid!r} in {project}/edit.py")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project")
    ap.add_argument("id", nargs="?", default=os.path.basename(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--field", type=float, default=None, help="when kinetic-hook's ground cuts in (s, output)")
    args = ap.parse_args()
    project, fid, field = os.path.abspath(os.path.expanduser(args.project)), args.id, args.field
    at, end = window(project, fid)
    f0 = round(at * FPS)
    n = max(1, round(end * FPS) - f0)
    pub = os.path.join(project, "public")
    clean = frames(os.path.join(pub, "clean.mp4"), f0, n)
    subj = frames(os.path.join(pub, "subject.webm"), f0, n, alpha=True) if field is not None else None
    sheet = np.zeros((n * H, W, 4), np.uint8)
    for k in range(n):
        rgb = clean[k, Y0:Y0 + H].astype(np.float32)
        luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        m = np.clip((luma - LO) / (HI - LO), 0, 1)
        if field is not None and (f0 + k) / FPS >= field - 1e-6:
            m *= subj[k, Y0:Y0 + H, :, 3].astype(np.float32) / 255      # only the speaker: the room is under the ground
        band = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(BLUR)))
        sheet[k * H:(k + 1) * H, :, 3] = band
        print(f"frame {f0 + k:4d}  dark {band.mean() / 255:.3f}")
    out = os.path.join(project, "fx", fid, "masks.png")
    Image.fromarray(sheet, "RGBA").save(out, optimize=True)
    print(f"{out}: {n} bands of {W}x{H} (frames {f0}-{f0 + n - 1})")


if __name__ == "__main__":
    main()
