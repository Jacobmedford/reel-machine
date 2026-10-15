# Card brief (every card agent reads this, then the creator's STYLE.md, then its own prompt)

You are building one full-screen motion-graphic card for a 1080x1920, 30fps vertical video. The card hard-cuts in
over the speaker while their voice keeps playing; the main edit lays live captions over it. It must look like it
came from the same hand as every other card in the video, and like the creator, not like this kit.

KIT is this repo. PROJECT is the video's folder. PY is the kit's Python, in the creator's home folder
(`~/reel-machine/.venv/bin/python` by default). Your prompt gives all three.
- `PROJECT/style/STYLE.md`: the creator's style in words, with a Hi-fi section that says how their cards should
  feel (read it first). `PROJECT/style/brand.css`: their tokens and fonts.
- `KIT/kit/TOKENS.md`: every token and what it means. `KIT/kit/card.css`: type voices and devices built on them.
- `KIT/cards/LIBRARY.md`: the card patterns; start from the closest one when your prompt names it.
- `KIT/kit/template.html`: a working skeleton with `q()`, `tok()`, `draw()` and `count()`.

Start: make your folder `PROJECT/cards/<id>/` and copy into it the library card you start from (if any), then
`PROJECT/style/brand.css`, `PROJECT/style/fonts/`, `KIT/kit/card.css`, `PROJECT/public/vendor/` (GSAP),
`KIT/kit/hyperframes.json`.
Never edit KIT, the style pack, or other cards.

## Style rules (hard)
- Every colour and font is a token. No hex, rgb or font names in your card: CSS uses `var(--...)`, JS reads `tok()`.
- Three voices, never swapped: `.display` speaks (titles, big figures, emphasis), `.text` informs (labels),
  `.mono` measures (every number, unit, axis, year, kicker).
- Grounds: `.ground-light` or `.ground-dark` on `#root`, whichever your prompt names.
- Fixed meaning: accent = emphasis, the thing to look at; negative = losses, down; positive = gains, up; ink or
  light = people and plain facts. Use `--c-accent-light`, `--c-neg-light`, `--c-pos-light` on a light ground.
- Hairlines 1.5-3px, corners `var(--radius)`. NO gradients, glows, blur as decoration, drop shadows, glassmorphism,
  emoji, clip art or decorative icons. Simple hairline diagrams are fine.
- Real artifacts first: screenshots of the source, scans of real objects, what the creator sends. A generated
  image only when your prompt hands you one; never make your own, and never generated people.
- No em dashes in on-screen text; use the real minus "−" for negatives.
- Data to scale: areas, lengths and splits are true to the numbers.

## Layout (hard)
- Content in x 70-1010, y 250-1150. y 1170-1430 is the caption band: ground only. Nothing to read below y 1470.
- Phone-readable: key numbers >= 96px, labels >= 30px, footnotes 24px (texture, not essential).

## Motion
- The creator's `STYLE.md` sets the pace (calm, normal or punchy). Within it:
- Hard cut in: frame 0 already shows the ground and the frame of the idea (axes, outlines, kicker).
- Every key beat lands on its spoken word from your prompt (card seconds, ±0.05s, snapped with `q()`), 2-3 frames
  early so the visual lands as the word does.
- Entrances 0.25-0.5s, `expo.out` / `power3.out`. Lines draw with stroke-dashoffset, bars grow with scale +
  transformOrigin, numbers roll with `count()` (fixed decimals so widths never jitter).
- One slow camera push across the card (`#cam` 1 to 1.02-1.03, ease none). No bounce; a stamp or pop may use
  `back.out(1.4)` at most. Hold the final state to the last frame.

## HyperFrames rules
- Root: `id="root"`, `data-composition-id="main"`, `data-start="0"`, `data-duration` = frames/30 exactly,
  `data-fps="30"`, `data-width="1080"`, `data-height="1920"`. One paused GSAP timeline at `window.__timelines["main"]`.
- Deterministic: no Math.random (seed it), no Date.now, no events. Drive anything computed from one clock tween's
  onUpdate so any seek lands on the right state.
- Never pair a CSS transform with a GSAP tween on the same property; `fromTo` that starts later needs
  `immediateRender:false`; hidden initial states via `gsap.set` outside the timeline.
- No apostrophes in ids, no `<br>` in text.

## Commands (inside your card folder)
- GSAP inside the page, before every lint, snapshot and render: `PY KIT/pipeline/inline_vendor.py index.html`. It
  swaps `<script src="vendor/gsap.min.js">` for the file itself (a data: URL), so a render worker cannot lose GSAP to
  a dropped fetch (a network change) and render your card frozen without a word. The page as it was stays in
  `index.html.pre-inline`; keep editing `index.html` and run it again before every render (a second run changes
  nothing). Any other file the card loads by `<script src>` (a `data.js`) is still fetched: keep data and helpers
  inside `index.html` where you can.
- Lint: `npx -y hyperframes@0.8.139 check` (0 errors).
- Snapshots: `npx -y hyperframes@0.8.139 snapshot --at <t1,t2,...> --no-end --describe false`.
- Render: `npx -y hyperframes@0.8.139 render -q delivery --quiet -o <id>.mp4`, then
  `ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames,width,height,r_frame_rate -of csv=p=0 <id>.mp4`
  must report 1080,1920,30/1 and your exact frame count, and `PY KIT/pipeline/animcheck.py --page . <id>.mp4` must
  PASS: it compares the render with your page snapshotted with and without its timeline, and fails a render where
  any worker's frames show the page standing still (its pictures: `<id>.animcheck.jpg`). Render again when it fails.
- Look at your own work: frames at every beat tiled into a contact sheet, judged like a senior motion designer;
  one frame with `class="debug"` on #root to prove the caption band is empty (remove it before rendering).

## Two phases
1. **Storyboard**: build the card, then save `still.jpg` (the final state, 1080x1920) and report its beats. Stop
   there unless your prompt says to render; the creator comments on the storyboard first.
2. **Render** (after their notes): apply them, render the mp4, verify, report.

## Report (short)
The mp4 or still path, exact frame count, every visible event with its card time (for sound design), and anything
you were unsure about. Don't restate the brief.
