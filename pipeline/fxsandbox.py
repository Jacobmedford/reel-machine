#!/usr/bin/env python3
"""FX sandbox: preview some of a video's motion graphics (edit.FX) without touching the real build, so several agents
can work on one video at once.

Makes <project>/work/sandbox/<name>/ (its own edit.py copy, words/timeline, public/ with every heavy file linked from
the project), builds it with only the FX ids you name (the others are left out, so a broken one can't break yours),
and snapshots the times you ask for. fx/ is the project's own folder (linked), so what you write there is the real file.
style/ is linked too, so the sandbox builds in the project's own pack; the sandbox keeps its own brand.css and fonts/
(the build installs them), so it never writes into the project's public/.

Run: PY pipeline/fxsandbox.py <project> <name> --only fx01,fx16 --at 0.5 1.2 2.0 [--fresh]
  --fresh   re-copy edit.py from the project (otherwise your sandbox edit.py edits are kept)
Edit <sandbox>/edit.py to try GRADES / CUT_WINDOWS / CAMERA changes; report them, the real edit.py is merged by hand.
Prints the snapshot paths: read every one at full size.
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KIT, PY  # noqa: E402


OWN = ("index.html", "snapshots", "fx", "brand.css", "fonts")   # the sandbox's own: never links into the project's public


def prepare(project, name, fresh=False):
    """<project>/work/sandbox/<name>/: copies of edit.py (unless kept), words, timeline; links to fx/, assets/, audio/,
    style/ (the project's own pack) and the heavy public files. Returns (sandbox, its public/)."""
    sb = os.path.join(project, "work", "sandbox", name)
    pub, ppub = os.path.join(sb, "public"), os.path.join(project, "public")
    os.makedirs(pub, exist_ok=True)
    for f in ("words.json", "timeline.json"):
        shutil.copy(os.path.join(project, f), os.path.join(sb, f))
    if fresh or not os.path.exists(os.path.join(sb, "edit.py")):
        shutil.copy(os.path.join(project, "edit.py"), os.path.join(sb, "edit.py"))
    for d in ("fx", "assets", "audio", "style"):
        link, target = os.path.join(sb, d), os.path.join(project, d)
        if not os.path.lexists(link) and os.path.exists(target):
            os.symlink(target, link)
    for f in OWN[3:]:                              # an older sandbox linked the pack files: drop the links, not the files
        if os.path.islink(os.path.join(pub, f)):
            os.unlink(os.path.join(pub, f))
    for f in os.listdir(ppub):                     # heavy media and vendor: links; the page, snapshots, the pack: own
        if f in OWN:
            continue
        if not os.path.lexists(os.path.join(pub, f)):
            os.symlink(os.path.join(ppub, f), os.path.join(pub, f))
    return sb, pub


def main():
    a = sys.argv[1:]
    project, name = os.path.abspath(os.path.expanduser(a[0])), a[1]
    only = a[a.index("--only") + 1] if "--only" in a else ""
    times = [float(x) for x in a[a.index("--at") + 1:] if not x.startswith("--")] if "--at" in a else []
    sb, pub = prepare(project, name, fresh="--fresh" in a)
    env = dict(os.environ, FX_ONLY=only)
    subprocess.run([PY, os.path.join(KIT, "pipeline", "build.py"), sb, "--stills"], check=True, env=env)
    if times:
        sys.path.insert(0, os.path.join(KIT, "pipeline"))
        from storyboard import snapshot
        out = os.path.join(sb, "shots")
        shutil.rmtree(out, ignore_errors=True)
        names = snapshot(sb, times, out)
        for t, n in zip(times, names):
            print(f"{t:7.3f}  {os.path.join(out, n)}")


if __name__ == "__main__":
    main()
