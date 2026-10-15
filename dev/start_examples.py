#!/usr/bin/env python3
"""Dev only: the start page's examples (storyboard/examples/), all made from the drawn stand-in (dev/standin.py), so
they hold nobody's footage and can be made again any time.

  modes   hifi.mp4, lofi.mp4, showcase.mp4: one stand-in project per mode. Its edit.py is the reference edit
          (examples/<mode>/edit.py) pointed at the stand-in, with a fixed words.json the stand-in "says" and stand-in
          material where the edit needs it (library cards, drawn screenshots, the effects library). Each one goes
          through the normal path (new.py, cut.py, build.py, then HyperFrames at delivery quality, cut at the window's
          end the way render.py --hook cuts the hook) and is trimmed to its 6 s window: 540x960 H.264 crf 28, no
          audio, under 1.5 MB.
  styles  style-<name>.jpg for each pack folder: the same moment of the stand-in hi-fi project in that pack, 540x960.
          <name> is the folder's name (a home's style/ folder is harbor, the default pack's name).
Run: PY dev/start_examples.py [--modes hifi,lofi,showcase] [--pack <dir>] [--packs <dir> [<dir> ...]] [--out <dir>]
  no options  the three mode clips, plus a style frame for every pack in the kit's packs/ folder (when it has one)
  --modes     only these mode clips (and no style frames unless --packs is given too)
  --packs     style frames for these pack folders (and no mode clips unless --modes is given too)
  --pack      the pack the mode clips wear: the kit's packs/harbor when it exists, else examples/packs/default
  --out       where the files go (default storyboard/examples/)
It renders: run it through the heavy lock where there is one (HOME/bin/heavy). Its work lives in
dev/out/start-home/, a home of its own (the pack, the stand-in, the three projects, GSAP copied from the installed kit).
"""
import argparse
import json
import math
import os
import re
import runpy
import shutil
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "pipeline"))
sys.path.insert(0, os.path.join(KIT, "dev"))
import common  # noqa: E402  (imported before the home moves below: its VENDOR is the installed kit's GSAP)

INSTALLED_VENDOR = common.VENDOR
HOME = os.path.join(KIT, "dev", "out", "start-home")
os.environ["REEL_KIT_HOME"] = os.environ["REEL_MACHINE_HOME"] = HOME      # every script below works in the dev home
import fxlab  # noqa: E402  (the showcase script: the lines the effects lab's stand-in says)
import hook as HK  # noqa: E402
import pack as PK  # noqa: E402

PY = sys.executable
PIPE = os.path.join(KIT, "pipeline")
STANDIN = os.path.join(HOME, "standin", "standin.mp4")
STANDIN_SECONDS = 66                 # the longest reference edit (hi-fi) reads its take to 63.5 s, plus its 0.6 s hold
OUT = os.path.join(KIT, "storyboard", "examples")
FPS = 30
SIZE, CRF, MAX_BYTES = (540, 960), 28, 1_500_000
FRAMES = {"WIDE": (1080, 1920, 0, 0), "CLOSE": (864, 1536, 108, 192)}    # a 1080x1920 take: full frame, 1.25x in
# each mode's 6 s on its output timeline, chosen so the loop joins on a cut: hi-fi a data card, then type behind the head
# as the wall fills; lo-fi a tip's text box, then a screenshot over the speaker, then a hard zoom; showcase the hook's
# stamped lines and the next three effects whole, one per line (from 0.0 the window would end inside the fourth)
WINDOWS = {"hifi": (8.0, 14.0), "lofi": (14.0, 20.0), "showcase": (1.0, 7.0)}
STYLE_AT = 2.0                       # the style frame: the hi-fi hook settled (eyebrow, both lines, the fan, a caption)
HIFI_CARDS = {"c1": "scissors", "c2": "source-screenshot", "c3": "counter-loupe", "c4": "doubling",
              "c5": "task-grid", "c6": "lines-by-group", "c7": "pie"}     # the library cards were built for these windows
# lo-fi: what the stand-in says, on the output timeline, landed on the reference edit's boxes, overlays and zooms
LOFI_LINES = [
    (0.05, 3.30, "Three things I do every Sunday so my week runs itself."),
    (3.45, 5.40, "Number one: I dump everything out of my head."),
    (5.50, 7.60, "Every task, every idea."),
    (7.80, 9.30, "Then I sort it into"),
    (9.40, 10.20, "three lists."),
    (10.30, 11.10, "This week,"),
    (11.20, 12.00, "someday,"),
    (12.10, 12.90, "and not mine."),
    (13.00, 14.40, "Everything else waits."),
    (14.60, 16.60, "Number two: I block my calendar"),
    (16.70, 18.20, "before anyone else can."),
    (18.30, 19.50, "Meetings fit around it,"),
    (19.60, 20.70, "and the deep work goes first."),
    (21.00, 22.70, "Every single week."),
    (23.00, 24.80, "Number three: I pick one thing."),
    (24.90, 26.30, "The one that matters most."),
    (26.40, 28.30, "If only that gets done,"),
    (28.40, 29.80, "the week was a win."),
    (30.20, 31.50, "Want my template?"),
    (31.60, 33.90, "It is the one I use every Sunday."),
    (34.10, 36.90, "Comment PLAN and I will send it over."),
]
OVERRIDE = '''

# ---- the stand-in (dev/start_examples.py): the drawn figure's footage in place of the take above
SRC = "{src}"
FRAMES = {frames}
{extra}'''


def run(*cmd, **kw):
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def quiet(*cmd):
    """a pipeline step with its output kept back, shown (the end of it) only when the step fails"""
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        print((r.stdout + r.stderr)[-3000:], file=sys.stderr)
        sys.exit(f"failed: {' '.join(os.path.basename(str(c)) for c in cmd[:2])} {' '.join(str(c) for c in cmd[2:])}")
    return r


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def frames_of(path):
    return int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                               "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True,
                              text=True).stdout.strip() or 0)


def spread(lines):
    """[(start, end, text)] on the output timeline -> words.json: each line's words spread evenly over it"""
    out = []
    for a, b, text in lines:
        ws = text.split()
        step = (b - a) / len(ws)
        out += [{"text": w, "start": round(a + i * step, 3), "end": round(a + (i + 0.85) * step, 3)}
                for i, w in enumerate(ws)]
    return out


def caption_lines(G):
    """hi-fi: the stand-in says what its captions show (CAPS), plus the words its titles set behind the head"""
    caps = sorted(G["CAPS"], key=lambda c: c[0])
    lines = []
    for i, c in enumerate(caps):
        nxt = caps[i + 1][0] if i + 1 < len(caps) else c[0] + 1.2
        end = c[3] if len(c) > 3 and isinstance(c[3], (int, float)) else nxt
        lines.append((c[0], min(end, nxt) - 0.04, c[1].replace("*", "")))
    for B in G.get("BEHIND", []):
        if B["kind"] == "titles":
            ts = [t for t, _ in B["items"]] + [B["end"]]
            lines += [(t, ts[k + 1] - 0.04, w) for k, (t, w) in enumerate(B["items"])]
    return sorted(lines)


def words_for(mode, G):
    if mode == "hifi":
        return spread(caption_lines(G))
    if mode == "lofi":
        return spread(LOFI_LINES)
    return fxlab.words()                                      # showcase: the effects lab's own lines


# ---------------------------------------------------------------- the dev home and its pack
def install_pack(src, dest):
    """a pack folder -> dest, built (brand.css + fonts/) as pack.py builds a named pack. Fonts already fetched into
    dest stay (a rebuild needs no network); everything else is replaced, so nothing of another pack lingers"""
    src = os.path.abspath(src)
    if not os.path.exists(os.path.join(src, "style.json")):
        sys.exit(f"{src} has no style.json: not a pack")
    os.makedirs(dest, exist_ok=True)
    for f in os.listdir(dest):
        if f != "fonts":
            p = os.path.join(dest, f)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for f in os.listdir(src):
        a, b = os.path.join(src, f), os.path.join(dest, f)
        if f == "fonts" and os.path.isdir(a):                 # a pack that ships built brings its fonts
            shutil.copytree(a, b, dirs_exist_ok=True)
        elif f not in ("board", "brand.css", "fonts"):
            shutil.copytree(a, b) if os.path.isdir(a) else shutil.copy2(a, b)
    PK.build(dest)
    return dest


def setup_home(pack):
    vendor = os.path.join(HOME, "vendor")
    if not os.path.exists(os.path.join(vendor, "gsap.min.js")):
        if not os.path.exists(os.path.join(INSTALLED_VENDOR, "gsap.min.js")):
            sys.exit(f"no GSAP in {INSTALLED_VENDOR}: run python3 setup/setup.py first")
        shutil.copytree(INSTALLED_VENDOR, vendor, dirs_exist_ok=True)
    install_pack(pack, os.path.join(HOME, "style"))
    if not os.path.exists(STANDIN) or duration(STANDIN) < STANDIN_SECONDS - 0.5:
        run(PY, os.path.join(KIT, "dev", "standin.py"), "video", STANDIN, STANDIN_SECONDS)


# ---------------------------------------------------------------- the stand-in projects
def stand_in(mode, cutout_until=0.0, cards=()):
    """the stand-in project for a mode, cut and built: <dev home>/projects/start-<mode>. cutout_until: key the figure
    out of the first this many seconds (the cutout windows the render reaches); cards: library cards to render"""
    slug = f"start-{mode}"
    p = os.path.join(HOME, "projects", slug)
    example = os.path.join(KIT, "examples", mode, "edit.py")
    G = runpy.run_path(example)
    if not os.path.exists(os.path.join(p, "edit.py")):
        quiet(PY, os.path.join(PIPE, "new.py"), slug, STANDIN, G.get("TITLE", slug), "--mode", mode)
    shutil.rmtree(os.path.join(p, "style"), ignore_errors=True)            # the dev home's pack, as it is now
    PK.copy_into(os.path.join(HOME, "style"), os.path.join(p, "style"))
    with open(example, encoding="utf-8") as fh:
        text = fh.read()
    extra = ""
    if mode == "hifi":            # its joins would snap the 10.067 reframe onto a J-cut inside a cutout window
        end = round((1.0 + sum(e - s for s, e in G["KEEP"])) * FPS) / FPS
        extra = f"KEEP = [(1.0, {end:.4f})]    # one unbroken take as long as the cut: the shots land where the edit put them\n"
    with open(os.path.join(p, "edit.py"), "w", encoding="utf-8") as fh:
        fh.write(text.rstrip("\n") + "\n" + OVERRIDE.format(src=STANDIN, frames=repr(FRAMES), extra=extra))
    quiet(PY, os.path.join(PIPE, "cut.py"), p)
    aroll, pub = os.path.join(p, "assets", "aroll.mp4"), os.path.join(p, "public")
    shutil.copy2(aroll, os.path.join(pub, "clean.mp4"))
    with open(os.path.join(p, "words.json"), "w", encoding="utf-8") as fh:
        json.dump(words_for(mode, G), fh, indent=1)
    with open(os.path.join(p, "timeline.json"), encoding="utf-8") as fh:
        total = json.load(fh)["total"]
    master = os.path.join(pub, "master.wav")                   # no voice to mix: silence, as the effects lab does
    if not os.path.exists(master) or abs(duration(master) - total) > 0.01:
        run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{total:.3f}",
            "-c:a", "pcm_s16le", master)
    if cutout_until:
        key_figure(p, cutout_until)
    for cid in cards:
        card(p, cid, HIFI_CARDS[cid])
    if mode == "lofi":
        draw_media(os.path.join(pub, "media"))
    if mode == "showcase":
        shutil.rmtree(os.path.join(p, "fx"), ignore_errors=True)
        for F in G["FX"]:
            shutil.copytree(os.path.join(KIT, "fx", F["id"]), os.path.join(p, "fx", F["id"]),
                            ignore=shutil.ignore_patterns("preview.jpg"))
    quiet(PY, os.path.join(PIPE, "build.py"), p)
    return p


def key_figure(p, until):
    """the cutout (subject.webm) for the first `until` seconds of the cut: the stand-in keys out by its colour"""
    aroll, sub = os.path.join(p, "assets", "aroll.mp4"), os.path.join(p, "assets", "subject.webm")
    fresh = (os.path.exists(sub) and os.path.getmtime(sub) > os.path.getmtime(aroll) and duration(sub) >= until - 0.05)
    if not fresh:
        head = os.path.join(p, "work", "aroll-head.mp4")
        run("ffmpeg", "-v", "error", "-y", "-i", aroll, "-t", f"{until:.3f}", "-c", "copy", head)
        quiet(PY, os.path.join(KIT, "dev", "standin.py"), "matte", head, sub)
    shutil.copy2(sub, os.path.join(p, "public", "subject.webm"))


def card(p, cid, lib):
    """a library card rendered into the project as a card agent would (dev/render_cards.py), again only when the pack
    it was rendered in has changed"""
    d = os.path.join(p, "cards", cid)

    def data(path):
        with open(path, "rb") as fh:
            return fh.read()
    same = (os.path.exists(os.path.join(d, f"{cid}.mp4")) and os.path.exists(os.path.join(d, "brand.css"))
            and data(os.path.join(d, "brand.css")) == data(os.path.join(p, "style", "brand.css")))
    if not same:
        r = quiet(PY, os.path.join(KIT, "dev", "render_cards.py"), p, f"{cid}={lib}")
        if " OK " not in r.stdout:
            sys.exit(f"card {cid} ({lib}) did not render:\n{r.stdout}")


# ---------------------------------------------------------------- lo-fi's drawn artifacts (never a real screenshot)
def font(size):
    from PIL import ImageFont
    return ImageFont.load_default(size=size)


def draw_media(media):
    """what the lo-fi reference edit lays on and behind the speaker, drawn: a week calendar, a notes app scrolling, a
    desk and a sticky note"""
    os.makedirs(media, exist_ok=True)
    jobs = (("calendar-week.png", calendar), ("desk.jpg", desk), ("one-thing.jpg", sticky), ("notes-scroll.mp4", notes))
    for name, draw in jobs:
        if not os.path.exists(os.path.join(media, name)):
            draw(os.path.join(media, name))


def calendar(path, W=938, H=720):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 62), fill="#F1F0EC")
    for i, c in enumerate(("#E0605A", "#E2B34A", "#5DB35E")):
        d.ellipse((22 + i * 26, 23, 38 + i * 26, 39), fill=c)
    d.text((112, 16), "This week", font=font(28), fill="#1F1F1F")
    d.text((W - 196, 21), "Oct 12 to 16", font=font(21), fill="#7A7873")
    x0, y0, rh = 78, 116, 57
    cw = (W - x0 - 18) / 5
    for i, day in enumerate(("Mon 12", "Tue 13", "Wed 14", "Thu 15", "Fri 16")):
        d.text((x0 + i * cw + 10, 80), day, font=font(20), fill="#4D4C49")
    for r in range(11):
        y = y0 + r * rh
        d.line((x0, y, W - 18, y), fill="#ECEAE5", width=1)
        if r < 10:
            d.text((16, y - 9), f"{8 + r}:00", font=font(16), fill="#9A9893")
    for i in range(6):
        x = x0 + i * cw
        d.line((x, y0, x, y0 + 10 * rh), fill="#ECEAE5", width=1)
    blocks = [(0, 0, 1, "Plan the week", "#F4DCA9", "#7C5410")]
    blocks += [(i, 1, 3, "Deep work", "#CCDAF7", "#284A97") for i in range(5)]
    blocks += [(1, 6, 7, "Calls", "#CFEBD8", "#22703D"), (3, 6, 7, "Calls", "#CFEBD8", "#22703D"),
               (2, 5, 6, "Lunch", "#EDEBE7", "#5A5853"), (4, 8, 9, "Admin", "#EDEBE7", "#5A5853")]
    for col, h0, h1, label, bg, ink in blocks:
        x, y = x0 + col * cw + 4, y0 + h0 * rh + 3
        d.rounded_rectangle((x, y, x + cw - 8, y0 + h1 * rh - 3), radius=8, fill=bg)
        d.text((x + 10, y + 8), label, font=font(18), fill=ink)
    im.save(path)


def desk(path):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1080, 1920), "#6F8A86")
    d = ImageDraw.Draw(im)
    d.rectangle((640, 560, 1020, 580), fill="#5B4636")                          # a shelf with books
    x = 660
    for k, (w, c) in enumerate(((38, "#D9C9A3"), (30, "#A6513D"), (44, "#3E5C76"), (26, "#E0B04F"), (40, "#2F3B36"))):
        d.rectangle((x, 410 + (k % 2) * 18, x + w, 560), fill=c)
        x += w + 6
    d.rectangle((110, 900, 250, 1060), fill="#B8643F")                         # a plant
    for dx, dy in ((-60, -120), (0, -170), (60, -120), (-30, -60), (40, -70)):
        d.ellipse((150 + dx, 880 + dy, 210 + dx, 980 + dy), fill="#3F6B43")
    d.rectangle((0, 1380, 1080, 1920), fill="#7A5A43")                         # the desk
    d.rectangle((0, 1380, 1080, 1394), fill="#8C6A51")
    d.rectangle((640, 1250, 980, 1382), fill="#2B2E31")                        # a laptop and a mug
    d.rectangle((600, 1382, 1020, 1400), fill="#3A3E42")
    d.rectangle((150, 1300, 240, 1384), fill="#ECE6DA")
    im.save(path, quality=88)


def sticky(path):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1080, 1920), "#C9A77C")
    d = ImageDraw.Draw(im)
    d.rectangle((96, 280, 500, 684), fill="#F6DB5E")
    d.rectangle((96, 280, 500, 318), fill="#EFCF45")
    for k, line in enumerate(("This week:", "ship the", "course page")):
        d.text((132, 352 + k * 82), line, font=font(56), fill="#2B2A26")
    im.save(path, quality=88)


def notes(path, W=938, H=648):
    from PIL import Image, ImageDraw
    tasks = ["Email the venue", "Draft the newsletter", "Book the dentist", "Fix the intro slide", "Call the printer",
             "Reply to the team thread", "Outline next week's video", "Pay the studio invoice", "Order a new mic stand",
             "Update the price page", "Pick up the prints", "Review the course notes", "Plan Friday's call",
             "Clean the desktop", "Back up the drive", "Write the thank-you notes", "Test the new lights",
             "Sort the receipts", "Buy coffee filters", "Renew the domain", "Read the contract", "Send the photos",
             "Draft three hooks", "Water the plants"]
    tall = Image.new("RGB", (W, 140 + 66 * len(tasks)), "#FFFDF7")
    d = ImageDraw.Draw(tall)
    d.text((48, 40), "Brain dump", font=font(44), fill="#1F1F1F")
    for k, t in enumerate(tasks):
        y = 140 + 66 * k
        d.ellipse((52, y + 10, 70, y + 28), outline="#B7B3AA", width=3)
        d.text((92, y), t, font=font(32), fill="#33322F")
        d.line((48, y + 52, W - 48, y + 52), fill="#EFEBE2", width=1)
    png = path + ".png"
    tall.save(png)
    travel = tall.height - H
    run("ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", png, "-t", "3",
        "-vf", f"crop={W}:{H}:0:'min({travel},max(0,(t-0.3))*{travel / 2.2:.1f})',format=yuv420p",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-an", path)
    os.remove(png)


# ---------------------------------------------------------------- the window render
def _attr(attrs, name):
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def window_doc(doc, a, b):
    """the built composition for a render of 0..b that keeps only a..b: cut at b as the hook render cuts it
    (hook.truncate), and every clip that is over by a is dropped too (a hidden stand-in keeps its id), so a file only
    an earlier beat plays need not exist"""
    out, af = HK.truncate(doc, b), round(a * FPS)

    def gone(m):
        attrs, close = m.group(2), m.group(3)
        s, d = _attr(attrs, "data-start"), _attr(attrs, "data-duration")
        if m.group(1).lower() != "video" or not close or s is None or d is None:
            return m.group(0)
        if round(float(s) * FPS) + math.ceil(float(d) * FPS - 1e-6) > af:
            return m.group(0)
        i = _attr(attrs, "id")
        return f'<div id="{i}" hidden></div>' if i else ""
    return HK.TAG.sub(gone, out)


def stage(p, a, b, name):
    """public/ mirrored into work/<name>/ (hard links) with the window's composition: what HyperFrames runs on"""
    pub = os.path.join(p, "public")
    with open(os.path.join(pub, "index.html"), encoding="utf-8") as fh:
        doc = window_doc(fh.read(), a, b)
    work = os.path.join(p, "work", name)
    shutil.rmtree(work, ignore_errors=True)
    HK.link_tree(pub, work, skip=("index.html", "snapshots"))
    with open(os.path.join(work, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(doc)
    return work


def render_window(p, a, b, out):
    """0..b rendered at delivery quality, then a..b trimmed out: 540x960 H.264 crf 28, no audio"""
    work = stage(p, a, b, "example")
    full = os.path.join(p, "renders", "example-window.mp4")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    common.hf(["render", "-q", "delivery", "--quiet", "-o", full], work)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run("ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-i", full, "-t", f"{b - a:.3f}", "-an",
        "-vf", f"scale={SIZE[0]}:{SIZE[1]}:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
        "-crf", str(CRF), "-profile:v", "high", "-movflags", "+faststart", out)
    n, size = frames_of(out), os.path.getsize(out)
    print(f"{out}  {size / 1e6:.2f} MB  {n} frames  ({a:g}-{b:g} s of {os.path.basename(p)})", flush=True)
    if size >= MAX_BYTES or n != round((b - a) * FPS):
        sys.exit(f"{out}: {size} bytes, {n} frames: wanted under {MAX_BYTES} bytes and {round((b - a) * FPS)} frames")


def snapshot(p, t, out):
    """one frame of the built composition at t -> a 540x960 jpg"""
    work = stage(p, 0.0, t + 0.2, "style-frame")
    common.hf(["snapshot", "--at", f"{t:.3f}", "--no-end", "--describe", "false"], work)
    shots = sorted(f for f in os.listdir(os.path.join(work, "snapshots")) if f.endswith(".png"))
    if not shots:
        sys.exit(f"snapshot wrote no frame in {work}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run("ffmpeg", "-v", "error", "-y", "-i", os.path.join(work, "snapshots", shots[0]),
        "-vf", f"scale={SIZE[0]}:{SIZE[1]}:flags=lanczos", "-q:v", "3", out)
    print(f"{out}  {os.path.getsize(out) // 1024} KB", flush=True)


# ---------------------------------------------------------------- the two jobs
def modes(which, out):
    for mode in which:
        a, b = WINDOWS[mode]
        G = runpy.run_path(os.path.join(KIT, "examples", mode, "edit.py"))
        reach = [(x, b if y == "end" else y) for x, y in G.get("CUT_WINDOWS", [])]
        cutout = b + 0.5 if any(x < b and y > a for x, y in reach) else 0.0
        cards = [c[0] for c in G.get("CARDS", []) if c[2] < b and c[3] > a]
        p = stand_in(mode, cutout_until=cutout, cards=cards)
        render_window(p, a, b, os.path.join(out, f"{mode}.mp4"))


def pack_name(d):
    name = os.path.basename(os.path.normpath(d))
    return PK.DEFAULT_NAMES[0] if name == "style" else name


def styles(packs, out):
    p = stand_in("hifi")
    for d in packs:
        name = pack_name(d)
        built = install_pack(d, os.path.join(HOME, "packs-built", name))
        shutil.rmtree(os.path.join(p, "style"), ignore_errors=True)
        PK.copy_into(built, os.path.join(p, "style"))
        quiet(PY, os.path.join(PIPE, "build.py"), p)
        snapshot(p, STYLE_AT, os.path.join(out, f"style-{name}.jpg"))


def main():
    ap = argparse.ArgumentParser(description="the start page's examples, from the stand-in")
    ap.add_argument("--modes", help="comma list of hifi,lofi,showcase")
    ap.add_argument("--pack", help="the pack the mode clips wear")
    ap.add_argument("--packs", nargs="+", help="pack folders to draw a style frame for")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    kit_packs = os.path.join(KIT, "packs")
    if args.modes is None and args.packs is None:
        which = list(WINDOWS)
        packs = sorted(os.path.join(kit_packs, n) for n in (os.listdir(kit_packs) if os.path.isdir(kit_packs) else [])
                       if os.path.exists(os.path.join(kit_packs, n, "style.json")))
    else:
        which = [m for m in (args.modes or "").split(",") if m]
        packs = args.packs or []
    bad = [m for m in which if m not in WINDOWS]
    if bad:
        sys.exit(f"no mode {bad}: hifi, lofi or showcase")
    pack = args.pack or next(d for d in (os.path.join(kit_packs, "harbor"), os.path.join(KIT, "examples", "packs", "default"))
                             if os.path.exists(os.path.join(d, "style.json")))
    out = os.path.abspath(args.out)
    setup_home(pack)
    modes(which, out)
    styles(packs, out)


if __name__ == "__main__":
    main()
