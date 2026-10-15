# The style pack

Everything that makes a video look like one particular creator lives in their pack, `HOME/style/` in their home
folder (default `~/reel-machine/style/`), built during onboarding from their brand file, their inspiration videos or
their answers:

- `style.json`: the values below. `pipeline/style.py` fills any missing field from its `DEFAULT`.
- `STYLE.md`: the same style in words, with a section per mode. Every agent that writes an edit, builds a card or
  an effect reads it. Where STYLE.md is more specific than style.json, follow STYLE.md.
- `brand.css` + `fonts/`: generated from style.json by `pipeline/style.py`. Never edited by hand.

Each project keeps a copy of the pack it was made with (`<project>/style/`), so changing the style never changes an
old video.

## The look (all modes)

| field | values | what it changes | read it off |
|---|---|---|---|
| `fonts.display` | Google Fonts family, italic, weight | hook line, thesis words, words behind the head, big figures, card titles | the brand's headline face; the emphasis face in the inspiration |
| `fonts.text` | same | hi-fi captions, labels, text boxes | the brand's body face; the caption face in the inspiration |
| `fonts.mono` | same | numbers, units, kickers, footnotes | the brand's mono, else one that sits well with the text face |
| `fonts.caption` | same | lo-fi word-by-word captions | the inspiration's caption face |
| `colors.*` | hex or rgba | grounds, ink, accent (emphasis), negative, positive, caption box, text box (`kit/TOKENS.md`) | the brand palette; the inspiration's caption box and highlight colours |
| `grounds.grid`, `grounds.radius` | true / false, px | graph paper on cards, every corner | the brand's shapes (sharp or rounded); the inspiration's cards |
| `captions.hifi` | box, uppercase, size, y | the hi-fi caption box on footage | the inspiration's captions |
| `captions.lofi` | box, uppercase, size, y | the lo-fi caption line | same |
| `grade` | a CSS filter | the whole picture | the inspiration's colour (warm, cool, contrasty, muted, straight) |
| `motion` | calm, normal, punchy | entrance speed, how often something new lands | cuts per minute and motion in `refs.py`'s summary |
| `sound.sfx` | light, normal, dense | how many effects; light also sits them 3 dB lower | the inspiration by feel |
| `sound.music` | none | music is added by the creator when they post | (a track is handed over per video) |
| `creator` | name, handle, site | an end card, when asked for one | ask once |

## How each mode edits for this creator (`modes`)
The same creator should feel like themselves in every mode. Decide all three from the same evidence: the
inspiration's caption rhythm, camera language and transitions carry across, adapted to each mode.

### `modes.hifi`
| field | values | engine or agent | what it changes |
|---|---|---|---|
| `hook` | `two-line`, `one-line`, `none` | agent | two-line: a plain line over a big display line; one-line: one display line; none: the first caption carries it |
| `captions` | `phrases`, `words`, `lines` | agent | how CAPS are cut: 2-4 word phrases, one word at a time, or a whole sentence |
| `emphasis` | list of `thesis`, `big`, `strike` | agent | the caption devices this creator uses |
| `behind_head` | `often`, `sometimes`, `never` | agent | type and numbers behind the speaker's head |
| `cards` | `often`, `sometimes`, `rarely` | agent | how often full-screen cards carry a beat |
| `camera` | `settle`, `zooms`, `still` | engine | settle: a small settle on every cut plus punch-ins and pushes; zooms: no settles, hard zooms on key phrases; still: no settles, no moves |
| `bw` | true / false | agent | black-and-white beats on the heaviest lines |
| `j_lead` | seconds (0 to 0.4) | engine | how far the next line's voice leads its picture at a join (0 = straight cuts) |

### `modes.lofi`
| field | values | engine or agent | what it changes |
|---|---|---|---|
| `captions` | `word-by-word`, `phrase`, `single` | engine | each word lights as it is spoken; the line lands lit at once; one word on screen at a time |
| `max_words`, `max_chars` | numbers | engine | the longest caption line |
| `text_boxes` | true / false | agent | native-looking text boxes for the hook, chapter labels and the CTA |
| `overlays` | `often`, `sometimes`, `never` | agent | screenshots and clips dropped on top of the speaker |
| `backdrops` | `often`, `sometimes`, `never` | agent | images and video swapped in behind the head |
| `zooms` | true / false | agent | hard zooms on the phrases that matter |
| `bw` | true / false | agent | one black-and-white beat |
| `j_lead` | seconds | engine | as in hi-fi |

### `modes.showcase`
| field | values | engine or agent | what it changes |
|---|---|---|---|
| `emphasis_word` | `stamp`, `slam`, `scale` | agent | one emphatic word: stamped letter by letter behind the head (`word-stamp`), slammed in whole, or scaled up from small |
| `transitions` | any of `whip`, `zoom`, `spin`, `push`, `drop`, `reveal` | agent | the moves `camera-transitions` may use on picture cuts |
| `density` | `medium`, `high` | agent | an effect on most beats, or on every beat |
| `motif` | a short description, or empty | agent | a recurring component for the creator's videos (empty: choose per video) |
| `j_lead` | seconds | engine | as in hi-fi |

"engine" means the pipeline applies it by itself; "agent" means the agent writing edit.py, cards or effects must
follow it. An explicit value in a project's edit.py (`J_LEAD`, `CAMERA["settles"]`, `KARAOKE`) beats the pack.

## STYLE.md: one section per mode
STYLE.md describes the look first (type, colour, captions, motion, sound, never), then has `## Hi-fi`, `## Lo-fi` and
`## Showcase` sections that say, in the creator's terms, how each mode edits for them: what the hook looks like,
how captions move, what the camera does, what goes behind the head, which transitions, what the motif could be.
Write them from the same evidence as `modes`, with the reference that shows it ("captions like ref 2: one word at a
time, centred, bold caps").
