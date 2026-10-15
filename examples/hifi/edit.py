"""Reference hi-fi edit: every field a hi-fi video uses, filled in for one illustrative video.

The video: a creator explains why their channel grew while their ad revenue fell. The script, the numbers and the
footage are made up for this example (no footage ships with the kit). Copy field shapes from here into a project's
edit.py; never copy the content. Read modes/HIFI.md first.
Every time is on the OUTPUT timeline in seconds, except KEEP (source seconds).
"""
TITLE = "Views Up Revenue Down"
STYLE = "hifi"
SRC = "~/Videos/views-up-revenue-down/take.mov"

# ---- cut: audio ranges to keep (source seconds), each gap a pause found with silencedetect -35dB.
# One range per clean take; when a line was said twice, only the last good take is kept.
KEEP = [
    (4.10, 9.62),    # My channel grew 32% last year. And my ad revenue? It fell.
    (11.80, 16.31),  # Views went up, but every single view paid me 11% less.
    (16.70, 22.95),  # Sponsors, courses, templates, coaching ... and a ton more. Here's the actual report.
    (24.40, 30.18),  # One video went viral last year. It added 1.6% to revenue. Barely noticeable.
    (30.60, 42.05),  # But my newsletter ... doubling every four and a half months.
    (42.50, 55.70),  # But here's the catch ... every other stream went up.
    (56.10, 63.48),  # The revenue grew, but costs took a bigger slice. So the real question ... who pays for them.
]
# 9:16 crops of a 3840x2160 source (w, h, x, y). Measure on a frame of THIS shoot: face centre, eyes, chin.
FRAMES = {
    "WIDE": (1216, 2160, 1312, 0),       # full height
    "CLOSE": (760, 1352, 1540, 378),     # 1.6x in
}
# shots on the output timeline; reframes hide under cards, visible ones are deliberate (the turn, the last line)
SHOTS = [(0.000, "WIDE"), (3.630, "CLOSE"), (10.067, "WIDE"), (16.500, "CLOSE"), (22.300, "WIDE"),
         (30.033, "CLOSE"), (46.433, "WIDE")]
HOLD = 0.6                            # picture after the last word (1.3 with an end card)
FIXES = {"add revenue": "ad revenue"}  # transcription mishearings -> the real words
PROMPT = "My channel grew 32% last year. Ad revenue. Sponsors, courses, templates, coaching. Newsletter."

# ---- captions: (start, text, kind[, end]). kind: "" phrase, "big" number, "thesis" one display word, "strike".
# *word* = accent. A caption holds until the next one starts unless an end is given ("end" = the last frame).
CAPS = [
    (0.02, "my channel grew", ""), (0.90, "*32%*", "big"), (1.62, "last year.", "", 2.30),
    (2.34, "and my ad revenue?", "", 3.55), (3.63, "it", ""), (3.90, "fell.", "thesis", 5.40),
    (5.52, "views went *up,*", ""), (6.70, "but every single view", ""), (8.02, "paid me", ""),
    (8.60, "*11%* less.", "big", 10.00),
    (12.70, "and a ton more.", "", 13.95), (14.05, "here's the", ""), (14.50, "actual report.", "", 16.40),
    (16.55, "one video", ""), (17.20, "went viral", ""), (17.95, "last year.", "", 19.30),
    (19.47, "it added", ""), (20.05, "*1.6%*", "big"), (20.90, "to revenue.", ""),
    (21.55, "barely noticeable.", "", 22.25),
    (22.35, "but my newsletter", ""), (23.40, "grows", ""), (24.70, "every month.", "", 25.95),
    (26.10, "10K subscribers,", ""), (27.30, "doubling", "thesis"), (27.95, "every four", ""),
    (28.70, "and a half months.", "", 29.95),
    (30.10, "but here's", ""), (30.55, "the catch.", "thesis", 31.40), (31.50, "running it all", ""),
    (32.60, "is a week of work,", ""), (33.80, "so I automated", ""), (34.60, "*almost all*", "big"),
    (35.40, "of it.", ""), (35.90, "it isn't", ""), (36.40, "*less* work.", "strike", 37.20),
    (37.30, "it's new work.", "", 38.30),
    (38.40, "sponsorships,", ""), (39.20, "courses,", ""), (39.85, "digital products:", ""),
    (40.95, "every other stream", ""), (41.75, "went *up.*", "big", 42.65),
    (42.75, "the revenue grew,", ""), (43.85, "but costs took", ""), (44.80, "a bigger slice.", "", 46.35),
    (46.50, "so the real question", ""), (47.35, "isn't how many", ""), (48.05, "views you get.", "", 49.10),
]

# ---- hook: readable from frame 0 over the first shot. fan (optional): a motif drawn from the source itself,
# here the report's three lines; band colours are names (accent, negative, positive, s1-s3)
HOOK = dict(
    eyebrow="Channel report · 2025", h1="my views went up.", h2="my revenue didn't.", off=3.600, shot_end=3.630,
    fan=dict(origin=(-30, 700), bands=[("views", "s1", 520, 90), ("streams", "positive", 640, 70),
                                       ("ads", "negative", 780, 80)]),
    tag=dict(text="2025 →", at=1.62, xy=(905, 438)),
)

# ---- behind the head (the cutout sits in front; keep ~70% of every letter readable, never cover the face)
WALL = ["memberships", "affiliate links", "workshops", "licensing", "brand deals", "consulting", "merch",
        "speaking", "paid community", "ebooks", "presets", "templates", "UGC", "tips", "masterclass", "audits",
        "1:1 calls", "newsletter ads", "podcast ads", "courses", "cohorts", "tools", "retainers", "events"]
BEHIND = [
    dict(kind="titles", items=[(10.18, "sponsors,"), (10.90, "courses,"), (11.48, "templates,"), (12.10, "coaching,")],
         end=12.62),
    dict(kind="wall", words=WALL, at=12.62, end=14.000),
    dict(kind="number", text="+16.7%", color="accent", at=23.40, end=25.900),
    dict(kind="phrase", text="who pays", color="accent", at=48.30, end="end", above=("it's", 48.10)),
]
# where the cutout plays: never across a picture cut or reframe
CUT_WINDOWS = [(10.067, 14.000), (23.300, 25.900), (48.000, "end")]

# ---- grade + camera
BW = [(3.630, 5.500), (30.033, 31.467)]                   # at most two: the heaviest beats
CAMERA = dict(punch=[(30.033, 1.12)],                     # "but here's the catch"
              pushes=[(3.900, 5.467, 1.035), (30.300, 31.400, 1.03), (46.433, "end", 1.055)],
              open=(1.04, 0.45))                          # settles on every visible cut are added automatically

# ---- cards: (id, file in public/, start, end, ground, what it shows). Built by card agents from cards/LIBRARY.md;
# light and dark alternate. A card's length is its frame count / 30.
CARDS = [
    ("c1", "cards/c1.mp4", 5.500, 10.067, "dark", "scissors: views +32.4%, ad revenue per view -11.5%"),
    ("c2", "cards/c2.mp4", 14.000, 16.500, "light", "the real report, the three numbers tagged"),
    ("c3", "cards/c3.mp4", 19.400, 22.300, "light", "counter-loupe: +1.6% from one viral video"),
    ("c4", "cards/c4.mp4", 26.000, 30.033, "dark", "doubling: 10K subscribers doubling every 4.5 months"),
    ("c5", "cards/c5.mp4", 31.467, 37.300, "light", "task-grid: a week of work as 100 tasks, 94 automated"),
    ("c6", "cards/c6.mp4", 37.300, 41.667, "dark", "lines-by-group: every other stream up, ads down"),
    ("c7", "cards/c7.mp4", 42.700, 46.433, "dark", "pie: revenue grows, costs take a bigger slice"),
]

END_CARD = None    # opt-in only: dict(q1=, q2=, src=[...]) when the creator asks for one

# ---- sound. Each sfx time is the moment the sound HITS (mix.py lines up its loudest point there).
# (time, name, gain dB[, max length]); a max length plays a run from its start (clicks-run).
SOUND = dict(
    music=None,                                   # none by default; "audio/<track>.wav" when the creator hands one over
    sfx=[
        (1.62, "shutter", -15),                   # the 2025 tag lands
        (3.63, "whoosh-deep", -17),               # cut to the black-and-white close-up on "it fell"
        (5.50, "whoosh", -14),                     # card: scissors
        (10.07, "whoosh-soft", -19),              # back to the speaker
        (10.18, "click", -17), (10.90, "click", -17), (11.48, "click", -17), (12.10, "click", -17),
        (12.62, "clicks-run", -15, 1.2),          # the wall fills
        (14.00, "shutter", -10),                  # the real report, a screenshot
        (16.50, "whoosh-soft", -19),
        (19.40, "whoosh", -14),                    # card: counter-loupe
        (22.30, "whoosh-soft", -19),
        (23.40, "drum-hit", -11),                 # +16.7% behind the head
        (26.00, "whoosh", -14),                    # card: doubling
        (30.03, "scratch", -8),                   # but here's the catch
        (31.47, "whoosh", -14),                    # card: task-grid
        (35.90, "click", -13),                    # "less" struck through
        (37.30, "whoosh", -14),                    # card: lines-by-group
        (42.70, "whoosh-deep", -16),              # card: pie
        (46.43, "whoosh-soft", -19),
        (48.30, "drum-hit", -13),                 # "who pays"
    ],
)
C1, C2, C3, C4, C5, C6, C7 = 5.500, 14.000, 19.400, 26.000, 31.467, 37.300, 42.700
# card sounds from each card agent's beat report: card start + beat time, same hit rule
CARD_SFX = [
    (C1 + 1.567, "riser", -15), (C1 + 1.833, "pop", -20), (C1 + 3.600, "whoosh-deep", -23), (C1 + 3.933, "pop", -20),
    (C2 + 0.80, "pop", -20), (C2 + 1.10, "pop", -20), (C2 + 1.35, "pop", -19),
    (C3 + 0.633, "clicks-run", -9, 0.6), (C3 + 1.733, "whoosh-soft", -23), (C3 + 2.033, "shutter", -16),
    (C4 + 1.700, "pop", -17), (C4 + 1.967, "tick", -11), (C4 + 2.233, "tick", -11), (C4 + 2.500, "tick", -11),
    (C4 + 2.767, "tick", -11), (C4 + 3.033, "tick", -11), (C4 + 3.300, "ding", -20),
    (C5 + 0.856, "clicks-run", -11, 1.5), (C5 + 3.700, "pop", -18),
    (C6 + 0.500, "pop", -20), (C6 + 1.200, "pop", -20), (C6 + 1.867, "pop", -20), (C6 + 3.867, "pop", -18),
    (C7 + 0.200, "pop", -17), (C7 + 1.433, "click", -11), (C7 + 2.467, "whoosh-soft", -24),
]

# ---- storyboard: what only the creator can send, and what a connected generator made (tagged so they can cut it)
NEEDS = [
    ("p05", "Screenshot of your real channel report (the revenue page), full window, so the c2 card shows the actual thing"),
]
GENERATED = []
