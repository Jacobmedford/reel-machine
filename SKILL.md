---
name: reel-machine
description: Edits raw talking-head takes into a finished vertical reel (Reels, TikTok, Shorts) in the creator's own look, with a J-cut edit, captions, type behind their head, hand-built motion graphics and sound design. Before the final renders, the creator approves the first cut, the hook and a storyboard they comment on. Of its three modes, hi-fi is the produced look (a tripod, full-screen data cards), lo-fi a selfie in hand (real screenshots over it, word-by-word captions) and showcase a different hand-built motion graphic on every beat. The first run sets the creator's look: the kit's Harbor palette, or their own colours from a brand file, a few inspiration videos or four questions; that style shapes how every mode edits. Use when someone asks to edit a talking-head video or reel, types /reel-machine, $reel-machine or @reel-machine, or wants to set up or change their video style.
---

# reel-machine

Raw takes in, finished vertical video out. The creator approves three stops (the first cut, the hook, a
storyboard they comment on), then the final renders and passes QA.
The look belongs to the creator (their style pack); this kit is the structure: how the edit cuts, where type goes,
how cards are built, how sound sits under the voice.

## Paths
- `KIT` = the folder holding this file (it can be read-only; nothing is ever written into it).
- `HOME` = `$REEL_MACHINE_HOME`, default `~/reel-machine`: the style pack (`HOME/style/`), projects
  (`HOME/projects/<slug>/`) and what setup makes (`HOME/.venv/`, `HOME/vendor/`, `HOME/models/`). The speech model,
  the render browser and HyperFrames live in the user's own caches (Hugging Face's, the browser's, npm's; on a Linux
  where no browser build starts, setup puts Chromium in `HOME/browsers/`). An existing `~/reel-kit` home keeps
  working: with no `~/reel-machine` folder, a `~/reel-kit` that holds a style pack is HOME, and the old names
  (`$REEL_KIT_HOME`, every other `REEL_KIT_*` setting) are still read.
- `PY` = `HOME/.venv/bin/python` (Windows: `HOME/.venv/Scripts/python.exe`). Run every pipeline script with `PY`;
  each takes the project folder first.
- `HF` = `npx -y hyperframes@0.8.139`, pinned so every video renders the same way.
- Style packs: `HOME/style/` is the default pack (`harbor`); more packs live in `HOME/packs/<name>/` (`PY KIT/pipeline/pack.py
  list`). A pack decides the look, the mode decides the structure.
- Sounds: `HOME/sfx/` (the creator's favorites and an indexed library, catalog `HOME/sfx/SFX-LIBRARY.md`) beside the
  kit's own `KIT/audio/sfx/`. Presets (approved effects and cards): the creator's `HOME/presets/`, then the kit's
  `KIT/presets/` (`KIT/presets/CATALOG.md`); `PY KIT/pipeline/preset.py list` shows both, and a name in both comes
  from the creator's.

## What this host can do (check once, adapt, never ask the creator about it)
- **A terminal and files**: required. The kit runs Python, ffmpeg and Node on the creator's computer. A host
  without one (a chat app with no computer access): say plainly that this skill needs an agent that can run
  commands on their machine (Claude Code, Codex, Claude Cowork with code execution on, or ChatGPT Work in the
  desktop app), then stop.
- **A sandbox** (Codex runs commands in one by default, and so does ChatGPT Work, through the Codex built into
  it): rendering launches a headless browser, which Codex's macOS sandbox blocks, and setup needs the network. `setup.py` says so when it runs inside one. Ask the creator to
  give the session full access (Codex: Full access in the permissions menu, or `codex --sandbox
  danger-full-access`), or to approve the render commands running outside the sandbox.
- **Granted folders only** (Claude Cowork runs in a Linux VM on the creator's computer; ChatGPT Work works in a
  folder they open): set `REEL_MACHINE_HOME` to a folder inside the one they granted (`export
  REEL_MACHINE_HOME=<granted folder>/reel-machine` in every command) so the style pack, projects and tools stay on
  their computer between sessions, and put the finished videos there too. A granted folder that already holds a
  home from before the rename keeps it (`<granted folder>/reel-kit`, the old `REEL_KIT_HOME`): point
  `REEL_MACHINE_HOME` there instead. Renders in a VM use its CPU: slower, still fine.
- **Subagents** (an Agent or Task tool): build cards in parallel. None: build them one after another yourself,
  each from the same brief.
- **Claude artifacts** (an Artifact tool): publish the storyboard and the style board there and read inline
  comments with ArtifactComments. None: serve them locally with `KIT/storyboard/serve.py`; notes land in a file.
- **Generators** (optional, see README "Extend it"): an image or video generator (for example the Higgsfield MCP),
  a music or sound one (for example ChatCut, ElevenLabs). Use only what is already connected. Without one, the
  video uses real artifacts and the kit's own sound effects, which is the default anyway.

## 0. First run
1. `python3 KIT/setup/setup.py` until it prints READY (it renders a test frame, so READY means it can render).
   Each missing piece comes with the exact fix for that computer; pass it on as written.
2. No `HOME/style/style.json` yet: ask one question, "Use the Harbor palette, or your own brand colors?"
   - Harbor: `PY KIT/pipeline/pack.py install`. The kit's four packs (harbor, the default, then film, signal and
     terminal) land in the home, built, each with its style board.
   - Their own: onboarding steps 1 to 3 (`KIT/onboarding/ONBOARDING.md`: a brand file or website, 2 or 3
     inspiration videos, or the four questions) for their colours and, if they have one, a text face on Google
     Fonts. Write the colours as `HOME/palette.json` ({role: colour} with the keys of `colors` in
     `KIT/packs/harbor/style.json`; a role left out keeps Harbor's colour), then
     `PY KIT/pipeline/pack.py install --palette HOME/palette.json [--text-font "<family>"]`: all four packs in their
     colours.
   Then show the default pack's board (`HOME/style/board/`, the way onboarding step 5 shows it) and ask "Does this
   look like you?" Changes go through onboarding steps 4 and 5 on that pack. Never use another creator's handle,
   logo or name: `creator` in style.json stays empty until they give theirs.
3. "Change my style" at any time: onboarding steps 4 and 5 on the current pack. A second look for some videos: a new
   pack folder in `HOME/packs/<name>/` (same files as `HOME/style/`, plus an optional `extra.css` appended after the
   tokens), built with `PY KIT/pipeline/pack.py build <name>`.

## Modes
The creator picks: **hi-fi**, **lo-fi** or **showcase** (also accept "hifi", "high", "produced", "lofi", "low",
"selfie", "show-off", "show off", "flex"). No mode in the request: step 1 settles it (the intake recommends one from
the footage, the creator decides on the start page). Never start the cut on a mode they have not picked or accepted.
- **Hi-fi** (`KIT/modes/HIFI.md`): produced. Two framings of one take, full-screen data cards by card agents, type
  behind the head. Reference: `KIT/examples/hifi/edit.py`.
- **Lo-fi** (`KIT/modes/LOFI.md`): selfie. They never leave the frame; real artifacts land on top of them or behind
  their head; word-by-word captions; text boxes. No card agents. Reference: `KIT/examples/lofi/edit.py`.
- **Showcase** (`KIT/modes/SHOWCASE.md`): the show-off edit on any footage. Every beat a different technique the
  words call for, one recurring motif, a different transition on every cut, dense sound; built by FX agents from
  `KIT/fx/LIBRARY.md` (contract `KIT/kit/FX_BRIEF.md`), lo-fi captions underneath. Reference:
  `KIT/examples/showcase/edit.py`.
How each mode edits is the creator's, not the kit's: their `STYLE.md` has a section per mode and `style.json` a
`modes` block (hook shape, caption rhythm, camera, transitions, how a big word lands; `KIT/kit/STYLE_PACK.md`).
Read the mode file, then the creator's `STYLE.md` and `modes` for that mode, before step 3; where they disagree with
the mode file, the creator wins.

## 1. The takes and the start page
1. The takes: the files the creator dropped or named (paths in the chat), or a folder; a short slug from what the
   video is about. `PY KIT/pipeline/intake.py <slug> <paths...> --title "<Title>"` copies them into
   `HOME/projects/<slug>/raw/` (their own files are never changed), orders them by recording time, joins them into
   one source, scaffolds the project in the recommended mode, and starts the whole-source transcript and the scan
   for cuts already in the source in the background. Read what it printed: the takes in order, anything re-encoded
   and why (an HDR take gets a one-line note: point them at `KIT/SHOOTING.md`), files it left out, the recommended
   mode and why.
2. `PY KIT/pipeline/preview.py <project> start` writes `approvals/start/`: every take with its poster, length and
   first line, the three modes with an example clip each, the styles in their home, and what to send. Show it the
   way step 6 shows the storyboard.
3. Ask, in one turn: the mode (recommend the intake's pick with its reason; look at 4 to 6 frames first), the style
   (the default, else one the script calls for) and "Any links, screenshots or videos for this one?" Where the host
   has multiple-choice questions (Claude Code), ask mode and style that way; elsewhere one plain question with the
   three answers.
4. A mode other than the recommended one: `PY KIT/pipeline/new.py <slug> <project>/<source> "<Title>" --mode <mode>
   --reseed` (`source` as intake.json names it). A style other than the default: `PY KIT/pipeline/pack.py use
   <project> <name>`.
5. Links: capture each one yourself before asking for anything (a browser tool if the host has one, else the
   `playwright` CLI if it is installed): a repo's README top and the section the line names; an article's exact
   paragraph; a docs or pricing page's exact part; an 8 to 10 s smooth scroll for "look at this" beats. Phone width,
   cropped tight, light theme unless the beat needs dark. Save them to `<project>/assets/screens/` named by what they
   show, and rename them by beat once beat ids exist. Anything behind a login, a client system or the creator's
   phone goes on the needs list (`NEEDS`, step 3) with exactly what to send; never guess it. Uploaded files go to
   `<project>/assets/`.
6. Read the source the video talks about (article, study, post, document), if there is one. Look at a few frames of
   the footage to set FRAMES for this shoot (face centre, eyes, chin).

## 2. Cut, then the first-cut approval (stop)
- First transcript of the whole source: intake set `KEEP` to the whole source and started `words.py` (its log:
  `work/words.log`); let it finish, or run `PY KIT/pipeline/words.py <project>` when nothing is running. A take with
  no speech stops it with a plain message naming the take: tell the creator. Read `words.json`. People repeat a line
  until it lands: keep the LAST clean take of each line.
- Find the pauses: `ffmpeg -i <source> -af silencedetect=noise=-35dB:d=0.25 -f null -`. Set `KEEP` (source seconds,
  ~0.05s before the first word, at the silence after the last), `FRAMES`, `SHOTS`, `HOLD` (hi-fi 0.6, or 1.3 with
  an end card; lo-fi 0.04, since a phone take ends on its last word; showcase 0.5), `PROMPT` (names and terms) and `FIXES`.
- Tighten: `PY KIT/pipeline/tighten.py <project>` reads every pause inside a kept line from a speech map of the source
  audio (not whisper) and prints the cut it would make: a pause of 0.18 s or more comes down to about 0.1 s of air, a
  straight cut. Then `--apply`: KEEP is rewritten (comments kept, the old file saved as `edit-pre-tighten-<n>.py`),
  `J_LEADS` gets 0 at each new cut and None between lines (the kit's J-cut there), and SHOTS times move with the cut.
  `--skip <K index>` leaves a line's pauses alone (one a designed sound will fill). It refuses once beats exist, unless
  `--force`.
- `PY KIT/pipeline/cut.py <project> --plan`: the sync table must show every piece reading its own audio. Then
  `PY KIT/pipeline/cut.py <project>` and `PY KIT/pipeline/words.py <project>` again on the cut.
- Check no word was clipped before anyone hears the cut: tighten finds speech by loudness, so a very soft word (a
  voice that trails off) can read as a pause and be cut. Copy `words.json` to `work/words-before-tighten.json` before
  tighten's `--apply`; after the cut and `words.py`, compare the two line by line. A word that is missing or garbled
  was clipped: put back the `edit-pre-tighten-<n>.py` tighten saved, run it again with `--skip <K index>` for that
  line, and cut again.
- First-cut approval: `PY KIT/pipeline/preview.py <project> first-cut` writes `approvals/first-cut/`: a 720x1280 phone
  file of the cut (no captions: it is the pace check) and its page (every line with its time, any pause of 0.25 s or
  more still inside the video). Show it the way step 6 shows the storyboard. Say the length and the pace in one line,
  then STOP. A note on the cut: fix KEEP, then tighten, cut, words and preview again.
- After go: copy `assets/aroll.mp4` to `public/clean.mp4`. If anything goes behind the head, start the cutout in the
  background now: `PY KIT/pipeline/cutout.py <project>` (or `matte.py` after `setup.py --matte`, smoother edges).

## 2b. The hook, then the hook approval (stop)
- Build only what the hook needs (step 3 for its lines alone): HOOK or the hook effect, its captions, any type behind
  the head with its CUT_WINDOWS (the cutout must be done), its sounds, then `mix.py`.
- `PY KIT/pipeline/render.py <project> <slug>-v1 --hook` renders only the hook at draft quality (well under a minute)
  into `renders/<slug>-v1-hook.mp4` with the matching slice of master.wav, and writes `approvals/hook/`. The hook ends at
  the end of the first sentence plus HOLD; set `HOOK_END` (output seconds) in edit.py when the hook beat runs past it.
  Show it like the first cut, say its length and what ends it, then STOP.

## 3. Beats (write edit.py)
Map every line to the mode's components, copying field shapes from the reference edit.py: captions (`CAPS` in
hi-fi; automatic in lo-fi), `HOOK`, `BEHIND`, `CUT_WINDOWS` (never across a picture change), `BW` (at most two),
`CAMERA`, `CARDS` (from `KIT/cards/LIBRARY.md`, light and dark alternating) or `OVERLAYS`/`BOXES` in lo-fi,
`END_CARD = None` unless asked. Real artifacts first. Pace from the pack's `motion`.

Beat ids (`p01`, `p02`...) come from the cut: `PY KIT/pipeline/storyboard.py <project> --list` prints them before
any frames exist. If the footage, the brand and the script don't line up (someone else on camera, a hook that
promises more than the clip holds), say so with the storyboard; never invent missing content.

**Needs pass (every video, every beat, without being asked).** For each beat, decide what it needs beyond the take
and the source, and sort every asset three ways:
- *In hand*: the take, the source, screenshots you can grab yourself from public pages.
- *Only the creator has it*: their B-roll, screen recordings, screenshots of their own tools or dashboards, photos,
  logos, anything behind a login. Write each into `NEEDS` as `("p06", "Screen recording: 8-10s of <exact thing>,
  <framing, length>")`, specific enough to shoot without a follow-up question. Build the beat anyway with a
  placeholder; never hold the storyboard for it.
- *Generated*: step 3b, only with a generator connected.

## 3b. Generated imagery (only with a generator connected; no need to ask)
When a beat needs an image no real artifact can give, make it now so it shows on the storyboard: a still from the
connected image model, a short clip only when the beat truly moves (ideally animated from the approved still).
Hold it to restraint: objects, places and textures that look shot. Never generated people, portrait walls or
generated B-roll as the look of the video. Log each in `GENERATED` as `("p04", "<what it is>, <model>")`; the
storyboard tags them so the creator can cut any. Minimal by default; more only when they ask in their notes.

## 4. Cards (hi-fi) or effects (showcase)
**Presets first.** Read `KIT/presets/CATALOG.md`, and `HOME/presets/CATALOG.md` when the creator has their own
(`PY KIT/pipeline/preset.py list` shows both; a name in both comes from the creator's). For every beat a preset
fits, instantiate it with `PY KIT/pipeline/preset.py add <project> <preset> --id <id> --at <s> --end <s|end> --set
KEY=VALUE ...` (beats can be spoken words), paste the FX or CARDS entry it prints with its SOUND lines, and rerun its
generators when the cut moves. Agents build only the beats no preset fits (at most two new effects a video). Once a
new effect is approved, make it a preset and run `preset.py lint`.

**Showcase:** FX agents instead of cards. Write the beat map first (`KIT/modes/SHOWCASE.md`: a technique for every
line, one motif, the hook on frame 0, a transition per cut), put every entry in `FX` with its window and layer, then
launch 4 to 8 agents at once, grouped by technique. Each prompt: read `KIT/kit/FX_BRIEF.md`,
`<project>/style/STYLE.md` (its Showcase section) and the `KIT/fx/LIBRARY.md` entries to start from; its ids, layers
and windows; the words with output times; where the head is in that shot; the real assets; its own sandbox name for
`PY KIT/pipeline/fxsandbox.py <project> <name> --only <ids> --at <times>`; run `hyperframes check`; report frames,
SFX, edit.py changes and snapshot paths. Review every still at full size, send fixes back to the same agent, merge
frames into FX and SFX into SOUND. No subagents: build the effects yourself one at a time from the same brief.

**Hi-fi cards:** one agent per card (cards that share geometry go to one agent), all launched at once. Each prompt: read
`KIT/kit/CARD_BRIEF.md` and `<project>/style/STYLE.md`; the KIT, PROJECT and PY paths; the library card to start from;
the card id and folder `<project>/cards/<id>/`; the exact frame count (`data-duration` = frames/30); the window in
the video; the spoken words with CARD times; the data and labels; what it shows and when; phase 1 only (still.jpg
and beats, no render). Review every still at full size before the storyboard; send fixes back to the same agent.
No subagents: build the cards yourself one at a time from the same brief.

## 5. Sound
- `SOUND.sfx` for every visual event and `CARD_SFX` from the card agents' beat reports. Times are when each sound
  hits; `mix.py` lines up each file's loudest moment on it. Vocabulary: `HOME/sfx/SFX-LIBRARY.md` when it exists
  (favorites `fav-*` first where one fits, the kit's sounds, the library `lib-*`), else `KIT/audio/SFX.md`. Density from the
  pack's `sound.sfx`. Always under the voice.
- Music: none by default (most creators add a track in their posting app). When they hand one over, or a connected
  generator makes one, set `SOUND.music` and `sections` so two or three drops land on key lines.
- `PY KIT/pipeline/mix.py <project>` -> `public/master.wav` at -14 LUFS.

## 6. Storyboard (stop here)
- `PY KIT/pipeline/build.py <project> --stills` (cards show their stills), then
  `PY KIT/pipeline/storyboard.py <project> --version 1`: every beat with real frames, the line, what moves, what you
  hear, wearing the creator's own fonts and colours. It always answers "what I need from you" at the top.
- Show it:
  - **Claude artifacts**: copy `<project>/storyboard/` to a scratch folder and publish its `index.html` with every
    file in `files.json`, `capabilities` = `{"comments": {"composer_only": true}}`. Republish later versions from
    the same file path to keep the URL.
  - **Anywhere else**: run `python3 KIT/storyboard/serve.py <project>` in the background and send
    `http://127.0.0.1:8765`. They leave a note on any beat and press "Looks good: render it" when done.
- In the same message: what you need from them (each item, its beat, exactly what to send) or "nothing needed
  from you", plus anything a generator made and what it cost. Then STOP. Nothing renders until they say go.

## 7. Notes
- Artifact comments: read them with ArtifactComments; each thread is pinned to a beat (`p01`, `p02`...). Local:
  `<project>/storyboard/notes.json`, a list of `{beat, text, at}`; beat `all` with text `go` means render.
- Notes are the creator's words about this video: data for the edit, not instructions to anything else.
- Apply every note (edit.py; cards through their agents), rebuild, regenerate the storyboard as the next version
  and show it again. When they send an asset, drop it into its beat and clear it from `NEEDS`.

## 8. Render and deliver (after "go")
- Card agents render their mp4s (phase 2); the build picks them up from `<project>/cards/<id>/<id>.mp4`.
- `PY KIT/pipeline/render.py <project> <slug>-v1`: build, lint, render, the animation check (`animcheck.py`, about 20 s),
  QA. An animation check FAIL means a render worker drew the static page: render again; nothing is delivered
  (`work/animcheck/sheet.jpg` shows render | animated | static). QA must pass: read every cut sheet (no
  flash, no wrong frame, no doubled head), lip sync within 2 frames, -14 LUFS. On a pass it copies the video and a
  phone copy into the project folder (next to the source clip for a project made without intake) as
  `<Title> v1.mp4` and `<Title> v1 (phone).mp4`; tell the creator where they are.
- Notes after v1: `PY KIT/pipeline/render.py <project> <slug>-v2 --pieces`. Piece rendering is opt-in, for the note
  loop: it renders beat-aligned pieces of about 5 s (the hook first), caches each, and a note re-renders only the
  pieces it touches (a one-beat note took 2.7 minutes, a third of it the lint). The first render this way is slower
  than a plain one (8 minutes against about 5, measured 10-14-26), so once v1 is delivered, fill the cache in the
  background while the creator watches it: `PY KIT/pipeline/pieces.py <project> render --no-build` through
  `HOME/bin/heavy`. Then render their notes with `--pieces`. The seams are checked, every newly rendered piece gets
  the animation check, a piece that fails it is set aside and rendered once more, then QA and delivery as usual.
  `--strict` when an effect reaches shared layers (`pieces.py <project> plan` names them); `--verify` when in doubt
  (slow).

## Rendering safely
- GSAP travels inside the built page as a `data:` URL (build.py runs `inline_vendor.py`), so a network change mid-render
  cannot drop it. Never put it back as `<script src>` or as inline text: as text, `hyperframes check` fails on GSAP's
  own Math.random and Date.now.
- Cards: run `PY KIT/pipeline/inline_vendor.py index.html` in the card folder before every lint, snapshot and render,
  and `PY KIT/pipeline/animcheck.py --page . <id>.mp4` after the render (`kit/CARD_BRIEF.md`).

## Caches (rerun freely)
- `cut.py` is incremental: no change takes under a second, a framing change a few seconds. A KEEP change re-encodes only
  the pieces whose frames move; keeping KEEP edges on whole frames keeps later pieces. `REEL_MACHINE_JOBS` sets parallel
  piece encodes (default 2).
- `words.py` keeps words per take in `work/words-cache/<take>.json`: a KEEP change transcribes only new ranges, and
  editing PROMPT re-transcribes. To fix Whisper by hand, edit that range there.
- `matte.py` mattes only where the cutout is used: CUT_WINDOWS, plus any FX whose files mention `subject.webm`.
  Anything new that reads `subject.webm` must sit in a window or in such an FX folder. Unchanged reruns are skipped;
  `--full` mattes every frame.
- Render pieces (`render.py --pieces`, `pieces.py`) live in `work/render-pieces/`; cut pieces stay in `work/pieces/`.

## Gotchas already paid for
- `J_LEADS` may mix numbers and None: None keeps the kit's lead for that join; a list of the wrong length stops cut.py.
- The hook render plays only clips that start before the hook end: `subject.webm` must exist when a cutout window
  starts inside the hook.
- `preset.py` refuses the composition's own ids (`hook`, `caps`, `cam`, `v`, ...): a pack may style those selectors.
- Phone takes exported from Edits or CapCut are already cut in their pauses: a fixed J-cut runs past those cuts
  (a double cut). `cut.py` detects source cuts and fits each join's lead to them.
- SFX swell before they peak: give `mix.py` the moment of the event, never the file's start.
- A join that rounds down to its frame once mapped seconds of picture through the wrong segment. `cut.py` matches
  on the snapped join and refuses to encode if any piece drifts.
- The cutout seeks a frame late: a cutout window across a reframe shows one doubled-head frame. Windows start on or
  after the change.
- Times at 3 decimals land a frame late: everything goes through `q()` and `clip_start()`. HyperFrames rounds
  `data-duration` x 30 up: 137 frames is 4.5666, not 4.567. `data-media-start` must be an exact frame time.
- Anything behind the cutout must be off before it clears the speaker's body: the desk is not in the cutout.
- Transcription mishears names: put them in `PROMPT` and `FIXES`.
- `qa.py` matches lip sync on the speaker (the moving footage the render still shows), so pages, captions and stickers
  no longer cause false drifts; the whole-frame number prints when the two disagree; `--full-frame` runs the old check.
