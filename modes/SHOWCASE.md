# Showcase: the edit that shows off

The third mode, next to hi-fi and lo-fi. Works on any footage, a 4K sit-down or a phone selfie: the footage only
decides FRAMES and the cutout. Set `STYLE = "showcase"`. The build uses the lo-fi type system (word-by-word captions,
text boxes, overlays, backdrops) plus `FX`: one hand-built motion graphic per beat, from `fx/LIBRARY.md` or new.
Reference: `examples/showcase/edit.py`.

The look is the creator's: `<project>/style/STYLE.md` (its Showcase section) and `modes.showcase` in `style.json`
decide how an emphatic word lands (stamp, slam or scale), which transitions the edit may use, how dense it gets and
what the motif could be (`kit/STYLE_PACK.md`). The lo-fi caption settings (`modes.lofi`) carry over, since showcase
uses the lo-fi type system. Where the pack and this file disagree, the creator's pack wins.

## The rule
Every beat shows off a different editing technique, and every technique is motivated by the words on it. The edit
does what the speaker says, on the word: "warms up" warms the picture, "magazine cover" puts them on a cover,
"tighter cut" cuts tighter, "huge" goes huge. A viewer should feel the range (kinetic type, masks, wipes, recursion,
grids, UI builds, camera moves) without it ever feeling random. Busy is the brief; slop is not. Showing off means
craft, not presets.

Still true: no gradients, glows, neon, glassmorphism, light leaks, lens flares, bokeh, emoji confetti, stock HUD.
Real artifacts over invented ones (the creator's files, screenshots, clips, headshot, the real storyboard, the
real raw take). Text on screen is their words or plain true labels. No imitation of a real brand's UI.

## Beat map (write it before any agent starts)
Read the transcript and give EVERY line a technique, no two adjacent beats the same kind. The menu is the library
(`fx/LIBRARY.md`); a new technique is welcome when a line asks for one. Then:
- **One motif** that recurs 3 or 4 times so the video feels designed, not assembled (a prompt bar that types each
  instruction, a sticker that tallies a count, a recurring frame). Same component, same position, same in and out
  move every time.
- **The hook** is the strongest beat: big type readable on frame 0 (it is the thumbnail), building on the words.
- **The payoff lines** get the literal treatment (the script says "bigger captions": the captions get giant).
- **A different transition on every picture cut** (`camera-transitions`: whip, zoom-through, spin, push, drop,
  reveal), camera moves only, 4 to 8 frames a side, never on a cut a graphic already covers. The creator's
  Showcase section can narrow the set.
- **Grades the script asks for** (`GRADES` + `grade-slider` / `mood-curtain` reveals), held until the next one.
- **Sound for every visual event**: each agent reports its SFX.

## Craft rules that came out of building it
- An emphatic single word (never, huge, always, zero) gets the creator's emphatic treatment, by default
  `word-stamp`: the display face, huge, stamped letter by letter behind the head so the head breaks it.
- Type over moving footage splits light/dark against the picture's own brightness (`kinetic-hook` builds the
  masks); never an outline.
- On a beat about the edit itself ("tighter cut"), go full frame and zoom; don't frame the picture in bars.
- Every video-in-video shows visible movement (the speaker AND the screen): pick moments by motion
  (`video-card/energy.py`), never a near-still. Speed-ups of 1.5-2.5x are fine to make movement read.
- "Lots of people are doing this" fills the grid with real screenshots of others doing it (the creator supplies
  them) and keeps the speaker live in the centre tile.
- A shot that runs into the speaker leaning in to the phone or reaching for the record button ends on the word:
  shorten that one join's J-cut with `J_LEADS` instead of moving KEEP.

## Layers and contract
`kit/FX_BRIEF.md` is the contract every FX agent reads (fx.html + fx.js per `fx/<id>/`, layers behind / cam / top /
over, determinism, footage copies, the `hyperframes check` rules that gate the render). `KARAOKE = dict(huge=[...],
hide=[...])`: `hide` windows hand the words to an effect (`giant-captions`, `word-stamp`). Image floats
(screenshots) work in BEHIND `float` like videos.

## Workflow differences from hi-fi and lo-fi
- Step 4 is **FX agents** instead of card agents: group the beats into 4 to 8 agents by technique (kinetic type;
  the motif; UI graphics; covers and file drops; footage tricks; grades and transitions; the close), each with its
  own sandbox (`pipeline/fxsandbox.py`). Each brief: FX_BRIEF.md, the library entries to start from, ids, layers and
  windows, the words with output times, where the head is in that shot, the real assets, and "report frames, SFX,
  edit.py changes, snapshot paths". No subagents: build the beats one after another yourself, same brief.
- Review every still at full size before merging; send fixes back to the same agent. Merge each agent's `frames`
  into its FX entry and its SFX into `SOUND.sfx`.
- The storyboard counts each FX with a note as a beat; an FX without a note (transitions) stays out of the beat list.
- The cutout matters more here (things sit behind the head often): `pipeline/matte.py` after `setup.py --matte`
  gives smoother edges than `cutout.py`.

## Sound
Much denser than hi-fi: one sound per visual event (100+ in a minute is normal), each placed at the time of its
event (mix.py lines up the loudest moment), 5 to 14 dB under the voice. Ticks per stamped letter, typing under a
typewriter, clicks on sends, pops on tiles, low hits on stamps, whooshes on transitions. Music stays off unless the
creator hands over a track.
