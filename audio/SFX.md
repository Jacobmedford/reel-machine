# Sound effects

Every file in `sfx/` was synthesized from scratch by `make_sfx.py` (numpy and scipy: sine waves, filtered noise,
envelopes, fixed seeds). No samples, recordings or third-party sounds went into them.

**License: CC0 1.0 Universal.** The sounds are dedicated to the public domain
(https://creativecommons.org/publicdomain/zero/1.0/). Use them anywhere, commercially or not, no credit needed.

Format: 48 kHz, 16-bit, stereo WAV. Every file peaks at -3 dBFS, so set the level per placement in the mix.

**Peak** is the time from the start of the file to the start of its loudest 10 ms window (most energy, both
channels), measured from the rendered file.
`pipeline/mix.py` lines that moment up for you: give it the time of the visual event, not the file's start.

**Start at** is a gain (dB) that sits the sound under a voice mixed to -14 LUFS, from a finished edit. Go
quieter for a dense edit. `sound.sfx: light` in the style pack sits every effect 3 dB lower.

| File | Sounds like | Use it when | Start at (dB) | Length (s) | Peak (s) |
|---|---|---|---:|---:|---:|
| `whoosh` | A dark air pass-by: swells, sweeps up as it passes and falls away, moving left to right | a card or graphic cuts in | -14 | 1.00 | 0.541 |
| `whoosh-soft` | A lighter, airy pass-by with a soft low body, moving right to left | cutting back to the speaker | -19 | 0.80 | 0.423 |
| `whoosh-deep` | A heavy whoosh: a sub that rises into the pass and sinks after it, low-mid air on top | a heavy beat, a zoom, a hard cut | -16 | 1.10 | 0.446 |
| `whoosh-long` | A 2.4 s build of rising, narrowing air and sub that peaks and drops away, widening as it grows | building into a big transition | -12 | 3.00 | 2.413 |
| `pop` | A short round bubble pop, pitch flicking up from about 440 Hz to 1 kHz, in a tiny room | a chart point, tag or list item lands | -19 | 0.22 | 0.001 |
| `click` | A crisp, rounded UI click with a faint second tap | a UI click, a text box appears | -16 | 0.12 | 0.002 |
| `tick` | A light, bright tick, shorter and higher than the click | one tick of a counter or clock (repeat it per tick) | -11 | 0.09 | 0.002 |
| `clicks-run` | A steady run of mechanical clacks, about 19 per second, first clack slightly accented | a grid flipping, a counter rolling; trim it to the motion | -12 | 2.50 | 0.002 |
| `key` | One keystroke: a soft click with a little body, and a light release click 70 ms later | a single key, an enter press | -18 | 0.12 | 0.002 |
| `typing` | 2.5 s of keyboard typing, about 10 keys a second in words, with a heavier space bar between them; no accent | under on-screen typing: place it by its start and trim it to the text with max_len | -11 | 2.50 | 1.228 |
| `ding` | A clean bell-like ding at 1.76 kHz with a soft octave shimmer and a 1 s ring | a counter lands on its final value | -20 | 1.40 | 0.002 |
| `shutter` | A two-stage camera shutter: clack, then a lighter clack 60 ms later | a screenshot or photo appears | -14 | 0.20 | 0.002 |
| `stamp` | A rubber stamp slam: short low thump with a paper slap on top | a stamp, a verdict, an APPROVED lands | -12 | 0.45 | 0.007 |
| `impact-low` | A short bass hit, 150 Hz dropping to 46 Hz, with a soft knock on the front | a punchy accent, a word or number hits | -14 | 0.80 | 0.007 |
| `boom-low` | A long sub boom that swells in over 0.15 s and rings down over about 2.5 s, 78 Hz sinking to 36 Hz | under a big moment or reveal | -17 | 3.00 | 0.147 |
| `riser` | A 1 s rising sweep (air, a two-voice tone and sub) that cuts off at its top | the second before a hit or reveal | -14 | 1.00 | 0.963 |
| `riser-long` | A 3.5 s suspense rise: a detuned chord climbing two octaves with a quickening pulse, air and sub | building tension before a reveal | -12 | 3.50 | 3.455 |
| `drum-hit` | One big low drum (taiko-like) in a room | the biggest number in the video | -12 | 1.45 | 0.006 |
| `scratch` | A short record-scratch gesture: forward, back, forward | "but here's the catch" | -8 | 0.42 | 0.060 |
| `switch-off` | An electronic switch-off: a stuttering buzz and static that collapses into a falling tone | a screen cuts out, a glitch-out | -12 | 0.40 | 0.004 |

Regenerate (writes the files and this table): `PY audio/make_sfx.py`.
Add `--review` to draw `dev/out/sfx_review.png`, an envelope and spectrogram per file.
