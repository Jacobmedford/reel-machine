#!/usr/bin/env python3
"""Dev only: the README's images, all made from the stand-in (no real person) so they can be regenerated any time.

  effects   docs/img/effects.jpg: every effect's preview.jpg on one labelled sheet
  styles    docs/img/styles.jpg: the same moments of the effects lab in the kit's four packs (packs/: Harbor, Film,
            Signal, Terminal)
  modes     docs/img/modes.jpg: hi-fi, lo-fi and showcase frames from each of the four packs' style boards
  pages     docs/img/storyboard.jpg and board.jpg: the lab's storyboard page in Harbor and Harbor's style board page
Run: .venv/bin/python dev/readme_shots.py effects|styles|modes|pages|all   (styles and pages need the lab: dev/fxlab.py)
It renders: run it through the heavy lock where there is one (HOME/bin/heavy). Each pack is built in place first
(brand.css and fonts/ beside its style.json, as pipeline/pack.py builds a pack; git ignores both).
"""
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "pipeline"))
import pack as PK  # noqa: E402
OUT = os.path.join(KIT, "docs", "img")
PY = sys.executable
FONTS = os.path.join(KIT, "examples", "packs", "default", "fonts")      # the sheets' labels: the neutral sample pack's
PACKS = [("harbor", "Harbor"), ("film", "Film"), ("signal", "Signal"), ("terminal", "Terminal")]   # the kit's packs/
LAB = os.path.join(KIT, "dev", "out", "fx-home", "projects", "fx-lab")
LAB_ENV = dict(os.environ, REEL_MACHINE_HOME=os.path.join(KIT, "dev", "out", "fx-home"))
PAPER, INK, MUTED, HAIR = (246, 245, 241), (18, 19, 20), (110, 109, 105), (214, 212, 206)
ORDER = ["kinetic-hook", "icon-strike", "prompt-bar", "grade-slider", "magazine-cover", "nle-timeline", "file-drop",
         "odometer-recursion", "mood-curtain", "grid-collapse", "page-scroll", "comment-thread", "word-stamp",
         "giant-captions", "video-card", "comment-cta", "camera-transitions"]


def font(name, size):
    if not os.path.exists(os.path.join(FONTS, name)):          # the sample pack's Google fonts, fetched once
        subprocess.run([PY, os.path.join(KIT, "pipeline", "style.py"), os.path.join(os.path.dirname(FONTS), "style.json")],
                       check=True, stdout=subprocess.DEVNULL)
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def built(name):
    """the kit's pack packs/<name>, built in place: brand.css and fonts/ from its style.json, local-fonts/ and
    extra.css, exactly as pipeline/pack.py builds a pack"""
    d = os.path.join(KIT, "packs", name)
    PK.build(d)
    return d


def sheet(tiles, cols, tw, th, labels=None, sub=None, gap=36, pad=56, label_h=0, row_labels=None, rl_w=0):
    """tiles: image paths in reading order; labels under each; optional row labels on the left"""
    rows = (len(tiles) + cols - 1) // cols
    W = pad * 2 + rl_w + cols * tw + (cols - 1) * gap
    H = pad * 2 + rows * (th + label_h) + (rows - 1) * gap
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    f_lab, f_sub, f_row = font("Inter-normal-600.ttf", 21), font("JetBrainsMono-normal-500.ttf", 16), font("Inter-normal-700.ttf", 28)
    for i, path in enumerate(tiles):
        r, c = divmod(i, cols)
        if r == rows - 1 and len(tiles) % cols:                      # centre a short last row
            c += (cols - len(tiles) % cols) / 2
        x, y = int(pad + rl_w + c * (tw + gap)), pad + r * (th + label_h + gap)
        t = Image.open(path).convert("RGB").resize((tw, th), Image.LANCZOS)
        im.paste(t, (x, y))
        d.rectangle((x - 1, y - 1, x + tw, y + th), outline=HAIR, width=1)
        if labels:
            if sub:
                d.text((x, y + th + 15), sub[i], font=f_sub, fill=MUTED)
            d.text((x + (36 if sub else 0), y + th + 11), labels[i], font=f_lab, fill=INK)
    if row_labels:
        for r, text in enumerate(row_labels):
            y = pad + r * (th + label_h + gap) + th // 2 - 16
            d.text((pad, y), text, font=f_row, fill=INK)
    return im


def save(im, name, width=None):
    os.makedirs(OUT, exist_ok=True)
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    p = os.path.join(OUT, name)
    im.save(p, quality=84, optimize=True, progressive=True)
    print(f"{p}  {im.width}x{im.height}  {os.path.getsize(p) // 1024} KB")


def effects():
    tiles = [os.path.join(KIT, "fx", e, "preview.jpg") for e in ORDER]
    im = sheet(tiles, 6, 270, 480, labels=ORDER, sub=[f"{i + 1:02d}" for i in range(len(ORDER))], label_h=56)
    save(im, "effects.jpg", width=1800)


def lab_shots(pack, times, name):
    """the effects lab at these times (none: built only), in one of the kit's packs, in a sandbox of its own.
    Returns the sandbox and its shots"""
    sb = os.path.join(LAB, "work", "sandbox", name)
    os.makedirs(sb, exist_ok=True)
    shutil.rmtree(os.path.join(sb, "style"), ignore_errors=True)
    shutil.copytree(built(pack), os.path.join(sb, "style"), ignore=shutil.ignore_patterns("board"))
    at = ["--at"] + [str(t) for t in times] if times else []
    subprocess.run([PY, os.path.join(KIT, "pipeline", "fxsandbox.py"), LAB, name] + at,
                   check=True, env=LAB_ENV, stdout=subprocess.DEVNULL)
    return sb, [os.path.join(sb, "shots", f"f{k:03d}.jpg") for k in range(len(times))]


def styles():
    times = [0.30, 8.60, 16.62, 21.65, 23.55, 27.95]
    rows = [lab_shots(p, times, f"readme-{p}")[1] for p, _ in PACKS]
    im = sheet([t for r in rows for t in r], len(times), 270, 480, row_labels=[n for _, n in PACKS], rl_w=150)
    save(im, "styles.jpg", width=1800)


def modes():
    clip = os.path.join(KIT, "dev", "out", "standin", "standin.mp4")
    tiles = []
    for p, _ in PACKS:
        pack = built(p)
        subprocess.run([PY, os.path.join(KIT, "onboarding", "board.py"), "--pack", pack, "--clip", clip, "--cards", "scissors"],
                       check=True, stdout=subprocess.DEVNULL)
        tiles += [os.path.join(pack, "board", "img", f"{m}.jpg") for m in ("hifi", "lofi", "showcase")]
    im = sheet(tiles, 3, 300, 533, labels=["Hi-fi", "Lo-fi", "Showcase"] * len(PACKS), label_h=50,
               row_labels=[n for _, n in PACKS], rl_w=150)
    save(im, "modes.jpg", width=1400)


def page_shot(folder, out, height, port):
    """a headless screenshot of a served review page, cropped to its top and scaled to 1000 px wide"""
    chrome = subprocess.run(["npx", "-y", "hyperframes@0.8.139", "browser", "path"], capture_output=True,
                            text=True).stdout.strip().splitlines()[-1]
    srv = subprocess.Popen([sys.executable, os.path.join(KIT, "storyboard", "serve.py"), folder, "--port", str(port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import time
        import urllib.request
        for _ in range(60):                                       # wait until the page answers (a few seconds)
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except OSError:
                time.sleep(0.25)
        png = os.path.join(KIT, "dev", "out", f"page-{port}.png")
        subprocess.run([chrome, "--headless", "--disable-gpu", "--hide-scrollbars", f"--screenshot={png}",
                        f"--window-size=1200,{height + 600}", f"http://127.0.0.1:{port}/"], capture_output=True)
        im = Image.open(png).convert("RGB").crop((0, 0, 1200, height))
        save(im.resize((1000, round(height * 1000 / 1200)), Image.LANCZOS), out)
    finally:
        srv.terminate()


def pages():
    sb, _ = lab_shots("harbor", [], "readme-pages")          # the lab built in Harbor (its own sandbox, its own pack)
    subprocess.run([PY, os.path.join(KIT, "pipeline", "storyboard.py"), sb, "--version", "1"], check=True, env=LAB_ENV,
                   stdout=subprocess.DEVNULL)
    page_shot(sb, "storyboard.jpg", 1700, 8797)
    harbor = os.path.join(KIT, "packs", "harbor")
    if not os.path.exists(os.path.join(harbor, "board", "index.html")):
        modes()
    page_shot(os.path.join(harbor, "board"), "board.jpg", 1690, 8798)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("effects", effects), ("styles", styles), ("modes", modes), ("pages", pages)):
        if what in (name, "all"):
            fn()
