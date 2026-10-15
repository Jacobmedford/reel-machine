# Harbor

Harbor is the default look, for tutorials and builds: tall condensed caps for the big type, a condensed sans for
every line you read, mono for every number, one accent colour used sparingly and a serif accent word now and then.
Produced but calm: the camera settles, things appear the way the content does, the screens and the speaker carry the
video. It must never look like AI slop, a neon tech promo, or a template.

The kit ships it drawn in the Harbor palette (deep green and cream with one warm coral accent); `pack.py recolor`
moves every colour role to the creator's own. So everything below names colours by role, the way the tokens do
(`kit/TOKENS.md`), with Harbor's colour in brackets. The identity (name, handle, references, call to action, what
never to say) is the creator's own: onboarding adds it here.

## Type
- Display: League Gothic, upright, ALL CAPS. Only for big type: words behind the head, statement lines, big figures,
  the emphatic stamp in showcase. It is narrow, so it carries big: lean on size, not weight. Never for captions,
  labels or small text (it does not read small).
- Text: Barlow Condensed 700 for all text: the hook's plain line, captions in both modes, text boxes, labels, card
  titles.
- Mono: IBM Plex Mono 500: every number, unit, kicker, file path, terminal line.
- Accent: DM Serif Display, mixed case, never caps. The engine puts it on the hi-fi hook's second line and the
  one-word `thesis` caption. Cards and effects use `var(--font-accent)` or the `.accent-serif` class for one or two
  accent words a beat (a card title's key word, a closing flourish). Never for captions, numbers or full sentences.
- League Gothic and DM Serif Display ship in `local-fonts/` (SIL Open Font License, `OFL.txt` beside them); Barlow
  Condensed and IBM Plex Mono come from Google Fonts when the pack is built. After a change, rebuild with
  `pipeline/pack.py build harbor`, never `style.py` alone: it leaves out the local fonts and `extra.css`, and the big
  type would fall back to a system font.

## Colour
- Accent (coral): emphasis, the one thing to look at. On the light ground use accent_on_light (a darker coral: the
  coral fails contrast on cream, so the darker shade is a deliberate variant). The accent is the only accent and is
  used sparingly.
- Negative (muted plum; a deeper plum on the light ground): losses. Kept off red so it never reads as the accent.
- Positive (sage; deep green on the light ground): gains.
- Grounds: light (cream), dark (green-black ink). Hairlines in sand. A faint grid on card grounds, 4px corners.
- Caption box: a darker cut of the deep green at 94%, so accent words still pass 3:1 inside it.

## Captions
Sentence case, never ALL CAPS. Boxed Barlow Condensed 700, light text on the caption box. Hi-fi: 64px in 2-4 word
phrases. Lo-fi: 72px, word by word, up to 4 words, waiting words dim. One accent word per caption at most, on the
word that carries the line. Now and then one word set in the accent serif inside the box: that is the `thesis`
device.

## Motion
Punchy pace (something new every 2-4 seconds), but the camera settles rather than whips: eased entrances 0.2-0.3s
(power3.out), WIDE/CLOSE reframes on the turns. Moves come from the content: a build step appears as the real UI
does, a number counts to its value, a prompt types itself. No plain fades as the main move, no generic slide-ins, no
glow, no neon, no lens flares.

## Sound
Normal density (`sound.sfx: normal`): the visual events get a sound, always under the voice; the master lands at
-14 LUFS. Names are the kit's sounds (`audio/SFX.md` has each one's start gain); a creator's own sound stands in
wherever one fits better. At most two sounds per event.
- a card cuts in: `whoosh`; back to the speaker: `whoosh-soft` or nothing.
- a text box or label appears: `click`; a chart point, tag or list item: `pop`.
- a number lands on its value: `ding`; a click or tap on screen: `click`.
- typing on screen: `typing`, placed by its start and trimmed to the text with max_len.
- a screenshot or photo appears: `shutter`; the second before a reveal: `riser`; a screen glitching out: `switch-off`.
Music none: the creator adds a track in the posting app. Never bake one into a render unless it is handed over.

## Hi-fi
Sit-down desk take, vertical 4K, locked off; WIDE and CLOSE cut on the turns. Hook from frame 0: a Barlow Condensed
line over an accent-serif line in the accent colour. Captions in 2-4 word phrases, sentence case. For any list
("three ways"), a huge League Gothic numeral in the accent colour behind the head on each item. A quoted League
Gothic word behind the head for the one idea to remember. Full-screen cards often (a third of the runtime is not too
much): dark or light grounds with the faint grid, an IBM Plex Mono kicker ("01 · GIVE IT A JOB"), an accent-serif
title, and the real UI or file tree drawn as clean line work. Real screenshots of the build float over the shot where
a card is too much. One black-and-white beat on the heaviest line. J-cut 0.3s.

## Lo-fi
Phone selfie, the speaker never leaves frame. Word-by-word captions in the box, up to 4 words, sentence case. A
light, native-looking text box carries the hook, step labels and the call to action. Real screenshots, screen
recordings and images stack in the upper half most of the time: the repo's README, the chat thread, the message that
came back, each popping in on the word that names it. Stacked kinetic words around the head on the key line, in
League Gothic for the big word and Barlow for the small ones. Hard zooms on the phrases that matter. J-cut 0.2s.

## Showcase
The flex edit: every beat a different technique the words call for. The emphatic word is a huge League Gothic word
behind the head that the head breaks, stamped in letter by letter (`word-stamp`), in the accent or the light colour.
Reach for: `prompt-bar` when the speaker tells an agent what to do, `icon-strike` for the tools it replaced,
`grid-collapse` for "lots of people", `file-drop` for a file going in, `nle-timeline` for the edit itself,
`video-card` for a walkthrough video. Transitions: push, reveal, zoom, drop. Never whip or spin. Motif: the Harbor
ridge, layered dithered mountain silhouettes in the light, positive and deep green (positive on light) colours that
rise behind the head on the hook and settle back for the close.

## Never
- No em dashes in any on-screen text. Commas, colons, periods.
- No neon, no heavy glow, no second accent colour.
- No unverified hard numbers on screen.
- No generated people. Generated imagery only for objects and places, tagged on the storyboard.
- No hype words, fake urgency, or "link in bio" bait.
- No logos, handles or signature graphics lifted from reference creators.
