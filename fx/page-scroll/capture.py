#!/usr/bin/env python3
"""page-scroll: capture a real page as tiles for the window card: the project's own storyboard, any local HTML file,
or a URL. Run it in your copy of the effect:

  PY <project>/fx/<id>/capture.py <file.html or URL> [--width 1080] [--scale 2] [--tile 1300] [--max 8000]

It finds the headless browser HyperFrames uses (npx -y hyperframes@0.8.139 browser path), screenshots the page
--width CSS px wide (the card shows 1080 page px across) at --scale device px per CSS px (2 stays sharp when the push
zooms in), trims the empty space under the content, and writes next to this file:
  page0.jpg, page1.jpg, ...   the page in tiles --tile CSS px tall (the card stacks them)
  page-full.png               the whole page at 1 px = 1 page px, to measure on
and prints TILES for fx.js. Then measure the rows you want lit on page-full.png (left, top, width, height, in page px)
into LIT: the underlines draw under those boxes, the rest of the page dims, and the push centres on them.
A page taller than --max CSS px is cut off at --max: raise it. HEADLESS_BROWSER=/path/to/it picks another browser.
"""
import os
import subprocess
import sys
import tempfile
from urllib.parse import quote

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
Image.MAX_IMAGE_PIXELS = None


def browser():
    if os.environ.get("HEADLESS_BROWSER"):
        return os.environ["HEADLESS_BROWSER"]
    npx = "npx.cmd" if os.name == "nt" else "npx"
    r = subprocess.run([npx, "-y", "hyperframes@0.8.139", "browser", "path"], capture_output=True, text=True)
    path = (r.stdout.strip().splitlines() or [""])[-1].strip()
    if not path or not os.path.exists(path):
        sys.exit("no headless browser found: run `npx -y hyperframes@0.8.139 browser ensure`, or set HEADLESS_BROWSER=/path/to/it")
    return path


def opt(a, name, default):
    return type(default)(a[a.index(name) + 1]) if name in a else default


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("--"):
        sys.exit(__doc__)
    target = a[0]
    width, scale, tile, tall = opt(a, "--width", 1080), opt(a, "--scale", 2), opt(a, "--tile", 1300), opt(a, "--max", 8000)
    if os.path.exists(os.path.expanduser(target)):
        target = "file://" + quote(os.path.abspath(os.path.expanduser(target)))
    shot = os.path.join(tempfile.mkdtemp(), "page.png")
    subprocess.run([browser(), "--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                    "--allow-file-access-from-files", "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=6000", f"--force-device-scale-factor={scale}",
                    f"--window-size={width},{tall}", f"--screenshot={shot}", target],
                   check=True, capture_output=True)
    im = Image.open(shot).convert("RGB")
    px = np.asarray(im).astype(np.int16)
    bg = px[-1].mean(axis=0)                                   # the page's own background, from its last row
    rows = np.nonzero(np.abs(px - bg).max(axis=(1, 2)) > 12)[0]
    bottom = int(rows[-1]) + 1 if len(rows) else im.height
    h_css = min(tall, int(np.ceil(bottom / scale)) + 48)       # the content plus a margin under it
    if bottom >= im.height - scale:
        print(f"the page runs past --max {tall}: it is cut off there; raise --max to get all of it")
    im = im.crop((0, 0, im.width, min(im.height, h_css * scale)))
    k = 1080 / width                                            # page px: the page as the card shows it, 1080 wide
    for old in os.listdir(HERE):                                # tiles from an earlier capture
        if old.startswith("page") and old[4:-4].isdigit() and old.endswith(".jpg"):
            os.remove(os.path.join(HERE, old))
    n = int(np.ceil(h_css / tile))
    for i in range(n):
        y0, y1 = i * tile * scale, min(im.height, (i + 1) * tile * scale)
        im.crop((0, y0, im.width, y1)).save(os.path.join(HERE, f"page{i}.jpg"), quality=88)
    im.resize((1080, round(h_css * k)), Image.LANCZOS).save(os.path.join(HERE, "page-full.png"))
    print(f"{n} tiles, the page is {round(h_css * k)} page px tall ({width} CSS px wide at {scale}x). In fx.js:")
    print(f"var TILES = {{ n: {n}, h: {round(tile * k, 2):g}, height: {round(h_css * k, 2):g} }};")
    print("var LIT = [[left, top, width, height], ...];   // the rows to light, measured on page-full.png (page px)")


if __name__ == "__main__":
    main()
