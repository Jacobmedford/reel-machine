# Terminal

Terminal is for builds and screen recordings: the speaker at the keyboard, coding tools and agents doing real work,
the steps to copy. It reads like a clean shell session: captions are command lines (IBM Plex Mono in a dark box, a
prompt mark in the positive colour, the key phrase in the accent), the hook is a terminal window that types the
command and prints the line the speaker says, and the picture is a touch cool and desaturated so the screens carry
the colour. Normal pace and sound. It must never look like a hacker movie: no green-on-black matrix, no scanlines, no
glitch filters, no fake code.

Built from Harbor: the same fonts and colours; what changes is the caption face and box, the lo-fi caption face
(`fonts.caption` is IBM Plex Mono), the grade and the hook. Colours are named by role (`kit/TOKENS.md`), with
Harbor's colour in brackets. Build it with `pipeline/pack.py build terminal`; use it with
`pipeline/pack.py use <project> terminal` (or `new.py ... --pack terminal`).

## Type
- Mono: IBM Plex Mono 500 for every caption (both modes), the hook window, text boxes, kickers and numbers. Thesis
  words 600.
- Display: League Gothic in caps for words behind the head ("BUILD", "SHIP") and big figures.
- Text: Barlow Condensed 700 stays for card titles and labels (cards are Harbor cards).
- Accent serif: DM Serif Display stays available (`var(--font-accent)`, `.accent-serif`) for a card title's one
  word; never in captions here.

## Colour
- The box is the dark ground (green-black in Harbor) at 92%; its text is the light colour (cream), the prompt marks
  `›` and `$` are the positive colour (sage), the key phrase and the cursor the accent (coral); hairlines and the
  negative as in Harbor. On the light ground the accent is accent_on_light and the prompt mark positive_on_light
  (deep green).
- Contrast in the box (Harbor): light 11:1, accent 4.5:1, positive 4.6:1, the muted path 4.8:1. style.py reports no
  warnings.
- Grade (style.json): `sepia(0) contrast(1.05) saturate(.8) brightness(1) hue-rotate(0deg)`, desaturated, the same
  filter list as the kit's warm and moody looks; then positive_on_light (deep green in Harbor) in soft light at 32%
  over the footage (extra.css) moves the neutrals to the palette's cool side. A hue rotation cannot cool a picture
  (greys stay grey; it pushed skin red in tests), so the cool comes from the palette's own green. Cards, captions and
  screens keep their true colours.

## Captions
A shell line: IBM Plex Mono in the dark box with a `›` in the positive colour before it. Hi-fi 46px in 2-4 word
phrases at y 1236 (mono is wide: keep a caption under about 28 characters so the box stays inside x 100 to 980);
lo-fi 52px word by word (up to 4 words, 22 characters) at y 1318, waiting words in the faded light colour. The key
phrase (`*phrase*`, can be two or three words) in the accent. `thesis` is one word in accent-coloured mono 600 at
72px; `strike` for the tool it replaces. On cards the line is plain mono with the prompt mark, no box. Sentence case,
always.

## Motion
Normal. Things appear the way a UI does: type on, step in, a cursor lands; entrances 0.2-0.3s power3 out, the camera
settles on cuts, a punch-in on the command that matters. Screen recordings carry the motion; the graphics stay crisp
and flat.

## Sound
Normal (`sound.sfx: normal`): the visual events get a sound, always under the voice. Names are the kit's sounds
(`audio/SFX.md`); a creator's own sound stands in wherever one fits better.
- typing a command or a prompt: `typing`, placed by its start and trimmed to the text with max_len.
- enter, a click, a selection: `click`; one key: `key`.
- a step finishes, a check lands, the build passes: `ding`.
- output or a window pops in, a message comes back: `pop`.
- something breaks or errors: `switch-off`, short (max_len), rarely.
- a card cutting in: `whoosh`; back to the speaker: `whoosh-soft` or nothing.
- Music none: the creator adds a track at post.

## Writing for this pack
- HOOK (hi-fi, `two-line`): `eyebrow` is the path (the project's folder or the repo), `h1` the command (written
  without the `$`: the pack adds it), `h2` the output, the line the speaker says. The command types itself from 0.2s
  at 30 characters a second with the accent cursor on its end; at 1.15s the output prints and the cursor drops to the
  end of it. So frame 0 shows the window, the path and `$` with the cursor:
  `dict(eyebrow="~/code/landing-page", h1="npm run deploy", h2="Live in under a minute.", off=...)`.
  Keep h1 under about 36 characters and h2 under about 30 per line.
- The hook is the kit's top layer, from y 236 to about 500: hold a WIDE framing under it until `off` (a CLOSE
  framing there puts the top of the head under the type). It never goes behind the head; for that, use an effect.
- Lo-fi BOXES are small terminal windows: the first line gets the `$`, the last line the cursor. Keep lines under
  about 34 characters.
- BEHIND `titles` and `phrase` in caps through the pack (write them in sentence case); a `wall` of mono words for
  "and a ton more".
- Show the real thing: the real terminal, real paths, real commands. Never invent output.

## Hi-fi
Desk take with the screen in the room, WIDE and CLOSE. Hook from frame 0: the terminal window. Captions as shell
lines, the key phrase in the accent. Behind the head: a League Gothic word on the step ("BUILD"), sometimes. Cards
often: the file tree, the prompt, the diff, the run log, drawn as clean line work on the dark ground. Screen
recordings float in where a card is too much. No black-and-white beats. Camera: settle on cuts, punch-in on the
command. J-cut 0.3s.

## Lo-fi
Phone selfie at the desk. Word-by-word shell captions. The hook, step labels and the call to action are small
terminal windows. Screenshots and screen recordings of the real tools on top often; hard zooms on the command. J-cut
0.2s.

## Showcase
Every beat a step of the build, shown as it happens. The emphatic word stamps in letter by letter like typed output
(`emphasis_word: stamp`). Transitions: push, reveal, zoom. Dense. Motif: the session, the hook's terminal window comes
back whenever a step runs, a new command typed under the last one, and its output lands as the B-roll.

## Never
- No em dashes on screen. Commas, colons, periods.
- No neon, no glow, no green-on-black matrix code, no scanlines, no CRT curvature, no glitch filters on the picture,
  no fake code or fake output.
- The accent is the only accent: the key phrase and the cursor. The positive colour is only the prompt mark.
- Captions in sentence case, inside the safe zone, never over the mouth.
- No secrets on screen: blur keys, tokens, emails and client names in any screen recording.
- No hype words, fake urgency or "link in bio" bait.
