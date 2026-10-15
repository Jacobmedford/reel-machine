#!/usr/bin/env python3
"""card-storyboard-note: write img/v2-clean.jpg, the focus beat's new frame: the source picture of that reel at a time,
with that reel's own grade baked in (no captions: the card lays the caption on it live, then grows it).

It reads FRAME from the PRESET CONSTANTS block of this folder's index.html: project ("" = the project given as the
argument, the one this card is in; a name = another project folder beside it; or a path to one) and t (seconds on
that reel's output timeline). The grade is the one that reel shows at t: black and white (edit.BW), a named look
(edit.GRADES), else its pack's house grade (style.json).

Run: PY cards/<id>/frame.py <project>
  writes  cards/<id>/img/v2-clean.jpg (1080x1920)
"""
import importlib.util
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
LOOKS = {"warm": "sepia(0.34) contrast(1.05) saturate(1.3) brightness(1.04) hue-rotate(-9deg)",     # pipeline/build.py
         "moody": "sepia(0.06) contrast(1.24) saturate(0.55) brightness(0.70) hue-rotate(4deg)"}  # LOOKS, the same values
MONO = "grayscale(1) contrast(1.2) brightness(0.9)"                                             # build.py's B&W


def resolve_home(env=os.environ, expand=os.path.expanduser, exists=os.path.exists):
    """the creator's home folder: the kit's rule (pipeline/common.py), copied because this file runs from a project's
    copy of the card, away from the kit (tests/test_home.py holds this copy to that one)"""
    for k in ("REEL_MACHINE_HOME", "REEL_KIT_HOME"):
        if env.get(k):
            return expand(env[k])
    new, old = expand("~/reel-machine"), expand("~/reel-kit")
    if exists(new):
        return new
    if exists(os.path.join(old, "style", "style.json")):
        return old
    return new


def preset_constants():
    text = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    a = text.index("// PRESET CONSTANTS START")
    b = text.index("// PRESET CONSTANTS END", a)
    dec, out = json.JSONDecoder(), {}
    for m in re.finditer(r"(?m)^\s*var\s+([A-Za-z_]\w*)\s*=\s*", text[a:b]):
        out[m.group(1)] = dec.raw_decode(text, a + m.end())[0]
    return out


def _sat(s):
    return np.array([[0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s],
                     [0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s],
                     [0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s]])


def _hue(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[0.213 + c * 0.787 - s * 0.213, 0.715 - c * 0.715 - s * 0.715, 0.072 - c * 0.072 + s * 0.928],
                     [0.213 - c * 0.213 + s * 0.143, 0.715 + c * 0.285 + s * 0.140, 0.072 - c * 0.072 - s * 0.283],
                     [0.213 - c * 0.213 - s * 0.787, 0.715 - c * 0.715 + s * 0.715, 0.072 + c * 0.928 + s * 0.072]])


def css_filter(rgb, spec):
    """a CSS filter list on an HxWx3 image in 0-1, the way the browser applies it (colour matrices, clamped)"""
    for name, val in re.findall(r"([a-z-]+)\(([^)]*)\)", spec or ""):
        v = float(val.replace("deg", "").replace("%", "")) / (100 if "%" in val else 1)
        if name == "sepia":
            a = min(1, v)
            full = np.array([[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]])
            rgb = rgb @ ((1 - a) * np.eye(3) + a * full).T
        elif name == "saturate":
            rgb = rgb @ _sat(v).T
        elif name == "grayscale":
            rgb = rgb @ ((1 - min(1, v)) * np.eye(3) + min(1, v) * _sat(0)).T
        elif name == "hue-rotate":
            rgb = rgb @ _hue(v).T
        elif name == "contrast":
            rgb = (rgb - 0.5) * v + 0.5
        elif name == "brightness":
            rgb = rgb * v
        rgb = np.clip(rgb, 0, 1)
    return rgb


def main():
    if os.path.exists(os.path.join(HERE, "preset.json")):
        sys.exit(f"{HERE} is the preset library: make an instance (pipeline/preset.py add) and run its copy")
    F = preset_constants()["FRAME"]
    here = os.path.abspath(os.path.expanduser(sys.argv[1])) if len(sys.argv) > 1 else ""
    name = str(F.get("project") or "")
    if not name:                                          # "" = the project this card is in
        if not here:
            sys.exit('FRAME.project is "" (this project): run PY frame.py <project>')
        proj = here
    elif os.sep in name:                                  # a path to a project
        proj = os.path.abspath(os.path.expanduser(name))
    else:                                                 # another project beside this one
        projects = os.path.dirname(here) if here else os.path.join(resolve_home(), "projects")
        proj = os.path.join(projects, name)
    t = float(F["t"])
    spec = importlib.util.spec_from_file_location("edit", os.path.join(proj, "edit.py"))
    E = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(E)
    look = None
    for a, b in getattr(E, "BW", []) or []:
        if a <= t < b:
            look = MONO
    for G in getattr(E, "GRADES", []) or []:
        if look is None and G[0] <= t < (1e9 if G[1] == "end" else G[1]):
            look = LOOKS.get(G[2], G[2])
    if look is None:
        p = os.path.join(proj, "style", "style.json")
        look = (json.load(open(p)).get("grade") or "") if os.path.exists(p) else ""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", os.path.join(proj, "public", "clean.mp4"),
                          "-frames:v", "1", "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    rgb = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255
    out = (css_filter(rgb, look) * 255 + 0.5).astype(np.uint8)
    os.makedirs(os.path.join(HERE, "img"), exist_ok=True)
    Image.fromarray(out).save(os.path.join(HERE, "img", "v2-clean.jpg"), quality=92)
    print(f"{HERE}/img/v2-clean.jpg: {os.path.basename(proj)} at {t:.3f}s, graded {look or 'none'}")


if __name__ == "__main__":
    main()
