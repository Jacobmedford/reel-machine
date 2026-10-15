"""Reference showcase edit: every field a showcase video uses, filled in for one illustrative video.

The video: a creator shows off what a one-sentence edit can do, a different technique on every line. The script and
the footage are made up for this example; the kit's effects lab (dev/fxlab.py) builds exactly this on a drawn
stand-in figure. Copy field shapes from here into a project's edit.py; never copy the content. Read
modes/SHOWCASE.md first. Every time is on the OUTPUT timeline in seconds, except KEEP (source seconds).
"""
TITLE = "One Sentence Edit"
STYLE = "showcase"
SRC = "~/Videos/one-sentence-edit/take.mov"

# ---- cut (source seconds): keep ranges from silencedetect, the last clean take of every line
KEEP = [(0.0, 7.2), (7.3, 16.0), (16.1, 28.7)]
FRAMES = {"WIDE": (1080, 1920, 0, 0), "CLOSE": (864, 1536, 108, 192)}
SHOTS = [(0.000, "WIDE"), (7.500, "CLOSE"), (16.200, "WIDE")]
J_LEADS = None                      # per-join leads when one shot must stop early (a lean-in to the phone)
HOLD = 0.5
FIXES = {}
PROMPT = "I didn't edit a single second of this video. Comment EDIT."

# ---- captions: word by word from words.json; effects that carry the words hide them in their window
CAPS = []
KARAOKE = dict(huge=[], hide=[(22.40, 23.90)])      # giant-captions sets "Bigger captions." itself
BOXES = []                                         # the effects carry the hook, the prompts and the CTA
OVERLAYS = []
BEHIND = []

# ---- the beat map: a different technique on every line, one motif (the prompt bar), a transition on every cut.
# (id, layer, at, end): layers behind (under the cutout) / cam / top / over; files in fx/<id>/, copied from fx/
FX = [
    dict(id="kinetic-hook", layer="behind", at=0.0, end=2.50, frames=[0.2, 0.8, 1.75, 2.3],
         note="Hook, readable on frame 0: the opening line in the display face behind your head, the key word stamping in."),
    dict(id="kinetic-hook-front", layer="top", at=0.0, end=0.37),
    dict(id="icon-strike", layer="top", at=2.50, end=4.50, frames=[2.98, 3.94, 4.30],
         note="Two app icons pop on their names, a stroke strikes each, they drop away; \"nothing.\" rises."),
    dict(id="prompt-bar", layer="top", at=4.50, end=5.90, frames=[5.05, 5.32, 5.55],
         note="The motif: the one sentence types into a bar and sends."),
    dict(id="grade-slider", layer="cam", at=5.90, end=7.00, frames=[6.3, 6.8],
         note="On \"warmer\": a before/after slider splits the frame, then sweeps the warm look across."),
    dict(id="magazine-cover", layer="behind", at=7.60, end=9.45, frames=[7.9, 8.6, 9.2],
         note="A magazine cover builds behind your head: masthead, dateline, coverlines, a sticker."),
    dict(id="nle-timeline", layer="top", at=9.30, end=10.90, frames=[9.7, 10.3, 10.56],
         note="An editing timeline built from this video's real cuts and captions, then folded away."),
    dict(id="file-drop", layer="top", at=10.90, end=12.50, frames=[11.3, 11.95, 12.25],
         note="The raw file drops in and opens on the filler the edit cut; BAD TAKE stamps."),
    dict(id="odometer-recursion", layer="cam", at=12.50, end=14.60, frames=[13.0, 13.9],
         note="The raw length rolls down to the final length, then the frame recurses into itself."),
    dict(id="mood-curtain", layer="cam", at=14.60, end=16.20, frames=[14.9, 15.6],
         note="On \"moody\": the dark look falls like a curtain, grain and a vignette hold."),
    dict(id="grid-collapse", layer="cam", at=16.20, end=17.60, frames=[16.6, 17.2],
         note="You shrink into the centre of a 3x3 grid of others doing it, then snap back full frame."),
    dict(id="page-scroll", layer="top", at=17.60, end=19.20, frames=[17.8, 18.4, 18.92],
         note="The plan page scrolls by, then the camera settles on one section."),
    dict(id="comment-thread", layer="top", at=19.20, end=20.70, frames=[19.85, 20.45],
         note="A pin drops on the beat, your note types in, the reply answers."),
    dict(id="word-stamp", layer="behind", at=20.80, end=22.40, frames=[21.6, 22.35],
         note="NEVER stamps letter by letter behind your head."),
    dict(id="giant-captions", layer="over", at=22.40, end=23.90, frames=[22.8, 23.5],
         note="\"Bigger captions.\": the captions grow into a giant slab, word by word."),
    dict(id="video-card", layer="top", at=23.90, end=25.60, frames=[24.21, 24.81, 25.28],
         note="A video card unfolds and plays your walkthrough, chapter by chapter."),
    dict(id="comment-cta", layer="top", at=25.60, end="end", frames=[26.20, 28.00, 28.90],
         note="CTA: the comment field types EDIT and posts; the CTA holds to the end."),
    dict(id="camera-transitions", layer="over", at=0.0, end="end"),     # a different move on every picture cut
]
CUT_WINDOWS = [(0.0, 2.50), (7.60, 9.45), (20.80, 22.40)]   # behind-layer effects (never across a picture cut)

# ---- looks the script asks for, held until the next one; hard zooms only where a line lands
BW = []
GRADES = [(7.00, 14.60, "warm"), (14.60, 16.20, "moody")]
CAMERA = dict(settles=[], open=(1.0, 0.01), zooms=[])
CARDS = []
END_CARD = None

# ---- sound: one event, one sound; times are when each one hits (mix.py lines up the loudest moment)
TYPE = lambda t, db, n: dict(at=t, name="typing", db=db, max_len=n, align="start")   # noqa: E731  typing runs from its start
SOUND = dict(music=None, sfx=[
    # kinetic-hook: the ground cuts in, EDIT stamps, lines push through, the timecode runs
    (0.367, "impact-low", -15), (0.367, "tick", -14), (0.433, "tick", -14), (0.500, "tick", -14), (0.567, "tick", -14),
    (0.833, "whoosh-soft", -20), (1.333, "clicks-run", -22, 1.15), (1.600, "whoosh-soft", -21), (2.067, "whoosh", -17),
    # icon-strike: two icons pop, two strikes, they drop, "nothing." lands
    (2.94, "pop", -17), (3.22, "stamp", -17), (3.62, "pop", -17), (3.84, "stamp", -17), (4.04, "whoosh", -16),
    (4.16, "impact-low", -17),
    # prompt-bar: opens, types, sends, lands, closes
    (4.50, "whoosh-soft", -22), TYPE(4.50, -15, 0.55), (5.10, "key", -13), (5.40, "pop", -18), (5.64, "whoosh-soft", -24),
    # grade-slider: slides in, labels, the sweep
    (5.97, "whoosh-soft", -19), (6.03, "click", -20), (6.72, "whoosh", -15),
    # camera-transitions: the whip into the close shot (the cut at 16.2 belongs to grid-collapse)
    (7.50, "whoosh", -14),
    # magazine-cover: the shutter, the masthead letters, the barcode, coverlines, the sticker, it clears
    (7.60, "shutter", -12), (7.62, "clicks-run", -20, 0.35), (8.07, "click", -16), (8.33, "pop", -19), (8.59, "pop", -19),
    (8.94, "stamp", -12), (9.36, "whoosh-soft", -19),
    # nle-timeline: the panel unfolds, clips land, blocks, captions, marks, it pinches to a line
    (9.34, "whoosh-soft", -17), (9.60, "clicks-run", -18, 0.25), (9.90, "pop", -19), (10.20, "tick", -12),
    (10.40, "tick", -12), (10.68, "whoosh-deep", -16), (10.82, "click", -16),
    # file-drop: the zone opens, the card lands, the player opens, BAD TAKE twice, it drops back
    (10.92, "whoosh-soft", -18), (11.23, "click", -14), (11.67, "whoosh", -14), (11.93, "stamp", -12), (12.17, "stamp", -12),
    (12.42, "whoosh-soft", -19),
    # odometer-recursion: the plate, the roll, the landing, one pop a level, the dive
    (12.55, "whoosh-soft", -19), (12.60, "clicks-run", -14, 0.71), (13.31, "ding", -20), (13.55, "pop", -20),
    (13.79, "pop", -21), (14.03, "pop", -22), (14.15, "pop", -23), (14.52, "whoosh-deep", -15),
    # mood-curtain: the curtain falls, a low boom under the dark
    (15.37, "boom-low", -20), (15.40, "whoosh-deep", -16),
    # grid-collapse: the shrink, a pop per tile, the scatter
    (16.35, "whoosh-soft", -19), (16.27, "pop", -21), (16.30, "pop", -21), (16.33, "pop", -21), (16.37, "pop", -21),
    (16.40, "pop", -21), (16.43, "pop", -21), (16.47, "pop", -21), (16.50, "pop", -21), (17.20, "whoosh", -15),
    # page-scroll: the card rises, two flicks, the push in, three rows light, it drops away
    (17.70, "whoosh", -14), (17.78, "whoosh-soft", -21), (18.02, "whoosh-soft", -21), (18.37, "whoosh-deep", -16),
    (18.57, "click", -16), (18.66, "click", -16), (18.85, "click", -16), (19.12, "whoosh-soft", -18),
    # comment-thread: the card, the pin, the note types, the reply, the underline, out
    (19.20, "click", -18), (19.44, "pop", -17), TYPE(19.52, -16, 0.36), (19.95, "pop", -18), (20.27, "tick", -14),
    (20.50, "whoosh-soft", -24),
    # word-stamp: NEVER stamps letter by letter, the small line sets, the strike
    (21.033, "impact-low", -14), (21.033, "tick", -13), (21.100, "tick", -13), (21.167, "tick", -13), (21.233, "tick", -13),
    (21.300, "tick", -13), (21.300, "click", -21), (21.800, "click", -21), (22.067, "click", -21), (22.200, "whoosh-soft", -21),
    # giant-captions: the box grows into the slab, lands, the line wipes open, the slabs fold
    (22.50, "whoosh", -15), (22.60, "impact-low", -17), (23.167, "whoosh-soft", -19), (23.633, "whoosh-soft", -22),
    # video-card: unfolds, play lands, play pressed, chapters, folds
    (23.95, "whoosh", -16), (24.06, "pop", -19), (24.375, "click", -12), (24.67, "tick", -15), (24.90, "tick", -15),
    (25.13, "tick", -15), (25.50, "whoosh-soft", -19),
    # comment-cta: the CTA box, the field, EDIT types and posts, the reply, the like, the fold, the box takes the hit
    (25.60, "pop", -16), (25.66, "whoosh-soft", -22), TYPE(26.01, -15, 0.28), (26.32, "click", -14), (26.56, "pop", -21),
    (26.64, "pop", -17), (27.89, "pop", -16), (28.30, "whoosh", -17), (28.57, "impact-low", -18),
])
CARD_SFX = []

NEEDS = [
    ("p02", "Two screenshots of the apps you say you don't need, or their names, to fetch the real icons"),
    ("p10", "Eight screenshots of other creators doing this (9:16, headlines readable)"),
    ("p14", "Two or three short clips from your walkthrough, with you and the screen moving"),
]
GENERATED = []
