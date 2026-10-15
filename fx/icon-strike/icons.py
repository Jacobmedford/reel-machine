#!/usr/bin/env python3
"""icon-strike: fetch real app icons by name from the public store search API, for when the speaker names real apps.

Run: PY icons.py <folder> "App One" "App Two" [--desktop] [--country us] [--dry-run]
  <folder>    your project's copy of the effect (<project>/fx/<id>/), never the library folder
  --desktop   search desktop apps instead of phone apps
  --country   the store to search (default us)
  --dry-run   print what it would fetch, write nothing
Writes <folder>/<name>.png (the store artwork, 512px) for each name and prints the ICONS lines to paste into
fx.js. App icons belong to their owners: they stay in your project's copy of the effect, out of the library and out
of anything you publish as a template.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def search(name, country, desktop):
    q = urllib.parse.urlencode({"term": name, "entity": "macSoftware" if desktop else "software", "limit": 5,
                                "country": country})
    with urllib.request.urlopen(f"https://itunes.apple.com/search?{q}", timeout=20) as r:
        results = json.load(r).get("results", [])
    if not results:
        return None
    exact = [x for x in results if x.get("trackName", "").lower() == name.lower()]
    return (exact or results)[0]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "app"


def main():
    argv, pos, country, dry, desktop = sys.argv[1:], [], "us", False, False
    while argv:
        a = argv.pop(0)
        if a == "--country" and argv:
            country = argv.pop(0)
        elif a == "--dry-run":
            dry = True
        elif a == "--desktop":
            desktop = True
        else:
            pos.append(a)
    if len(pos) < 2:
        raise SystemExit(__doc__)
    folder, names = os.path.abspath(os.path.expanduser(pos[0])), pos[1:]
    if os.path.realpath(folder) == os.path.realpath(HERE) and not dry:
        raise SystemExit("that is the library folder: copy the effect into your project (fx/<id>/) and fetch the icons there")
    if not os.path.isdir(folder):
        raise SystemExit(f"no folder {folder}")
    lines = []
    for name in names:
        app = search(name, country, desktop)
        if not app:
            print(f"{name}: nothing found in the {country} store (try --desktop, or another spelling)")
            continue
        url = (app.get("artworkUrl512") or app.get("artworkUrl100", "")).replace("bb.jpg", "bb.png")
        file = slug(name) + ".png"
        print(f"{name}: {app.get('trackName')} by {app.get('sellerName', '?')}  {url}")
        if not dry:
            with urllib.request.urlopen(url, timeout=30) as r, open(os.path.join(folder, file), "wb") as f:
                f.write(r.read())
        word = name.split()[0].lower()
        lines.append("  { on: %s, label: %s, glyph: \"\", img: %s }" % (json.dumps(word), json.dumps(name), json.dumps(file)))
    if lines:
        print("\nICONS for fx.js (set `on` to the word the icon pops on):\nvar ICONS = [\n" + ",\n".join(lines) + "\n];")


if __name__ == "__main__":
    main()
