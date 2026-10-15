# Lo-fi: the selfie talking head

For phone takes shot handheld (1080x1920, often already cut in the pauses by Edits or CapCut). The speaker never
leaves the frame: the real thing lands on top of them or swaps in behind their head, captions light word by word,
native-looking text boxes carry the hook and the CTA. Set `STYLE = "lofi"` in edit.py. Reference:
`examples/lofi/edit.py`. The cut, lip sync, cutout, QA and render are the same pipeline as hi-fi.

The creator's pack decides how lo-fi looks and edits for them: `<project>/style/STYLE.md` (its Lo-fi section)
and `modes.lofi` in `style.json`: the caption rhythm (word by word, a phrase at once, or one word at a time) and
line length, text boxes or not, how often things land on top or swap in behind, zooms or not, black and white or
not, the J-cut lead (`kit/STYLE_PACK.md`). Read both first; below are the defaults when the pack is silent.

## The rule
They never leave the frame. Nothing cuts away to a full-screen card: the real thing lands on top of them or swaps
in behind their head, and they keep talking through it. Real artifacts only (screenshots, screen recordings,
photos). Restraint is still the design: one thing on screen at a time, on its word.

## Edit
- Phone takes arrive pre-cut in the pauses. `cut.py` finds those cuts and shortens each join's J-cut so the
  outgoing shot stops at the source cut (never a frame of the next take), and snaps SHOTS onto joins and in-line
  source cuts. Check the a-roll has no two cuts under 0.4s apart.
- Same cut as hi-fi otherwise: dead air trimmed, J-cuts, WIDE/CLOSE alternating on every join. On a 1080 source
  CLOSE is a gentle 1.25x crop (no 4K headroom).
- No settles, no slow pushes. Hard zooms instead: `CAMERA.zooms = [(start, end, scale)]`, in hard and out hard on
  the phrase that matters. Keep the total under ~1.4x (CLOSE 1.25 x zoom 1.12) or it goes soft.
- One black-and-white beat on the turn or the heaviest line, at most.
- Cutout: `pipeline/cutout.py` works; `pipeline/matte.py` (optional, `setup.py --matte`) gives smoother edges and
  is worth it when things sit behind the speaker a lot. Anything that starts or ends near a cut goes ON the cut.
- Pace (style.json `motion`): calm = an overlay or swap every 6-8s; normal = every 4-5s; punchy = every 2-3s
  plus a hard zoom on every key phrase.

## Type
- **Captions** (automatic, from words.json): one line in the caption face (`fonts.caption`) at 66px in the pack's
  caption box at y 1318; each word lights up as it is spoken, the rest of the line waits dim. Max 4 words / 24
  characters, break on punctuation and pauses. `CAPS = []`. `KARAOKE = dict(huge=[(start, end)])` sets lines at
  124px, two words a line, for a script that asks for it ("the captions come in huge").
- **Text boxes** (`BOXES`): the native Instagram look, text face 800 at 54px on the pack's text-box colours,
  per-line boxes. The hook from frame 0, a short label on each tip ("2. Edit videos like a pro"), and the CTA held
  to the last frame.
- **Lines behind or above the head** (`BEHIND` kind `list`): the caption face, light, a soft shadow. Stacked when
  there is headroom; `replace=True` (a small header line, one item at a time under it) when the head sits high.

## On top of them and behind them
- **Overlays** (`OVERLAYS`): screenshots, recordings, photos dropped flat over the upper half (y 300-1290, above the
  caption band), the pack's corners or square (`cls="plain"` for screen recordings), no frame, no shadow. Pop in on
  the word (0.94 to 1 in 0.16s), cut out hard. Covering the face for a second or two is fine; that is the style.
- **Backdrops** (`BEHIND` kind `backdrop`): a full-bleed real image or video swapped in behind them with the cutout
  on top (the hook: the product's own page behind their head). Needs a `CUT_WINDOWS` entry.

## Sound
- SFX: a whoosh on every backdrop swap, pops on list items and overlays, clicks on text boxes, peaks 5-10 dB under
  the voice (`audio/SFX.md`). Density from `sound.sfx` in style.json.
- Music: none by default, as in hi-fi.

## Safe zones
Same as hi-fi: top 220, nothing below y 1470, sides 35, right 100 from y 1155.
