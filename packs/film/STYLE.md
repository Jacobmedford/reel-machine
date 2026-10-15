# Film

Film is for stories: the reflective videos, a lesson learned, the "here's what actually happened" ones. It should
feel like a short film, not an ad: the picture faded like film stock (lifted blacks, a tint in the shadows, warm
mids), fine grain that moves, a soft vignette, and type that sits in the picture instead of on top of it. Light words
with a soft shadow, no caption box, one accent-serif word per line in a faded accent. Calm: the camera settles,
things fade and rise, the sound stays light. It must never look like a template "cinematic" filter, a light leak, or
a sad-music edit.

Built from Harbor: the same fonts and colours, except the accent, the caption treatment, the grade and the pace.
Colours are named by role (`kit/TOKENS.md`), with Harbor's colour in brackets. Build it with
`pipeline/pack.py build film`; use it with `pipeline/pack.py use <project> film` (or `new.py ... --pack film`).

## Type
- Accent: DM Serif Display (`var(--font-accent)`), mixed case, never caps. It carries this pack: the hook's big line,
  the one accent word in a caption, the thesis word, words behind the head, the first line of a lo-fi text box.
- Text: Barlow Condensed 600 for captions and the hook's small line (lighter than Harbor's 700: it reads calmer);
  labels and cards keep 700.
- Display: League Gothic, only for big figures behind the head (`number`) and card numbers. Words behind the head
  are in the accent serif here, not League Gothic.
- Mono: IBM Plex Mono 500 for numbers, kickers and the hook's eyebrow (sentence case here, not caps).

## Colour
- Accent: a faded accent (in Harbor, the coral lightened toward cream so it sits in the film grade: 8.2:1 on the
  dark ground, 42 delta E from the negative). On the light ground it is accent_on_light, as in Harbor. A recolor gives
  this role the creator's accent as it is: lighten it by hand in style.json if it should stay faded.
- Everything else is Harbor's. The caption box token keeps Harbor's colour for any effect that draws a box (no
  caption on the picture uses it).
- Grade (style.json): `sepia(.3) contrast(.88) saturate(.84) brightness(1.03) hue-rotate(0deg)`, the same filter
  list as the kit's warm and moody looks so GRADES fade between them. On top of the picture (extra.css, footage
  only): positive_on_light (deep green in Harbor) in soft light at 36% (a tint in the mids and shadows), the same
  colour mixed with the dark ground in screen at 38% (the blacks lift to a tinted floor while skin stays warm), grain
  at 32% overlay, clumped about 2px so it survives a phone's video compression, that changes every two frames, and a
  vignette. Cards, captions and graphics are never graded or grained.

## Captions
No box. Light Barlow Condensed 600 with a soft dark shadow (it is what makes them read on a light wall, it is not a
glow). Hi-fi 60px in 2-4 word phrases at y 1236; lo-fi 66px, the whole line lands at once
(`modes.lofi.captions: phrase`, no dim waiting words) at y 1318. Sentence case. One accent word per caption at most,
written `*word*`: it is set in the accent serif at 1.18x in the faded accent. `thesis` is one word in big light
accent serif (104px). On cards captions are plain ink or light, as in Harbor. Big and strike are rare here.
The deliberate variant: with no box, a caption over a light shirt or a bright wall can measure just under 3:1 in
`hyperframes check` (it ignores the shadow: a lo-fi test take gave one warning, 2.93:1, on a grey-green shirt). It is
a warning, the render passes and the line reads on a phone; when a whole stretch sits on something bright, frame
tighter so the caption band lands on a darker part of the picture rather than adding a box.

## Motion
Calm. Entrances 0.3-0.5s, power2/power3 out, things rise 20-30px and settle; the camera settles on cuts, slow pushes
on the heavy lines, no hard zooms, no whips. Something new every 4-6 seconds is enough. The grain is the only thing
that moves all the time.

## Sound
Light (`sound.sfx: light`: the mixer sits every effect 3 dB lower). Only the big beats get a sound. Names are the
kit's sounds (`audio/SFX.md`); a creator's own sound stands in wherever one fits better.
- a reveal or the payoff: `riser` into it, or `boom-low` under it, low; the line that lands the lesson: `ding`, low.
- a text line or label appears: `click`, low; typing on screen: `typing`, trimmed with max_len.
- a cut to a card or back: `whoosh-soft`, or nothing (Film often lets the cut breathe).
- Never: `scratch`, `switch-off`, `drum-hit`, stacked hits. Music none: the creator adds a track at post.

## Writing for this pack
- HOOK (hi-fi, `modes.hifi.hook: two-line`): `h1` is the big accent-serif line, short (under about 16 characters
  fits one line at 124px; two lines balance), `h2` is the small Barlow line that finishes the sentence. Split the
  first sentence where it turns: `dict(h1="I almost quit", h2="the week it finally worked.", off=...)`. An eyebrow
  is optional and quiet mono, sentence case.
- The hook is the kit's top layer, from y 236 to about 470: hold a WIDE framing under it until `off` (a CLOSE
  framing there puts the top of the head under the type). It never goes behind the head; for that, use an effect.
- BEHIND `titles` and `phrase`: write the word in lower or sentence case ("nothing", not "NOTHING"): it is set in
  the accent serif. `number` stays League Gothic. Colour `light` for words, `accent` for the one that matters.
- Lo-fi BOXES are paper slips (the text box tokens: light ground, ink): the first line in the accent serif, the next
  lines in small Barlow. Keep the first line under about 30 characters so it stays one line.
- Accent words: one per caption, the word that carries the feeling, not the number.

## Hi-fi
A sit-down story take, WIDE and CLOSE on the turns. Hook from frame 0: the big accent-serif line over the small
Barlow line, no box. Captions in phrases, one accent-serif word in the faded accent now and then, a light
accent-serif thesis word on the line to remember. Behind the head: one accent-serif word on the turn of the story,
now and then (`sometimes`). Cards sometimes, on the light or dark ground, kicker in mono, title with one accent-serif
word. One black-and-white beat on the heaviest line, held a little longer than in Harbor. Camera: settle on every
cut, a slow push on the last line. J-cut 0.3s.

## Lo-fi
Phone selfie, the speaker never leaves frame. Captions land a line at a time, light, no box. The hook, chapter labels
and the call to action are paper slips: a light ground with ink type, the first line in the accent serif, the rest in
Barlow (a selfie puts a cap or the hair right where they sit, and light type cannot read on it, so these keep a
ground). Screenshots and photos land on top sometimes, the quiet way (a fade-rise, no pop). No hard zooms. J-cut
0.3s.

## Showcase
The story edit with one crafted move per beat, never busy (`density: medium`). The emphatic word scales up from small
in the accent serif behind the head (`emphasis_word: scale`). Transitions: push and reveal only. Motif: the title
line, one accent-serif line that sets itself like a film title over the opening shot and comes back in the same size
and place over the last one.

## Never
- No em dashes on screen. Commas, colons, periods.
- No neon, no glow, no light leaks, no lens flares, no film-burn transitions, no fake scratches or dust.
- The accent is the only accent (faded on the picture, the darker shade on the light ground). No second accent
  colour.
- Captions in sentence case, inside the safe zone (y 1236 hi-fi, 1318 lo-fi), never over the mouth.
- Grain and grade on the footage only: never on cards, captions or graphics.
- No hype words, fake urgency or "link in bio" bait; no unverified numbers on screen.
