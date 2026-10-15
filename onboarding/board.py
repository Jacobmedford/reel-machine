#!/usr/bin/env python3
"""Board: the creator's style on one page, the approval step at the end of onboarding.

Shows their type, their colours and what each one means, a hook and captions on a frame of their own footage
(hi-fi and lo-fi), and a few library cards rebuilt in their style. Every picture is a frame from the same renderer
the videos use, so what they approve is what they get.
Run: PY onboarding/board.py [--clip <one of their videos>] [--cards id,id,id] [--pack <style dir>]
Writes <pack>/board/: index.html, img/*.jpg, fonts/, files.json (every file to publish with the page).
"""
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import types

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "pipeline"))
from common import HF, VENDOR, hf  # noqa: E402
import inline_vendor as IV  # noqa: E402
import style as ST  # noqa: E402
import build as B  # noqa: E402
from storyboard import theme_css  # noqa: E402

DEFAULT_CARDS = ["scissors", "counter-loupe", "task-grid"]
SWATCHES = [("accent", "Accent", "emphasis, the thing to look at"), ("accent_on_light", "Accent on light", "the same, on a light ground"),
            ("negative", "Negative", "losses, down, no"), ("positive", "Positive", "gains, up, yes"),
            ("light", "Light", "light ground, text on dark"), ("dark", "Dark", "dark ground"),
            ("ink", "Ink", "text on light"), ("caption_box", "Caption box", "behind captions on footage")]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else default


def frame_from(clip, out):
    """one frame from a third of the way in, filled to 9:16"""
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip],
                         capture_output=True, text=True).stdout.strip()
    t = float(dur or 0) * 0.35
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", clip, "-frames:v", "1", "-vf",
                    "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-q:v", "2", out], check=True)


def kit_files(d, pack, css):
    """what a composition folder needs: the pack's brand.css and fonts, kit css, GSAP, the HyperFrames config"""
    shutil.copy(os.path.join(pack, "brand.css"), d)
    shutil.copytree(os.path.join(pack, "fonts"), os.path.join(d, "fonts"), dirs_exist_ok=True)
    for c in css:
        shutil.copy(os.path.join(KIT, "kit", c), d)
    shutil.copytree(VENDOR, os.path.join(d, "vendor"), dirs_exist_ok=True)
    shutil.copy(os.path.join(KIT, "kit", "hyperframes.json"), d)


SETTLED = 1.9      # board frames are taken here, after any entrance a pack's extra.css animates (Terminal types its hook)


def phone(d, pack, body, css, extra_css):
    """a two-second composition: one still picture of the look, settled"""
    os.makedirs(d, exist_ok=True)
    kit_files(d, pack, css)
    links = "".join(f'<link rel="stylesheet" href="{c}" />' for c in css)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><title>board frame</title><link rel="stylesheet" href="brand.css" />{links}
<style>{extra_css}</style></head>
<body><div id="root" data-composition-id="main" data-start="0" data-duration="2.000" data-fps="30" data-width="1080" data-height="1920">
{body}
</div>
<script src="vendor/gsap.min.js"></script>
<script>window.__timelines = window.__timelines || {{}}; window.__timelines["main"] = gsap.timeline({{ paused: true }}).to({{}}, {{ duration: 2 }});</script>
</body></html>''')


def snap(d, t, out):
    """the frame at t of the composition in d -> a 540x960 jpg. GSAP goes inside the page first (inline_vendor.py):
    a dropped fetch would show a card standing still on the board"""
    page = os.path.join(d, "index.html")
    with open(page, encoding="utf-8") as fh:
        doc = fh.read()
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(IV.inline(doc, d))
    shutil.rmtree(os.path.join(d, "snapshots"), ignore_errors=True)
    hf(["snapshot", "--at", f"{t:.3f}", "--no-end", "--describe", "false"], d)
    files = glob.glob(os.path.join(d, "snapshots", "frame-*.png"))
    if not files:
        sys.exit(f"snapshot wrote no frame in {d}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", files[0], "-vf", "scale=540:960:flags=lanczos", "-q:v", "3", out],
                   check=True)


def split_word(S, pack, word, size, top, frame):
    """the emphatic word with each letter light or ink against the picture under it, the way the showcase effects
    split type over footage (no outline). Letter widths from the pack's own display font file. With no frame (no
    --clip) the ground is the pack's dark colour, so the whole word is light"""
    from PIL import Image, ImageFont
    F = S["fonts"]["display"]
    name = f"{F['family'].replace(' ', '')}-{'italic' if F.get('italic') else 'normal'}-{F.get('weight', 400)}.ttf"
    files = sorted(glob.glob(os.path.join(pack, "fonts", F["family"].replace(" ", "") + "-*.ttf")))
    path = os.path.join(pack, "fonts", name) if os.path.exists(os.path.join(pack, "fonts", name)) else (files[0] if files else None)
    if not frame or not path:
        return f'<span style="color:var(--c-light)">{html.escape(word)}</span>'
    font = ImageFont.truetype(path, size)
    widths = [font.getlength(ch) - 0.03 * size for ch in word]
    x = 540 - sum(widths) / 2
    grey = Image.open(frame).convert("L")
    out = []
    for ch, w in zip(word, widths):
        box = (int(max(0, x)), int(top + size * 0.15), int(min(1080, x + w)), int(top + size * 0.85))
        light = sum(grey.crop(box).getdata()) / max(1, (box[2] - box[0]) * (box[3] - box[1])) / 255 > 0.55
        out.append(f'<span style="color:var({"--c-ink" if light else "--c-light"})">{html.escape(ch)}</span>')
        x += w
    return "".join(out)


def card_title(cid):
    lib = os.path.join(KIT, "cards", "LIBRARY.md")
    if os.path.exists(lib):
        for line in open(lib, encoding="utf-8"):
            if line.startswith(f"| `{cid}`"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                return cells[2] if len(cells) > 2 else ""
    return ""


def summary(pack):
    """the first plain paragraph of the creator's STYLE.md, if there is one"""
    p = os.path.join(pack, "STYLE.md")
    if not os.path.exists(p):
        return ""
    for block in open(p, encoding="utf-8").read().split("\n\n"):
        b = block.strip()
        if b and not b.startswith(("#", "-", "|", "*", ">")):
            return " ".join(b.split())
    return ""


def main():
    pack = os.path.abspath(os.path.expanduser(arg("--pack", ST.STYLE_DIR)))
    if not os.path.exists(os.path.join(pack, "style.json")):
        sys.exit(f"no style.json in {pack}: write the pack first (onboarding/ONBOARDING.md)")
    S = ST.load(os.path.join(pack, "style.json"))
    if not os.path.exists(os.path.join(pack, "brand.css")) or not os.path.isdir(os.path.join(pack, "fonts")):
        ST.write(S, pack)
    board = os.path.join(pack, "board")
    work = os.path.join(board, "_work")
    shutil.rmtree(board, ignore_errors=True)
    os.makedirs(os.path.join(board, "img"), exist_ok=True)
    os.makedirs(work, exist_ok=True)
    C = S["colors"]
    E = types.SimpleNamespace(S=S)
    extra = B.pack_css(E)

    clip = arg("--clip")
    if clip:
        clip = os.path.abspath(os.path.expanduser(clip))
        frame_from(clip, os.path.join(work, "frame.jpg"))
    for d in ("hifi", "lofi", "showcase"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
        if clip:
            shutil.copy(os.path.join(work, "frame.jpg"), os.path.join(work, d))
    ground = (f'<img class="full" src="frame.jpg" alt="" style="filter:{html.escape(S["grade"])}" />' if clip else
              '<div class="full" style="background:var(--c-dark)"></div>')

    def foot(inner):
        """the picture layers wrapped as build.py wraps them (#foot > #cam), so a pack that treats the footage
        (a film grade, grain, a vignette in its extra.css) shows it here exactly as in a video"""
        return f'<div id="foot" class="layer"><div id="cam" class="layer">{inner}</div></div>'

    name = S["creator"].get("name") or "Your source"

    M = S.get("modes", {})
    hook_kind = M.get("hifi", {}).get("hook", "two-line")
    # the hook in build.py's own markup (.eb / .h1 / .h2 with their .hw spans), so a pack styles it here as in a video
    lines = {"two-line": dict(eyebrow=f"{html.escape(name)} · 2026", h1="This is your hook", h2="in your style"),
             "one-line": dict(eyebrow=f"{html.escape(name)} · 2026", h2="Your hook, one line")}.get(hook_kind)
    hook = B.hook(types.SimpleNamespace(HOOK=dict(lines, off=SETTLED + 0.1)))[0] if lines else ""
    print("rendering the hi-fi frame ...", flush=True)
    phone(os.path.join(work, "hifi"), pack, f'''{foot(ground)}
{hook}
<div class="capw"><div class="cap onfoot" style="opacity:1">Captions look <span class="em">like this</span></div></div>''',
          ["reel.css"], extra)
    snap(os.path.join(work, "hifi"), SETTLED, os.path.join(board, "img", "hifi.jpg"))

    print("rendering the lo-fi frame ...", flush=True)
    lit = html.escape(C["caption_ink"])
    rhythm = M.get("lofi", {}).get("captions", "word-by-word")
    line = {"word-by-word": f'<span style="color:{lit}">each word</span> lights up',
            "phrase": f'<span style="color:{lit}">the line lands at once</span>',
            "single": f'<span style="color:{lit}">one</span>'}.get(rhythm, "")
    box = ('<div class="nb" style="opacity:1"><span class="ln">Your hook, in a text box</span></div>'
           if M.get("lofi", {}).get("text_boxes", True) else "")
    phone(os.path.join(work, "lofi"), pack, f'''{foot(ground)}
{box}
<div class="kw"><div class="kc" style="opacity:1">{line}</div></div>''',
          ["reel.css", "reel-lofi.css"], extra)
    snap(os.path.join(work, "lofi"), SETTLED, os.path.join(board, "img", "lofi.jpg"))

    print("rendering the showcase frame ...", flush=True)
    land = M.get("showcase", {}).get("emphasis_word", "stamp")
    sd = os.path.join(work, "showcase")
    os.makedirs(sd, exist_ok=True)
    cut = ""
    if clip:
        shutil.copy(os.path.join(work, "frame.jpg"), sd)
        if subprocess.run(HF + ["remove-background", "frame.jpg", "-o", "subject.png"], cwd=sd,
                          capture_output=True).returncode == 0 and os.path.exists(os.path.join(sd, "subject.png")):
            cut = f'<img class="full" src="subject.png" alt="" style="filter:{html.escape(S["grade"])}" />'   # the speaker in front: the head breaks the word
    top = 340 if cut else 250
    word = split_word(S, pack, "NEVER", 250, top, os.path.join(sd, "frame.jpg") if clip else None)
    pic = f'{ground}<div class="bh" style="top:{top}px;font-size:250px;">{word}</div>{cut}'   # the head breaks the word
    phone(sd, pack, f'''{foot(pic)}
<div class="kw"><div class="kc" style="opacity:1"><span style="color:{lit}">I never open an editing app</span></div></div>''',
          ["reel.css", "reel-lofi.css"], extra)
    snap(os.path.join(work, "showcase"), SETTLED, os.path.join(board, "img", "showcase.jpg"))

    cards = [c for c in (arg("--cards") or ",".join(DEFAULT_CARDS)).split(",") if c]
    shown = []
    for cid in cards:
        src = os.path.join(KIT, "cards", cid)
        if not os.path.exists(os.path.join(src, "index.html")):
            print(f"no card {cid}, skipped", flush=True)
            continue
        print(f"rendering card {cid} ...", flush=True)
        d = os.path.join(work, f"card-{cid}")
        shutil.copytree(src, d, ignore=shutil.ignore_patterns("*.mp4", "snapshots", "preview.jpg", "still.jpg"))
        kit_files(d, pack, ["card.css"])
        m = re.search(r'id="root"[^>]*data-duration="([\d.]+)"', open(os.path.join(d, "index.html"), encoding="utf-8").read())
        frames = round(float(m.group(1)) * 30) if m else 60
        snap(d, (frames - 1) / 30, os.path.join(board, "img", f"card-{cid}.jpg"))
        shown.append(cid)

    theme = theme_css(S, board)
    F = S["fonts"]
    chips = "".join(f'<div class="chip"><i style="background:{html.escape(C[k])}"></i><b>{label}</b>'
                    f'<span>{html.escape(C[k])}<br />{meaning}</span></div>' for k, label, meaning in SWATCHES if k in C)
    who = " · ".join(x for x in (S["creator"].get("name"), S["creator"].get("handle")) if x)
    footage = ("on a frame of your own footage" if clip else
               "on a plain ground (run the board with --clip to see it on your footage)")
    card_figs = "".join(f'<figure><img src="img/card-{c}.jpg" alt="The {c} card in your style" />'
                        f'<figcaption><b>{c}</b> {html.escape(card_title(c))}</figcaption></figure>' for c in shown)
    cards_section = (f'  <section>\n    <h2>Cards</h2>\n    <div class="grid">{card_figs}</div>\n  </section>\n'
                     if shown else "")
    lede = html.escape(summary(pack)) or "Your fonts, your colours and what each one means, on your footage."
    page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Style Board</title>
<style>
{theme}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--paper); color: var(--ink); font-family: var(--font-text); -webkit-font-smoothing: antialiased; }}
main {{ max-width: 1120px; margin: 0 auto; padding: 48px 16px 96px; }}
header {{ padding-bottom: 28px; border-bottom: 1px solid var(--hair); }}
.eyebrow, h2 {{ font: 500 13px/1 var(--font-mono); letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }}
h1 {{ margin-top: 14px; font-family: var(--font-display); font-style: var(--display-style); font-weight: var(--display-weight);
      font-size: clamp(40px, 7vw, 72px); line-height: 1; letter-spacing: -.02em; }}
.lede {{ margin-top: 16px; max-width: 62ch; font-size: 17px; line-height: 1.5; color: var(--muted); }}
section {{ padding: 36px 0; border-bottom: 1px solid var(--hair); }}
h2 {{ margin-bottom: 22px; }}
.spec {{ display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 16px; align-items: baseline; padding: 12px 0; }}
.spec + .spec {{ border-top: 1px solid var(--hair); }}
.spec .k {{ font: 500 12px/1.5 var(--font-mono); color: var(--muted); }}
.spec .v {{ overflow-wrap: anywhere; }}
.d {{ font-family: var(--font-display); font-style: var(--display-style); font-weight: var(--display-weight); font-size: clamp(36px, 6vw, 60px); line-height: 1.05; }}
.t {{ font-size: 22px; line-height: 1.35; font-weight: 600; }}
.m {{ font-family: var(--font-mono); font-size: 20px; }}
.sw {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }}
.chip {{ border: 1px solid var(--hair); border-radius: 6px; overflow: hidden; background: var(--sheet); }}
.chip i {{ display: block; height: 72px; border-bottom: 1px solid var(--hair); }}
.chip b {{ display: block; padding: 10px 12px 3px; font-weight: 600; font-size: 14px; }}
.chip span {{ display: block; padding: 0 12px 12px; font: 400 12px/1.45 var(--font-mono); color: var(--muted); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 18px; }}
figure img {{ display: block; width: 100%; height: auto; aspect-ratio: 9 / 16; border-radius: 6px; border: 1px solid var(--hair); }}
figcaption {{ margin-top: 9px; font-size: 14px; line-height: 1.45; color: var(--muted); }}
figcaption b {{ color: var(--ink); font-weight: 600; }}
.note {{ margin-top: -8px; margin-bottom: 20px; font-size: 15px; color: var(--muted); }}
footer {{ padding-top: 32px; font-size: 16px; line-height: 1.55; max-width: 62ch; }}
@media (max-width: 560px) {{ .spec {{ grid-template-columns: 1fr; gap: 6px; }} }}
</style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">{html.escape(who) if who else "reel-machine"} · style board</p>
    <h1>Your style</h1>
    <p class="lede">{lede}</p>
  </header>
  <section>
    <h2>Type</h2>
    <div class="spec"><div class="k">Display · {html.escape(F["display"]["family"])}</div><div class="v d">The big idea</div></div>
    <div class="spec"><div class="k">Text · {html.escape(F["text"]["family"])}</div><div class="v t">Captions and labels read like this</div></div>
    <div class="spec"><div class="k">Mono · {html.escape(F["mono"]["family"])}</div><div class="v m">2026 · 15% · $1.4M · −10%</div></div>
  </section>
  <section>
    <h2>Colour</h2>
    <div class="sw">{chips}</div>
  </section>
  <section>
    <h2>Your three modes</h2>
    <p class="note">How each mode looks for you, {footage}.</p>
    <div class="grid">
      <figure><img src="img/hifi.jpg" alt="Hi-fi hook and caption" /><figcaption><b>Hi-fi</b> produced: {html.escape(hook_kind)} hook, captions in phrases, cards, camera {html.escape(str(M.get("hifi", {}).get("camera", "settle")))}</figcaption></figure>
      <figure><img src="img/lofi.jpg" alt="Lo-fi text box and caption" /><figcaption><b>Lo-fi</b> selfie: captions {html.escape(rhythm)}{", text boxes" if M.get("lofi", {}).get("text_boxes", True) else ""}</figcaption></figure>
      <figure><img src="img/showcase.jpg" alt="Showcase emphatic word" /><figcaption><b>Showcase</b> show-off: a big word lands with a {html.escape(land)}; transitions {html.escape(", ".join(M.get("showcase", {}).get("transitions", [])))}</figcaption></figure>
    </div>
  </section>
{cards_section}  <footer>Anything here can change: fonts, colours, captions, pace. Say what feels off and the board comes back with it fixed.</footer>
</main>
</body>
</html>
'''
    with open(os.path.join(board, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    shutil.rmtree(work, ignore_errors=True)
    files = sorted(os.path.relpath(p, board) for p in glob.glob(os.path.join(board, "**", "*"), recursive=True)
                   if os.path.isfile(p) and not p.endswith("index.html") and not p.endswith("files.json"))
    json.dump(files, open(os.path.join(board, "files.json"), "w"), indent=1)
    print(f"BOARD {os.path.join(board, 'index.html')}  ({len(shown)} cards, {len(files)} files to publish with it)")


if __name__ == "__main__":
    main()
