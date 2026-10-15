#!/usr/bin/env python3
"""file-drop: the real file's facts for the card, a frame for its thumbnail, and (optionally) a clip of real filler
for the player. Run it in your copy of the effect, on the raw recording the video was cut from:

  PY <project>/fx/<id>/facts.py <raw file> [--at T] [--clip START SECONDS [--speed 2.3]]

Prints FILE = { name, length, size, res } (from ffprobe) to paste into fx.js, and writes thumb.jpg next to this file:
a frame of the raw file at --at seconds (default a third of the way in; use the moment the player opens on, so the
thumbnail grows into the same picture). With --clip it also cuts raw.mp4: SECONDS of the raw file from START (source
seconds), sped up by --speed (default 2.3), 676x1200, no sound. Pick filler the edit threw out: a gap between the
KEEP ranges in edit.py (dead air, a fumbled line, a restart). Then point the player at it: on the <video> in fx.html
set src to fx/<id>/raw.mp4 (the id is this folder's name), data-media-start to 0 and data-playback-rate to 1, since
raw.mp4 is already sped up; keep SPEED in fx.js as its speed.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def length(sec):
    s = int(round(sec))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def size(nbytes):
    mb = nbytes / 1e6
    if mb >= 1000:
        return f"{mb / 1000:.1f} GB"
    return f"{mb:.1f} MB" if mb < 100 else f"{mb:.0f} MB"


def short(name, keep=8):
    return name if len(name) <= 2 * keep + 2 else name[:keep] + "…" + name[-keep:]


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("--"):
        sys.exit(__doc__)
    src = os.path.abspath(os.path.expanduser(a[0]))
    info = probe(src)
    dur = float(info["format"]["duration"])
    v = next(s for s in info["streams"] if s.get("codec_type") == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []):
        rot = int(sd.get("rotation", rot) or 0)
    rot = int(v.get("tags", {}).get("rotate", rot) or 0)
    if abs(rot) % 180 == 90:                      # phone footage stored sideways
        w, h = h, w
    facts = dict(name=short(os.path.basename(src)), length=length(dur), size=size(int(info["format"]["size"])),
                 res=f"{w}\\u00d7{h}")
    print("var FILE = { name: '%(name)s', length: '%(length)s', size: '%(size)s', res: '%(res)s' };" % facts)

    at = float(a[a.index("--at") + 1]) if "--at" in a else dur / 3
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", src, "-frames:v", "1", "-vf",
                    "scale=112:200:force_original_aspect_ratio=increase,crop=112:200", "-q:v", "3",
                    os.path.join(HERE, "thumb.jpg")], check=True)
    print(f"thumb.jpg: the frame at {at:.2f}s")

    if "--clip" in a:
        i = a.index("--clip")
        start, secs = float(a[i + 1]), float(a[i + 2])
        speed = float(a[a.index("--speed") + 1]) if "--speed" in a else 2.3
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{secs:.3f}", "-i", src, "-vf",
                        f"setpts=PTS/{speed},scale=676:1200:force_original_aspect_ratio=increase,crop=676:1200,fps=30",
                        "-an", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        os.path.join(HERE, "raw.mp4")], check=True)
        print(f"raw.mp4: {secs:.2f}s of the raw file from {start:.2f}s at {speed:g}x ({secs / speed:.2f}s long). On the "
              f"<video> in fx.html set src=\"fx/{os.path.basename(HERE)}/raw.mp4\", data-media-start=\"0\", "
              f"data-playback-rate=\"1\"; in fx.js keep SPEED = '{speed:g}\u00d7'")


if __name__ == "__main__":
    main()
