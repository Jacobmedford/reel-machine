#!/usr/bin/env python3
"""Render: build the composition, lint it, render it, check that its graphics animated (animcheck.py: a render worker
that lost its script renders the static page with no error), QA it (cuts, lip sync, loudness), make the phone copy
and, when both pass, deliver both next to the source clip. Refuses to render while any card is still a placeholder.
Run: PY pipeline/render.py <project> [name] [--no-deliver]   -> <project>/renders/<name>.mp4 (default <slug>-v1)
     PY pipeline/render.py <project> [name] --hook   -> only the hook, draft quality, in well under a minute:
        renders/<name>-hook.mp4 and its approval stop approvals/hook/ (index.html + files.json). The hook ends at
        HOOK_END in edit.py, else at the end of the first sentence plus HOLD (hook.py). No QA, nothing delivered.
     PY pipeline/render.py <project> [name] --pieces [--jobs N] [--strict] [--verify] [--no-deliver]
        -> the same build, lint, QA and delivery around a picture joined from cached beat-aligned pieces (pieces.py,
        cache in work/render-pieces/): only the pieces a note touched render again (--jobs at a time, default 3).
        Then the seam checks (a FAIL delivers nothing), --verify (each seam against a continuous render, slow), the
        animation check inside every piece that lacks its pass (a piece that fails is set aside in rejected/ and
        rendered once more; failing twice delivers nothing), QA and delivery, then a prune of the piece cache (also
        after a gate failed: old plans, old set-aside pieces, PNG leftovers, unused pieces over
        REEL_MACHINE_PIECES_BUDGET MiB, default 1024). --strict: an effect that reaches shared layers keys into every
        piece. One line of times at the end.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS, HF, PY, hf, load_edit, project_arg, timeline  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
VALUED = ("--jobs",)                                  # options followed by a value


def positional(args):
    """the arguments that are not options (an option's value, as in --jobs 2, is not one)"""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in VALUED:
            skip = True
        elif not a.startswith("--"):
            out.append(a)
    return out


def preflight(project, E):
    """what every full render does first: the finished card mp4s in, no placeholder card, the footage and the mix
    present, the build, the HyperFrames lint. Returns public/"""
    pub = os.path.join(project, "public")
    from build import sync_cards                      # bring finished card mp4s in before checking for them
    sync_cards(E, project, pub)
    missing = [c[0] for c in E.CARDS if not os.path.exists(os.path.join(pub, c[1]))]
    if missing:
        sys.exit(f"cards not rendered yet: {missing}")
    for f in ("clean.mp4", "master.wav"):
        if not os.path.exists(os.path.join(pub, f)):
            sys.exit(f"public/{f} missing (clean.mp4 = assets/aroll.mp4; master.wav from mix.py)")
    subprocess.run([PY, os.path.join(HERE, "build.py"), project], check=True)
    chk = hf(["check"], pub)
    print(chk.stdout[-600:])
    return pub


def main():
    project = project_arg()
    E = load_edit(project)
    rest = positional(sys.argv[2:])
    name = rest[0] if rest else f"{os.path.basename(project)}-v1"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or ".." in name:
        sys.exit(f"'{name}' can't name a render: use letters, numbers, - and _ (like my-reel-v1)")
    if "--hook" in sys.argv:
        return render_hook(project, E, name)
    if "--pieces" in sys.argv:
        return render_pieces(project, E, name)
    pub = preflight(project, E)
    os.makedirs(os.path.join(project, "renders"), exist_ok=True)
    out = os.path.join("..", "renders", f"{name}.mp4")
    hf(["render", "-q", "delivery", "--quiet", "-o", out], pub)
    shutil.rmtree(os.path.join(pub, "snapshots"), ignore_errors=True)
    # the renderer's own audio pass can come out ~0.7 dB under the mix on graphics-heavy edits: lay
    # the exact master.wav over the rendered picture (video copied untouched, both start at 0, so sync can't move)
    final = os.path.join(project, "renders", f"{name}.mp4")
    tmp = final.replace(".mp4", ".mix.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", final, "-i", os.path.join(pub, "master.wav"), "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest",
                    "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, final)
    ac = subprocess.run([PY, os.path.join(HERE, "animcheck.py"), project, os.path.join("renders", f"{name}.mp4")])
    if ac.returncode == 1:
        sys.exit("The animation check failed: part of the render did not animate (above). Render again. "
                 "Nothing was delivered.")
    if ac.returncode:
        sys.exit("The animation check could not run (above): fix that and run it again "
                 f"(PY pipeline/animcheck.py {project} renders/{name}.mp4). Nothing was delivered.")
    qa = subprocess.run([PY, os.path.join(HERE, "qa.py"), project, os.path.join("renders", f"{name}.mp4"), "--phone"])
    if qa.returncode:
        sys.exit("QA failed: fix what it reports, render again. Nothing was delivered.")
    if "--no-deliver" not in sys.argv:
        deliver(E, name, final)


def render_pieces(project, E, name):
    """--pieces: the plain render's gates around a picture joined from cached beat-aligned pieces (pieces.py). Every
    piece whose cache meta lacks the animation check's pass (a piece rendered now, or one rendered by pieces.py on its
    own) gets the check inside its own worker runs; a piece that fails it is set aside and rendered once more. Reused
    pieces that passed before are not checked again."""
    import animcheck as AC
    import pieces as PC
    a = sys.argv
    jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 3
    T = dict(build=0.0, render=0.0, assemble=0.0, seams=0.0, verify=0.0, animcheck=0.0, qa=0.0)
    t0 = time.time()
    preflight(project, E)
    T["build"] = time.time() - t0
    P = PC.Project(project, strict="--strict" in a)
    S = dict(pieces=None, final=None, timing=None, rendered=set(), checked=set(), probes=0, redone=[], failed=[])
    sheet = os.path.join(project, "work", "animcheck", "sheet.jpg")
    try:
        for attempt in (1, 2):                           # one more render for the pieces that did not animate
            t = time.time()
            try:
                S["pieces"], S["timing"] = PC.render(P, jobs=jobs)
            except RuntimeError as e:
                sys.exit(f"A piece failed to render: {e}. Nothing was delivered.")
            finally:
                T["render"] += time.time() - t
            pieces = S["pieces"]
            S["rendered"] |= {m["index"] for m in S["timing"]["pieces"]}
            t = time.time()
            S["final"], _ = PC.assemble(P, pieces, name)
            T["assemble"] += time.time() - t
            t = time.time()
            ok, _ = PC.check(P, S["final"])
            T["seams"] += time.time() - t
            if not ok:
                sys.exit("The seam check failed (above): the pieces do not join cleanly. Render again without --pieces. "
                         "Nothing was delivered.")
            if "--verify" in a:
                t = time.time()
                ok, _ = PC.verify(P, jobs=jobs)
                T["verify"] += time.time() - t
                if not ok:
                    sys.exit("The seam verify failed (above): a piece differs from a continuous render at a seam. "
                             "Render again without --pieces. Nothing was delivered.")
            todo = PC.unchecked(P, pieces)
            if not todo:
                break
            runs = AC.piece_runs(todo, {p["key"]: PC.meta_of(P, p["key"]) for p in todo})
            t = time.time()
            try:
                ok, rows = AC.check(project, S["final"], runs=runs)
            except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as e:
                print(f"animcheck could not check this render: {e}", file=sys.stderr)
                sys.exit("The animation check could not run (above): fix that and run it again "
                         f"(PY pipeline/animcheck.py {project} renders/{name}.mp4 --pieces). Nothing was delivered.")
            finally:
                T["animcheck"] += time.time() - t
            S["checked"] |= {p["index"] for p in todo}
            S["probes"] += len(rows)
            bad = sorted({r["piece"] for r in rows if r["state"] in ("static", "neither")})
            if ok or bad:                                # a piece whose every probe animated passes
                PC.mark_checked(P, [p["key"] for p in todo if AC.piece_label(p) not in bad])
            if ok:
                break
            if not bad:                                  # no piece to blame (the page itself does not animate)
                sys.exit("The animation check failed: part of the render did not animate (above). Render again. "
                         "Nothing was delivered.")
            for p in todo:
                if AC.piece_label(p) in bad:
                    PC.set_aside(P, p["key"])
            if attempt == 2:
                S["failed"] = bad
                sys.exit(f"The animation check failed again: {', '.join(bad)} did not animate (above; the probe "
                         f"pictures: {sheet}). Render again. Nothing was delivered.")
            S["redone"] += bad
            print(f"{', '.join(bad)} did not animate: set aside in {os.path.join(P.work, 'rejected')}, rendering "
                  f"{'it' if len(bad) == 1 else 'them'} once more", flush=True)
        t = time.time()
        sys.stdout.flush()                               # the seam and check tables before QA's own lines in a log
        qa = subprocess.run([PY, os.path.join(HERE, "qa.py"), project, os.path.join("renders", f"{name}.mp4"), "--phone"])
        T["qa"] = time.time() - t
        if qa.returncode:
            sys.exit("QA failed: fix what it reports, render again. Nothing was delivered.")
        if "--no-deliver" not in a:
            deliver(E, name, S["final"])
    finally:
        if S["final"]:                                   # assembled: prune even when a later gate failed
            t = time.time()
            try:
                print(PC.prune_line(PC.prune(P, S["pieces"], PC.budget())), flush=True)
            except Exception as e:                       # noqa: BLE001  (a cleanup never fails the render)
                print(f"prune: {e}", file=sys.stderr)
            T["prune"] = time.time() - t
        if S["pieces"] is not None:
            T["total"] = time.time() - t0
            print(timing_line(T, S, verify="--verify" in a), flush=True)
            if S["final"]:
                with open(os.path.splitext(S["final"])[0] + ".timing.json", "w") as fh:
                    json.dump(dict({k: round(v, 1) for k, v in T.items()}, pieces=len(S["pieces"]),
                                   rendered=sorted(S["rendered"]), checked=sorted(S["checked"]), probes=S["probes"],
                                   rendered_again=S["redone"], failed_twice=S["failed"], last_render=S["timing"]),
                              fh, indent=1)
    return S["final"]


def timing_line(T, S, verify=False):
    """one line: the seconds of each stage, then the pieces rendered, reused and checked"""
    stages = ["build", "render", "assemble", "seams"] + (["verify"] if verify else []) + ["animcheck", "qa", "prune",
                                                                                          "total"]
    n = len(S["pieces"])
    line = ("times: " + ", ".join(f"{k} {T[k]:.1f} s" for k in stages if k in T)
            + f"; pieces {n}: rendered {len(S['rendered'])}, reused {n - len(S['rendered'])}, checked "
              f"{len(S['checked'])} ({S['probes']} probes)")
    if S["redone"]:
        line += f", set aside and rendered again: {', '.join(S['redone'])}"
    if S.get("failed"):
        line += f", set aside after failing twice: {', '.join(S['failed'])}"
    return line


def in_hook(E, end):
    """what the creator sees in the hook, in words, for its approval page"""
    out = []
    plain = lambda t: re.sub(r"<[^>]+>", "", str(t))              # noqa: E731  (hook text may carry markup)
    if E.HOOK:
        out.append("The hook text: " + " / ".join(plain(E.HOOK[k]) for k in ("eyebrow", "h1", "h2") if E.HOOK.get(k)) + ".")
    for F in getattr(E, "FX", []):
        if F["at"] < end - 1e-6:
            out.append(F.get("note") or f"Effect {F['id']}.")
    for c in E.CARDS:
        if c[2] < end - 1e-6:
            out.append(f"Card {c[0]}: {c[5] if len(c) > 5 else c[0]}.")
    for m in E.BEHIND:
        items = m.get("items") or [None]
        at = (items[0][0] if m["kind"] in ("titles", "list") and items[0] else
              items[0]["at"] if m["kind"] == "float" and items[0] else m.get("at", 0))
        if at < end - 1e-6:
            out.append(f"Behind your head: {m['kind']}.")
    if getattr(E, "STYLE", "hifi") in ("lofi", "showcase"):
        out.append("Word-by-word captions.")
    else:
        n = sum(1 for c in E.CAPS if c[0] < end - 1e-6)
        out.append(f"{n} caption{'s' if n != 1 else ''}." if n else "No captions in the hook (an effect carries the words).")
    if any(a < end - 1e-6 for a, _ in E.BW):
        out.append("Black and white on the claim.")
    return out or ["Your footage, nothing on top yet."]


def render_hook(project, E, name):
    """--hook: build as usual, cut a copy of the composition at the hook's end into work/hook/ (every asset a hard
    link into public/; public/index.html is never cut), render it at draft quality, lay the matching slice of
    master.wav on, then write the approval stop approvals/hook/"""
    import hook as H
    import preview as PV
    t0 = time.time()
    pub = os.path.join(project, "public")
    if not os.path.exists(os.path.join(pub, "clean.mp4")):
        sys.exit("public/clean.mp4 missing (clean.mp4 = assets/aroll.mp4, SKILL.md step 2)")
    subprocess.run([PY, os.path.join(HERE, "build.py"), project, "--stills"], check=True)   # a card with no mp4 shows its still
    t_build = time.time() - t0
    TL = timeline(project)
    wp = os.path.join(project, "words.json")
    words = []
    if os.path.exists(wp):
        with open(wp, encoding="utf-8") as fh:
            words = json.load(fh)
    override = getattr(E, "HOOK_END", None)
    end = H.hook_end(words, E.HOLD, TL["total"], override, joins=[k["out"] for k in TL["keep"][1:]])
    frames = round(end * FPS)
    with open(os.path.join(pub, "index.html"), encoding="utf-8") as fh:
        cut = H.truncate(fh.read(), end)
    for src in sorted(set(re.findall(r'<video\b[^>]*?\bsrc="([^"]+)"', cut, re.S))):     # what the hook still plays
        if not os.path.exists(os.path.join(pub, src)):
            sys.exit(f"public/{src} is missing and the hook plays it before {end:.2f} s: make it first "
                     "(cutout.py or matte.py for subject.webm, the card agent's render for cards/)")
    work = os.path.join(project, "work", "hook")
    shutil.rmtree(work, ignore_errors=True)               # links only: removing them never touches public/
    H.link_tree(pub, work, skip=("index.html", "snapshots"))
    with open(os.path.join(work, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(cut)
    os.makedirs(os.path.join(project, "renders"), exist_ok=True)
    final = os.path.join(project, "renders", f"{name}-hook.mp4")
    picture = final.replace(".mp4", ".picture.mp4")
    t1 = time.time()
    hf(["render", "-q", "draft", "--quiet", "-o", picture], work)
    t_render = time.time() - t1
    master = os.path.join(pub, "master.wav")
    if os.path.exists(master):
        audio, sound = master, "The master mix: your voice and the sound effects."
    else:
        audio, sound = os.path.join(project, "assets", "voice.wav"), "Your voice alone (mix.py adds the sound effects)."
    fade = min(0.04, end / 4)                            # the slice ends on a fade, never a click
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", picture, "-t", f"{end:.4f}", "-i", audio, "-map", "0:v:0",
                    "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-af", f"apad,afade=t=out:st={end - fade:.4f}:d={fade:.4f}", "-t", f"{end:.4f}",
                    "-movflags", "+faststart", final], check=True)
    os.remove(picture)
    got = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", final], capture_output=True, text=True).stdout.strip()
    folder = os.path.join(project, "approvals", "hook")
    os.makedirs(folder, exist_ok=True)
    shutil.copy2(final, os.path.join(folder, "hook.mp4"))
    PV.poster(final, os.path.join(folder, "poster.jpg"), min(1.0, end / 2))
    how_end = "HOOK_END in edit.py" if override is not None else "the end of the first sentence"
    said = PV.sentences(words, 0.0, end - 0.1)            # a word that starts in the last 0.1 s isn't heard in the hook
    shown = "".join(f"<li>{html.escape(x)}</li>" for x in in_hook(E, end))
    facts = [("Length", f"{PV.tc(end)} ({frames} frames), ending at {how_end}.", False),
             ("On screen", f"<ul>{shown}</ul>", False),
             ("Sound", sound, False),
             ("Render", f"Draft quality, rendered in {t_render:.0f} s. The final render is full quality.", False)]
    PV.page(folder, E, "hook.mp4", title=f"{E.TITLE} Hook", eyebrow=f"Hook · {PV.tc(end)} · draft", head=E.TITLE,
            how=("The opening as it will play, at draft quality: the type, the effects, the captions and the sound. "
                 "Watch it on your phone with the sound on. <b>Leave a note</b> on any line, or <b>say go</b> and I "
                 "build the rest."),
            go="Looks good: build the rest", facts=facts, lines=said,
            missing=None if words else f"The lines show once words.py has run on this cut: PY pipeline/words.py {project}",
            foot=(f"A draft render of the first {frames} frames, from the same composition the final renders from. "
                  "Tap a time to jump there."))
    print(f"hook: {final}  {end:.3f} s, {frames} frames expected, {got} rendered  ({how_end})")
    if said:
        print(f"the hook ends on: \"{said[-1][1]}\" (HOOK_END in edit.py moves it)")
    print(f"times: build {t_build:.1f} s, render {t_render:.1f} s, total {time.time() - t0:.1f} s")
    print(f"page: {folder}/index.html (+ files.json): publish it with comments, or "
          f"python3 {os.path.join(os.path.dirname(HERE), 'storyboard', 'serve.py')} {folder}")
    if got != str(frames):
        sys.exit(f"the hook rendered {got} frames, {frames} expected")
    return final


def deliver(E, name, final):
    """the render and its phone copy where the creator finds them: '<Title> v1.mp4' and '<Title> v1 (phone).mp4' in
    the project folder when intake.py made the source (the takes sit in the project's raw/), else next to the clip"""
    ver = name.rsplit("-", 1)[-1] if name.rsplit("-", 1)[-1].startswith("v") else name
    dest = os.path.dirname(os.path.abspath(os.path.expanduser(E.SRC)))
    if os.path.basename(dest) == "raw" and os.path.exists(os.path.join(os.path.dirname(dest), "intake.json")):
        dest = os.path.dirname(dest)
    title = "".join(ch for ch in E.TITLE if ch not in '/\\:*?"<>|').strip() or "Video"
    pairs = [(final, f"{title} {ver}.mp4"), (final.replace(".mp4", "-phone.mp4"), f"{title} {ver} (phone).mp4")]
    for src, out in pairs:
        if os.path.exists(src) and os.access(dest, os.W_OK):
            shutil.copy(src, os.path.join(dest, out))
            print("delivered", os.path.join(dest, out))


if __name__ == "__main__":
    main()
