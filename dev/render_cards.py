#!/usr/bin/env python3
"""Dev only: render library cards into a test project, as card agents would after their notes.
Run: .venv/bin/python dev/render_cards.py <project> <card id>=<library card>[@index-file] ... [--jobs 3]
e.g. c1=scissors c8b=dollar-split@index-followup.html
"""
import concurrent.futures as cf
import os
import shutil
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "pipeline"))
from common import HF, VENDOR  # noqa: E402


def one(project, cid, lib, index):
    d = os.path.join(project, "cards", cid)
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(os.path.join(KIT, "cards", lib), d, ignore=shutil.ignore_patterns("preview.jpg", "snapshots", "*.mp4"))
    if index != "index.html":
        shutil.copy(os.path.join(d, index), os.path.join(d, "index.html"))
    for f in os.listdir(d):                      # one composition per card folder
        if f.endswith(".html") and f != "index.html":
            os.remove(os.path.join(d, f))
    for f in ("brand.css",):
        shutil.copy(os.path.join(project, "style", f), d)
    shutil.copytree(os.path.join(project, "style", "fonts"), os.path.join(d, "fonts"), dirs_exist_ok=True)
    shutil.copy(os.path.join(KIT, "kit", "card.css"), d)
    shutil.copytree(VENDOR, os.path.join(d, "vendor"), dirs_exist_ok=True)
    shutil.copy(os.path.join(KIT, "kit", "hyperframes.json"), d)
    r = subprocess.run(HF + ["render", "-q", "delivery", "--quiet", "-o", f"{cid}.mp4"], cwd=d, capture_output=True, text=True)
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", os.path.join(d, f"{cid}.mp4")],
                       capture_output=True, text=True).stdout.strip()
    return cid, lib, r.returncode, n, (r.stdout + r.stderr)[-400:] if r.returncode else ""


def main():
    project = os.path.abspath(sys.argv[1])
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 3
    pairs = []
    for a in sys.argv[2:]:
        if "=" in a:
            cid, lib = a.split("=", 1)
            lib, _, index = lib.partition("@")
            pairs.append((cid, lib, index or "index.html"))
    with cf.ThreadPoolExecutor(jobs) as ex:
        for cid, lib, rc, n, err in ex.map(lambda p: one(project, *p), pairs):
            print(f"{cid:5} {lib:18} {'OK' if rc == 0 else 'FAIL'} frames {n} {err}", flush=True)


if __name__ == "__main__":
    main()
