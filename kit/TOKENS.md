# Style tokens

These are the colour and font tokens. The whole pack, including how each mode edits for the creator, is described in
`kit/STYLE_PACK.md`.

Everything that makes a video look like a particular creator lives in their style pack
(`HOME/style/style.json` in their home folder, default `~/reel-machine/style/`). `pipeline/style.py` turns it into `brand.css`:
CSS variables plus the pack's fonts. The composition, every card and the storyboard read only these variables. If
you are writing CSS or JS for this kit and you are about to type a colour or a font name, use a token instead.

## CSS variables (brand.css)

| variable | from style.json | use it for |
|---|---|---|
| `--font-display`, `--display-style`, `--display-weight` | fonts.display | the expressive face: hook line two, emphasis words, words behind the head, big figures |
| `--font-text`, `--text-weight` | fonts.text | captions, labels, text boxes |
| `--font-mono` | fonts.mono | every number, unit, axis, year, kicker, footnote |
| `--font-caption`, `--caption-style`, `--caption-weight` | fonts.caption | lo-fi word-by-word captions |
| `--c-light` / `--c-dark` | colors.light / dark | the two grounds; `--c-light` is also text on dark |
| `--c-ink` | colors.ink | text on light |
| `--c-muted-light` / `--c-muted-dark` | colors.muted_* | secondary text on light / dark |
| `--c-hair-light` / `--c-hair-dark` | colors.hair_* | hairlines, frames, rules |
| `--c-accent` / `--c-accent-light` | colors.accent / accent_on_light | the one colour that means "look here": emphasis, the hero line in a chart |
| `--c-neg` / `--c-neg-light` | colors.negative* | losses, down, "no" |
| `--c-pos` / `--c-pos-light` | colors.positive* | gains, up, "yes" |
| `--c-s1`, `--c-s2`, `--c-s3` | colors.series | up to three data series |
| `--c-box`, `--c-box-ink`, `--c-box-dim` | colors.caption_* | the caption box on footage, its text, words not yet spoken (lo-fi) |
| `--c-tb-bg`, `--c-tb-ink` | colors.textbox_* | the Instagram-style text box (lo-fi hook and CTA) |
| `--radius` | grounds.radius | every corner |

Classes from brand.css: `.ground-light`, `.ground-dark` (card backgrounds; graph paper when `grounds.grid` is true).
Classes from `kit/card.css`: `.display`, `.text`, `.mono`, `.kicker`, `.foot`, `.box`, `.rule`.

## In JavaScript
Read tokens once at load, never hard-code them:
```js
function tok(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
var C = { light: tok('--c-light'), dark: tok('--c-dark'), ink: tok('--c-ink'), accent: tok('--c-accent'),
          accentL: tok('--c-accent-light'), neg: tok('--c-neg'), pos: tok('--c-pos'), hairD: tok('--c-hair-dark') };
```
In the composition, `pipeline/build.py` resolves colour names in Python (`color(E, name)`: accent, negative, positive,
light, dark, ink, s1-s3) and writes the values into the JS.

## Meaning is fixed, values are not
Accent always means emphasis, negative always means loss, positive gain, on every card in every video. Which colour
that is belongs to the creator. A card must still read with any pack: test new work against at least two packs
(`examples/packs/bold`, `examples/packs/soft`).
