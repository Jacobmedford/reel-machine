#!/usr/bin/env python3
"""magazine-cover: rebuild mask-ink.png and mask-light.png, the masks that turn the cover's type to ink wherever ink
reads better than the light colour against the picture behind it (a window, a lamp, a pale wall). Run it in your copy
of the effect after the cut, and again whenever the shot or the style pack changes:

  PY <project>/fx/<id>/mask.py [project] [--at T [T ...]] [--threshold L]

It reads <project>/edit.py (this folder's FX entry gives the window), samples a few frames of <project>/public/clean.mp4
across it and takes the median luminance per pixel (a moving hand or a passing shadow doesn't count). A pixel goes to
ink where the pack's ink colour has more contrast against it than the pack's light colour (WCAG contrast, colours from
the project's style.json). Writes mask-ink.png next to this file (1080x1920, opaque where the type turns ink, clear
elsewhere, with a soft edge) and mask-light.png, its exact inverse. The speaker stands in front of the cover (the
cutout): where they are, the mask copies the nearest background around them (from public/subject.webm), so the type
doesn't flip colour in a ring around them as they move. --threshold sets the switch point yourself (relative
luminance 0-1, lower = more ink).
"""
import importlib.util
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920


def load_edit(project):
    spec = importlib.util.spec_from_file_location("edit", os.path.join(project, "edit.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def linear(c):
    c = np.asarray(c, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance_of(css, fallback):
    """relative luminance of a pack colour written as #rrggbb (anything else: the fallback)"""
    s = str(css).strip().lstrip("#")
    if len(s) != 6:
        return fallback
    try:
        r, g, b = linear([int(s[i:i + 2], 16) for i in (0, 2, 4)])
    except ValueError:
        return fallback
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def resolve_home(env=os.environ, expand=os.path.expanduser, exists=os.path.exists):
    """the creator's home folder: the kit's rule (pipeline/common.py), copied because this file runs from a project's
    copy of the effect, away from the kit (tests/test_home.py holds this copy to that one)"""
    for k in ("REEL_MACHINE_HOME", "REEL_KIT_HOME"):
        if env.get(k):
            return expand(env[k])
    new, old = expand("~/reel-machine"), expand("~/reel-kit")
    if exists(new):
        return new
    if exists(os.path.join(old, "style", "style.json")):
        return old
    return new


def pack_colours(project):
    home = resolve_home()
    for p in (os.path.join(project, "style", "style.json"), os.path.join(home, "style", "style.json")):
        if os.path.exists(p):
            c = json.load(open(p)).get("colors", {})
            return luminance_of(c.get("light"), 0.9), luminance_of(c.get("ink"), 0.01)
    return 0.9, 0.01


def frame_luminance(video, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                          f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    rgb = linear(np.frombuffer(raw, np.uint8).reshape(H, W, 3))
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def speaker(cutout, t):
    """the speaker's matte at t (alpha of the VP9 cutout), or None when there is no cutout"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{t:.3f}", "-i", cutout, "-frames:v", "1",
                        "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True)
    if r.returncode or len(r.stdout) != W * H * 4:
        return None
    return np.frombuffer(r.stdout, np.uint8).reshape(H, W, 4)[..., 3] > 76


def main():
    args = sys.argv[1:]
    project = os.path.abspath(args[0]) if args and not args[0].startswith("--") else os.path.dirname(os.path.dirname(HERE))
    times = []
    if "--at" in args:
        for a in args[args.index("--at") + 1:]:
            if a.startswith("--"):
                break
            times.append(float(a))
    if not times:
        fid = os.path.basename(HERE)
        E = load_edit(project)
        entry = next((F for F in getattr(E, "FX", []) if F.get("id") == fid), None)
        if entry is None:
            sys.exit(f"no FX entry with id '{fid}' in {project}/edit.py: pass --at <seconds>")
        a = float(entry["at"])
        b = a + 1.0 if entry.get("end") == "end" else float(entry["end"])
        times = [a + (b - a) * k / 6 for k in range(1, 6)]
    if "--threshold" in args:
        thr = float(args[args.index("--threshold") + 1])
    else:      # where light-on-picture and ink-on-picture have the same contrast
        ll, li = pack_colours(project)
        thr = float(np.sqrt((ll + 0.05) * (li + 0.05)) - 0.05)
    video = os.path.join(project, "public", "clean.mp4")
    if not os.path.exists(video):
        sys.exit(f"{video} not found: run the cut first")
    lum = np.median(np.stack([frame_luminance(video, t) for t in times]), axis=0)
    cls = lum > thr
    cutout = os.path.join(project, "public", "subject.webm")
    mats = [m for m in (speaker(cutout, t) for t in times) if m is not None] if os.path.exists(cutout) else []
    if mats:          # behind the speaker: the class of the nearest background pixel
        person = ndimage.binary_dilation(np.any(mats, axis=0), iterations=10)
        if person.any() and not person.all():
            _, (iy, ix) = ndimage.distance_transform_edt(person, return_indices=True)
            cls = cls[iy, ix]
    else:
        print("no cutout (public/subject.webm): the mask keeps the speaker's own brightness")
    ink = Image.fromarray((cls * 255).astype(np.uint8), "L")
    ink = ink.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))     # drop specks, keep shapes
    alpha = ink.filter(ImageFilter.GaussianBlur(1.2))
    white = (Image.new("L", (W, H), 255),) * 3
    Image.merge("RGBA", white + (alpha,)).save(os.path.join(HERE, "mask-ink.png"), optimize=True)
    Image.merge("RGBA", white + (alpha.point(lambda v: 255 - v),)).save(os.path.join(HERE, "mask-light.png"), optimize=True)
    print(f"mask-ink.png / mask-light.png: type turns ink on {np.asarray(ink).mean() / 255:.0%} of the frame (switch at luminance "
          f"{thr:.3f}; frames at {', '.join(f'{t:.2f}' for t in times)})")


if __name__ == "__main__":
    main()
