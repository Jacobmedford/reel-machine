"""Reference lo-fi edit: every field a lo-fi video uses, filled in for one illustrative video.

The video: a creator shares three things they do every Sunday to plan their week, shot as a phone selfie. The
script, the footage and the media files are made up for this example. Copy field shapes from here into a
project's edit.py; never copy the content. Read modes/LOFI.md first.
Every time is on the OUTPUT timeline in seconds, except KEEP (source seconds).
"""
TITLE = "Sunday Planning"
STYLE = "lofi"
SRC = "~/Videos/sunday-planning/selfie.mp4"

# ---- cut (source seconds): keep ranges from silencedetect, the last clean take of every line.
# Phone takes often arrive already cut in the pauses: cut.py finds those cuts and fits each J-cut to them.
KEEP = [
    (0.00, 3.40),    # Three things I do every Sunday so my week runs itself.
    (3.62, 7.95),    # Number one: I dump everything out of my head. Every task, every idea.
    (8.30, 15.10),   # Then I sort it into three lists ... and anything that isn't on them waits.
    (15.40, 23.80),  # Number two: I block my calendar before anyone else can ... the deep work goes first.
    (24.15, 31.60),  # Number three: I pick one thing ... if only that gets done, the week was a win.
    (31.90, 38.70),  # Want my planning template? Comment PLAN and I'll send it over.
]
# a 1080x1920 phone source has no headroom: CLOSE is a gentle 1.25x crop
FRAMES = {"WIDE": (1080, 1920, 0, 0), "CLOSE": (864, 1536, 108, 192)}
SHOTS = [(0.000, "WIDE"), (3.400, "CLOSE"), (7.733, "WIDE"), (14.500, "CLOSE"), (22.700, "WIDE"),
         (30.133, "CLOSE"), (36.400, "WIDE")]
HOLD = 0.04                           # a phone take ends on the last word
FIXES = {}
PROMPT = "Three things I do every Sunday. Comment PLAN."

# ---- captions: word by word from words.json; nothing to write here
CAPS = []
KARAOKE = dict(huge=[(30.20, 31.50)])   # this line comes in huge: two words a line at 124px

# ---- native text boxes: the hook from frame 0, a label on each tip, the CTA held to the end
BOXES = [
    dict(text="3 things I do every Sunday\nso my week runs itself", at=0.0, end=3.367,
         note="Hook box from frame 0."),
    dict(text="1. Empty your head", at=3.40, end=5.40, note="Tip label."),
    dict(text="2. Block the calendar first", at=14.50, end=16.60, note="Tip label."),
    dict(text="3. Pick the one thing", at=22.70, end=24.80, note="Tip label."),
    dict(text="Comment “PLAN” and\nI’ll send my template", at=34.10, end="end", note="CTA box held to the last frame."),
]

# ---- on top of them: the real thing, above the caption band (y < 1300); plain = no corners (screen recordings)
OVERLAYS = [
    dict(src="media/calendar-week.png", at=16.70, end=19.40, x=71, y=330, w=938, h=720,
         note="Their real calendar, the week blocked out, on 'before anyone else can'."),
    dict(src="media/notes-scroll.mp4", at=5.50, end=7.70, x=71, y=330, w=938, h=648, cls="plain",
         note="Screen recording: scrolling the brain-dump note."),
]

# ---- behind them: a real backdrop swapped in with the cutout on top, and lines that build on the words
BEHIND = [
    dict(kind="backdrop", src="media/desk.jpg", at=0.0, end=3.367, note="Their real desk on Sunday, behind the hook."),
    dict(kind="list", head=True, items=[(9.40, "three lists..."), (10.30, "1. This week"), (11.20, "2. Someday"),
                                        (12.10, "3. Not mine")],
         end=13.90, replace=True, top=222, dy=62, note="Above the head, each on its word."),
    dict(kind="backdrop", src="media/one-thing.jpg", at=26.40, end=29.80,
         note="A photo of the sticky note with this week's one thing."),
]
CUT_WINDOWS = [(0.0, 3.367), (9.20, 13.90), (26.40, 29.80)]

# ---- grade + camera: hard cuts, hard zooms on the words that matter, at most one black-and-white beat
BW = [(30.133, 31.500)]
CAMERA = dict(settles=[], open=(1.0, 0.01),
              zooms=[(19.60, 20.70, 1.12),        # "the deep work goes first"
                     (28.40, 29.80, 1.10),        # "the week was a win"
                     (36.40, "end", 1.08)])       # the CTA, close
CARDS = []
END_CARD = None

# ---- sound: times are when each sound hits. A whoosh on every backdrop swap, pops on list items, clicks on boxes.
SOUND = dict(
    music=None,
    sfx=[
        (3.40, "click", -9), (14.50, "click", -9), (22.70, "click", -9),    # tip label boxes
        (5.50, "whoosh-soft", -16),                                             # the notes recording
        (9.40, "pop", -10), (10.30, "pop", -10), (11.20, "pop", -10), (12.10, "pop", -10),
        (16.70, "whoosh", -11), (16.75, "pop", -13),                             # the calendar lands on top
        (19.60, "whoosh-deep", -15),                                            # zoom
        (26.40, "whoosh", -9),                                                  # backdrop swap
        (28.40, "whoosh-deep", -15),                                            # zoom
        (30.13, "scratch", -9),                                                 # the turn, black and white
        (34.10, "click", -7), (34.25, "ding", -16),                             # the CTA box
    ],
)
CARD_SFX = []

NEEDS = [
    ("p03", "Screen recording, 3s: scrolling your real brain-dump note, phone or desktop, any app"),
    ("p06", "Screenshot of your calendar for a planned week (blur anything private)"),
]
GENERATED = []
