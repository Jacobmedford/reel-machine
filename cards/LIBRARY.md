# Card library

Nine full-screen motion-graphic cards, 1080x1920 at 30fps. Every colour and font in them is a token from the
creator's style pack (`kit/TOKENS.md`), so each one comes out in the creator's look. A new card starts from the
closest one here: copy its folder, add the pack and kit files (`kit/CARD_BRIEF.md`), then change the data, the
labels and the beat times to the script. `preview.jpg` in each folder is its final frame in the neutral pack; the
sample content in each card is made up.

| folder | ground | what it shows | use it when the script says | length |
|---|---|---|---|---|
| `scissors` | dark | two lines from one origin: one rises (accent), one falls (negative), the gap fills with hatching; end labels roll to their values | "X grows while Y falls" | 4.567s (137 frames) |
| `source-screenshot` | light | the real source page in a window, tags landing on its key items, figures underneath | "they ran three scenarios": proof, the real thing | 2.500s (75) |
| `counter-loupe` | light | a figure rolls up, a bar fills, a loupe glides in to show how small the change is | "up 1.6%... barely noticeable": a small number | 2.900s (87) |
| `doubling` | dark | a labelled square fills, its copy slides out (x2), a clock runs to the doubling time | "doubling every N years": growth over time | 4.033s (121) |
| `task-grid` | light | a 10x10 grid flips tile by tile to "automated", a few stay; a row of new-task slots | "almost all of the work": a share of a whole | 5.833s (175) |
| `lines-by-group` | dark | the scissors chart again (a callback): tags for each group, one line climbs past the others with a counter | "these groups go up, that one goes down": groups compared | 4.367s (131) |
| `blueprint-stamp` | dark | a building plots itself as a technical drawing, steps tick off, an APPROVED stamp slams | "design and review get faster": a process step done | 2.267s (68) |
| `dollar-split` | light | a real $1 bill (public-domain scan) as a 100-cent bar, inked by share and cut on the boundary; `index-followup.html` slides the cut to a new share | "60 cents of every dollar goes to...": a share of money | 4.933s (148) + 1.300s (39) |
| `pie` | dark | a pie pops in, grows (area to scale), one share shrinks and another takes its place | "the pie gets bigger but the slice gets smaller": shares of a growing whole | 3.733s (112) |

Lengths are what the cards were built at; a card agent sets `data-duration` to its own window (frames / 30) and
moves the beats to the spoken words.

## Rules that came out of building these
- One composition per card folder. `dollar-split` ships two (`index.html` and `index-followup.html`); a card agent
  keeps the one it needs and renames it `index.html` in its own folder.
- A card shared between two moments (`dollar-split`) keeps one layout and one paint function (`dollar.js`), so the
  last frame of the first card and the first frame of the follow-up match pixel for pixel.
- A callback card (`lines-by-group` after `scissors`) reuses the first card's geometry exactly.
- Data stays true to scale: a pie that grows 1.48x in value grows 1.48x in area, a bar is split at the real share.
- Wide display faces run long: cards that show a big figure measure it after the pack's fonts load and fit it
  (`pie`, `dollar-split`). Keep figures short (`4.5 mo`, `45%`) and test with two packs.
- Real artifacts first: the source screenshot, the public-domain bill. A generated image only when the lead hands
  one over (tagged on the storyboard), never generated people.
- `source-screenshot` ships a made-up example page (`img/source.png`); swap in a real screenshot of the source and
  move the dots and tags to its items (the comment at the top of its `index.html` says how).

## Tokens the cards use beyond the contract
Strengths of light text and lines on a dark ground are `color-mix(in srgb, var(--c-light) N%, transparent)`, and a
sunken fill on light is `color-mix(in srgb, var(--c-ink) 5%, var(--c-light))`. Series colours are nudged toward
ink in JS only as far as 3:1 contrast on the light ground needs. Keep to these when building new cards.
