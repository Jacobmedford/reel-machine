# Signal

Signal is for proof, results and news: the numbers, the before and after, the "this just shipped" videos. It reads
like a news chyron built from the pack's own colours: ink Barlow 800 on accent slabs for every caption and the hook,
the key word set on a light chip, a mono proof line that says where the claim comes from, big League Gothic figures
behind the head, a punchier picture. Fast and confident, never loud: something lands every 2-3 seconds, the camera
zooms on the phrase that matters, the sound is dense but stays under the voice. It must never look like clickbait, a
crypto ad, or a red "BREAKING" template.

Built from Harbor: the same fonts and colours; what changes is the caption box (the accent), the text weight, the
grade, the pace and the sound. Colours are named by role (`kit/TOKENS.md`), with Harbor's colour in brackets. Build
it with `pipeline/pack.py build signal`; use it with `pipeline/pack.py use <project> signal` (or
`new.py ... --pack signal`).

## Type
- Text: Barlow Condensed 800 for captions, the hook and text boxes (labels and cards keep 700).
- Display: League Gothic in caps: figures and words behind the head, the thesis word.
- Mono: IBM Plex Mono 500: the proof line (the hook's eyebrow and the line above the head, set as a small light tag
  on the dark ground, like a news source bug, so it reads over a bright wall), every number on a card, sources,
  dates. Sentence case and letter-spaced, not caps.
- Accent serif: DM Serif Display stays available (`var(--font-accent)`, `.accent-serif`) for a card title's one
  word; never in captions here.

## Colour
- Harbor's roles: the accent (coral) is also the slab; light (cream), dark and ink (green-black), positive (sage),
  positive on light (deep green), hairlines (sand), negative (plum). On the light ground the accent is
  accent_on_light, as in Harbor.
- Slabs: `caption_box` and `textbox_bg` are the accent, `caption_ink` and `textbox_ink` are ink (4.8:1 in Harbor).
  Waiting lo-fi words are ink at 70% (3.1:1 in Harbor: they are read ahead, so they pass the 3:1 floor; at 45%
  `hyperframes check` flagged them at 2:1), lit words full ink.
- The one deliberate contrast variant: the slab is the accent colour, so "accent words inside the caption box" would
  read 1.0:1. That is by design: the accent word (`*word*`) is never accent on accent, it is set in ink on a light chip
  inside the slab (11.1:1 in Harbor). style.json's `checks` answers that check, so the build prints no warning for
  it. Do not "fix" it by changing the slab colour.
- Grade (style.json): `sepia(0) contrast(1.12) saturate(1.02) brightness(1) hue-rotate(0deg)`: more contrast, a
  touch more colour (more than that turned warm selfie skin red in tests), the same filter list as the kit's warm
  and moody looks.

## Captions
Accent slabs with ink Barlow 800, hi-fi 68px in 2-4 word phrases at y 1236, lo-fi 70px word by word (up to 3 words,
22 characters) at y 1318. On cards too: the slab is the caption, on every ground. One key word per caption, written
`*word*`: ink on a light chip. `thesis` is one word in League Gothic caps on a light slab (128px); `big` and `strike`
are welcome here (the strike bar is ink). Sentence case for every caption; League Gothic words are caps by design.

## Motion
Punchy. The hook's slabs land with a short overshoot, the second 0.12s after the first (in extra.css, so every
Signal hook does it). Entrances 0.15-0.25s, power3/expo out and back(1.6) on slabs; hard zooms on the phrase that
matters (`modes.hifi.camera: zooms`: no settles, the agent writes `CAMERA["zooms"]`); figures slam in; something
lands every 2-3 seconds. Transitions: zoom, push, drop. Never whip or spin (Harbor's rule).

## Sound
Dense (`sound.sfx: dense`): most visual events get a sound, always under the voice. Names are the kit's sounds
(`audio/SFX.md`); a creator's own sound stands in wherever one fits better.
- a figure or result lands: `ding` (the final value of a count) and, once per video at most, `drum-hit` on the
  biggest number.
- a slab, label or chip pops on: `click`; a chart point or list item: `pop` (alternate the two in a run).
- the before and after flips, the result shows: `riser` into it, `impact-low` on it.
- news coming in (a post, a release note, a screenshot of it): `shutter`; a click in a UI: `click`.
- a zoom or a hard cut: `whoosh-deep`; a card cutting in: `whoosh`.
- At most two sounds per event. Music none: the creator adds a track at post.

## Writing for this pack
- HOOK (hi-fi, `two-line`): the eyebrow is the mono proof line (where the claim comes from, parts joined with
  " · "), `h1` and `h2` are two short slabs, each under about 18 characters so each stays one line:
  `dict(eyebrow="12 tests · 30 days · one budget", h1="Same ads, half", h2="the cost per lead.", off=...)`.
- The hook is the kit's top layer, from y 236 to about 480: hold a WIDE framing under it until `off` (a CLOSE
  framing there puts the top of the head under the type). It never goes behind the head; for that, use an effect.
- BEHIND `number` for every figure (the accent colour, League Gothic), `phrase` with `above=` for a figure and its
  source line: the line above the head is set as the mono proof line here.
- Lo-fi BOXES are accent slabs: keep each line under about 26 characters.
- Every number on screen is real and sourced: the proof line says where it is from.

## Hi-fi
A produced take, WIDE and CLOSE, cut fast. Hook from frame 0: the proof line over two accent slabs. Captions in
phrases on accent slabs, the key word on a light chip. Behind the head: a League Gothic figure in the accent colour on
every number ("3x"), often. Full-screen cards often: the chart, the before and after, the release note, mono
kickers, the hero series in the accent. No black-and-white beats (the news stays in colour). Camera: hard zooms on
the phrase that matters. J-cut 0.15s (tighter joins).

## Lo-fi
Phone selfie. Word-by-word captions on an accent slab, waiting words in faded ink. The hook, chapter labels and the
call to action are accent slabs. Screenshots and screen recordings land on top often, with their source in a mono
line; hard zooms on the numbers. J-cut 0.15s.

## Showcase
Every beat proves something. The emphatic word or figure slams in whole (`emphasis_word: slam`) in League Gothic
behind the head. Transitions: zoom, push, drop. Dense. Motif: the proof stamp, every figure lands as a big League
Gothic number in the accent colour behind the head with its mono source line above it, the way the hook's proof line
reads.

## Never
- No em dashes on screen. Commas, colons, periods.
- No neon, no glow, no red "breaking news" bars, no tickers, no fake UI of a real news brand.
- The accent is the only accent: the slab is the accent, the chip is light, nothing else gets a colour.
- No unverified numbers. Every figure has its source.
- Captions in sentence case, inside the safe zone, never over the mouth; slabs never wider than x 100 to 980 near
  the bottom (the like and comment buttons).
- No hype words, fake urgency or "link in bio" bait.
