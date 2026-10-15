#!/usr/bin/env python3
"""Preview: the approval stops of the fast lane, built in seconds, so the creator signs off on the cut and the hook
before anything else gets made, and the start page in front of them.

  start      intake.json (intake.py) -> approvals/start/: the first page after the takes are in (storyboard/start.html).
             Every take in order with its poster, length, recording time, first line (from words.json, once the first
             transcript is done) and why it was re-encoded, if it was; the three modes, each with its example clip
             (storyboard/examples/<mode>.mp4) and the intake's pick marked recommended; the styles in the creator's
             home (HOME/style/ and HOME/packs/<name>/), each with a frame: the pack's board/frame.jpg, else
             storyboard/examples/style-<name>.jpg, else a plain card with its name; what to send. The creator answers
             in the chat (mode, style, links and files); a note on any card reaches it like a note on a stop.
  first-cut  assets/aroll.mp4 + assets/voice.wav -> approvals/first-cut/first-cut.mp4: 720x1280 H.264 (the Mac's
             hardware encoder, else libx264 veryfast), AAC 128k, about 1.1 Mb/s (under 12 MB for 75 s), no captions:
             it is a pace check. Its page: the video, the length, every line with its time, the dead-air check (any
             pause of 0.25 s or more inside the video, silencedetect -35 dB d=0.12 on the voice), "leave a note or
             say go".
  hook       render.py <project> <name> --hook renders the hook and writes its stop with page() below.
Each stop is a folder holding index.html and files.json (every file the page needs, to publish with it). Publish it
as a Claude artifact with comments (capabilities {"comments": {"composer_only": true}}), or review it locally with
python3 storyboard/serve.py <project>/approvals/<stop> (notes land in notes.json there; "go" arrives as beat "all").
Run: PY pipeline/preview.py <project> start|first-cut
"""
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS, KIT, load_edit  # noqa: E402

PHONE = (720, 1280)
VIDEO_KBPS, AUDIO_KBPS = 1000, 128            # about 1.1 Mb/s together: 10.6 MB for 75 s
SILENCE_DB, SILENCE_MIN, DEAD_AIR = -35, 0.12, 0.25


def tc(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


_ENC = {}


def has_encoder(name):
    if name not in _ENC:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        _ENC[name] = re.search(rf"\s{re.escape(name)}\s", out) is not None
    return _ENC[name]


def phone_mp4(video, audio, out, length, size=PHONE, kbps=VIDEO_KBPS):
    """video scaled to size + audio (padded with silence to the picture's length), H.264 + AAC, faststart.
    Returns the encoder used: the hardware one where this ffmpeg has it, else libx264 veryfast (capped CRF)"""
    W, H = size
    tries = []
    if has_encoder("h264_videotoolbox"):
        tries.append(["-c:v", "h264_videotoolbox", "-b:v", f"{kbps}k", "-maxrate", f"{kbps * 5 // 4}k",
                      "-bufsize", f"{kbps * 2}k", "-profile:v", "high"])
    tries.append(["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-maxrate", f"{kbps}k",
                  "-bufsize", f"{kbps * 2}k", "-profile:v", "high"])
    tmp = out + ".part.mp4"
    err = ""
    for enc in tries:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
                            "-vf", f"scale={W}:{H}:flags=bicubic,format=yuv420p", *enc, "-g", "60",
                            "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-ar", "48000", "-ac", "2", "-af", "apad",
                            "-t", f"{length:.4f}", "-movflags", "+faststart", tmp], capture_output=True, text=True)
        if r.returncode == 0:
            os.replace(tmp, out)
            return enc[1]
        err = r.stderr[-800:]
    sys.exit(f"could not encode the phone file:\n{err}")


def poster(video, out, at=0.5):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", video, "-frames:v", "1", "-q:v", "4", out],
                   check=True)


def dead_air(wav):
    """[(start, end)] of every pause of DEAD_AIR s or more between the first and the last sound of the file
    (silencedetect at -35 dB, d=0.12); the silence before the first sound and after the last is not inside the video"""
    r = subprocess.run(["ffmpeg", "-nostats", "-i", wav, "-af", f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[0-9.]+)", r)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[0-9.]+)", r)]
    end = duration(wav) - 0.01
    return [(round(a, 3), round(b, 3)) for a, b in zip(starts, ends) if a > 0.01 and b < end and b - a >= DEAD_AIR]


def starts(keep):
    out, t = [], 0.0
    for s, e in keep:
        out.append(t)
        t += e - s
    return out


def words_on_cut(E, words):
    """do these words belong to this cut? each word's source time must map onto its output time through KEEP
    (words.py writes both); words from the whole take, before the cut, don't"""
    O = starts(E.KEEP)
    ok = 0
    for w in words:
        k = [i for i, (s, e) in enumerate(E.KEEP) if s - 0.02 <= w.get("src", -1) <= e + 0.02]
        ok += bool(k) and abs(O[k[0]] + w["src"] - E.KEEP[k[0]][0] - w["start"]) < 0.06
    return bool(words) and ok >= 0.9 * len(words)


def sentences(words, a=0.0, b=None):
    """[(start, text)]: the words from a to b, one line per sentence; a sentence that runs on past b ends in ' ...'"""
    out, cur, runs_on = [], [], False
    for w in words:
        if w["start"] < a - 1e-6:
            continue
        if b is not None and w["start"] >= b - 1e-6:
            runs_on = bool(cur)
            break
        cur.append(w)
        if w["text"].rstrip("\"')]").endswith((".", "?", "!")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    text = [re.sub(r"\s+([%,.!?;:])", r"\1", " ".join(w["text"] for w in ln)) for ln in out]
    if runs_on:
        text[-1] += " ..."
    return [(ln[0]["start"], t) for ln, t in zip(out, text)]


LEAD_IN = 0.2       # whisper's word starts run late: a tap on a line plays from a little before it


def lines_html(lines, missing=None):
    if missing:
        return f'        <li class="quiet">{html.escape(missing)}</li>'
    out = []
    for k, (t, text) in enumerate(lines):
        at = max(0.0, t - LEAD_IN)
        out.append(f'        <li id="l{k + 1:02d}" data-t="{at:.3f}" data-comment-target>'
                   f'<button class="t" type="button" data-t="{at:.3f}" aria-label="Play from {tc(t)}">{tc(t)}</button>'
                   f'<span class="txt">{html.escape(text)}</span>'
                   f'<button class="note" type="button" data-note>Note</button></li>')
    return "\n".join(out)


def facts_html(facts):
    return "".join(f"<dt>{html.escape(k)}</dt><dd{' class=' + chr(34) + 'warn' + chr(34) if warn else ''}>{v}</dd>"
                   for k, v, warn in facts)


def pace_fact(gaps):
    """the dead-air row: (label, html, is it a warning)"""
    if not gaps:
        return ("Pace", f"No pause of {DEAD_AIR} s or more inside the video.", False)
    items = "".join(f'<li><button class="t" type="button" data-t="{a:.3f}">{tc(a)}</button> {b - a:.2f} s</li>'
                    for a, b in gaps)
    return ("Pace", f"{len(gaps)} pause{'s' if len(gaps) > 1 else ''} of {DEAD_AIR} s or more:<ul>{items}</ul>", True)


def page(folder, E, video, *, title, eyebrow, head, how, go, facts, lines, lines_head="Lines", foot="", missing=None,
         poster_name="poster.jpg"):
    """write <folder>/index.html (KIT/storyboard/approval.html filled in, the pack's fonts and colours) and
    files.json (every file it needs)"""
    import build as B
    import storyboard as SB
    S = B.project_style(E)
    with open(os.path.join(KIT, "storyboard", "approval.html"), encoding="utf-8") as fh:
        tpl = fh.read()
    fill = {"__TITLE__": html.escape(title), "__EYEBROW__": html.escape(eyebrow), "__HEAD__": html.escape(head),
            "__HOW__": how, "__GO__": html.escape(go), "__VIDEO__": video, "__POSTER__": poster_name,
            "__FACTS__": facts_html(facts), "__LINES_HEAD__": html.escape(lines_head),
            "__LINES__": lines_html(lines, missing), "__FOOT__": html.escape(foot), "__THEME__": SB.theme_css(S, folder)}
    for k, v in fill.items():
        tpl = tpl.replace(k, v)
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(tpl)
    files = [video, poster_name] + sorted(f"fonts/{n}" for n in os.listdir(os.path.join(folder, "fonts")))
    with open(os.path.join(folder, "files.json"), "w") as fh:
        json.dump(files, fh, indent=1)
    return files


def first_cut(project):
    """the first-cut stop: approvals/first-cut/first-cut.mp4 + index.html + files.json. Returns the mp4's path."""
    t0 = time.time()
    E = load_edit(project)
    aroll, voice = (os.path.join(project, "assets", f) for f in ("aroll.mp4", "voice.wav"))
    for f in (aroll, voice):
        if not os.path.exists(f):
            sys.exit(f"{f} is missing: run PY pipeline/cut.py {project} first")
    folder = os.path.join(project, "approvals", "first-cut")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, "first-cut.mp4")
    length = duration(aroll)
    enc = phone_mp4(aroll, voice, out, length)
    poster(out, os.path.join(folder, "poster.jpg"), min(0.5, length / 2))
    gaps = dead_air(voice)
    wp = os.path.join(project, "words.json")
    words = []
    if os.path.exists(wp):
        with open(wp, encoding="utf-8") as fh:
            words = json.load(fh)
    fresh = words_on_cut(E, words)
    lines = sentences(words) if fresh else []
    straight = sum(1 for x in (getattr(E, "J_LEADS", None) or []) if x == 0)
    facts = [("Length", f"{tc(length)} ({length:.1f} s), {len(E.KEEP)} pieces"
              + (f", {straight} straight cuts inside lines" if straight else ""), False),
             pace_fact(gaps),
             ("On screen", "Nothing yet: no captions, type or effects. This stop is the takes and the pace.", False),
             ("Sound", "Your voice alone.", False)]
    page(folder, E, "first-cut.mp4", title=f"{E.TITLE} First Cut", eyebrow=f"First cut · {tc(length)} · {len(lines)} lines",
         head=E.TITLE,
         how=("The cut as it stands: the takes I kept, the pauses out, nothing on top yet. Watch it on your phone with "
              "the sound on. <b>Leave a note</b> on any line, or <b>say go</b> and I build the hook."),
         go="Looks good: build the hook", facts=facts, lines=lines,
         foot="A 720x1280 phone file of the cut, without captions or effects. Tap a time to jump there.",
         missing=None if fresh else f"The lines show once words.py has run on this cut: PY pipeline/words.py {project}")
    size = os.path.getsize(out) / 1e6
    print(f"first cut: {out}  {size:.1f} MB  {length:.2f} s  {enc}  built in {time.time() - t0:.1f} s")
    print("pace: " + ("no pause of 0.25 s or more inside the video" if not gaps else
                      ", ".join(f"{tc(a)} {b - a:.2f} s" for a, b in gaps)))
    if not fresh:
        print(f"WARNING: words.json doesn't match this cut: run PY pipeline/words.py {project}, then this again")
    print(f"page: {folder}/index.html (+ files.json): publish it with comments, or "
          f"python3 {os.path.join(KIT, 'storyboard', 'serve.py')} {folder}")
    return out


# ---------------------------------------------------------------- the start page
EXAMPLES = os.path.join(KIT, "storyboard", "examples")     # <mode>.mp4 and style-<pack>.jpg (dev/start_examples.py)
MODES = (("hifi", "Hi-fi", "Produced, for a camera on a tripod: full-screen data cards and type behind you."),
         ("lofi", "Lo-fi", "For a selfie in hand: real screenshots over you and word-by-word captions."),
         ("showcase", "Showcase", "For showing off: a different hand-built motion graphic on every line."))
STYLE_LINES = {"harbor": "The default, tutorials and builds.", "film": "Stories, slower, a film grade.",
               "signal": "Proof, results and news, fastest.", "terminal": "Builds and screen recordings, mono captions."}
FIRST_LINE_WORDS = 14       # a take's first line stops at its first sentence end, or after this many words
EXAMPLE_POSTER = {"hifi": 1.0, "lofi": 3.0, "showcase": 1.0}   # each example's poster (s into it): what shows
                                                                # before it plays (a card, the screenshot, the hook)
SENTENCE_END = (".", "?", "!")


def length_label(seconds):
    """61.233 -> '1:01' (to the nearest second)"""
    s = int(float(seconds or 0) + 0.5)
    return f"{s // 60}:{s % 60:02d}"


def recorded_label(iso, tz=None, now=None):
    """'2026-10-13T19:02:11Z' -> 'Oct 13, 12:02 pm' in this computer's time zone (tz in a test), with the year only
    when it is not this year; '' when there is no time or it can't be read"""
    if not iso:
        return ""
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)              # a container's creation time is UTC
    t = t.astimezone(tz)
    now = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(tz)
    day = f"{t:%b} {t.day}" + (f", {t.year}" if t.year != now.year else "")
    return f"{day}, {t.hour % 12 or 12}:{t:%M} {'am' if t.hour < 12 else 'pm'}"


def first_line(words, start, duration, cap=FIRST_LINE_WORDS):
    """a take's first line: its words (src, the time in the joined source, in [start, start + duration)) up to the
    first sentence end or cap words, with ' ...' when the take goes on past the cap; '' when it has no words"""
    mine = sorted((w for w in words if start - 1e-6 <= w.get("src", w.get("start", -1.0)) < start + duration - 1e-6),
                  key=lambda w: w.get("src", w.get("start", 0.0)))
    out, ended = [], False
    for w in mine:
        out.append(w["text"])
        ended = w["text"].rstrip("\"')]”’").endswith(SENTENCE_END)
        if ended or len(out) == cap:
            break
    text = re.sub(r"\s+([%,.!?;:])", r"\1", " ".join(out)).strip()
    return text + (" ..." if text and not ended and len(mine) > len(out) else "")


def encode_note(take, plan):
    """why this take was re-encoded on its way into the joined source; '' when it went in untouched. A join that
    re-encodes ("encode") re-encodes every take: an HDR reason belongs to a take only when it was shot in HDR, and a
    take of another size says so"""
    plan = plan or {}
    if plan.get("mode") != "encode":
        return ""
    why = [w for w in plan.get("why") or [] if take.get("hdr") or "HDR" not in w]
    size, want = take.get("size"), plan.get("size")
    if size and want and list(size)[:2] != list(want)[:2]:
        why.append(f"{size[0]}x{size[1]}, fit to {want[0]}x{want[1]}")
    return "; ".join(why) or "to match the other takes"


def home_packs():
    """[(name, folder, is the default)]: the creator's default pack (HOME/style/) when it holds a style.json, then
    every pack in HOME/packs/ in name order (pack.py names())"""
    import pack as PK
    out = []
    for n in PK.names():
        d = PK.default_dir() if n == PK.DEFAULT_NAMES[0] else os.path.join(PK.home(), "packs", n)
        if os.path.exists(os.path.join(d, "style.json")):
            out.append((n, d, n == PK.DEFAULT_NAMES[0]))
    return out


def pack_line(name, d):
    """one line on what a pack is for: the four shipped packs say it here; any other pack, the first sentence of its
    STYLE.md"""
    if name in STYLE_LINES:
        return STYLE_LINES[name]
    p = os.path.join(d, "STYLE.md")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            for part in fh.read().split("\n\n"):
                b = " ".join(part.split())
                if b and not b.startswith(("#", "-", "|", "*", ">")):
                    one = re.split(r"(?<=[.!?])\s", b, maxsplit=1)[0]
                    return one if len(one) <= 140 else one[:137].rsplit(" ", 1)[0] + " ..."
    return "One of your packs."


def style_frame(name, d, examples):
    """the picture for a pack's card: its own board/frame.jpg, else its board's hi-fi frame (drawn in its own colours,
    so a recolored pack shows itself), else the kit's example frame, else None (a plain card)"""
    for p in (os.path.join(d, "board", "frame.jpg"), os.path.join(d, "board", "img", "hifi.jpg"),
              os.path.join(examples, f"style-{name}.jpg")):
        if os.path.exists(p):
            return p
    return None


def thumb(video, out, at):
    """one frame of a video, 640 px tall: an example clip's poster, or a take's when the intake left it none. True
    when it was written"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, at):.3f}", "-i", video, "-frames:v", "1",
                        "-vf", "scale=-2:640", "-q:v", "4", out], capture_output=True)
    return r.returncode == 0 and os.path.exists(out)


def take_poster(k, take, project, folder):
    """the take's poster as a path inside the page folder: the intake's (approvals/start/posters/), a copy of one kept
    anywhere else, or one made now from the take; None when there is no picture"""
    src = os.path.join(project, take["poster"]) if take.get("poster") else None
    if src and os.path.isfile(src):
        rel = os.path.relpath(os.path.abspath(src), folder)
        if not rel.startswith(".."):
            return rel.replace(os.sep, "/")
        os.makedirs(os.path.join(folder, "posters"), exist_ok=True)
        name = f"posters/{k + 1:02d}{os.path.splitext(src)[1].lower() or '.jpg'}"
        shutil.copyfile(src, os.path.join(folder, name))
        return name
    clip = os.path.join(project, take["file"]) if take.get("file") else None
    if clip and os.path.isfile(clip):
        os.makedirs(os.path.join(folder, "posters"), exist_ok=True)
        name = f"posters/{k + 1:02d}.jpg"
        if thumb(clip, os.path.join(folder, name), min(1.0, float(take.get("duration") or 2) / 2)):
            return name
    return None


def take_html(k, take, poster_src, line, note):
    e = html.escape
    size = list(take.get("size") or [])
    w, h = size[:2] if len(size) >= 2 else (9, 16)
    ar = f"--ar: {int(w)} / {int(h)}"
    pic = (f'<img class="thumb" src="{e(poster_src)}" alt="The start of take {k + 1}" loading="lazy" style="{ar}">'
           if poster_src else f'<div class="thumb" style="{ar}"></div>')
    meta = [f'<span class="len">{length_label(take.get("duration"))}</span>']
    when = recorded_label(take.get("recorded"))
    if when:
        meta.append(f"<span>Recorded {e(when)}</span>")
    body = [f'<div class="head"><span class="n">{k + 1:02d}</span><span class="name">'
            f'{e(os.path.basename(str(take.get("name") or take.get("file") or f"Take {k + 1}")))}</span></div>',
            f'<div class="meta">{"".join(meta)}</div>']
    if line:
        body.append(f'<p class="line">“{e(line)}”</p>')
    if note:
        body.append(f'<p class="enc">re-encoded: <span>{e(note)}</span></p>')
    body.append(f'<button class="note" type="button" data-note aria-label="Note on take {k + 1}">Note</button>')
    return (f'      <li class="card take" id="take-{k + 1:02d}" data-comment-target data-ask="A note on this take">\n'
            f'        {pic}\n        <div class="body">{"".join(body)}</div>\n      </li>')


def mode_html(key, name, line, clip, poster_src, rec_why):
    """one mode's card; rec_why is the intake's reason when this is the mode it recommends, else None"""
    e = html.escape
    if clip:
        poster_attr = f' poster="{poster_src}"' if poster_src else ""
        media = (f'<video class="clip" src="{clip}"{poster_attr} muted loop playsinline autoplay preload="metadata" '
                 f'width="540" height="960" aria-label="An example of {name}, made with a stand-in"></video>')
    else:
        media = '<div class="clip noclip">No example yet</div>'
    rec = rec_why is not None
    what = [f"<h3>{name}</h3>"] + (['<span class="badge">Recommended</span>'] if rec else []) + [f"<p>{e(line)}</p>"]
    if rec and rec_why:
        what.append(f'<p class="why">{e(rec_why)}</p>')
    return (f'      <article class="card mode{" rec" if rec else ""}" id="mode-{key}" data-comment-target '
            f'data-ask="A note on {name}">\n        {media}\n        <div class="what">{"".join(what)}</div>\n'
            f'        <button class="note" type="button" data-note aria-label="Note on {name}">Note</button>\n'
            f'      </article>')


def style_html(name, frame_src, line, default):
    e = html.escape
    label = e(name.replace("-", " ").replace("_", " ").title())
    pic = (f'<img class="frame" src="{e(frame_src)}" alt="{label} on the stand-in" loading="lazy" width="540" height="960">'
           if frame_src else f'<div class="frame plain" aria-hidden="true">{label}</div>')
    tag = '<span class="tag">Default</span>' if default else ""
    return (f'      <article class="card style" id="style-{e(name)}" data-comment-target data-ask="A note on {label}">\n'
            f'        {pic}\n        <div class="text"><div class="name"><h3>{label}</h3>{tag}</div>'
            f'<p>{e(line)}</p></div>\n'
            f'        <button class="note" type="button" data-note aria-label="Note on {label}">Note</button>\n'
            f'      </article>')


def ignored_names(items):
    """the files the intake left out, as names only (never a full path)"""
    out = []
    for x in items or []:
        if isinstance(x, dict):
            x = x.get("name") or x.get("file") or x.get("path") or ""
        if isinstance(x, str) and x:
            out.append(os.path.basename(x))
    return out


def start(project, examples=None):
    """the start page: approvals/start/index.html + files.json from intake.json (and words.json once it exists).
    Copies in what the page shows: the example clips (examples/ + a poster each), a frame per style (styles/), the
    pack's fonts; the take posters stay where the intake put them (posters/). Returns the page's path."""
    import build as B
    import storyboard as SB
    examples = examples or EXAMPLES
    ip = os.path.join(project, "intake.json")
    if not os.path.exists(ip):
        sys.exit(f"{ip} is missing: run PY pipeline/intake.py <slug> <takes> first, it writes the start page's facts")
    with open(ip, encoding="utf-8") as fh:
        I = json.load(fh)
    folder = os.path.join(project, "approvals", "start")
    os.makedirs(folder, exist_ok=True)
    words = []
    wp = os.path.join(project, "words.json")
    if os.path.exists(wp):
        with open(wp, encoding="utf-8") as fh:
            words = json.load(fh)
    files = []

    takes = I.get("takes") or []
    rows, lines = [], 0
    for k, t in enumerate(takes):
        poster_src = take_poster(k, t, project, folder)
        if poster_src:
            files.append(poster_src)
        line = first_line(words, float(t.get("start") or 0.0), float(t.get("duration") or 0.0)) if words else ""
        lines += bool(line)
        rows.append(take_html(k, t, poster_src, line, encode_note(t, I.get("plan"))))
    total = sum(float(t.get("duration") or 0.0) for t in takes)
    sub = (f"One take, {length_label(total)}." if len(takes) == 1 else
           f"{len(takes)} takes, {length_label(total)} in all, joined in recording order." if takes else "No takes.")
    if takes and not lines:
        sub += " The first line of each take shows here once the transcript is done."
    left_out = ignored_names(I.get("ignored"))
    if left_out:
        sub += f" Left out, not a video: {', '.join(left_out)}."

    rec = I.get("recommended") or {}
    cards = []
    for key, name, line in MODES:
        clip = poster_src = None
        src = os.path.join(examples, f"{key}.mp4")
        if os.path.isfile(src):
            os.makedirs(os.path.join(folder, "examples"), exist_ok=True)
            clip = f"examples/{key}.mp4"
            shutil.copyfile(src, os.path.join(folder, clip))
            files.append(clip)
            if thumb(src, os.path.join(folder, "examples", f"{key}.jpg"), EXAMPLE_POSTER.get(key, 1.0)):
                poster_src = f"examples/{key}.jpg"
                files.append(poster_src)
        cards.append(mode_html(key, name, line, clip, poster_src, (rec.get("why") or "") if rec.get("mode") == key else None))

    styles = []
    packs = home_packs()
    for name, d, default in packs:
        frame = style_frame(name, d, examples)
        frame_src = None
        if frame:
            os.makedirs(os.path.join(folder, "styles"), exist_ok=True)
            frame_src = f"styles/{name}.jpg"
            shutil.copyfile(frame, os.path.join(folder, frame_src))
            files.append(frame_src)
        styles.append(style_html(name, frame_src, pack_line(name, d), default))
    styles_sub = ("Each style is a pack in your home folder. Any style works with any mode." if packs else
                  "You have no style yet. Say “set up my style” in the chat first.")

    S = B.project_style(types.SimpleNamespace(PROJECT=project))
    title = I.get("title") or str(I.get("slug") or os.path.basename(project)).replace("-", " ").title()
    with open(os.path.join(KIT, "storyboard", "start.html"), encoding="utf-8") as fh:
        tpl = fh.read()
    fill = {"__TITLE__": html.escape(f"{title} Start"), "__HEAD__": html.escape(title),
            "__TAKES_SUB__": f'    <p class="sub">{html.escape(sub)}</p>', "__TAKES__": "\n".join(rows),
            "__MODES__": "\n".join(cards), "__STYLES_SUB__": html.escape(styles_sub), "__STYLES__": "\n".join(styles),
            "__THEME__": SB.theme_css(S, folder)}
    for k, v in fill.items():
        tpl = tpl.replace(k, v)
    page_path = os.path.join(folder, "index.html")
    with open(page_path, "w", encoding="utf-8") as fh:
        fh.write(tpl)
    files += [f"fonts/{n}" for n in os.listdir(os.path.join(folder, "fonts"))]
    with open(os.path.join(folder, "files.json"), "w") as fh:
        json.dump(sorted(set(files)), fh, indent=1)
    picked = rec.get("mode") or "none"
    print(f"start page: {len(takes)} take{'s' if len(takes) != 1 else ''} ({length_label(total)}), "
          f"{lines} first line{'s' if lines != 1 else ''}, recommended {picked}, {len(packs)} style"
          f"{'s' if len(packs) != 1 else ''}")
    print(f"page: {page_path} (+ files.json): publish it with comments, or "
          f"python3 {os.path.join(KIT, 'storyboard', 'serve.py')} {folder}")
    return page_path


STOPS = {"start": start, "first-cut": first_cut}


def main():
    if len(sys.argv) < 3 or sys.argv[2] not in STOPS or not os.path.isdir(os.path.expanduser(sys.argv[1])):
        sys.exit(__doc__)
    STOPS[sys.argv[2]](os.path.abspath(os.path.expanduser(sys.argv[1])))


if __name__ == "__main__":
    main()
