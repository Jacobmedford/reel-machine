#!/usr/bin/env python3
"""New: scaffold a video project -> $REEL_MACHINE_HOME/projects/<slug>/ (default ~/reel-machine/projects/<slug>/), with the
creator's style pack copied in and a starter edit.py.
Run: PY pipeline/new.py <slug> "<source clip path>" ["Title"] --mode hifi|lofi|showcase [--pack <name>] [--reseed]
FRAMES are seeded from the clip as it displays (a sideways phone take turned upright): 4K landscape gets two 9:16 crops
(WIDE, CLOSE), anything else full frame + a 1.25x CLOSE.
--pack picks a named pack from $REEL_MACHINE_HOME/packs/ (pipeline/pack.py list); without it the default pack (style/).
The style pack is copied, not linked, so an old project still renders the same after the creator changes their style.
A folder intake.py made (raw/ + intake.json) is fine; one with edit.py is refused unless --reseed: edit.py is then
rewritten from the new mode's starter, keeping KEEP (with its J_LEADS), PROMPT and FIXES as written, the old one kept as
edit-before-<mode>-<MM-DD-YY>.py; the project's style/ stays as it is (with --pack it is swapped, as pack.py use does).
"""
import ast
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KIT, VENDOR  # noqa: E402
import pack as PK  # noqa: E402
import style as ST  # noqa: E402

STARTER = '''"""{title}: the one file that describes this video. Read modes/{mode_doc}, then copy what you need from
examples/{mode}/edit.py. Times are on the OUTPUT timeline unless marked source."""
TITLE = "{title}"
STYLE = "{mode}"                    # hifi (modes/HIFI.md), lofi (modes/LOFI.md) or showcase (modes/SHOWCASE.md)
SRC = "{src}"

# ---- cut (source seconds): keep ranges from silencedetect, last clean take of every line
KEEP = []
# 9:16 crops of the source (w, h, x, y): seeded from its size, then measure on a frame of THIS shoot (face, eyes, chin)
FRAMES = {frames}
SHOTS = [(0.000, "WIDE")]           # add CLOSE/WIDE changes; hide them under cards where you can
HOLD = {hold}                         # picture after the last word: hi-fi 0.6 (1.3 with an end card), lo-fi 0.04
FIXES = {{}}                         # transcription mishearings -> the real word
PROMPT = ""                         # names, products and numbers in the script, to help transcription

# ---- after words.py: captions (start, text, kind[, end]); kinds "", "big", "thesis", "strike"; *word* = accent
CAPS = []
HOOK = None                         # dict(eyebrow=, h1=, h2=, off=, shot_end=[, tag=])
BEHIND = []                         # moments behind the speaker's head
CUT_WINDOWS = []                    # where the cutout plays (never across a picture change)
BW = []                             # black-and-white beats, at most two
CAMERA = dict(punch=[], pushes=[], open=(1.04, 0.45))
CARDS = []                          # (id, "cards/<id>.mp4", start, end, "light"|"dark", "what it shows")
END_CARD = None                     # opt-in only
SOUND = dict(sfx=[], music=None)    # music is off by default: the creator adds a track in their posting app
CARD_SFX = []
NEEDS = []                          # (beat id, what the creator should send: a screenshot, a clip, a logo)
GENERATED = []                      # (beat id, what a connected generator made, which model); empty without one
{extra}'''

SHOWCASE = '''
# ---- showcase (modes/SHOWCASE.md): the lo-fi type system + one hand-built motion graphic per beat
KARAOKE = dict(huge=[], hide=[])    # huge: lines set at 124px; hide: windows an effect carries the words in
BOXES = []                          # native text boxes (hook, CTA) when no effect carries them
OVERLAYS = []
FX = []                             # dict(id, layer behind|cam|top|over, at, end, frames=[...], note=); files in fx/<id>/
GRADES = []                         # (start, end, "warm"|"moody"|css filter): looks the script asks for
J_LEADS = None                      # per-join J-cut leads, when one shot must stop early (a lean-in to the phone)
'''
LOFI = '''
KARAOKE = {}                        # dict(huge=[(start, end)], hide=[(start, end)])
BOXES = []                          # Instagram-style text boxes: hook, chapter labels, CTA
OVERLAYS = []                       # real screenshots or clips dropped on top of the speaker
'''
EXTRA = {"lofi": LOFI, "showcase": SHOWCASE}


def frames_for(src):
    """FRAMES seeded from the clip's size as it displays (ffmpeg turns a sideways take upright before it crops):
    4K landscape -> two 9:16 crops; anything else -> full frame + a 1.25x CLOSE"""
    import intake as I
    d = I.probe(src)
    if not d:
        sys.exit(f"could not read the video size of {src}: is it a video file?")
    w, h = I.shape(d)
    if w > h:
        # landscape: a full-height 9:16 window in the middle, and a tighter one 1.6x in (move both onto the face)
        ww = round(h * 9 / 16) // 2 * 2
        cw, ch = round(ww / 1.6) // 2 * 2, round(h / 1.6) // 2 * 2
        return (f'{{"WIDE": ({ww}, {h}, {(w - ww) // 2}, 0), '
                f'"CLOSE": ({cw}, {ch}, {(w - cw) // 2}, {round(h * 0.18)})}}')
    cw, ch = round(w * 0.8) // 2 * 2, round(h * 0.8) // 2 * 2
    return f'{{"WIDE": ({w}, {h}, 0, 0), "CLOSE": ({cw}, {ch}, {(w - cw) // 2}, {(h - ch) // 2})}}'


def lit(s):
    """s as it goes between the starter's double quotes: a title or a take name with quotes still makes a working
    edit.py"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def copy_pack(project, name=None):
    """the creator's style pack (style.json, brand.css, fonts/; a named pack also its extra.css) -> <project>/style/.
    name None = the default pack; a name that is not a pack stops with the list (pack.pack_dir)"""
    PK.copy_into(PK.ready(name), os.path.join(project, "style"))


CARRY = ("KEEP", "J_LEADS", "PROMPT", "FIXES")       # what a mode change keeps: the cut and the transcription hints


def _spans(text):
    """{name: (first line, last line)} of every top-level NAME = ... in text (the last one when a name repeats)"""
    out = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            out[node.targets[0].id] = (node.lineno, node.end_lineno)
    return out


def carry(old, new):
    """new (another mode's starter) with KEEP, J_LEADS, PROMPT and FIXES as old has them, lines and comments as
    written. One the starter has no line for (J_LEADS) goes right after KEEP"""
    o, n = _spans(old), _spans(new)
    src, out = old.splitlines(keepends=True), new.splitlines(keepends=True)
    edits = []
    for name in CARRY:
        if name not in o:
            continue
        lines = src[o[name][0] - 1:o[name][1]]
        lines[-1] = lines[-1] if lines[-1].endswith("\n") else lines[-1] + "\n"
        a, b = (n[name][0] - 1, n[name][1]) if name in n else (n["KEEP"][1], n["KEEP"][1])
        edits.append((a, b, lines))
    for a, b, lines in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):    # last first: line numbers hold
        out[a:b] = lines
    return "".join(out)


def _free(path, ext):
    if not os.path.exists(path + ext):
        return path + ext
    k = 2
    while os.path.exists(f"{path}-{k}{ext}"):
        k += 1
    return f"{path}-{k}{ext}"


def reseed(project, text, mode):
    """edit.py -> text with the old KEEP, J_LEADS, PROMPT and FIXES carried in; the old file is kept as
    edit-before-<mode>-<MM-DD-YY>.py. If the new file doesn't read back with the same four, the old one comes back"""
    from common import load_edit
    path = os.path.join(project, "edit.py")
    with open(path, encoding="utf-8") as fh:
        text = carry(fh.read(), text)
    was = load_edit(project)
    kept = _free(os.path.join(project, f"edit-before-{mode}-{time.strftime('%m-%d-%y')}"), ".py")
    os.rename(path, kept)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    now = load_edit(project)
    lost = [k for k in CARRY if getattr(was, k, None) != getattr(now, k, None)]
    if lost:
        os.replace(kept, path)
        sys.exit(f"the reseeded edit.py read back with a different {', '.join(lost)}: the old one is restored. Copy "
                 f"them by hand from {path}")
    return kept


def main():
    argv = sys.argv[1:]
    mode, pack = None, None
    again = "--reseed" in argv
    argv = [a for a in argv if a != "--reseed"]
    if "--pack" in argv:
        i = argv.index("--pack")
        pack = argv[i + 1] if i + 1 < len(argv) else ""
        argv = argv[:i] + argv[i + 2:]
    for flag in ("--mode", "--style"):                  # --style is the old name of --mode
        if flag in argv:
            i = argv.index(flag)
            mode = argv[i + 1] if i + 1 < len(argv) else None
            argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2 or mode not in ("hifi", "lofi", "showcase"):
        sys.exit(__doc__ + "\n--mode hifi|lofi|showcase is required: the creator picks the mode, never guess it.")
    slug, src = args[0], os.path.abspath(os.path.expanduser(args[1]))
    import intake as I
    if not I.SLUG.fullmatch(slug) or ".." in slug:
        sys.exit(f"'{slug}' can't name a project folder: use letters, numbers, - and _ (like my-first-reel)")
    if not os.path.exists(src):
        sys.exit(f"source clip not found: {src}")
    title = args[2] if len(args) > 2 else slug.replace("-", " ").title()
    project = os.path.join(ST.HOME, "projects", slug)
    again = again and os.path.exists(os.path.join(project, "edit.py"))
    if os.path.exists(os.path.join(project, "edit.py")) and not again:
        sys.exit(f"{project}/edit.py already exists (to switch it to another mode, keeping KEEP, PROMPT and FIXES: "
                 "--reseed)")
    PK.ready(pack)                                      # an unknown pack stops here, before any folder is made
    for d in ("assets", "audio", "cards", "fx", "public/cards", "public/media", "renders", "storyboard", "work"):
        os.makedirs(os.path.join(project, d), exist_ok=True)
    if not (again and os.path.isdir(os.path.join(project, "style"))):
        copy_pack(project, pack)
    elif pack is not None:
        PK.use(project, pack)                           # the style it wore is kept under a new name
    if not os.path.exists(os.path.join(VENDOR, "gsap.min.js")):
        sys.exit(f"{VENDOR}/gsap.min.js is missing: run python3 setup/setup.py first")
    shutil.copytree(VENDOR, os.path.join(project, "public", "vendor"), dirs_exist_ok=True)
    shutil.copy(os.path.join(KIT, "kit", "hyperframes.json"), os.path.join(project, "public"))
    text = STARTER.format(title=lit(title), src=lit(src), mode=mode, mode_doc=f"{mode.upper()}.md", hold=0.6 if mode == "hifi" else 0.04 if mode == "lofi" else 0.5,
                          frames=frames_for(src), extra=EXTRA.get(mode, ""))
    if again:
        kept = reseed(project, text, mode)
        print(f"{project}/edit.py is now {mode}, with its KEEP, PROMPT and FIXES; the old one is {kept}")
    else:
        with open(os.path.join(project, "edit.py"), "w") as fh:
            fh.write(text)
    print(project)


if __name__ == "__main__":
    main()
