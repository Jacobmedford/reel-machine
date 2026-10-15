# Effects library (showcase)

Hand-built motion graphics for showcase videos. Every colour and font in them is a token from the creator's style
pack, so each one comes out in the creator's look. A new beat starts from the closest effect: copy its folder to
`<project>/fx/<id>/` (no renaming: `{{ID}}` becomes the id), change the constants at the top of `fx.js` (the words,
the cue words, the labels), and supply what the row says. The contract is `kit/FX_BRIEF.md`; the rules for using
them are `modes/SHOWCASE.md`.

`preview.jpg` in each folder is a frame from the kit's effects lab (`dev/fxlab.py`): a drawn stand-in figure (no
real person), the neutral pack, sample words. Placeholders in the effects (icons, headshots, screenshots, clips)
are labelled as placeholders; the creator's real material replaces them.

![All seventeen effects](../docs/img/effects.jpg)

| folder | layer | what it does | reach for it when the line says | supply |
|---|---|---|---|---|
| `kinetic-hook` (+ `kinetic-hook-front`) | behind + top | the hook: line one in the display face readable on frame 0, the creator's dark ground cuts in as line two stamps letter by letter (the head breaks it), sans lines push through masks on their words over the video's own running timecode, the last tracks in from wide; optional payoff slams in; the front copy carries line one over the speaker for the opening frames, split light/dark by per-frame masks | the first line, a claim about the video itself | the words and the cue word each beat lands on (fx.js constants); `kinetic-hook-front/mkmask.py <project>` rebuilds the masks from clean.mp4; end the front window on the frame the ground cuts in |
| `word-stamp` | behind | one emphatic word in the display face, huge, stamped letter by letter behind the head (the head breaks it), ink where it crosses a light part of the picture; a small line sets word by word above it and a negative stroke strikes it through | one emphatic word: never, huge, always, zero | the word, its line, their cue words, CENTER_X / Y on the head; `mkmask.py <project>` rebuilds the mask from the room behind the speaker |
| `giant-captions` | over | the caption box grows out of the caption band into a giant slab, a display-face line in the accent wipes open under it, optional word tiles and a slab that slams the last word; every slab folds shut before the end | "bigger captions", a payoff line | the words and their cue words; `KARAOKE["hide"]` over the window |
| `icon-strike` | top | icons pop on their names, a hand-drawn stroke strikes each (flinch, grey), they drop with gravity, one word rises where they were | "no X, no Y, nothing" | the words; token placeholder tiles, or real app icons fetched into the project's copy with `icons.py` (never committed); `INK` light or dark for the footage |
| `prompt-bar` | top | the motif: a pill opens into a bar, types the instruction on the words, sends (press, ring, SENT), a line runs, the result rolls in (DONE, check), closes back to the pill | every time they say what they told the AI to do | the sentences; `gen.py` writes every appearance from one BEATS table so the motif is identical each time |
| `comment-thread` | top | a storyboard beat card pops in, a pin with the headshot drops onto a word, the note types into a comment, a reply ("On it.") slides in, an underline lands on the word | "I leave a note", "I just explain what I want", feedback loops | the note, the reply, the beat's line and marked word; the creator's headshot (`HEADSHOT`), optionally two beat stills |
| `comment-cta` | top | the CTA text box holds to the end; a comment field types the keyword on the word and posts, the reply card (headshot, handle) answers word by word, a like, the thread folds into the box; optional Follow chip on "follow" | the CTA | the keyword, the CTA lines, `HANDLE`, `HEADSHOT`; `FOLLOW_ON` for the chip |
| `grade-slider` | cam | a before/after slider tilted 8 degrees splits the frame through the face (BEFORE / AFTER), then sweeps the new look across on the cue word; GRADES takes over at the end | "make it warmer", "it warms up", any look change | a GRADES entry for the look starting at the effect's end (LOOK = its name or a CSS filter) |
| `mood-curtain` | cam | on the cue word the moody look falls top-down like a curtain (the previous look lifts away, a light hem on its edge), then grain and a vignette hold | "make it moody", "the colours go dark" | a GRADES entry for the new look starting between the effect's start and the cue; `grain.png` is made by `make_grain.py` |
| `odometer-recursion` | cam | a mechanical counter rolls the raw take's length down to the finished length, then the frame recurses into itself four levels deep, one level per word, and dives through | "a few minutes later", "this is the video", "exactly what you're seeing now" | the two true lengths (m:ss); the levels are synced copies of clean.mp4 |
| `grid-collapse` | cam | the frame shrinks into the centre tile of a 3x3 grid, eight tiles pop in from the centre out, on the cue word they fall away and the speaker snaps back full frame | "lots of people do this" | 8 real screenshots of others doing it (9:16, headlines readable) replacing the placeholder cards |
| `video-card` | top | a card unfolds, play presses on the word, chapters skip with a moving clip in each (scrubber fills, label rolls), the card folds back into its centre | "I recorded a video walking you through it", a walkthrough or course | clips of the real walkthrough picked by motion with `energy.py` (it cuts them and prints the tags), the title and chapter names |
| `camera-transitions` | over | a different camera move on every picture cut (whip with motion blur, zoom-through, spin, push, drop, reveal), keyed on the footage wrapper so timing and zooms are untouched, overscaled so no corner shows; a cut another full-frame effect starts on is left to that effect | every picture cut | nothing: MOVES (which, in order, cycling; the creator's `modes.showcase.transitions`), SKIP, STRENGTH per move |
| `magazine-cover` | behind | a full cover behind the head: the frame draws, the masthead drops letter by letter in the display face (the head breaks it), dateline, barcode, coverlines on the words, a sticker slaps; all type splits light/ink against the picture | "looks like a magazine cover", "the titles" | true masthead and coverlines (constants); LAYOUT measured on a still (baseline about 60 px under the top of the head); rerun `mask.py` per shot; a CUT_WINDOWS entry |
| `file-drop` | top | a dashed drop zone, the file card falls in on "drop", opens into a player of the raw footage, BAD TAKE stamps slam on the words | "I just drop in the raw footage" | `facts.py <raw file>`: the card's facts (ffprobe) and thumb.jpg; `--clip`: raw.mp4 of filler the edit cut |
| `nle-timeline` | top | an editing timeline of THIS video builds on the words (captions, effects by layer, cutout windows, the cut with thumbnails, transitions, keyframes, waveforms, SFX), a playhead tears across with a running timecode, it folds to a line | "I know nothing about editing", how much work an edit is | nothing by hand: `gen.py` regenerates it from edit.py, timeline.json, words.json, the voice and clean.mp4 (rerun after the mix and any effect change) |
| `page-scroll` | top | a window card slides up with a page, two scroll flicks like a screen recording, one push into a section whose rows light and underline on the words | showing a real document or page, "here is the plan it made" | `capture.py` on the project's storyboard or a URL (prints TILES) plus LIT rows measured on page-full.png; without them, a placeholder plan from the video's own lines |

## Rules that came out of building these
- `hyperframes check` gates the render: every `<video>` needs an id (else it renders frozen), no tweening layout
  props (left, top, letterSpacing: use x / y / scale), no CSS `transform` on an element GSAP tweens, overlap and
  occlusion allowances on the text elements themselves.
- Media timing is written with `{{START+x}}`, `{{SYNC+x}}`, `{{DUR}}` / `{{DUR-x}}` (the build fills them in), so
  a copied effect times itself. Footage copies are frame-identical to the main picture (proven by pixel diff in the
  lab). Hide a copy with opacity, never `visibility`.
- Type over footage splits light/dark against the picture (masks), never an outline. Text fitted after the pack's
  fonts load keeps its fx.html size as a maximum and only shrinks.
- `clip-path` tweens use `fromTo`; a `.to` jumps.
- A snapshot taken exactly on a cut can show the previous frame; check transitions at mid-frame (cut + k/30 + 0.012).
- Generators live next to the effect (`gen.py`, `mkmask.py`, `energy.py`, `icons.py`, `make_grain.py`): rerun them
  when the cut moves. They refuse to write into the library folder itself.
