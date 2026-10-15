# Presets: approved effects and cards, ready to reuse

A preset is a finished effect or card with every per-video value pulled into one block of constants, so a new video
uses it by setting those constants instead of rebuilding it: one command instead of an agent rebuilding the effect
from the library, turn by turn.

Two libraries, read in this order:

- **the creator's**: `HOME/presets/` (or `$REEL_MACHINE_PRESETS`, else `$REEL_KIT_PRESETS`): effects they approved in
  their own finished videos.
- **the kit's**: `KIT/presets/` (this folder): the common devices below, ready for any creator's footage and pack.

A name found in both comes from the creator's library, so a creator's own version of a device always wins.
`preset.py list` shows where each one comes from.

**Presets first.** For every beat, look here (and in the creator's library) before the kit's effect and card
libraries (`KIT/fx/LIBRARY.md`, `KIT/cards/LIBRARY.md`). Build a new effect only for a beat no preset fits, at most
two new effects a video.

## Use one

```bash
PY KIT/pipeline/preset.py list                       # both libraries: where each preset comes from, kind, layer, length
PY KIT/pipeline/preset.py show stamp-strike          # what it does, its inputs, every constant and its default
PY KIT/pipeline/preset.py add <project> stamp-strike --id apps --at 3.9 --end 6.6 \
    --set 'STAMPS=[{"text": "MEETINGS", "x": 46, "align": "left"}, {"text": "EMAILS", "x": 1034, "align": "right"}]' \
    --set 'T.stamp=["meetings", "emails"]' --set T.strike.0=nothing --note "MEETINGS and EMAILS stamp, struck on nothing"
```

`add` copies the preset to `fx/<id>/` (a card to `cards/<id>/`, with the project's pack files), writes the values into
the block and nothing else, fills the static HTML that has to carry a constant, runs the generators (masks, timelines,
captures) against the project's own footage, and prints: the entry to paste into `edit.FX` (or `CARDS`, or a lo-fi
list), the other edit.py lines it needs (CUT_WINDOWS, GRADES, CAPS gaps), and its sounds at this window's real times
for `SOUND.sfx` / `CARD_SFX`.

- `--set KEY=VALUE`: VALUE is JSON (`380`, `true`, `null`, `[1, 2]`, `{"a": 1}`), anything else is a string (`\n` is
  a line break). `KEY.field=` sets one field, `KEY.0=` one list item. A wrong name, field or type stops with the
  valid ones.
- **Beats key on words.** In a cue constant (`T`, `HANDOFF`) a beat is seconds after the window start, or a spoken
  word: `"nothing"` is the first "nothing" at or after the start, `"nothing-0.05"` nudges it; in a list each word is
  looked for after the one before (and from the start when it isn't said again). `add` checks every word against
  words.json and prints the table of real times. Transcripts can run a word 0.05 to 0.3 s late: nudge.
- `--replace` renames the old `fx/<id>/` to `<id>-before-preset-<date>` (never deleted). `--no-gen` skips generators.
- Each instance carries `PRESET.md` (where it came from, the command to make it again).
- Ids are HTML ids in the composition: `add` refuses the composition's own (`hook`, `caps`, `cam`, `v`, `root`, ...),
  whose pack CSS would land on the effect. Name instances after the beat (`apps`, `cover`, `hook1`).
- Generators refuse to run in a library; run the instance's copy when the cut, the window or the footage moves.

## The library

| preset | use it when | layer | length | inputs |
|---|---|---|---|---|
| `hook-front` | the hook, when one true fact sells it: a small proof line over the hook ("3 takes · 2:40 · edited by Claude"), knocked out wherever the head is; line one big behind the head on frame 0 (the thumbnail) | top | the hook's window (2.9 s) | LINE (true facts) or `[]`; OPEN for frame 0 (OPEN_UNTIL_FRAMES 0 drops it); keep BAND clear of the hook's own lines; mkmask.py makes the masks |
| `stamp-strike` | things the speaker doesn't use or need ("no meetings, no emails, nothing else"), struck on the negation; a callback later | behind | 2.7-3.4 s | STAMPS (word, x where they point, align), stamp and strike beats; CUT_WINDOWS; SPLIT false on a handheld shot; mkmask.py makes the wall mask |
| `grade-slider` | a look change the line asks for ("a touch warmer"), before/after through the face | cam | 2.1 s | LOOK (a LOOKS name or a CSS filter), the face path on stills, nudge and sweep words; GRADES from B |
| `mood-curtain` | a look that should drop like a curtain ("make it moody", "and then it goes dark"), grain and vignette after | cam | 5.6 s | the cue word; GRADES for the new look from the curtain's first frame |
| `nle-timeline` | the video about its own edit ("you'd think this took hours in an editor"): this video's own timeline floods in and folds away | top | 3.1 s | nothing by hand (gen.py draws it from the edit); rerun gen.py after pasting the entry and after the mix |
| `odometer-recursion` | the raw length against the cut ("hours of takes became minutes"), then the frame recurses and dives | cam | 3.1 s | RAW and FINAL (true m:ss), four level words, PLATE and FOCUS on bare wall; end on the cut |
| `giant-captions` | a payoff about the captions or size: the caption box goes giant, slams, covers the frame, hands back | over | 4.7 s | the words and beats, NEXT = the next CAPS caption's exact text; no CAPS inside; hi-fi only |
| `wall-window` | a video or recording the viewer can get ("here's the full version"): a window on the wall plays a clip | behind | 3.5 s | LABEL, a true TAG, WIN on bare wall, the clip (SRC, MEDIA_START), open word; CUT_WINDOWS |
| `card-raw-ledger` | raw footage against the cut: every take to scale, the bad takes struck and quoted, collapsing into the cut | card (light) | 4.3 s | BAD (take, span, words as said) or `[]`, beats; gen.py writes the takes, waveforms, thumbs; render the card |
| `card-storyboard-note` | the storyboard and notes loop: a real storyboard beat, a note, the answer, the beat updates | card (dark) | 4.6 s | CAPTURE (`""` = this project's storyboard, three beats), FRAME, NOTE, NAME, CAPTION; the capture (heavy) and frame.py; render the card |
| `text-box` | lo-fi: the hook box from frame 0, a numbered label on each section, the CTA box held to the end | BOXES | 2.4-5 s, CTA to the end | TEXT, ROLE (hook, label, cta) |
| `overlay-stack` | lo-fi: real pages on top of the speaker in one slot above the eyes, each taking over on its word | OVERLAYS | 1.7-3.8 s an item | ITEMS (real captures in public/media, true notes), HANDOFF beats; bottoms 15 px above the eyes |
| `captions-huge` | lo-fi: one line of captions comes in huge (124 px, two words a line) | KARAOKE huge | 1-2 s | the window of the line |

`stamp-strike` can run twice in one video: the words, then a callback to one of them later (see `examples` in its
preset.json). Every constant's default is an example: set the creator's own words, facts and places.

**Modes.** `giant-captions` reads the hi-fi caption box, so it is hi-fi only; `odometer-recursion` is a showcase
piece. The three devices are lo-fi (also showcase). Cards are full-screen compositions: render them (`add` prints the
command) before the final build.

**Packs.** Every preset reads only tokens (`var(--c-*)`, `var(--font-*)`, `--font-accent` with the display face as
its fallback, `--font-caption` with the text face as its fallback) and the kit's own caption box, and fits big type to
the pack's faces (lines set smaller rather than run off the frame or stay in a slot), so it renders in any pack.
`preset.py lint` refuses a literal colour, a font name, an em or en dash, a leftover per-video time warp, or a space
letter that lost its no-break space (a two-word line set as letters would close up).

**Masks and generators.** Nothing in this library was made from anyone's footage. A mask ships as its generator's
neutral sheet (`--blank`: light type only, nothing knocked out); `add` runs the generator against the project's own
clean.mp4 and cutout and writes the real masks into the instance. When a generator fails, its fallback writes the
neutral sheet again and `add` says so. The grain tile is seeded noise (`make_grain.py`).

## Make a new preset (after the creator approves a new effect)

1. Copy the approved folder to the creator's library, `HOME/presets/<name>/` (never a project's own files in place).
2. In fx.js (a card: its index.html script), put every per-video value in one block, one JSON value per line:
   `// PRESET CONSTANTS START` / `var NAME = <JSON>;   // what it is` / `// PRESET CONSTANTS END`. Beats go in a
   constant listed in `cues`, resolved once with the `cues()` helper the other presets carry (`T = cues(T);`).
3. Static HTML that must carry a constant uses `[[NAME.path]]` (preset.py fills it); cards bind `[[@DUR]]`,
   `[[@FRAMES]]`, `[[@AT]]` (their window). Generators read their settings from the block and take `--at/--end`.
4. Write preset.json (name, kind, layer, from, source, does, use_when, inputs, constants = the block's defaults, notes,
   cues, lengths, generators, needs, sfx, typical_length, modes, signature, pairs_with) and run
   `PY KIT/pipeline/preset.py lint <name>` until it is clean. To change a kit preset, copy it into the creator's
   library under the same name: theirs is used from then on.
