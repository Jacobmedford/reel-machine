#!/usr/bin/env python3
"""Package: the skill as one zip for hosts that install skills by upload (Claude Cowork, claude.ai, ChatGPT).
The zip holds one folder named reel-machine with SKILL.md at its top, and leaves out everything setup.py makes on the
creator's computer (the Python environment, GSAP, models) and everything only the kit's own tests use (dev/).
In a git checkout it packs only the files git tracks, so nothing kept beside the kit by hand (a creator's style or
projects, local notes, a hidden tool folder) can reach the zip.
Run: python3 setup/package.py   -> dist/reel-machine.zip
"""
import os
import subprocess
import zipfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".venv", ".models", ".git", "dist", "dev", "__pycache__", "vendor", "snapshots", "node_modules",
             "fonts", "board"}                   # fonts and boards are generated per pack (docs/ ships: the README's images)
SKIP_FILES = {".DS_Store"}


def candidates(kit=KIT):
    """every file the kit holds, relative to it: what git tracks in a checkout, else every file under it outside
    hidden folders. A symlink is left out and named: zipped, it would carry whatever it points at."""
    try:
        r = subprocess.run(["git", "-C", kit, "ls-files", "-z"], capture_output=True, text=True)
        tracked = sorted(f for f in r.stdout.split("\0") if f) if r.returncode == 0 else []
    except OSError:
        tracked = []
    if not tracked:
        for root, dirs, files in os.walk(kit):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            tracked += [os.path.relpath(os.path.join(root, f), kit) for f in sorted(files)]
    out = []
    for f in tracked:
        p = os.path.join(kit, f)
        if os.path.islink(p):
            print(f"skipped a symlink (ship the file itself): {f}")
        elif os.path.isfile(p):
            out.append(f)
    return out


def keep(rel):
    """whether a kit file goes in the zip"""
    parts = rel.split(os.sep) if os.sep in rel else rel.split("/")
    name = parts[-1]
    if any(p in SKIP_DIRS or p.startswith(".") for p in parts[:-1]):
        return False
    if name in SKIP_FILES or name.endswith(".pyc"):
        return False
    return not (name == "brand.css" and "packs" in parts[:-1])


def main(out=None):
    out = out or os.path.join(KIT, "dist", "reel-machine.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in candidates():
            if keep(rel):
                z.write(os.path.join(KIT, rel), os.path.join("reel-machine", rel))
                n += 1
    print(f"{out}  {n} files, {os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
