#!/usr/bin/env python3
"""Dev only: redraw every library card's preview.jpg (its final frame) in a pack, by default the neutral one.
Run: .venv/bin/python dev/previews.py [--pack examples/packs/default] [card ...]
"""
import os
import re
import shutil
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "onboarding"))
sys.path.insert(0, os.path.join(KIT, "pipeline"))
import board  # noqa: E402


def main():
    args = sys.argv[1:]
    pack = os.path.join(KIT, "examples", "packs", "default")
    if "--pack" in args:
        i = args.index("--pack")
        pack = os.path.abspath(args[i + 1])
        args = args[:i] + args[i + 2:]
    cards = args or sorted(d for d in os.listdir(os.path.join(KIT, "cards"))
                           if os.path.exists(os.path.join(KIT, "cards", d, "index.html")))
    work = tempfile.mkdtemp(prefix="previews-")
    for cid in cards:
        d = os.path.join(work, cid)
        shutil.copytree(os.path.join(KIT, "cards", cid), d, ignore=shutil.ignore_patterns("*.mp4", "snapshots", "preview.jpg"))
        board.kit_files(d, pack, ["card.css"])
        m = re.search(r'id="root"[^>]*data-duration="([\d.]+)"', open(os.path.join(d, "index.html"), encoding="utf-8").read())
        frames = round(float(m.group(1)) * 30)
        board.snap(d, (frames - 1) / 30, os.path.join(KIT, "cards", cid, "preview.jpg"))
        print(f"{cid:18} preview.jpg  (frame {frames - 1})", flush=True)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
