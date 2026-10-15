#!/usr/bin/env python3
"""Storyboard: the built composition, beat by beat, as a page the creator reviews before anything renders.

Every panel is one beat of the reel: its time range, the line they say, real frames snapshotted from the actual
composition (their footage, the captions, the cards as designed), what moves and what you hear. The page wears the
creator's own fonts and colours (their style pack). Two ways to review it (SKILL.md, step 6):
  - Claude: publish it as an artifact with inline comments (capabilities {"comments": {"composer_only": true}})
  - anywhere: `python3 storyboard/serve.py <project>`, notes land in <project>/storyboard/notes.json
Run: PY pipeline/storyboard.py <project> [--version N] [--no-frames | --list]
     --list prints the beat ids (p01, p02...) and stops: use it to fill NEEDS before any frames exist
Writes <project>/storyboard/index.html, frames/*.jpg, fonts/ and files.json (every file to publish with the page).
"""
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KIT, hf, load_edit, project_arg, q, timeline  # noqa: E402
import build as B  # noqa: E402
import style as ST  # noqa: E402

SFX_WORDS = {
    "whoosh": "whoosh", "whoosh-soft": "soft whoosh", "whoosh-deep": "deep whoosh", "whoosh-long": "long whoosh",
    "pop": "pop", "click": "click", "tick": "tick", "clicks-run": "clicking run", "ding": "ding", "shutter": "shutter",
    "stamp": "stamp", "impact-low": "low impact", "boom-low": "low boom", "riser": "riser", "riser-long": "long riser",
    "drum-hit": "drum hit", "scratch": "scratch", "switch-off": "switch-off", "typing": "typing", "key": "key press",
}
KIND_WORDS = {"thesis": "display word", "big": "big", "strike": "struck through"}


def tc(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def panels(E, TL):
    """beat boundaries: cards, the hook shot, b&w beats, visible picture changes, the end card"""
    bounds = {0.0, E.TOTAL}
    for c in E.CARDS:
        bounds |= {c[2], c[3]}
    for a, b in E.BW:
        bounds |= {a, b}
    if E.HOOK:
        bounds.add(E.HOOK.get("shot_end", E.HOOK["off"]))
    if E.END_CARD:
        bounds.add(E.END_IN)
    for O in getattr(E, "OVERLAYS", []) + getattr(E, "BOXES", []):      # lofi: each overlay and text box is a beat
        bounds |= {O["at"], B.T(E, O["end"])}
    for F in getattr(E, "FX", []):                                          # each motion graphic (with a note) is a beat
        if F.get("note"):
            bounds |= {F["at"], B.T(E, F["end"])}
    bounds |= {t for t in TL["picture_cuts"] + TL["reframes"] if B.visible(E, t)}
    bs = sorted(round(t, 3) for t in bounds if 0 <= t <= E.TOTAL)
    out = []
    for a, b in zip(bs, bs[1:]):
        if out and b - a < 0.6:          # too short to be its own beat
            out[-1][1] = b
        else:
            out.append([a, b])
    return out


def describe(E, TL, a, b, words):
    mid = (a + b) / 2
    card = next((c for c in E.CARDS if c[2] - 1e-6 <= mid < c[3] - 1e-6), None)
    end = bool(E.END_CARD) and mid >= E.END_IN
    shot = [s for s in TL["shots"] if s["t"] <= mid + 1e-6][-1]["frame"]
    bw = any(x <= mid < y for x, y in E.BW)
    frames, moves = [], []
    if end:
        kind, label = "end", "End card"
        D = E.END_CARD
        mark = D.get("mark") or E.S["creator"].get("site") or E.S["creator"].get("handle") or ""
        moves.append(f"End card: “{D['q1']} {D['q2']}”" + (f", {mark}." if mark else "."))
        frames = [min(b - 0.1, a + 0.7)]
    elif card:
        kind = "light" if card[4] == "light" else "dark"
        label = f"Data card, {kind} ground"
        note = (card[5] if len(card) > 5 else card[0]).rstrip(".")
        moves.append(note[:1].upper() + note[1:] + ".")
        dur = b - a
        frames = [a + dur * 0.5, b - 0.12] if dur > 1.6 else [a + dur * 0.7]
    else:
        kind = "footage"
        label = f"Talking head, {'close' if shot == 'CLOSE' else 'wide'}" + (", black and white" if bw else "")
        if E.HOOK and a < E.HOOK.get("shot_end", E.HOOK["off"]) - 0.05:
            H = E.HOOK
            moves.append(f"Hook over the first shot from frame 0: “{H['h1']} / {H['h2']}”")
            if H.get("fan"):
                moves.append("The source's scenario fan draws behind your head.")
            if H.get("tag"):
                moves.append(f"“{H['tag']['text']}” lands beside your head at {tc(H['tag']['at'])}.")
            frames += [0.6, min(b - 0.15, H["tag"]["at"] + 0.3) if H.get("tag") else b - 0.3]
        for m in E.BEHIND:
            if m["kind"] in ("list", "backdrop"):
                continue
            at = m["items"][0][0] if m["kind"] == "titles" else m["items"][0]["at"] if m["kind"] == "float" else m["at"]
            if a - 0.05 <= at < b:
                if m["kind"] == "titles":
                    moves.append("Behind your head, one word at a time: " + ", ".join(w.strip(",") for _, w in m["items"]) + ".")
                elif m["kind"] == "wall":
                    moves.append(f"The wall fills with {len(m['words'])} more words.")
                elif m["kind"] == "number":
                    moves.append(f"“{m['text']}” in {m.get('color', 'accent')} behind your head.")
                elif m["kind"] == "phrase":
                    above = f"“{m['above'][0]}” above, " if m.get("above") else ""
                    moves.append(f"{above}“{m['text']}” behind your head.")
                elif m["kind"] == "float":
                    moves.append(f"{len(m['items'])} of your own clips float in behind you, playing.")
                elif m["kind"] == "cover":
                    moves.append(f"A magazine cover: “{m['masthead']}” masthead behind your head, coverlines down the sides.")
                frames.append(min(b - 0.1, at + 0.45))
        for t, s in E.CAMERA.get("punch", []):
            if a - 0.01 <= t < b:
                moves.append("Punch-in on the cut.")
        for x in getattr(E, "BOXES", []) + getattr(E, "OVERLAYS", []):  # lo-fi: say what lands on top of you
            if a - 0.05 <= x["at"] < b and x.get("note"):
                moves.append(x["note"])
                frames.append(min(b - 0.1, x["at"] + 0.45))
        for F in getattr(E, "FX", []):                                      # motion graphics: note + its key frames
            if a - 0.05 <= F["at"] < b and F.get("note"):
                moves.append(F["note"])
                frames += [min(b - 0.1, t) for t in F.get("frames", [F["at"] + 0.45])]
        for m in E.BEHIND:
            if m["kind"] not in ("list", "backdrop"):
                continue
            at = m["items"][0][0] if m["kind"] == "list" else m["at"]
            if m["kind"] in ("list", "backdrop") and a - 0.05 <= at < b and m.get("note"):
                moves.append(m["note"])
                last = m["items"][-1][0] if m["kind"] == "list" else at
                frames.append(min(b - 0.1, last + 0.45))
        for t0, t1, z in E.CAMERA.get("zooms", []):
            if a - 0.01 <= t0 < b:
                moves.append(f"Hard zoom in ({z}x) at {tc(t0)}, back out at {tc(B.T(E, t1))}.")
        if bw:
            moves.append("Black and white, slow push.")
        for G in E.GRADES:
            if a - 0.05 <= G[0] < b:
                moves.append(f"The picture goes {G[2]}" + (f" (eases in over {G[3]}s)" if len(G) > 3 else "") + f", until {tc(B.T(E, G[1]))}.")
        if not frames:
            frames = [a + (b - a) * 0.5]
        if len(frames) == 1 and b - a > 2.4:
            frames.append(b - 0.2)
    caps = [c for c in E.CAPS if a - 1e-6 <= c[0] < b - 1e-6]
    emph = [f"{c[1].replace('*', '').rstrip('.,!?')} ({KIND_WORDS[c[2]]})" for c in caps if c[2] in KIND_WORDS]
    accent = [m.rstrip('.,!?') for c in caps for m in re.findall(r"\*([^*]+)\*", c[1]) if c[2] != "big"]
    sounds = []
    for item in sorted(list(E.SOUND.get("sfx", [])) + list(E.CARD_SFX), key=lambda x: x[0]):
        if a - 0.25 <= item[0] < b - 0.25:
            w = SFX_WORDS.get(item[1], item[1].replace("-", " "))
            if not sounds or sounds[-1] != w:
                sounds.append(w)
    marks = [m for t, m in E.SOUND.get("marks", []) if a - 0.1 <= t < b - 0.05]
    # at a J-cut join the line you hear starts J_LEAD before its picture; cards and reframes cut on the word
    joins = TL["picture_cuts"]
    la = a - (E.J_LEAD if any(abs(a - j) < 0.02 for j in joins) else 0.0)
    lb = b - (E.J_LEAD if any(abs(b - j) < 0.02 for j in joins) else 0.0)
    line = " ".join(w["text"] for w in words if la <= (w["start"] + w["end"]) / 2 < lb)
    line = re.sub(r"\s+([%,.!?;:])", r"\1", line)          # "15 %" -> "15%"
    frames = sorted({round(min(max(t, a + 0.04), b - 0.07), 3) for t in frames})[:3]
    return dict(kind=kind, label=label, line=line, moves=moves, emph=emph, accent=accent,
                sound=", ".join(sounds), marks=marks, frames=frames)


KIND_LABEL = {"footage": "you on camera", "light": "light card", "dark": "dark card", "end": "end card"}


def strip_html(E, ps):
    out = []
    for p in ps:
        w = 100 * (p["t1"] - p["t0"]) / E.TOTAL
        out.append(f'<a class="seg {p["kind"]}" href="#{p["id"]}" style="flex:0 0 calc({w:.3f}% - 2px)" '
                   f'title="{p["n"]:02d} · {p["tc0"]} · {html.escape(p["label"])}" aria-label="Beat {p["n"]}, {p["tc0"]}"></a>')
    return "".join(out)


def ticks_html(E):
    return "".join(f'<i class="tick" style="left:{100 * t / E.TOTAL:.2f}%" title="{html.escape(m)} {tc(t)}"></i>'
                   for t, m in E.SOUND.get("marks", []))


def frame_html(p, im):
    return (f'<button class="frame" type="button" data-cap="Beat {p["n"]:02d} at {im["t"]}">'
            f'<img src="{im["src"]}" alt="Frame at {im["t"]}" loading="lazy" width="540" height="960">'
            f'<span>{im["t"]}</span></button>')


def beat_html(p):
    e = html.escape
    imgs = "".join(frame_html(p, im) for im in p.get("imgs", []))
    line = (f'<p class="line">“{e(p["line"])}”</p>' if p["line"] else '<p class="line quiet">No words here.</p>')
    moves = "".join(f"<li>{e(m)}</li>" for m in p["moves"])
    facts = []
    for t in p.get("needs", []):
        facts.append(f'<dt class="need">From you</dt><dd class="need">{e(t)}</dd>')
    for t in p.get("generated", []):
        facts.append(f'<dt>Generated</dt><dd>{e(t)}</dd>')
    if p["emph"]:
        facts.append(f"<dt>Emphasis</dt><dd>{e(', '.join(p['emph']))}</dd>")
    if p["accent"]:
        facts.append(f"<dt>Accent</dt><dd>{e(', '.join(p['accent']))}</dd>")
    if p["sound"]:
        facts.append(f"<dt>Sound</dt><dd>{e(p['sound'])}</dd>")
    if p["marks"]:
        facts.append(f'<dt>Music</dt><dd class="score">{e(", ".join(p["marks"]))}</dd>')
    return (f'    <section class="beat" id="{p["id"]}" data-comment-target aria-label="Beat {p["n"]}">\n'
            f'      <div class="frames">{imgs}</div>\n'
            f'      <div class="notes">\n'
            f'        <div class="meta"><span class="n">{p["n"]:02d}</span><span>{p["tc0"]}–{p["tc1"]}</span>'
            f'<span>{p["dur"]}</span><span class="kind"><i class="sw {p["kind"]}"></i>{e(p["label"])}</span></div>\n'
            f'        {line}\n'
            f'        {"<ul class=" + chr(34) + "moves" + chr(34) + ">" + moves + "</ul>" if moves else ""}\n'
            f'        {"<dl class=" + chr(34) + "facts" + chr(34) + ">" + "".join(facts) + "</dl>" if facts else ""}\n'
            f'        <button class="note" type="button" data-note>Comment on this beat</button>\n'
            f'      </div>\n    </section>')


def snapshot(project, times, out):
    """real frames from the built composition (cards that have no mp4 yet show their still)"""
    pub = os.path.join(project, "public")
    snaps = os.path.join(pub, "snapshots")
    shutil.rmtree(snaps, ignore_errors=True)
    at = ",".join(f"{t:.3f}" for t in times)
    hf(["snapshot", "--at", at, "--no-end", "--describe", "false"], pub)
    files = sorted(glob.glob(os.path.join(snaps, "frame-*.png")), key=lambda f: int(re.search(r"frame-(\d+)", f).group(1)))
    if len(files) != len(times):
        raise SystemExit(f"snapshot returned {len(files)} frames for {len(times)} times")
    os.makedirs(out, exist_ok=True)
    names = []
    for k, f in enumerate(files):
        name = f"f{k:03d}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f, "-vf", "scale=540:960:flags=lanczos", "-q:v", "4",
                        os.path.join(out, name)], check=True)
        names.append(name)
    return names


def main():
    project = project_arg()
    E = load_edit(project)
    TL = timeline(project)
    B.setup(E, TL)
    words = json.load(open(os.path.join(project, "words.json")))
    version = int(sys.argv[sys.argv.index("--version") + 1]) if "--version" in sys.argv else 1
    ps = []
    for k, (a, b) in enumerate(panels(E, TL)):
        d = describe(E, TL, a, b, words)
        d.update(id=f"p{k + 1:02d}", n=k + 1, t0=a, t1=b, tc0=tc(a), tc1=tc(b), dur=f"{b - a:.1f}s")
        d["needs"] = [t for bid, t in E.NEEDS if bid == d["id"]]
        d["generated"] = [t for bid, t in E.GENERATED if bid == d["id"]]
        ps.append(d)
    if "--list" in sys.argv:            # the beat ids, before any frames exist (for NEEDS and GENERATED)
        for p in ps:
            print(f"  {p['id']} {p['tc0']}-{p['tc1']} {p['label']:<34} {p['line'][:70]}")
        return
    ids = {p["id"] for p in ps}
    stray = [bid for bid, _ in list(E.NEEDS) + list(E.GENERATED) if bid not in ids]
    if stray:
        raise SystemExit(f"NEEDS/GENERATED name beats that don't exist: {stray} (beats are p01-p{len(ps):02d}; run --list to see them)")
    sb = os.path.join(project, "storyboard")
    fdir = os.path.join(sb, "frames")
    times = [t for p in ps for t in p["frames"]]
    if "--no-frames" not in sys.argv:
        names = snapshot(project, times, fdir)
    else:                               # reuse the frames from the last run (same beats, same times)
        names = sorted(os.listdir(fdir))[:len(times)] if os.path.isdir(fdir) else []
        if len(names) < len(times):
            raise SystemExit("--no-frames reuses the last run's frames and there aren't enough: run it without "
                             "--no-frames (or --list for the beat ids only)")
    if True:
        k = 0
        for p in ps:
            p["imgs"] = [{"src": f"frames/{names[k + i]}", "t": tc(t)} for i, t in enumerate(p["frames"])]
            k += len(p["frames"])
    page = open(os.path.join(KIT, "storyboard", "page.html")).read()
    cards = sum(1 for p in ps if p["kind"] in ("light", "dark"))
    eyebrow = f"Storyboard · v{version} · {tc(E.TOTAL)} · {len(ps)} beats · {cards} cards"
    fill = {"__TITLE__": html.escape(E.TITLE), "__EYEBROW__": html.escape(eyebrow), "__TOTAL__": tc(E.TOTAL),
            "__STRIP__": strip_html(E, ps), "__TICKS__": ticks_html(E),
            "__MARKS__": html.escape(" · ".join(f"{m} {tc(t)}" for t, m in E.SOUND.get("marks", [])) or "none"),
            "__BEATS__": "\n".join(beat_html(p) for p in ps), "__NEEDS__": needs_html(E), "__THEME__": theme_css(E.S, sb)}
    for k, v in fill.items():
        page = page.replace(k, v)
    with open(os.path.join(sb, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    files = sorted(f"{d}/{n}" for d in ("frames", "fonts") for n in os.listdir(os.path.join(sb, d)))
    json.dump(files, open(os.path.join(sb, "files.json"), "w"), indent=1)
    print(f"storyboard v{version}: {len(ps)} beats, {len(times)} frames -> {sb}/index.html (+ {len(files)} files, listed in files.json)")
    for p in ps:
        print(f"  {p['id']} {p['tc0']}-{p['tc1']} {p['label']:<34} {len(p['frames'])} frames  {p['line'][:60]}")
    # the message that goes with the link: what the creator has to send, what was generated
    print("NEEDS FROM YOU:" if E.NEEDS else "NEEDS FROM YOU: nothing")
    for bid, t in E.NEEDS:
        print(f"  {bid} {t}")
    for bid, t in E.GENERATED:
        print(f"GENERATED: {bid} {t}")


def theme_css(S, sb):
    """the page in the creator's own fonts and colours: light ground in light mode, dark ground in dark mode"""
    C, F = S["colors"], S["fonts"]
    stack = lambda f, g: f"'{f['family']}', {g}"                                          # noqa: E731
    common = (f"--font-display: {stack(F['display'], 'Georgia, serif')}; --display-style: {'italic' if F['display']['italic'] else 'normal'}; "
              f"--display-weight: {F['display']['weight']}; --font-text: {stack(F['text'], 'system-ui, sans-serif')}; "
              f"--font-mono: {stack(F['mono'], 'ui-monospace, monospace')};")
    light = (f"--paper: {C['light']}; --sheet: color-mix(in srgb, {C['light']} 80%, #ffffff); --ink: {C['ink']}; "
             f"--muted: {C['muted_light']}; --hair: {C['hair_light']}; --accent: {C['accent_on_light']}; "
             f"--accent-line: {C['accent_on_light']}; --seg-foot: {C['muted_light']}; "
             f"--seg-light: color-mix(in srgb, {C['light']} 86%, {C['ink']}); --seg-dark: {C['dark']}; --focus: {C['accent_on_light']};")
    dark = (f"--paper: {C['dark']}; --sheet: color-mix(in srgb, {C['dark']} 88%, {C['light']}); --ink: {C['light']}; "
            f"--muted: {C['muted_dark']}; --hair: {C['hair_dark']}; --accent: {C['accent']}; --accent-line: {C['accent']}; "
            f"--seg-foot: {C['muted_dark']}; --seg-light: {C['light']}; "
            f"--seg-dark: color-mix(in srgb, {C['dark']} 65%, {C['light']}); --focus: {C['accent']}; color-scheme: dark;")
    src = os.path.dirname(S["_path"]) if S.get("_path") else ST.STYLE_DIR
    faces = ""
    if os.path.exists(os.path.join(src, "brand.css")):
        faces = "\n".join(re.findall(r"@font-face \{[^}]*\}", open(os.path.join(src, "brand.css")).read()))
        shutil.copytree(os.path.join(src, "fonts"), os.path.join(sb, "fonts"), dirs_exist_ok=True)
    else:
        os.makedirs(os.path.join(sb, "fonts"), exist_ok=True)
    return (f"{faces}\n:root {{ {common} {light} }}\n"
            f"@media (prefers-color-scheme: dark) {{ :root:not([data-theme=\"light\"]) {{ {dark} }} }}\n"
            f":root[data-theme=\"dark\"] {{ {dark} }}")


def needs_html(E):
    """Always answered at the top of the board:
    edit.NEEDS = [("p06", "what to send for that beat"), ...]: assets only the creator has (their B-roll, screen
    recordings, screenshots of their own tools). Empty -> the page says nothing is needed.
    edit.GENERATED = [("p04", "what a connected generator made, which model"), ...]: tagged so they can cut it."""
    if E.NEEDS:
        items = "".join(f'<li><a href="#{b}">{b}</a> {html.escape(t)}</li>' for b, t in E.NEEDS)
        out = f'<h2>What I need from you</h2><ol>{items}</ol>'
        cls = "needs"
    else:
        out = '<h2>What I need from you</h2><p>Nothing. Every clip and screenshot in this cut is in hand.</p>'
        cls = "needs none"
    if E.GENERATED:
        items = "".join(f'<li><a href="#{b}">{b}</a> {html.escape(t)}</li>' for b, t in E.GENERATED)
        out += f'<h2>Generated for this video</h2><ol>{items}</ol><p>Leave a note on the beat to cut any of them.</p>'
    return f'<aside class="{cls}">{out}</aside>'


if __name__ == "__main__":
    main()
