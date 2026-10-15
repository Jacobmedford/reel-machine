# Hi-fi: the produced talking head

For a sit-down take, ideally 4K and locked off. The video cuts between two framings of the one take, type lands
behind the speaker's head, and full-screen motion-graphic cards carry the numbers. Set `STYLE = "hifi"` in edit.py.
Reference: `examples/hifi/edit.py`.

This file is the structure and its defaults. The creator's pack decides how hi-fi looks and edits for them:
`<project>/style/STYLE.md` (its Hi-fi section) in words, `style.json` in values: the look (fonts, colours, caption
treatment, grade, pace) and `modes.hifi`: the hook shape, how captions are cut, how often things go behind the head
and how often a card carries a beat, the camera (settle, zooms or still), black and white or not, the J-cut lead
(every field: `kit/STYLE_PACK.md`). Read both before writing edit.py. Where they and this file disagree, the
creator's pack wins.

## The rule
Motion graphics carry the story, built from real artifacts first: the source (article, study, post), real
documents and screenshots, scans of real objects, and what the creator sends (B-roll, screen recordings). Restraint
is the design. If a beat can be told with type and a hairline chart, it is.

Generated imagery (only when the creator has a generator connected) is the exception, for a beat that needs an
image nothing real can give: objects, places and textures that look shot. Never generated people, portrait walls or
generated B-roll as the look of the video. Every generated asset is made before the storyboard and tagged there,
so the creator can cut it before anything renders.

## Edit
- One take. Dead air trimmed between lines (keep ranges from silencedetect -35 dB), the last clean take of each line.
- J-cuts on every join: the voice leads its picture by 0.30s.
- Two framings from one camera: WIDE (full height) and CLOSE (about 1.6x on 4K, 1.25x on 1080p). Reframes hide
  under cards; the visible ones are deliberate (the turn, the last line).
- Lip sync is proven twice: before encoding (`cut.py`, every piece reads the same source second as its audio) and
  after rendering (`qa.py`, rendered frames matched against the source).
- Camera: a settle (scale 1.045 to 1 over 0.32s) every time the talking head comes back or cuts; a punch-in
  (1.12 to 1) on the turn ("but here's the catch"); slow pushes (to 1.03-1.055) on black-and-white beats and the
  last shot. Nothing else moves the camera.
- Black and white (grayscale, contrast 1.2, brightness 0.9) only on the heaviest beats, at most two per video.
- Cards hard-cut in and out on word boundaries. No wipes, dissolves or zoom transitions between shots.
- Grade: `style.json` `grade` (a CSS filter) over the whole video.

## Pace (style.json `motion`)
- **calm**: the values above; card entrances 0.35-0.5s; a behind-head moment or card every 6-10s.
- **normal**: entrances 0.25-0.4s; punch-ins on two or three key lines, not just the turn; something new every 4-6s.
- **punchy**: entrances 0.2-0.3s; hard zooms (`CAMERA.zooms`) on the phrases that matter; `big` captions more
  often; something new every 2-4s. Cards still hard-cut; pace never means transitions.

## Type: three voices, never swapped
- **Display speaks**: the hook's second line, thesis words, words behind the head, big figures.
- **Text informs**: captions and labels.
- **Mono measures**: every number, unit, year, axis, kicker, footnote.
Which faces those are is the creator's (`fonts` in style.json).

## Colour: fixed meanings, the creator's values
- **accent**: emphasis, the thing to look at, the hero line in a chart.
- **negative**: losses, down, "no". **positive**: gains, up, "yes".
- **light / dark**: the two grounds; **ink**: text on light.
Cards alternate light and dark grounds through the video.

## Captions
- 2-4 word phrases, in on the first word, held until the next phrase.
- On footage: the caption treatment from the pack (`captions.hifi`: box or plain, size, case), centred at y ~1236.
- On cards: the same type without the box (ink on light, light on dark).
- `*word*` for the words that matter (accent). `big` (84px, 800) for numbers and quantity phrases ("almost all",
  "60 cents").
- `thesis`: one word in the display face at 112px, accent colour, that carries the beat ("boom", "the catch");
  about five per video.
- `strike`: an accent bar strikes the word, for negation ("isn't *unemployment*").
- No captions where words behind the head already say it.

## Behind the head
The speaker cutout sits in front in short windows that never span a picture change. Keep about 70% of every
letter readable and never cover the face.
- **titles**: one display word per spoken word, 132px ("accountants, marketers...").
- **wall**: small mono words fill the wall around the speaker ("and a ton more": 36 job titles). Text, not portraits.
- **number**: one 350px figure, accent or positive for gains ("15%"), negative for losses ("−10%").
- **phrase**: a 196px accent line ("the money"), with a text line above it ("it's who gets").
- More kinds when a beat calls for them (shapes in `pipeline/build.py`, `BEHIND`): **plate** (one real screenshot
  as the wall), **stack** (real screenshots dropping in as a deck, one per spoken item), **float** (the creator's
  own clips drifting up in framed windows), **cover** (a magazine-cover masthead the head breaks), **backdrop** and
  **list** (from lo-fi). Colours are always names: `accent`, `negative`, `positive`, `light`, `ink`, `s1`-`s3`.

## Hook
Readable from frame 0 over the first shot: a mono eyebrow (source and year), a text line at 60px, a display line at
94px in the accent (the contradiction). Off before the next caption. Optional: a motif behind the head drawn from
the source itself, and a mono tag ("2030 →").

## Cards
- Full screen, the pack's light or dark ground (graph paper when `grounds.grid` is on).
- Hairlines 1.5-3px, the pack's corner radius. No gradients, glows, shadows, emoji or clip art.
- Numbers in mono or display, never the text face. Lines draw, numbers roll, beats land on the spoken word
  (±0.05s). One slow camera push per card, frame 0 already complete.
- Content in x 70-1010, y 250-1150; the caption band y 1170-1430 stays empty; nothing to read below y 1470.
- Real artifacts welcome inside cards: screenshots of the source, scans of real objects.
- The patterns to start from are in `cards/LIBRARY.md`; the build contract is `kit/CARD_BRIEF.md`.

## End card
Off by default. Only when the creator asks: the closing line in the display face, the source line, their handle
or site from `style.json`.

## Sound
- SFX under every visual event, always under the voice (`audio/SFX.md` has the vocabulary): a whoosh on card cuts,
  pops on chart pings and tags, a click run on grids and flips, ticks on counters, a ding on a landing, a drum hit
  on the two biggest numbers, a scratch on the turn, a shutter on a screenshot, a low impact under a stamp, a riser
  under a big negative. `sound.sfx` in style.json sets the density (light, normal, dense).
- Music: none by default; the creator adds a track in their posting app. When they hand over a track (theirs or
  from a connected generator), cut it so two or three drops land on key lines; bed about 20 LU under the voice.
- Master -14 LUFS, -1.5 dBTP.

## Safe zones (Reels, TikTok, Shorts)
Top 220, bottom 450 (nothing below y 1470), sides 35, right 100 from y 1155.
