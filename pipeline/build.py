#!/usr/bin/env python3
"""Build: <project>/edit.py -> <project>/public/index.html, the HyperFrames composition of the reel.

Layers, bottom to top:
  #foot   graded footage (clean.mp4), the behind-head layer, and the speaker cutout (subject.webm) only in the
          windows where something sits behind the speaker (edit.CUT_WINDOWS)
  cards   full-screen data cards (public/cards/*.mp4, built from cards/) hard-cut over the footage
  #hook   the text hook over the first shot
  #caps   live captions: a box on footage, plain type on cards
  #end    end card, only when edit.END_CARD is set (opt-in)
Lo-fi mode (edit.STYLE = "lofi", modes/LOFI.md) adds, on top of the same layers: backdrops and lists behind the head
(BEHIND kinds "backdrop", "list"), overlays on top of the speaker (edit.OVERLAYS), Instagram-style text boxes
(edit.BOXES: hook, chapter labels, CTA), word-by-word captions built from words.json, hard zooms.
The look comes from the creator's style pack (pipeline/style.py): its brand.css (tokens + fonts) is inlined first,
then kit/reel.css (+ kit/reel-lofi.css) which only use tokens. Audio is one pre-mixed file (public/master.wav).
GSAP (public/vendor/gsap.min.js) travels inside the page, a data: URL (pipeline/inline_vendor.py): no worker fetches it.
Run: PY pipeline/build.py <project> [--safe] [--stills]
  --safe    red safe-zone overlay for snapshots
  --stills  cards that have no mp4 yet show their key-frame still (cards/<id>/still.jpg) for the storyboard
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KIT, clip_start, load_edit, project_arg, q, timeline, wide  # noqa: E402
import inline_vendor as IV  # noqa: E402
import style as ST  # noqa: E402

NL = "\n"


# ------------------------------------------------------------------ timing helpers
def setup(E, TL):
    E.TOTAL = TL["total"]
    E.AUDIO_END = TL["total_audio"]
    E.END_IN = q(E.AUDIO_END) if E.END_CARD else E.TOTAL
    E.WINDOWS = [(c[2], c[3], c[4]) for c in E.CARDS] + ([(E.END_IN, E.TOTAL, "light")] if E.END_CARD else [])
    E.S = project_style(E)


def project_style(E):
    """the pack this project was made with (<project>/style/, copied by new.py), else the creator's current pack"""
    local = os.path.join(E.PROJECT, "style", "style.json")
    return ST.load(local if os.path.exists(local) else None)


def color(E, name):
    """colours by meaning, from the pack: accent, negative, positive (+ _on_light), light, dark, ink, s1-s3 (series).
    A raw CSS colour passes through."""
    C = E.S["colors"]
    named = {k: C[k] for k in ("accent", "accent_on_light", "negative", "negative_on_light", "positive",
                               "positive_on_light", "light", "dark", "ink") if k in C}
    named.update({f"s{i + 1}": c for i, c in enumerate(C.get("series", []))})
    return named.get(name, name)


def pack_css(E):
    """caption size, case, position and box from the pack"""
    hf, lf = E.S["captions"]["hifi"], E.S["captions"]["lofi"]
    css = [f".capw {{ top:{hf.get('y', 1236)}px; }} .cap {{ font-size:{hf.get('size', 56)}px; "
           f"{'text-transform:uppercase;' if hf.get('uppercase') else ''} }}",
           f".kw {{ top:{lf.get('y', 1318)}px; }} .kc {{ font-size:{lf.get('size', 66)}px; "
           f"{'text-transform:uppercase;' if lf.get('uppercase') else ''} }}"]
    shadow = "text-shadow:0 2px 14px rgba(0,0,0,.6), 0 0 2px rgba(0,0,0,.5);"
    if not hf.get("box", True):
        css.append(f".cap.onfoot {{ background:none; {shadow} }}")
    if not lf.get("box", True):
        css.append(f".kc {{ background:none; {shadow} }}")
    return "\n".join(css)


def T(E, t):
    """'end' -> when the last thing on screen ends (the end card, or the last frame)"""
    return E.END_IN if t == "end" else t


def ground_at(E, t):
    for a, b, g in E.WINDOWS:
        if a - 1e-6 <= t < b - 1e-6:
            return g
    return "foot"


def visible(E, t):
    """is the talking head on screen at t (no card over it)"""
    return ground_at(E, t + 0.001) == "foot"


# ------------------------------------------------------------------ captions
def fmt(text):
    out = []
    for k, part in enumerate(text.split("*")):
        if part:
            out.append(f'<span class="em">{part}</span>' if k % 2 else part)
    return "".join(out)


def captions(E):
    html, js, n = [], [], 0
    for i, c in enumerate(E.CAPS):
        t0, text, kind = c[0], c[1], c[2]
        t1 = T(E, c[3]) if len(c) > 3 else E.CAPS[i + 1][0]
        cuts = sorted({t0, t1} | {x for a, b, _ in E.WINDOWS for x in (a, b) if t0 < x < t1})   # style follows the ground
        for a, b in zip(cuts, cuts[1:]):
            g = ground_at(E, a + 0.001)
            cls = "cap " + {"foot": "onfoot", "light": "onlight", "dark": "ondark"}[g]
            if kind:
                cls += " " + kind
            cid = f"cap{n}"
            n += 1
            inner = fmt(text)
            if kind == "strike":
                inner = f'<span class="sx">{inner}<i class="strk" id="{cid}s"></i></span>'
            html.append(f'<div class="capw"><div id="{cid}" class="{cls}">{inner}</div></div>')
            js.append(f"pop('#{cid}', {q(a):.3f});" if a == t0 else f"on('#{cid}', {q(a):.3f});")
            js.append(f"off('#{cid}', {q(b):.3f});")
            if kind == "strike":
                js.append(f"tl.fromTo('#{cid}s', {{scaleX: 0}}, {{scaleX: 1, duration: 0.22, ease: 'power2.inOut', immediateRender: false}}, q({a + 0.27:.3f}));")
                js.append(f"gsap.set('#{cid}s', {{scaleX: 0}});")
    return html, js


def karaoke_lines(E):
    """lofi: words.json grouped into one-line phrases; break on punctuation, pauses, max words or characters"""
    M = getattr(E, "MODE", {})
    pack = {k: M[k] for k in ("max_words", "max_chars") if k in M}
    if M.get("captions") == "single":                                  # one word at a time
        pack.update(max_words=1)
    K = {**dict(max_words=4, max_chars=24, gap=0.35, huge=[], huge_words=2, huge_chars=12), **pack, **getattr(E, "KARAOKE", {})}
    big = lambda w: any(a <= w["start"] < b for a, b in K["huge"])     # noqa: E731  ("captions come in huge")
    words = []
    for w in json.load(open(os.path.join(E.PROJECT, "words.json"))):
        if words and w["text"].startswith("-"):                  # "re" + "-explain" -> "re-explain"
            words[-1] = dict(words[-1], text=words[-1]["text"] + w["text"], end=w["end"])
        else:
            words.append(dict(w))
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        text = " ".join(x["text"] for x in cur)
        mw, mc = (K["huge_words"], K["huge_chars"]) if big(w) else (K["max_words"], K["max_chars"])
        if (nxt is None or w["text"][-1] in ".,?!:;" or len(cur) >= mw or big(nxt) != big(w)
                or len(text) + 1 + len(nxt["text"]) > mc or nxt["start"] - w["end"] > K["gap"]):
            out.append(cur)
            cur = []
    return out


def karaoke(E):
    """lofi captions: each line in on its first word, every word lights as it is spoken, held to the next line"""
    html, js = [], []
    L = karaoke_lines(E)
    huge = getattr(E, "KARAOKE", {}).get("huge", [])
    hide = getattr(E, "KARAOKE", {}).get("hide", [])           # windows an FX carries the words in (custom captions)
    for i, ln in enumerate(L):
        if any(a <= ln[0]["start"] < b for a, b in hide):
            continue
        t0 = ln[0]["start"]
        nxt = L[i + 1][0]["start"] if i + 1 < len(L) else E.TOTAL
        t1 = nxt if nxt - ln[-1]["end"] < 0.6 else min(nxt, ln[-1]["end"] + 0.3)
        spans = " ".join(f'<span class="k" id="kc{i}_{j}">{w["text"]}</span>' for j, w in enumerate(ln))
        cls = "kc huge" if any(a <= t0 < b for a, b in huge) else "kc"
        html.append(f'<div class="kw"><div id="kc{i}" class="{cls}">{spans}</div></div>')
        js.append(f"on('#kc{i}', {t0:.3f}); off('#kc{i}', {min(t1, E.TOTAL):.3f});")
        lit = E.S['colors']['caption_ink']
        if getattr(E, "MODE", {}).get("captions") == "phrase":          # the whole line lands lit at once
            js.append(f"gsap.set('#kc{i} .k', {{ color: '{lit}' }});")
        else:                                                          # every word lights as it is spoken
            js.append(" ".join(f"tl.set('#kc{i}_{j}', {{ color: '{lit}' }}, q({w['start']:.3f}));" for j, w in enumerate(ln)))
    return html, js


def boxes(E):
    """native text boxes (the Instagram classic text with a white background): hook, chapter labels, CTA"""
    html, js = [], []
    for i, B in enumerate(getattr(E, "BOXES", [])):
        lines = "<br>".join(f'<span class="ln">{t}</span>' for t in B["text"].split("\n"))
        html.append(f'<div id="nb{i}" class="nb" data-layout-allow-overlap style="top:{B.get("top", 236)}px;">{lines}</div>')
        js.append(f"tl.set('#nb{i}', {{ opacity: 1 }}, q({B['at']:.3f}));")
        if B["at"] > 0.05:
            js.append(f"tl.fromTo('#nb{i}', {{ scale: 0.92 }}, {{ scale: 1, duration: 0.18, ease: 'back.out(1.6)', immediateRender: false }}, q({B['at']:.3f}));")
        js.append(f"off('#nb{i}', {T(E, B['end']):.3f});")
    return html, js


def media_tag(tag_id, cls, src, a, b, style, track, media_start=0.0):
    """an <img> or a framework-timed <video> for overlays and backdrops"""
    if src.endswith((".mp4", ".mov", ".webm")):
        return (f'<video id="{tag_id}" class="{cls}" src="{src}" muted playsinline data-start="{clip_start(a):.4f}" '
                f'data-media-start="{media_start:.4f}" data-duration="{q(b) - q(a):.4f}" data-track-index="{track}" '
                f'style="{style}opacity:1;"></video>'), True
    return f'<img id="{tag_id}" class="{cls}" src="{src}" style="{style}">', False


def overlays(E):
    """lo-fi: the real thing on top of the speaker (a screenshot, a screen recording, a photo), above the caption band"""
    html, js = [], []
    for k, O in enumerate(getattr(E, "OVERLAYS", [])):
        b = T(E, O["end"])
        h = f'height:{O["h"]}px;' if O.get("h") else "height:auto;"
        style = f'left:{O.get("x", 90)}px;top:{O.get("y", 300)}px;width:{O.get("w", 900)}px;{h}'
        tag, vid = media_tag(f"ov{k}", "ov " + O.get("cls", ""), O["src"], O["at"], b, style, 40 + k, O.get("media_start", 0.0))
        html.append(tag)
        if not vid:
            js.append(f"tl.set('#ov{k}', {{ opacity: 1 }}, q({O['at']:.3f})); off('#ov{k}', {b:.3f});")
        js.append(f"tl.fromTo('#ov{k}', {{ scale: 0.94 }}, {{ scale: 1, duration: 0.16, ease: 'power3.out', immediateRender: false }}, q({O['at']:.3f}));")
    return html, js


# ------------------------------------------------------------------ motion graphics (edit.FX)
FX_LAYERS = ("behind", "cam", "top", "over")


def fx(E):
    """edit.FX: hand-built motion graphics, one folder each: <project>/fx/<id>/fx.html (markup + a <style> scoped to
    #<id>), fx.js (GSAP on the reel's timeline: tl, q, on, off, gsap, A = start, B = end), assets beside them
    (published as fx/<id>/...). The wrapper div #<id> is shown from A to B; the build places it on a layer:
      behind  under the cutout, inside the camera (needs a CUT_WINDOWS entry), for type and graphics behind the head
      cam     on the camera above the cutout (zooms carry it): extra footage layers, wipes, grids, recursion
      top     above the speaker and the overlays, under the captions
      over    above everything (captions too): letterbox bars, full-frame transitions
    In fx.html and fx.js, {{ID}} becomes the entry's id (so a library effect is copied without renaming) and
    {{T0}}..{{T9}} become unique data-track-index values for <video> elements."""
    out, js = {k: [] for k in FX_LAYERS}, []
    only = [x for x in os.environ.get("FX_ONLY", "").split(",") if x]       # fxsandbox.py: build just these
    for k, F in enumerate(getattr(E, "FX", [])):
        fid, layer = F["id"], F.get("layer", "top")
        if only and fid not in only:
            continue
        if layer not in FX_LAYERS:
            raise SystemExit(f"FX {fid}: layer must be one of {FX_LAYERS}")
        d = os.path.join(E.PROJECT, "fx", fid)
        if not os.path.exists(os.path.join(d, "fx.html")):
            out[layer].append(f'<div id="{fid}" class="layer fx ph dark">{fid} pending</div>')
            js.append(f"gsap.set('#{fid}', {{opacity: 0}}); on('#{fid}', {F['at']:.3f}); off('#{fid}', {T(E, F['end']):.3f});")
            continue
        markup = fx_times(open(os.path.join(d, "fx.html"), encoding="utf-8").read().replace("{{ID}}", fid),
                          F["at"], T(E, F["end"]))
        for i in range(10):
            markup = markup.replace("{{T%d}}" % i, str(300 + 10 * k + i))
        out[layer].append(f'<div id="{fid}" class="layer fx" data-layout-allow-occlusion data-layout-allow-overlap>{markup}</div>')
        js.append(f"gsap.set('#{fid}', {{opacity: 0}}); on('#{fid}', {F['at']:.3f}); off('#{fid}', {T(E, F['end']):.3f});")
        body = open(os.path.join(d, "fx.js"), encoding="utf-8").read().replace("{{ID}}", fid) if os.path.exists(os.path.join(d, "fx.js")) else ""
        js.append(f"(function (A, B) {{\n{body}\n}})({F['at']:.3f}, {T(E, F['end']):.3f});")
    return out, js


def fx_times(markup, A, B):
    """media timing in an effect's static HTML, relative to where the effect sits, so a copied effect times itself:
    {{START}} / {{START+0.77}}  data-start for a clip that starts at A (+0.77), frame-snapped (clip_start)
    {{SYNC}} / {{SYNC+0.77}}    data-media-start for a copy of clean.mp4 starting there: the same frame as the
                                main picture (lips in sync)
    {{DUR}} / {{DUR-0.133}}     the effect's length (less 0.133 s, for a clip that starts late), frames / 30"""
    import re

    def at(m):
        t = A + (float(m.group(3)) * (1 if m.group(2) == "+" else -1) if m.group(3) else 0.0)
        return f"{clip_start(t):.4f}" if m.group(1) == "START" else f"{q(t) + 0.001:.4f}"
    markup = re.sub(r"\{\{(START|SYNC)(?:([+-])([0-9.]+))?\}\}", at, markup)
    return re.sub(r"\{\{DUR(?:-([0-9.]+))?\}\}",
                  lambda m: f"{round((B - A - float(m.group(1) or 0)) * 30) / 30:.4f}", markup)


def sync_fx(E, project, pub):
    """fx assets (everything in fx/<id>/ but fx.html / fx.js / notes) -> public/fx/<id>/"""
    import shutil
    for F in getattr(E, "FX", []):
        src = os.path.join(project, "fx", F["id"])
        if not os.path.isdir(src):
            continue
        dst = os.path.join(pub, "fx", F["id"])
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(src):
            a = os.path.join(src, f)
            if os.path.isfile(a) and f not in ("fx.html", "fx.js", "preview.jpg") and not f.endswith((".md", ".py")):
                if not os.path.exists(os.path.join(dst, f)) or os.path.getmtime(a) > os.path.getmtime(os.path.join(dst, f)):
                    shutil.copy(a, os.path.join(dst, f))


# ------------------------------------------------------------------ hook
def fan_svg(E, fan):
    """dashed paths fanning from the left edge toward the year: the source's own scenario chart as a motif"""
    def rnd(i):  # seeded, deterministic
        x = math.sin(i * 12.9898 + 78.233) * 43758.5453
        return x - math.floor(x)
    ox, oy = fan.get("origin", (-30, 700))
    paths, k = [], 0
    for name, col, yc, spread in fan["bands"]:
        for j in range(9):
            y_end = yc + (j - 4) / 4 * spread * (0.6 + 0.4 * rnd(k))
            c1x, c1y = 260 + 60 * rnd(k + 1), oy - 10 * rnd(k + 2)
            c2x, c2y = 640 + 90 * rnd(k + 3), oy + (y_end - oy) * (0.35 + 0.2 * rnd(k + 4))
            dash = f"{9 + 5 * rnd(k + 5):.0f} {7 + 6 * rnd(k + 6):.0f}"
            w = 3.2 + 1.6 * rnd(k + 7)
            op = 0.55 + 0.35 * rnd(k + 8)
            paths.append(f'<path class="fp" d="M{ox} {oy} C {c1x:.0f} {c1y:.0f}, {c2x:.0f} {c2y:.0f}, 1110 {y_end:.0f}" '
                         f'stroke="{color(E, col)}" stroke-width="{w:.1f}" stroke-opacity="{op:.2f}" stroke-dasharray="{dash}" '
                         f'stroke-linecap="round" fill="none"/>')
            k += 9
    return ('<svg id="fan" class="layer" viewBox="0 0 1080 1920"><defs><clipPath id="fanclip">'
            '<rect id="fanrect" x="-40" y="0" width="1160" height="1920"/></clipPath></defs>'
            f'<g clip-path="url(#fanclip)">{"".join(paths)}</g></svg>')


def hook(E):
    """the text hook over the first shot, readable from frame 0; optional fan + tag behind the head"""
    H = E.HOOK
    if not H:
        return "", [], []
    # every part is optional: the creator's modes.hifi.hook decides the shape (two-line: eyebrow + h1 + h2;
    # one-line: h2 alone, the display line; none: no HOOK at all, the first caption carries it)
    parts = []
    if H.get("eyebrow"):
        eb = " · ".join(f'<span class="hw">{p}</span>' for p in H["eyebrow"].split(" · "))
        parts.append(f'<div class="eb">{eb}</div>')
    for k in ("h1", "h2"):
        if H.get(k):
            parts.append(f'<div class="{k}" data-layout-allow-overlap><span class="hw" data-layout-allow-overlap>{H[k]}</span></div>')
    top = f'<div id="hook" data-layout-allow-overlap>{"".join(parts)}</div>'
    behind, js = [], ["gsap.set('#hook .hw', { opacity: 1 });",
                      "tl.fromTo('#hook', { scale: 1.035 }, { scale: 1, duration: 0.5, ease: 'power3.out' }, 0);",
                      f"off('#hook', {H['off']:.3f});"]
    shot_end = H.get("shot_end", H["off"])
    if H.get("fan"):
        behind.append(fan_svg(E, H["fan"]))
        js += ["gsap.set('#fanrect', { attr: { width: 0 } });",
               "tl.to('#fanrect', { attr: { width: 1160 }, duration: 2.6, ease: 'power2.inOut' }, 0.05);",
               f"tl.fromTo('.fp', {{ strokeDashoffset: 0 }}, {{ strokeDashoffset: -120, duration: {shot_end:.2f}, ease: 'none' }}, 0);",
               f"off('#fan', {shot_end:.3f});"]
    if H.get("tag"):
        text, at, (x, y) = H["tag"]["text"], H["tag"]["at"], H["tag"].get("xy", (905, 438))
        behind.append(f'<div id="hook-tag" data-layout-allow-occlusion>{text}</div>')
        js += [f"gsap.set('#hook-tag', {{ opacity: 0, x: {x}, y: {y} }});",
               f"tl.fromTo('#hook-tag', {{ opacity: 0, x: {x - 20} }}, {{ opacity: 1, x: {x}, duration: 0.3, ease: 'power3.out', immediateRender: false }}, q({at:.3f}));",
               f"off('#hook-tag', {shot_end:.3f});"]
    return top, behind, js


# ------------------------------------------------------------------ behind the head (the cutout sits on top)
def behind(E):
    """edit.BEHIND moments:
      titles  one big display word at a time behind the head        items=[(t, text)], end[, top][, size][, stack=dict(x, dy, size)]
      wall    many small mono words around the head ("and a ton more")  words=[...], at, end
      number  one huge figure behind the head                        text, at, end, color, enter rise|drop[, top][, dx][, size]
      phrase  a line behind the head, optional line above it          text, at, end, color, above=(text, at)[, top][, size][, dx][, above_top]
      plate   a real screenshot as the wall behind the speaker               src (public/), at, end[, box=(x, y, w, h)][, pos]
      stack   screenshots drop in as a deck on the dark wall        items=[(t, src, num, label)], at, end[, kicker]
      list    lofi: a serif list that builds line by line            items=[(t, text)], end[, head][, replace][, top][, dy][, size]
      backdrop lofi: a full-bleed image or video swapped in behind the speaker  src, at, end[, media_start][, style]
      float   real videos drift in behind the speaker as framed windows      items=[dict(src, at, x, y, w[, ar][, rot])], end
      cover   a magazine masthead behind the head, coverlines         masthead, at, end[, top][, size][, dateline][, lines]
    """
    html, top, js = [], [], []
    for m, B in enumerate(E.BEHIND):
        k = B["kind"]
        if k == "titles":
            items, end = B["items"], T(E, B["end"])
            stack = B.get("stack")          # dict(x=, dy=[, size=]): the titles pile up as a left-aligned list
            for j, (t, w) in enumerate(items):
                jid = f"t{m}_{j}"
                if stack:
                    style = (f'top:{B.get("top", 362) + j * stack["dy"]}px;left:{stack["x"]}px;width:auto;text-align:left;'
                             f'font-size:{stack.get("size", 132)}px;')
                else:
                    style = f'top:{B.get("top", 362)}px;' + (f'font-size:{B["size"]}px;' if B.get("size") else "")
                html.append(f'<div id="{jid}" class="bh job" data-layout-allow-occlusion style="{style}">{w}</div>')
                nxt = end if stack else ((items[j + 1][0] - 0.03) if j + 1 < len(items) else end)
                js.append(f"gsap.set('#{jid}', {{opacity: 0}}); tl.fromTo('#{jid}', {{opacity: 0, y: 26}}, {{opacity: 1, y: 0, duration: 0.22, ease: 'power3.out', immediateRender: false}}, q({t - 0.03:.3f})); off('#{jid}', {nxt:.3f});")
        elif k == "wall":
            cols, row0, dy = B.get("cols", [62, 402, 742]), B.get("row0", 252), B.get("dy", 62)
            for j, w in enumerate(B["words"]):
                wid = f"w{m}_{j}"
                x, y = cols[j % len(cols)], row0 + dy * (j // len(cols))
                html.append(f'<div id="{wid}" class="wt w{m}" data-layout-allow-occlusion style="left:{x}px;top:{y}px;">{w}</div>')
            js.append(f"gsap.set('.w{m}', {{opacity: 0}});")
            js.append(f"for (var i = 0; i < {len(B['words'])}; i++) {{ var t = {B['at']} + (i * 0.6180339 % 1) * 0.75; "
                      f"tl.fromTo('#w{m}_' + i, {{opacity: 0, y: 10}}, {{opacity: 1, y: 0, duration: 0.18, ease: 'power2.out', immediateRender: false}}, q(t)); }}")
            js.append(f"tl.set('.w{m}', {{opacity: 0}}, q({T(E, B['end']):.3f}));")
        elif k == "number":
            nid = f"n{m}"
            col = color(E, B.get("color", "accent"))
            html.append(f'<div id="{nid}" class="bh num" data-layout-allow-occlusion data-layout-allow-overlap style="top:{B.get("top", 196)}px;left:{B.get("dx", 0)}px;color:{col};{f'font-size:{B["size"]}px;' if B.get("size") else ''}">{B["text"]}</div>')
            js.append(f"gsap.set('#{nid}', {{opacity: 0}});")
            if B.get("enter", "rise") == "drop":
                js.append(f"tl.fromTo('#{nid}', {{opacity: 0, y: -26}}, {{opacity: 1, y: 0, duration: 0.28, ease: 'power3.out', immediateRender: false}}, q({B['at']:.3f}));")
            else:
                js.append(f"tl.fromTo('#{nid}', {{opacity: 0, scale: 1.08, y: 20}}, {{opacity: 1, scale: 1, y: 0, duration: 0.3, ease: 'power3.out', immediateRender: false}}, q({B['at']:.3f}));")
            js.append(f"off('#{nid}', {T(E, B['end']):.3f});")
        elif k == "phrase":
            pid = f"p{m}"
            col = color(E, B.get("color", "accent"))
            html.append(f'<div id="{pid}" class="bh" data-layout-allow-occlusion data-layout-allow-overlap '
                        f'style="top:{B.get("top", 296)}px;left:{B.get("dx", 0)}px;font-size:{B.get("size", 196)}px;color:{col};">{B["text"]}</div>')
            js.append(f"gsap.set('#{pid}', {{opacity: 0}});")
            js.append(f"tl.fromTo('#{pid}', {{opacity: 0, y: 30}}, {{opacity: 1, y: 0, duration: 0.3, ease: 'power3.out', immediateRender: false}}, q({B['at']:.3f}));")
            js.append(f"off('#{pid}', {T(E, B['end']):.3f});")
            if B.get("above"):
                text, at = B["above"]
                atop = f'top:{B["above_top"]}px;' if "above_top" in B else ""
                top.append(f'<div id="{pid}a" class="above" data-layout-allow-overlap style="left:{B.get("dx", 0)}px;{atop}">{text}</div>')
                js.append(f"gsap.set('#{pid}a', {{opacity: 0}});")
                js.append(f"tl.fromTo('#{pid}a', {{opacity: 0, y: 10}}, {{opacity: 1, y: 0, duration: 0.14, ease: 'power2.out', immediateRender: false}}, q({at:.3f}));")
                js.append(f"off('#{pid}a', {T(E, B['end']):.3f});")
        elif k == "list":
            # stacked (default): the lines pile up under each other. replace=True: a header line stays, each item
            # takes the one slot under it until the next (for framings with little headroom above the head)
            top0, dy, end = B.get("top", 420), B.get("dy", 84), T(E, B["end"])
            items, head = B["items"], B.get("head")
            for j, (t, text) in enumerate(items):
                lid = f"l{m}_{j}"
                is_head = j == 0 and head
                cls = "ls head" if is_head else "ls"
                slot = (0 if is_head else 1) if B.get("replace") else j
                size = f'font-size:{B["size"]}px;' if B.get("size") and not is_head else ""
                html.append(f'<div id="{lid}" class="{cls}" data-layout-allow-occlusion style="top:{top0 + slot * dy}px;{size}">{text}</div>')
                nxt = items[j + 1][0] - 0.03 if B.get("replace") and not is_head and j + 1 < len(items) else end
                js.append(f"tl.fromTo('#{lid}', {{opacity: 0, y: 14}}, {{opacity: 1, y: 0, duration: 0.2, ease: 'power3.out', immediateRender: false}}, q({t:.3f})); off('#{lid}', {nxt:.3f});")
        elif k == "backdrop":
            end = T(E, B["end"])
            tag, vid = media_tag(f"bd{m}", "bd", B["src"], B["at"], end, B.get("style", ""), 70 + m, B.get("media_start", 0.0))
            html.append(tag)
            if not vid:
                js.append(f"on('#bd{m}', {B['at']:.3f}); off('#bd{m}', {end:.3f});")
        elif k == "plate":
            # a real screenshot as the wall behind the speaker (green-screen look), hard cut in and out on the words.
            # box=(x, y, w, h) on the 1080x1920 frame; keep it above the desk (the desk is not in the cutout)
            x, y, w, h = B.get("box", (0, 190, 1080, 960))
            pid = f"pl{m}"
            html.append(f'<img id="{pid}" class="plate" src="{B["src"]}" data-layout-allow-occlusion '
                        f'style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;object-position:{B.get("pos", "50% 0%")};">')
            js.append(f"gsap.set('#{pid}', {{opacity: 0}}); on('#{pid}', {B['at']:.3f}); off('#{pid}', {T(E, B['end']):.3f});")
        elif k == "stack":
            # real screenshots dropping in behind the speaker as a stacked deck of windows on the dark wall, one per
            # spoken item, each fitted to the content width with a numbered mono tag on its bar
            from PIL import Image
            sid, gh = f"st{m}", B.get("ground_h", 1700)
            x, w, y0, dy = B.get("x", 70), B.get("w", 940), B.get("y0", 330), B.get("dy", 96)
            parts = [f'<div id="{sid}" class="stack ground-dark" data-layout-allow-occlusion data-layout-allow-overlap '
                     f'style="height:{gh}px;">']
            if B.get("kicker"):
                parts.append(f'<div class="stk-k">{B["kicker"]}</div>')
            for j, (t, src, num, label) in enumerate(B["items"]):
                iw, ih = Image.open(os.path.join(E.PROJECT, "public", src)).size
                h = round(w * ih / iw)
                parts.append(f'<div id="{sid}_{j}" class="stk-w" style="left:{x}px;top:{y0 + j * dy}px;width:{w}px;">'
                             f'<div class="stk-b"><span class="stk-n">{num}</span>{label}</div>'
                             f'<img src="{src}" style="width:{w}px;height:{h}px;"></div>')
                js.append(f"gsap.set('#{sid}_{j}', {{opacity: 0}}); tl.fromTo('#{sid}_{j}', {{opacity: 0, y: -46}}, "
                          f"{{opacity: 1, y: 0, duration: 0.32, ease: 'power3.out', immediateRender: false}}, q({t - 0.03:.3f}));")
            parts.append('</div>')
            html.append("".join(parts))
            js.append(f"gsap.set('#{sid}', {{opacity: 0}}); on('#{sid}', {B['at']:.3f}); off('#{sid}', {T(E, B['end']):.3f});")
        elif k == "float":
            # real videos (the creator's own clips) drift in behind the speaker as framed windows, one per item, slow float up
            end = T(E, B["end"])
            for j, it in enumerate(B["items"]):
                fid = f"fl{m}_{j}"
                style = (f'left:{it["x"]}px;top:{it["y"]}px;width:{it["w"]}px;height:{round(it["w"] * it.get("ar", 16 / 9))}px;'
                         f'transform:rotate({it.get("rot", 0)}deg);')
                tag, vid = media_tag(fid, "flt", it["src"], it["at"], end, style, 80 + 4 * m + j, it.get("media_start", 0.0))
                html.append(tag)
                if not vid:                     # a still (a screenshot of the reel): timed by hand, like a video would be
                    js.append(f"gsap.set('#{fid}', {{opacity: 0}}); on('#{fid}', {it['at']:.3f}); off('#{fid}', {end:.3f});")
                js.append(f"tl.fromTo('#{fid}', {{ y: {it.get('rise', 90)}, scale: 0.94 }}, {{ y: 0, scale: 1, duration: 0.55, ease: 'power3.out', immediateRender: false }}, q({it['at']:.3f}));")
                js.append(f"tl.to('#{fid}', {{ y: -{it.get('drift', 18)}, duration: {max(0.1, end - it['at'] - 0.55):.3f}, ease: 'none' }}, q({it['at'] + 0.55:.3f}));")
        elif k == "cover":
            # a magazine cover: the masthead set behind the head (the head breaks it, as on a real cover), a dateline
            # above it and coverlines down the sides. masthead, at, end[, top][, size][, dateline][, lines=[(t, x, y, kicker, text)]]
            cid, end = f"cv{m}", T(E, B["end"])
            parts = [f'<div id="{cid}" class="cover" data-layout-allow-occlusion data-layout-allow-overlap>']
            if B.get("dateline"):
                parts.append(f'<div class="cv-d" data-layout-allow-overlap data-layout-allow-occlusion style="top:{B.get("dl_top", B.get("top", 200) - 34)}px;">{B["dateline"]}</div>')
            parts.append(f'<div class="cv-m" data-layout-allow-overlap data-layout-allow-occlusion style="top:{B.get("top", 200)}px;font-size:{B.get("size", 250)}px;">{B["masthead"]}</div>')
            for j, (t, x, y, kick, text) in enumerate(B.get("lines", [])):
                lns = "".join(f'<span class="cv-t">{t}</span>' for t in text.split(" / "))     # " / " breaks the line
                parts.append(f'<div id="{cid}_{j}" class="cv-l" data-layout-allow-overlap data-layout-allow-occlusion style="left:{x}px;top:{y}px;"><span class="cv-k">{kick}</span>{lns}</div>')
                js.append(f"gsap.set('#{cid}_{j}', {{opacity: 0}}); tl.fromTo('#{cid}_{j}', {{opacity: 0, y: 12}}, {{opacity: 1, y: 0, duration: 0.22, ease: 'power3.out', immediateRender: false}}, q({t:.3f}));")
            parts.append('</div>')
            html.append("".join(parts))
            js.append(f"gsap.set('#{cid}', {{opacity: 0}}); on('#{cid}', {B['at']:.3f}); off('#{cid}', {end:.3f});")
            js.append(f"tl.fromTo('#{cid} .cv-m', {{ y: 40, scale: 1.04 }}, {{ y: 0, scale: 1, duration: 0.4, ease: 'expo.out', immediateRender: false }}, q({B['at']:.3f}));")
        else:
            raise SystemExit(f"unknown BEHIND kind: {k}")
    return html, top, js


def cutouts(E, TL):
    """cutout windows: something sits behind the speaker. A window must not span a picture change (the cutout seeks a frame
    late, so a reframe inside a window renders one doubled-head frame)."""
    changes = TL["picture_cuts"] + TL["reframes"]
    out = []
    for k, (a, b) in enumerate(E.CUT_WINDOWS):
        b = T(E, b)
        bad = [c for c in changes if q(a) + 0.5 / 30 < c < q(b) - 0.5 / 30]     # frame-snapped: 39.333 starts ON 39.3333
        if bad:
            raise SystemExit(f"cutout window {a}-{b} spans a picture change at {bad}: split the window or move the shot")
        out.append(f'<video id="s{k}" class="full g" src="subject.webm" muted playsinline data-start="{clip_start(a):.4f}" '
                   f'data-media-start="{q(a) + 0.001:.4f}" data-duration="{q(b) - q(a):.4f}" data-track-index="{2 + k if k < 8 else 100 + k}"></video>')
    return out


# ------------------------------------------------------------------ camera + grade
def settle_times(E, TL):
    """a short settle (scale 1.045 -> 1) every time the talking head comes back after a card and on every visible
    picture cut or reframe, except where a punch-in or a push starts"""
    C = E.CAMERA
    if "settles" in C:
        return C["settles"]
    if getattr(E, "MODE", {}).get("camera", "settle") != "settle":      # the creator's camera: "zooms" or "still"
        return []
    starts = [p[0] for p in C.get("punch", [])] + [p[0] for p in C.get("pushes", [])]
    card_ends = [c[3] for c in E.CARDS if visible(E, c[3])]
    changes = [t for t in TL["picture_cuts"] + TL["reframes"] if visible(E, t)]
    return sorted({round(t, 3) for t in card_ends + changes if all(abs(t - p) > 0.02 for p in starts)})


def camera(E, TL):
    C = E.CAMERA
    settles = settle_times(E, TL)
    js = [f"[{', '.join(f'{t:.3f}' for t in settles)}].forEach(function (t) {{",
          "  tl.fromTo('#cam', { scale: 1.045 }, { scale: 1, duration: 0.32, ease: 'power2.out', immediateRender: false }, q(t));",
          "});"]
    for t, s in C.get("punch", []):
        js.append(f"tl.fromTo('#cam', {{ scale: {s} }}, {{ scale: 1.0, duration: 0.18, ease: 'power3.out', immediateRender: false }}, q({t:.3f}));")
    for a, b, s in C.get("zooms", []):              # lofi: a hard zoom held for the phrase, hard back out
        js.append(f"tl.set('#cam', {{ scale: {s} }}, q({a:.3f})); tl.set('#cam', {{ scale: 1 }}, q({T(E, b):.3f}));")
    for a, b, s in C.get("pushes", []):
        b = T(E, b)
        js.append(f"tl.fromTo('#cam', {{ scale: 1 }}, {{ scale: {s}, duration: {b - a:.3f}, ease: 'none', immediateRender: false }}, q({a:.3f}));")
    o_s, o_d = C.get("open", (1.04, 0.45))
    js.append(f"tl.fromTo('#cam', {{ scale: {o_s} }}, {{ scale: 1, duration: {o_d}, ease: 'power2.out' }}, 0);")
    return js


# looks the script can ask for (edit.GRADES), same filter list as the house grade so they tween into each other
LOOKS = {"warm": "sepia(0.34) contrast(1.05) saturate(1.3) brightness(1.04) hue-rotate(-9deg)",
         "moody": "sepia(0.06) contrast(1.24) saturate(0.55) brightness(0.70) hue-rotate(4deg)"}


def grade(E):
    js = [f"var COLOR = '{E.S.get('grade') or 'none'}';",
          "var MONO = 'grayscale(1) contrast(1.2) brightness(0.9)';",
          "gsap.set('.g', { filter: COLOR });",
          f"[{', '.join(f'[{a:.3f}, {b:.3f}]' for a, b in E.BW)}].forEach(function (w) {{",
          "  tl.set('.g', { filter: MONO }, q(w[0])); tl.set('.g', { filter: COLOR }, q(w[1]));",
          "});"]
    for G in E.GRADES:                     # (start, end, look[, fade in seconds]); out is a hard cut back
        a, b, look = G[0], T(E, G[1]), LOOKS.get(G[2], G[2])
        fade = G[3] if len(G) > 3 else 0
        if fade:
            js.append(f"tl.fromTo('.g', {{ filter: COLOR }}, {{ filter: '{look}', duration: {fade}, ease: 'power1.inOut', immediateRender: false }}, q({a:.3f}));")
        else:
            js.append(f"tl.set('.g', {{ filter: '{look}' }}, q({a:.3f}));")
        js.append(f"tl.set('.g', {{ filter: COLOR }}, q({b:.3f}));")
    return js


# ------------------------------------------------------------------ end card (opt-in)
def end_card(E):
    if not E.END_CARD:
        return "", []
    D = E.END_CARD
    src = "".join(f'<div class="src" style="top:{930 + 36 * i}px;">{s}</div>' for i, s in enumerate(D.get("src", [])))
    mark = D.get("mark") or E.S["creator"].get("site") or E.S["creator"].get("handle") or ""
    html = (f'<div id="end" class="layer ground-light"><div class="q1">{D["q1"]}</div><div class="q2">{D["q2"]}</div>{src}'
            f'<div class="mark" style="top:1060px;">{mark}</div></div>')
    e = E.END_IN
    js = [f"on('#end', {e:.3f});",
          "gsap.set(['#end .q1', '#end .q2', '#end .src', '#end .mark'], { opacity: 0 });",
          f"tl.set('#end .q1', {{ opacity: 1 }}, q({e:.3f}));",
          f"tl.fromTo('#end .q1', {{ y: 14 }}, {{ y: 0, duration: 0.3, ease: 'power3.out', immediateRender: false }}, q({e:.3f}));",
          f"tl.fromTo('#end .q2', {{ opacity: 0, y: 16 }}, {{ opacity: 1, y: 0, duration: 0.25, ease: 'power3.out', immediateRender: false }}, q({e + 0.12:.3f}));",
          f"tl.to(['#end .src', '#end .mark'], {{ opacity: 1, duration: 0.2, ease: 'none' }}, q({e + 0.40:.3f}));"]
    return html, js


SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')

LOFI_HIDE = "gsap.set(['.kc', '.nb', 'img.ov', '.ls', 'img.bd'], { opacity: 0 });"


def build(E, TL, safe=False, stills=False):
    pub = os.path.join(E.PROJECT, "public")
    lofi = getattr(E, "STYLE", "hifi") in ("lofi", "showcase")      # showcase = the lo-fi type system + edit.FX
    cap_html, cap_js = karaoke(E) if lofi else captions(E)
    box_html, box_js = boxes(E)
    ov_html, ov_js = overlays(E)
    hook_top, hook_behind, hook_js = hook(E)
    bh_html, bh_top, bh_js = behind(E)
    end_html, end_js = end_card(E)
    fx_html, fx_js = fx(E)
    card_html, card_js = [], []
    for k, c in enumerate(E.CARDS):
        cid, f, a, b, g = c[:5]
        still = os.path.join("cards", cid, "still.jpg")
        if os.path.exists(os.path.join(pub, f)):
            card_html.append(f'<video id="{cid}" class="full" src="{f}" muted playsinline data-start="{clip_start(a):.4f}" '
                             f'data-duration="{q(b) - q(a):.4f}" data-media-start="0" data-track-index="{20 + k}"></video>')
        elif stills and os.path.exists(os.path.join(pub, still)):
            card_html.append(f'<img id="{cid}" class="full" src="{still}">')
            card_js += [f"gsap.set('#{cid}', {{opacity: 0}});", f"on('#{cid}', {a:.3f});", f"off('#{cid}', {b:.3f});"]
        else:
            card_html.append(f'<div id="{cid}" class="layer ph {"light" if g == "light" else "dark"}">{cid.upper()} pending</div>')
            card_js += [f"gsap.set('#{cid}', {{opacity: 0}});", f"on('#{cid}', {a:.3f});", f"off('#{cid}', {b:.3f});"]
    if wide(E):
        raise SystemExit("16:9 wide cuts are not in this version of the kit: keep CANVAS = (1080, 1920)")
    brand = open(os.path.join(pub, "brand.css")).read()          # the creator's pack: fonts + tokens (installed by main)
    css = open(os.path.join(KIT, "kit", "reel.css")).read()
    W, H = E.CANVAS
    css += f"\n#cam {{ transform-origin:{E.CAM_ORIGIN[0]}px {E.CAM_ORIGIN[1]}px; }}"
    if lofi:
        css += "\n" + open(os.path.join(KIT, "kit", "reel-lofi.css")).read()
    css += "\n" + pack_css(E)
    words_path = os.path.join(E.PROJECT, "words.json")
    words = [[w["start"], w["end"], w["text"]] for w in json.load(open(words_path))] if os.path.exists(words_path) else []
    cuts = [round(t, 4) for t in TL.get("picture_cuts", [])]
    fxs = [dict(id=F["id"], layer=F.get("layer", "top"), at=round(F["at"], 4), end=round(T(E, F["end"]), 4))
           for F in getattr(E, "FX", [])]
    js = f"""
  var FPS = 30, TOTAL = {E.TOTAL:.4f};
  var tl = gsap.timeline({{ paused: true }});
  function q(t) {{ return Math.max(0, Math.round(t * FPS) / FPS - 0.002); }}   // land every event ON its frame
  // for effects (edit.FX): the picture cuts and the words on the output timeline, and the time of a word
  var CUTS = {json.dumps(cuts)};
  var FXS = {json.dumps(fxs)};                         // every effect's window: {{id, layer, at, end}}
  var LOOKS = {json.dumps(LOOKS)};                     // the named grades (GRADES): name -> CSS filter
  var WORDS = {json.dumps(words)};
  function wordAt(text, after) {{
    var want = String(text).toLowerCase().replace(/[^a-z0-9%$']/g, ''), from = after || 0;
    for (var i = 0; i < WORDS.length; i++) {{
      if (WORDS[i][0] >= from - 0.001 && WORDS[i][2].toLowerCase().replace(/[^a-z0-9%$']/g, '') === want) return WORDS[i][0];
    }}
    return null;
  }}
  function wordSpan(text, after) {{                    // [start, end] of the same word, or null
    var t = wordAt(text, after);
    if (t === null) return null;
    for (var i = 0; i < WORDS.length; i++) {{ if (Math.abs(WORDS[i][0] - t) < 0.0005) return [WORDS[i][0], WORDS[i][1]]; }}
    return null;
  }}
  function on(x, t) {{ tl.set(x, {{ opacity: 1 }}, q(t)); }}
  function off(x, t) {{ tl.set(x, {{ opacity: 0 }}, q(t)); }}
  function pop(x, t) {{
    tl.set(x, {{ opacity: 1 }}, q(t));
    tl.fromTo(x, {{ scale: 0.95 }}, {{ scale: 1, duration: 0.16, ease: 'power3.out', immediateRender: false }}, q(t));
  }}
  {LOFI_HIDE if lofi else "gsap.set('.cap', { opacity: 0 });"}

  // ---- grade: the pack's grade; black and white on the fear beats
  {NL.join(grade(E))}

  // ---- camera: a settle on every visible cut, a punch-in, slow pushes
  {NL.join(camera(E, TL))}

  // ---- hook
  {NL.join(hook_js)}

  // ---- behind the head
  {NL.join(bh_js)}

  // ---- cards
  {NL.join(card_js)}

  // ---- lo-fi: overlays on top of the speaker, text boxes
  {NL.join(ov_js)}
  {NL.join(box_js)}

  // ---- motion graphics (edit.FX)
  {NL.join(fx_js)}

  // ---- captions
  {NL.join(cap_js)}

  // ---- end card
  {NL.join(end_js)}

  tl.set({{}}, {{}}, TOTAL);
  window.__timelines['main'] = tl;
"""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{E.TITLE}</title>
<style>
{brand}
{css}
.above {{ width:{W}px; top:{getattr(E, 'ABOVE_TOP', 236)}px; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{E.TOTAL:.4f}" data-fps="30" data-width="{W}" data-height="{H}">
  <div id="foot" class="layer">
    <div id="cam" class="layer">
      <video id="v" class="full g" src="clean.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{E.TOTAL:.4f}" data-track-index="1"></video>
      <div id="behind" class="layer">
        {NL.join(hook_behind)}
        {NL.join(bh_html)}
        {NL.join(fx_html['behind'])}
      </div>
      {NL.join(cutouts(E, TL))}
      {NL.join(fx_html['cam'])}
    </div>
  </div>
  <audio id="mix" src="master.wav" data-start="0" data-duration="{E.TOTAL:.4f}" data-track-index="10" data-volume="1"></audio>
  {NL.join(card_html)}
  {NL.join(ov_html)}
  {hook_top}
  {NL.join(box_html)}
  {NL.join(bh_top)}
  {NL.join(fx_html['top'])}
  <div id="caps" class="layer">
{NL.join(cap_html)}
  </div>
  {NL.join(fx_html['over'])}
  {end_html}
  {SAFE_GUIDE if safe else ''}
</div>
<script src="vendor/gsap.min.js"></script>
<script>
(function () {{{js}}})();
</script>
</body>
</html>
"""


def sync_cards(E, project, pub):
    """card agents work in <project>/cards/<id>/: bring their mp4 (and storyboard still) into public/cards/"""
    import shutil
    for c in E.CARDS:
        cid, f = c[0], c[1]
        src_dir = os.path.join(project, "cards", cid)
        mp4 = os.path.join(src_dir, f"{cid}.mp4")
        dst = os.path.join(pub, f)
        if os.path.exists(mp4) and f == f"cards/{cid}.mp4" and (not os.path.exists(dst) or os.path.getmtime(mp4) > os.path.getmtime(dst)):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(mp4, dst)
        still = os.path.join(src_dir, "still.jpg")
        if os.path.exists(still):
            os.makedirs(os.path.join(pub, "cards", cid), exist_ok=True)
            shutil.copy(still, os.path.join(pub, "cards", cid, "still.jpg"))


def main():
    project = project_arg()
    E = load_edit(project)
    TL = timeline(project)
    setup(E, TL)
    pub = os.path.join(project, "public")
    ST.install(E.S, pub)
    sync_cards(E, project, pub)
    sync_fx(E, project, pub)
    doc = build(E, TL, safe="--safe" in sys.argv, stills="--stills" in sys.argv)
    try:          # GSAP inside the page: a render worker that loses a fetch (a network change) loses every animation
        doc = IV.inline(doc, pub)
    except (OSError, ValueError) as e:
        raise SystemExit(f"build: {e}")
    with open(os.path.join(pub, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(doc)
    have = [c[0] for c in E.CARDS if os.path.exists(os.path.join(pub, c[1]))]
    missing = [c[0] for c in E.CARDS if c[0] not in have]
    print(f"wrote {pub}/index.html  {E.TOTAL:.3f}s  cards ready: {have}  missing: {missing or 'none'}")


if __name__ == "__main__":
    main()
