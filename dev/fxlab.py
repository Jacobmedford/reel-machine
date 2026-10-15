#!/usr/bin/env python3
"""Dev only: the effects lab. A showcase project on the stand-in footage (dev/standin.py) whose script triggers every
effect in the library, so each one can be built, tested and previewed in a real composition. Its fx/ folder is a link
to this kit's fx/ library: an agent working in the lab edits the library itself.

Run: .venv/bin/python dev/fxlab.py [--pack default|bold|soft]  -> dev/out/fx-home/projects/fx-lab/
Then: PY pipeline/fxsandbox.py <lab> <your-name> --only <ids> --at <times>
"""
import json
import os
import shutil
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
HOME = os.path.join(KIT, "dev", "out", "fx-home")
LAB = os.path.join(HOME, "projects", "fx-lab")
STANDIN = os.path.join(KIT, "dev", "out", "standin", "standin.mp4")

# the script on the OUTPUT timeline: (start, end, line). Every line calls for one effect.
LINES = [
    (0.10, 2.40, "I didn't edit a single second of this video."),
    (2.60, 4.30, "No timeline, no presets, nothing."),
    (4.50, 5.70, "I typed one sentence."),
    (5.90, 6.90, "Make it warmer."),
    (7.30, 9.10, "Now it looks like a magazine cover."),
    (9.30, 10.80, "I know nothing about editing."),
    (11.00, 12.40, "I drop in the raw file."),
    (12.60, 14.50, "A few minutes later, this is the video."),
    (14.70, 15.70, "Make it moody."),
    (16.00, 17.40, "Lots of people do this."),
    (17.60, 19.10, "Here is the plan it made."),
    (19.30, 20.60, "I leave one note."),
    (20.80, 22.30, "I never open an editing app."),
    (22.50, 23.80, "Bigger captions."),
    (24.00, 25.50, "I recorded a walkthrough."),
    (25.70, 28.20, "Comment EDIT and I'll send it to you."),
]

EDIT = '''"""FX LAB (dev only): the stand-in footage with one line per library effect. Edit freely in your sandbox copy."""
TITLE = "FX Lab"
STYLE = "showcase"
SRC = "{src}"
KEEP = [(0.0, 7.2), (7.3, 16.0), (16.1, 28.7)]     # two joins, so there are picture cuts for the transitions
FRAMES = {{"WIDE": (1080, 1920, 0, 0), "CLOSE": (864, 1536, 108, 192)}}
SHOTS = [(0.000, "WIDE"), (7.500, "CLOSE"), (16.200, "WIDE")]
HOLD = 0.5
FIXES = {{}}
PROMPT = ""
CAPS = []
KARAOKE = dict(huge=[], hide=[(22.40, 23.90)])     # giant-captions carries the words there
BOXES = []
OVERLAYS = []
BEHIND = []
CUT_WINDOWS = [(0.0, 2.50), (7.60, 9.45), (20.80, 22.40)]
BW = []
GRADES = [(7.00, 14.60, "warm"), (14.60, 16.20, "moody")]
CAMERA = dict(settles=[], open=(1.0, 0.01), zooms=[])
CARDS = []
END_CARD = None
FX = [
    dict(id="kinetic-hook", layer="behind", at=0.0, end=2.50, frames=[0.2, 0.8, 1.75, 2.3], note="the hook"),
    dict(id="kinetic-hook-front", layer="top", at=0.0, end=0.37),
    dict(id="icon-strike", layer="top", at=2.50, end=4.50, frames=[2.98, 3.94, 4.30], note="no timeline, no presets, nothing"),
    dict(id="prompt-bar", layer="top", at=4.50, end=5.90, frames=[5.05, 5.32, 5.55], note="the motif: one sentence types and sends"),
    dict(id="grade-slider", layer="cam", at=5.90, end=7.00, frames=[6.3, 6.8], note="make it warmer"),
    dict(id="magazine-cover", layer="behind", at=7.60, end=9.45, frames=[7.9, 8.6, 9.2], note="a magazine cover"),
    dict(id="nle-timeline", layer="top", at=9.30, end=10.90, frames=[9.7, 10.3, 10.56], note="nothing about editing"),
    dict(id="file-drop", layer="top", at=10.90, end=12.50, frames=[11.3, 11.95, 12.25], note="the raw file drops in"),
    dict(id="odometer-recursion", layer="cam", at=12.50, end=14.60, frames=[13.0, 13.9], note="a few minutes later"),
    dict(id="mood-curtain", layer="cam", at=14.60, end=16.20, frames=[14.9, 15.6], note="make it moody"),
    dict(id="grid-collapse", layer="cam", at=16.20, end=17.60, frames=[16.6, 17.2], note="lots of people do this"),
    dict(id="page-scroll", layer="top", at=17.60, end=19.20, frames=[17.8, 18.4, 18.92], note="the plan it made"),
    dict(id="comment-thread", layer="top", at=19.20, end=20.70, frames=[19.85, 20.45], note="I leave one note"),
    dict(id="word-stamp", layer="behind", at=20.80, end=22.40, frames=[21.6, 22.35], note="NEVER behind the head"),
    dict(id="giant-captions", layer="over", at=22.40, end=23.90, frames=[22.8, 23.5], note="bigger captions"),
    dict(id="video-card", layer="top", at=23.90, end=25.60, frames=[24.21, 24.81, 25.28], note="the walkthrough"),
    dict(id="comment-cta", layer="top", at=25.60, end="end", frames=[26.20, 28.00, 28.90], note="the CTA"),
    dict(id="camera-transitions", layer="over", at=0.0, end="end"),
]
SOUND = dict(sfx=[], music=None)
CARD_SFX = []
NEEDS = []
GENERATED = []
'''


def run(*cmd):
    subprocess.run(cmd, check=True, env=dict(os.environ, REEL_MACHINE_HOME=HOME))


def words():
    out = []
    for a, b, line in LINES:
        ws = line.split()
        step = (b - a) / len(ws)
        for i, w in enumerate(ws):
            out.append({"text": w, "start": round(a + i * step, 3), "end": round(a + (i + 0.85) * step, 3)})
    return out


def main():
    pack = sys.argv[sys.argv.index("--pack") + 1] if "--pack" in sys.argv else "default"
    if not os.path.exists(STANDIN):
        run(PY, os.path.join(KIT, "dev", "standin.py"), "video", STANDIN, "32")
    shutil.rmtree(LAB, ignore_errors=True)
    style = os.path.join(HOME, "style")
    shutil.rmtree(style, ignore_errors=True)
    shutil.copytree(os.path.join(KIT, "examples", "packs", pack), style)
    run(PY, os.path.join(KIT, "pipeline", "style.py"), os.path.join(style, "style.json"))
    run(PY, os.path.join(KIT, "pipeline", "new.py"), "fx-lab", STANDIN, "FX Lab", "--mode", "showcase")
    with open(os.path.join(LAB, "edit.py"), "w") as fh:
        fh.write(EDIT.format(src=STANDIN))
    shutil.rmtree(os.path.join(LAB, "fx"), ignore_errors=True)
    os.symlink(os.path.join(KIT, "fx"), os.path.join(LAB, "fx"))
    run(PY, os.path.join(KIT, "pipeline", "cut.py"), LAB)
    json.dump(words(), open(os.path.join(LAB, "words.json"), "w"), indent=1)
    shutil.copy(os.path.join(LAB, "assets", "aroll.mp4"), os.path.join(LAB, "public", "clean.mp4"))
    run(PY, os.path.join(KIT, "dev", "standin.py"), "matte", os.path.join(LAB, "assets", "aroll.mp4"),
        os.path.join(LAB, "assets", "subject.webm"))
    shutil.copy(os.path.join(LAB, "assets", "subject.webm"), os.path.join(LAB, "public", "subject.webm"))
    # silence for the master: there is no voice to mix
    tl = json.load(open(os.path.join(LAB, "timeline.json")))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t",
                    f"{tl['total']:.3f}", "-c:a", "pcm_s16le", os.path.join(LAB, "public", "master.wav")], check=True)
    print(f"LAB {LAB}  ({tl['total']:.2f}s, pack {pack}); fx/ -> {os.path.join(KIT, 'fx')}")


if __name__ == "__main__":
    main()
