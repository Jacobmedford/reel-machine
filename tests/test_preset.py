"""pipeline/preset.py: instantiate approved effects and cards by setting constants. A fake library and project in a
temp dir; nothing here touches the real HOME or any real project."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import preset  # noqa: E402

FX_JS = """// demo: a stamped word behind the head
// PRESET CONSTANTS START
// the words and where they land
var WORD = "SECOND";                       // the key word
var T = {"push": 0.767, "stamp": 1.267};   // s after A, or a spoken word
var SIZE = 432;                            // px
var STAMPS = [
  {"text": "EMAILS", "x": 46},
  {"text": "MEETINGS", "x": 1034}
];
var SPLIT = true;
var FRONT = null;                          // (luma, y) or null
// PRESET CONSTANTS END
function cues(o) { return o; }
T = cues(T);
tl.set('#{{ID}}', { opacity: 1 }, q(A + T.push));
"""

FX_HTML = """<div id="{{ID}}-w"></div>
<video id="{{ID}}-v" src="clean.mp4" muted playsinline data-start="{{START+[[T.push]]}}" data-media-start="0" data-duration="{{DUR-[[T.push]]}}" data-track-index="{{T0}}"></video>
<style>#{{ID}}-w { color:var(--c-light); }</style>
"""

GEN = """import sys, os
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "made.txt"), "w").write(" ".join(sys.argv[1:]))
if "--fail" in sys.argv:
    sys.exit(3)
"""

CARD_HTML = """<!doctype html>
<html><head><link rel="stylesheet" href="brand.css" /><link rel="stylesheet" href="card.css" /></head><body>
<div id="root" class="ground-dark" data-composition-id="main" data-start="0" data-duration="[[@DUR]]" data-fps="30" data-width="1080" data-height="1920"></div>
<script src="vendor/gsap.min.js"></script>
<script>
(function () {
  var FPS = 30, DUR = [[@DUR]];
  // PRESET CONSTANTS START
  var TEXT = "Make the hook land harder.";   // the sentence
  var T = {"send": 0.933, "done": 1.033};        // card seconds, or a spoken word
  // PRESET CONSTANTS END
})();
</script></body></html>
"""

FX_CONSTANTS = {"WORD": "SECOND", "T": {"push": 0.767, "stamp": 1.267}, "SIZE": 432,
                "STAMPS": [{"text": "EMAILS", "x": 46}, {"text": "MEETINGS", "x": 1034}], "SPLIT": True, "FRONT": None}

WORDS = [{"start": 10.0, "end": 10.3, "text": "And"}, {"start": 10.4, "end": 10.9, "text": "window"},
         {"start": 11.2, "end": 11.5, "text": "sends,"}, {"start": 12.0, "end": 12.4, "text": "window."}]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class PresetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = os.path.join(self.tmp, "home", "presets")
        d = os.path.join(self.lib, "demo-fx")
        write(os.path.join(d, "fx.js"), FX_JS)
        write(os.path.join(d, "fx.html"), FX_HTML)
        write(os.path.join(d, "gen.py"), GEN)
        write(os.path.join(d, "preset.json"), json.dumps(dict(
            name="demo-fx", kind="fx", layer="behind", **{"from": "kit fx/word-stamp"},
            does="stamps a word behind the head", inputs=["the word"], constants=FX_CONSTANTS,
            notes={"WORD": "the key word"}, cues=["T"],
            generators=[{"run": "{py} gen.py {project} {id} --at {at} --end {end}", "when": "the cut moves",
                         "required": True}],
            sfx=[{"at": "T.stamp", "name": "stamp", "db": -12, "what": "the word stamps"},
                 {"at": "T.push+0.1", "name": "typing", "db": -14, "max_len": 0.6, "what": "it types"}],
            needs=["CUT_WINDOWS: ({at}, {end})"], typical_length="3 s", signature=None), indent=1))
        c = os.path.join(self.lib, "demo-card")
        write(os.path.join(c, "index.html"), CARD_HTML)
        write(os.path.join(c, "preset.json"), json.dumps(dict(
            name="demo-card", kind="card", layer="card", ground="dark", block="index.html",
            **{"from": "kit cards/scissors"}, does="a dark card", inputs=[],
            constants={"TEXT": "Make the hook land harder.", "T": {"send": 0.933, "done": 1.033}}, cues=["T"],
            generators=[], sfx=[{"at": "T.send", "name": "click", "db": -20, "what": "send"}],
            what="the sentence types and sends", typical_length="2.9 s", signature="reference reels"), indent=1))
        b = os.path.join(self.lib, "demo-box")
        write(os.path.join(b, "preset.json"), json.dumps(dict(
            name="demo-box", kind="device", layer="BOXES", list="BOXES", **{"from": "kit BOXES"},
            does="a native text box", inputs=["the text"], constants={"TEXT": "Your hook.", "TOP": 236},
            entry={"text": "@TEXT", "at": "@at", "end": "@end", "top": "@TOP", "note": "@note"},
            sfx=[{"at": 0.03, "name": "click", "db": -18, "what": "the box"}], typical_length="3-5 s",
            signature=None), indent=1))
        self.proj = os.path.join(self.tmp, "proj")
        write(os.path.join(self.proj, "edit.py"), 'TITLE = "Demo"\nSTYLE = "hifi"\nFX = []\nCARDS = []\n')
        write(os.path.join(self.proj, "words.json"), json.dumps(WORDS))
        write(os.path.join(self.proj, "timeline.json"), json.dumps({"total": 20.0, "fps": 30}))
        write(os.path.join(self.proj, "style", "brand.css"), ":root { --c-light: #fff; }\n")
        write(os.path.join(self.proj, "style", "fonts", "a.ttf"), "font")
        write(os.path.join(self.proj, "public", "vendor", "gsap.min.js"), "/* gsap */")
        self.kitlib = os.path.join(self.tmp, "kit", "presets")       # the kit's own library: empty unless a test fills it
        os.makedirs(self.kitlib)
        self.patches = [mock.patch.object(preset, "PRESETS", self.lib), mock.patch.object(preset, "PY", sys.executable),
                        mock.patch.object(preset, "KIT_PRESETS", self.kitlib, create=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, *a, **kw):
        out = io.StringIO()
        with redirect_stdout(out):
            entry = preset.add(*a, **kw)
        return entry, out.getvalue()

    def lib_text(self, name, f="fx.js"):
        return preset.read(os.path.join(self.lib, name, f))

    def inst_text(self, fid, f="fx.js", where="fx"):
        return preset.read(os.path.join(self.proj, where, fid, f))

    # ---- the constants block
    def test_constants_replaced_and_nothing_else_changed(self):
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"WORD": "NEVER", "SIZE": 380})
        lib, inst = self.lib_text("demo-fx"), self.inst_text("s1")
        a0, b0 = preset.block_span(lib)
        a1, b1 = preset.block_span(inst)
        self.assertEqual(lib[:a0], inst[:a1])                       # everything before the block
        self.assertEqual(lib[b0:], inst[b1:])                       # everything after it
        got = preset.constants(inst)
        want = dict(FX_CONSTANTS, WORD="NEVER", SIZE=380)
        self.assertEqual(got, want)
        changed = [ln for ln in inst.splitlines() if ln not in lib.splitlines()]
        self.assertEqual(len(changed), 2, changed)                  # only the two value lines
        self.assertTrue(any("NEVER" in ln and "// the key word" in ln for ln in changed))   # its comment kept

    def test_dotted_set_changes_one_field(self):
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"T.push": 0.5, "STAMPS.1.text": "PREMIERE"})
        got = preset.constants(self.inst_text("s1"))
        self.assertEqual(got["T"], {"push": 0.5, "stamp": 1.267})
        self.assertEqual(got["STAMPS"][1], {"text": "PREMIERE", "x": 1034})
        self.assertEqual(got["STAMPS"][0], {"text": "EMAILS", "x": 46})

    def test_unknown_constant_rejected_with_the_valid_ones(self):
        with self.assertRaises(SystemExit) as e:
            self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"NOPE": 1})
        msg = str(e.exception)
        for name in ("WORD", "T", "SIZE", "STAMPS"):
            self.assertIn(name, msg)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "fx", "s1")))   # nothing half-written

    def test_unknown_field_rejected(self):
        with self.assertRaises(SystemExit) as e:
            self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"T.nope": 1})
        self.assertIn("push", str(e.exception))

    def test_wrong_type_rejected(self):
        with self.assertRaises(SystemExit):
            self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"SIZE": "big"})
        with self.assertRaises(SystemExit):
            self.add(self.proj, "demo-fx", "s2", 3.9, 6.6, {"STAMPS": {"text": "x"}})

    def test_a_cue_constant_takes_a_spoken_word(self):
        self.add(self.proj, "demo-fx", "s1", 10.0, 13.0, {"T.stamp": "sends"})
        self.assertEqual(preset.constants(self.inst_text("s1"))["T"]["stamp"], "sends")

    def test_parse_set(self):
        self.assertEqual(preset.parse_set("SIZE=380"), ("SIZE", 380))
        self.assertEqual(preset.parse_set("WORD=NEVER"), ("WORD", "NEVER"))
        self.assertEqual(preset.parse_set("TAG=THIS VIDEO · 1:11"), ("TAG", "THIS VIDEO · 1:11"))
        self.assertEqual(preset.parse_set('T={"push": 0.5}'), ("T", {"push": 0.5}))
        self.assertEqual(preset.parse_set("FRONT=null"), ("FRONT", None))
        self.assertEqual(preset.parse_set("STAMPS.0.x=50"), ("STAMPS.0.x", 50))
        self.assertEqual(preset.parse_set("TEXT=line one\\nline two"), ("TEXT", "line one\nline two"))   # typed \n breaks

    # ---- the instance folder
    def test_the_compositions_own_ids_are_refused(self):
        for bad in ("hook", "caps", "cam", "v", "root"):
            with self.assertRaises(SystemExit) as e:
                self.add(self.proj, "demo-fx", bad, 3.9, 6.6, {})
            self.assertIn("composition", str(e.exception))

    def test_existing_id_refused_without_replace(self):
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        with self.assertRaises(SystemExit) as e:
            self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        self.assertIn("--replace", str(e.exception))

    def test_replace_renames_the_old_folder(self):
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        write(os.path.join(self.proj, "fx", "s1", "hand-note.txt"), "keep me")
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"WORD": "AGAIN"}, replace=True)
        old = [d for d in os.listdir(os.path.join(self.proj, "fx")) if d.startswith("s1-before-preset-")]
        self.assertEqual(len(old), 1)
        self.assertTrue(os.path.exists(os.path.join(self.proj, "fx", old[0], "hand-note.txt")))
        self.assertEqual(preset.constants(self.inst_text("s1"))["WORD"], "AGAIN")
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {}, replace=True)            # a second replace: -2
        old = sorted(d for d in os.listdir(os.path.join(self.proj, "fx")) if d.startswith("s1-before-preset-"))
        self.assertEqual(len(old), 2)

    def test_preset_json_stays_in_the_library(self):
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        self.assertFalse(os.path.exists(os.path.join(self.proj, "fx", "s1", "preset.json")))
        self.assertTrue(os.path.exists(os.path.join(self.proj, "fx", "s1", "PRESET.md")))

    # ---- what it prints
    def test_printed_fx_entry_is_valid_python(self):
        entry, out = self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {}, note="EMAILS stamps behind the head")
        self.assertIn(entry, out)
        d = eval(entry, {"__builtins__": {}, "dict": dict})          # what edit.py would evaluate
        self.assertEqual(d, dict(id="s1", layer="behind", at=3.9, end=6.6, preset="demo-fx",
                                 note="EMAILS stamps behind the head"))

    def test_end_of_video(self):
        entry, _ = self.add(self.proj, "demo-fx", "s1", 18.0, "end", {})
        self.assertEqual(eval(entry, {"__builtins__": {}, "dict": dict})["end"], "end")
        made = preset.read(os.path.join(self.proj, "fx", "s1", "made.txt"))
        self.assertIn("--end 20", made)                              # generators get the real end time

    def test_needs_and_sfx_printed_with_real_times(self):
        _, out = self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"T.stamp": 1.0})
        self.assertIn("CUT_WINDOWS: (3.9, 6.6)", out)
        sfx = [ln.split("#")[0].strip().rstrip(",") for ln in out.splitlines() if '"stamp"' in ln or '"typing"' in ln]
        got = [eval(s, {"__builtins__": {}}) for s in sfx]
        self.assertIn((4.9, "stamp", -12), got)
        self.assertIn((4.767, "typing", -14, 0.6), got)

    def test_sfx_star_places_one_sound_per_item(self):
        meta = preset.read_json(os.path.join(self.lib, "demo-fx", "preset.json"))
        meta["sfx"] = [{"at": "T.*+0.01", "name": "stamp", "db": -13, "what": "each beat"},
                       {"at": "STAMPS.5.x", "name": "pop", "db": -20, "what": "a path that is not there"}]
        write(os.path.join(self.lib, "demo-fx", "preset.json"), json.dumps(meta))
        _, out = self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        got = [eval(ln.split("#")[0].strip().rstrip(","), {"__builtins__": {}}) for ln in out.splitlines()
               if '"stamp"' in ln]
        self.assertEqual(got, [(4.677, "stamp", -13), (5.177, "stamp", -13)])
        self.assertNotIn('"pop"', out)                               # skipped, said so
        self.assertIn("STAMPS.5.x", out)

    def test_sfx_length_from_two_beats(self):
        meta = preset.read_json(os.path.join(self.lib, "demo-fx", "preset.json"))
        meta["sfx"] = [{"at": "T.push", "name": "typing", "db": -14, "max_len": "T.stamp - T.push", "what": "types"}]
        write(os.path.join(self.lib, "demo-fx", "preset.json"), json.dumps(meta))
        _, out = self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        got = [eval(ln.split("#")[0].strip().rstrip(","), {"__builtins__": {}}) for ln in out.splitlines() if '"typing"' in ln]
        self.assertEqual(got, [(4.667, "typing", -14, 0.5)])

    def test_needs_can_name_a_beat(self):
        meta = preset.read_json(os.path.join(self.lib, "demo-fx", "preset.json"))
        meta["needs"] = ["GRADES: ({@T.stamp}, {end}, \"moody\")"]
        write(os.path.join(self.lib, "demo-fx", "preset.json"), json.dumps(meta))
        _, out = self.add(self.proj, "demo-fx", "s1", 10.0, 13.0, {"T.stamp": "sends"})
        self.assertIn('GRADES: (11.2, 13, "moody")', out)

    def test_sfx_if_a_constant_is_set_and_spread_to_a_count(self):
        meta = preset.read_json(os.path.join(self.lib, "demo-fx", "preset.json"))
        meta["sfx"] = [{"at": "T.*", "name": "key", "db": -17, "spread": "WORD", "what": "a letter"},
                       {"at": "T.stamp", "name": "pop", "db": -20, "if": "FRONT", "what": "only with FRONT"},
                       {"at": "T.stamp", "name": "ding", "db": -20, "if": "!FRONT", "what": "only without FRONT"}]
        write(os.path.join(self.lib, "demo-fx", "preset.json"), json.dumps(meta))
        _, out = self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"WORD": "ABC"})
        keys = [eval(ln.split("#")[0].strip().rstrip(","), {"__builtins__": {}})[0] for ln in out.splitlines() if '"key"' in ln]
        self.assertEqual(keys, [4.667, 4.917, 5.167])               # three letters between the two beats
        self.assertNotIn('"pop"', out)                               # FRONT is null
        self.assertIn('"ding"', out)

    def test_lengths_stay_out_of_the_beat_table_and_needs_name_constants(self):
        meta = preset.read_json(os.path.join(self.lib, "demo-fx", "preset.json"))
        meta["lengths"] = ["T.push"]
        meta["needs"] = ["NEEDS: confirm the {=WORD} flow"]
        write(os.path.join(self.lib, "demo-fx", "preset.json"), json.dumps(meta))
        _, out = self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        table = out[out.index("beats"):out.index("generators")]
        self.assertNotIn("T.push", table)
        self.assertIn("T.stamp", table)
        self.assertIn("NEEDS: confirm the SECOND flow", out)

    # ---- generators
    def test_generator_runs_with_its_placeholders(self):
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        made = preset.read(os.path.join(self.proj, "fx", "s1", "made.txt"))
        self.assertEqual(made, f"{self.proj} s1 --at 3.9 --end 6.6")

    def test_no_gen_skips_generators(self):
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {}, gen=False)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "fx", "s1", "made.txt")))

    def test_failing_generator_uses_its_fallback(self):
        meta = preset.read_json(os.path.join(self.lib, "demo-fx", "preset.json"))
        meta["generators"] = [{"run": "{py} gen.py {project} {id} --fail", "required": True,
                               "fallback": "{py} gen.py {project} {id} --blank"}]
        write(os.path.join(self.lib, "demo-fx", "preset.json"), json.dumps(meta))
        _, out = self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        self.assertIn("--blank", preset.read(os.path.join(self.proj, "fx", "s1", "made.txt")))
        self.assertIn("fallback", out.lower())

    def test_failing_required_generator_without_fallback_stops(self):
        meta = preset.read_json(os.path.join(self.lib, "demo-fx", "preset.json"))
        meta["generators"] = [{"run": "{py} gen.py {project} {id} --fail", "required": True}]
        write(os.path.join(self.lib, "demo-fx", "preset.json"), json.dumps(meta))
        with self.assertRaises(SystemExit):
            self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})

    # ---- bindings: static HTML that must carry a constant (media timing)
    def test_binding_takes_the_constant(self):
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {"T.push": 0.7333})
        html = self.inst_text("s1", "fx.html")
        self.assertIn('data-start="{{START+0.7333}}"', html)
        self.assertIn('data-duration="{{DUR-0.7333}}"', html)
        self.assertNotIn("[[", html)

    def test_binding_resolves_a_spoken_word(self):
        self.add(self.proj, "demo-fx", "s1", 10.0, 13.0, {"T.push": "window"})
        self.assertIn('data-start="{{START+0.4}}"', self.inst_text("s1", "fx.html"))

    def test_word_cues(self):
        W = WORDS
        self.assertAlmostEqual(preset.cue(W, "window", 10.0), 0.4)
        self.assertAlmostEqual(preset.cue(W, "window-0.1", 10.0), 0.3)
        self.assertAlmostEqual(preset.cue(W, "SENDS", 10.0), 1.2)               # case and punctuation ignored
        self.assertEqual(preset.cues(W, ["window", "window"], 10.0), [0.4, 2.0])   # a list moves on
        self.assertEqual(preset.cues(W, ["sends", "and"], 10.0), [1.2, 0.0])     # not after it: from the window start
        self.assertEqual(preset.cues(W, {"a": "window", "b": 0.5}, 10.0), {"a": 0.4, "b": 0.5})
        with self.assertRaises(SystemExit):
            preset.cue(W, "nowhere", 10.0)

    # ---- cards
    def test_card_instance_and_entry(self):
        entry, out = self.add(self.proj, "demo-card", "c9", 6.6, 9.4667, {"TEXT": "One sentence."},
                              note="the sentence types and sends")
        d = os.path.join(self.proj, "cards", "c9")
        for f in ("brand.css", "card.css", "hyperframes.json", os.path.join("vendor", "gsap.min.js"),
                  os.path.join("fonts", "a.ttf"), "index.html"):
            self.assertTrue(os.path.exists(os.path.join(d, f)), f)
        html = preset.read(os.path.join(d, "index.html"))
        self.assertIn('data-duration="2.8667"', html)               # 86 frames
        self.assertIn("DUR = 2.8667", html)
        self.assertEqual(preset.constants(html)["TEXT"], "One sentence.")
        tup = eval(entry, {"__builtins__": {}})
        self.assertEqual(tup, ("c9", "cards/c9.mp4", 6.6, 9.4667, "dark", "the sentence types and sends"))
        self.assertIn("render", out)                                 # it says how to render the card
        line = next(x for x in out.splitlines() if x.startswith("render the card"))
        self.assertLess(line.index("inline_vendor.py index.html"), line.index(" check"))   # GSAP inside first
        self.assertTrue(line.rstrip().endswith("animcheck.py --page . c9.mp4"), line)      # the check after

    def test_card_word_cue_becomes_card_seconds(self):
        self.add(self.proj, "demo-card", "c9", 10.0, 13.0, {"T.send": "sends"})
        html = preset.read(os.path.join(self.proj, "cards", "c9", "index.html"))
        self.assertEqual(preset.constants(html)["T"]["send"], 1.2)  # a card has no words.json: resolved at add

    # ---- devices (edit.py entries only)
    def test_device_entry_is_valid_python(self):
        entry, out = self.add(self.proj, "demo-box", None, 0.0, 4.95, {"TEXT": "Your hook, in two lines."},
                              note="hook box")
        d = eval(entry, {"__builtins__": {}, "dict": dict})
        self.assertEqual(d, dict(text="Your hook, in two lines.", at=0.0, end=4.95, top=236, note="hook box"))
        self.assertIn("BOXES", out)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "fx")))

    def test_device_sfx_only_for_its_role(self):
        meta = preset.read_json(os.path.join(self.lib, "demo-box", "preset.json"))
        meta["constants"]["ROLE"] = "hook"
        meta["sfx"] = [{"at": 0.03, "name": "click", "db": -18, "what": "hook", "if": "ROLE=hook"},
                       {"at": 0.13, "name": "ding", "db": -20, "what": "cta", "if": "ROLE=cta"}]
        write(os.path.join(self.lib, "demo-box", "preset.json"), json.dumps(meta))
        _, out = self.add(self.proj, "demo-box", None, 15.0, "end", {"ROLE": "cta"})
        self.assertIn('"ding"', out)
        self.assertNotIn('"click"', out)

    def test_device_stack_hands_on_at_its_cues(self):
        write(os.path.join(self.lib, "demo-stack", "preset.json"), json.dumps(dict(
            name="demo-stack", kind="device", layer="OVERLAYS", list="OVERLAYS", **{"from": "x"}, does="a stack",
            inputs=[], typical_length="4 s", cues=["HANDOFF"],
            constants={"SLOT": {"x": 90, "y": 262, "w": 900},
                       "ITEMS": [{"src": "media/a.png", "h": 300}, {"src": "media/b.png", "h": 400}],
                       "HANDOFF": [1.0]},
            each="ITEMS", chain="HANDOFF",
            entry={"src": "@item.src", "at": "@item.at", "end": "@item.end", "x": "@SLOT.x", "y": "@SLOT.y",
                   "w": "@SLOT.w", "h": "@item.h"})))
        entry, _ = self.add(self.proj, "demo-stack", None, 10.0, 13.0, {"HANDOFF": ["sends"]})
        got = eval("[" + entry + "]", {"__builtins__": {}, "dict": dict})
        self.assertEqual([(d["src"], d["at"], d["end"]) for d in got], [("media/a.png", 10.0, 11.2), ("media/b.png", 11.2, 13.0)])
        self.assertEqual(got[1]["h"], 400)

    def test_device_stack_items_override_the_slot(self):
        write(os.path.join(self.lib, "demo-stack", "preset.json"), json.dumps(dict(
            name="demo-stack", kind="device", layer="OVERLAYS", list="OVERLAYS", **{"from": "x"}, does="a stack",
            inputs=[], typical_length="4 s", cues=["HANDOFF"],
            constants={"SLOT": {"x": 100, "y": 262, "w": 880},
                       "ITEMS": [{"src": "a.png", "h": 300}, {"src": "b.png", "h": 400, "x": 90, "w": 900}],
                       "HANDOFF": [1.0]},
            each="ITEMS", chain="HANDOFF", item_defaults="SLOT",
            entry={"src": "@item.src", "at": "@item.at", "end": "@item.end", "x": "@item.x", "y": "@item.y",
                   "w": "@item.w", "h": "@item.h"})))
        entry, _ = self.add(self.proj, "demo-stack", None, 10.0, 13.0, {})
        got = eval("[" + entry + "]", {"__builtins__": {}, "dict": dict})
        self.assertEqual([(d["x"], d["w"]) for d in got], [(100, 880), (90, 900)])

    # ---- the library check
    def test_lint_passes_a_clean_library_and_catches_drift(self):
        self.assertEqual(preset.lint(), [])
        meta = preset.read_json(os.path.join(self.lib, "demo-fx", "preset.json"))
        meta["constants"]["SIZE"] = 999                              # preset.json says one thing, fx.js another
        write(os.path.join(self.lib, "demo-fx", "preset.json"), json.dumps(meta))
        write(os.path.join(self.lib, "demo-fx", "fx.html"), FX_HTML.replace("var(--c-light)", "#EBDFBF"))
        issues = "\n".join(preset.lint())
        self.assertIn("SIZE", issues)
        self.assertIn("colour", issues)

    def test_lint_catches_an_em_dash(self):
        write(os.path.join(self.lib, "demo-fx", "fx.js"), FX_JS.replace("a stamped word", "a word \u2014 stamped"))
        self.assertIn("dash", "\n".join(preset.lint()))

    def test_lint_catches_a_space_letter_that_lost_its_no_break_space(self):
        # letter-by-letter effects swap a space letter for a no-break space: an inline-block holding a plain space has
        # no width, so "A SINGLE" set as letters reads "ASINGLE" (an editor can turn the character into a plain space)
        js = FX_JS + "\nfunction letters(t) { return Array.from(t).map(function (c) { return c === ' ' ? '\\u00a0' : c; }); }\n"
        write(os.path.join(self.lib, "demo-fx", "fx.js"), js)
        self.assertEqual(preset.lint(), [])
        write(os.path.join(self.lib, "demo-fx", "fx.js"), js.replace("'\\u00a0'", "' '"))
        self.assertIn("no-break space", "\n".join(preset.lint()))

    def test_lint_takes_only_the_reference_reels_signature(self):
        # the flag names no person or handle: null, or "reference reels"
        meta = preset.read_json(os.path.join(self.lib, "demo-card", "preset.json"))
        meta["signature"] = "reference creator"
        write(os.path.join(self.lib, "demo-card", "preset.json"), json.dumps(meta))
        self.assertIn("reference reels", "\n".join(preset.lint()))

    def test_unknown_preset_lists_the_library(self):
        with self.assertRaises(SystemExit) as e:
            self.add(self.proj, "nope", "x", 1.0, 2.0, {})
        self.assertIn("demo-fx", str(e.exception))

    # ---- two libraries: the creator's first, then the kit's own
    def kit_copy(self, name, src="demo-fx", **constants):
        """a preset in the kit's library: the creator's `src` copied under `name`, constants changed in both places"""
        d = os.path.join(self.kitlib, name)
        shutil.copytree(os.path.join(self.lib, src), d)
        meta = preset.read_json(os.path.join(d, "preset.json"))
        meta["name"] = name
        meta["constants"].update(constants)
        write(os.path.join(d, "preset.json"), json.dumps(meta))
        bf = os.path.join(d, "fx.js")
        write(bf, preset.write_block(preset.read(bf), meta["constants"]))
        return d

    def test_libraries_are_the_creators_then_the_kits(self):
        self.assertEqual(preset.libraries(), [self.lib, self.kitlib])

    def test_the_creators_library_comes_from_the_environment(self):
        self.assertEqual(preset.creator_library({}), os.path.join(preset.HOME, "presets"))
        self.assertEqual(preset.creator_library({"REEL_KIT_PRESETS": "/srv/old"}), "/srv/old")
        self.assertEqual(preset.creator_library({"REEL_MACHINE_PRESETS": "/srv/new", "REEL_KIT_PRESETS": "/srv/old"}),
                         "/srv/new")
        self.assertEqual(preset.creator_library({"REEL_MACHINE_PRESETS": "", "REEL_KIT_PRESETS": "/srv/old"}), "/srv/old")
        self.assertEqual(preset.creator_library({"REEL_MACHINE_PRESETS": "~/mine"}), os.path.expanduser("~/mine"))

    def test_a_preset_only_in_the_kits_library_is_found_and_added(self):
        d = self.kit_copy("kit-fx", WORD="KIT")
        self.assertEqual(preset.load("kit-fx")[0], d)
        self.assertIn("kit-fx", preset.names())
        self.add(self.proj, "kit-fx", "k1", 3.9, 6.6, {"SIZE": 300})
        got = preset.constants(self.inst_text("k1"))
        self.assertEqual((got["WORD"], got["SIZE"]), ("KIT", 300))
        self.assertTrue(os.path.exists(os.path.join(self.proj, "fx", "k1", "made.txt")))       # its generator ran
        self.assertIn(d, preset.read(os.path.join(self.proj, "fx", "k1", "PRESET.md")))      # where it came from

    def test_a_name_in_both_libraries_comes_from_the_creators(self):
        self.kit_copy("demo-fx", WORD="KIT")
        self.assertEqual(preset.load("demo-fx")[0], os.path.join(self.lib, "demo-fx"))
        self.assertEqual(preset.names().count("demo-fx"), 1)
        self.add(self.proj, "demo-fx", "s1", 3.9, 6.6, {})
        self.assertEqual(preset.constants(self.inst_text("s1"))["WORD"], "SECOND")

    def test_list_shows_where_each_preset_comes_from(self):
        self.kit_copy("kit-fx")
        self.kit_copy("demo-fx")
        out = io.StringIO()
        with redirect_stdout(out):
            preset.cmd_list()
        text = out.getvalue()
        rows = {ln.split()[0]: ln.split() for ln in text.splitlines() if ln.strip()}
        self.assertEqual(rows["kit-fx"][1], "kit")
        self.assertEqual(rows["demo-card"][1], "creator")
        self.assertEqual(rows["demo-fx"][1], "creator")            # the creator's copy is the one used...
        self.assertIn("kit", rows["demo-fx"][2:])                   # ...and the row says the kit has one too
        self.assertIn(self.lib, text)                               # both libraries named
        self.assertIn(self.kitlib, text)

    def test_show_says_which_library(self):
        d = self.kit_copy("kit-fx")
        out = io.StringIO()
        with redirect_stdout(out):
            preset.cmd_show("kit-fx")
            preset.cmd_show("demo-fx")
        lines = [ln for ln in out.getvalue().splitlines() if ln.startswith("library:")]
        self.assertEqual(lines, [f"library: kit ({d})", f"library: creator ({os.path.join(self.lib, 'demo-fx')})"])

    def test_lint_checks_the_kits_library_too(self):
        d = self.kit_copy("kit-fx")
        write(os.path.join(d, "fx.html"), FX_HTML.replace("var(--c-light)", "#EBDFBF"))
        issues = "\n".join(preset.lint())
        self.assertIn("kit-fx", issues)
        self.assertIn("colour", issues)

    def test_unknown_preset_names_both_libraries(self):
        self.kit_copy("kit-fx")
        with self.assertRaises(SystemExit) as e:
            preset.load("nope")
        msg = str(e.exception)
        for want in (self.lib, self.kitlib, "demo-fx", "kit-fx"):
            self.assertIn(want, msg)


class ShippedPresetsTest(unittest.TestCase):
    """the kit's own library (presets/): it lints clean, holds no signature set pieces, and ships nothing made from
    anyone's footage (a mask is a generator's neutral output; the member's project makes the real one on add)"""
    KIT_LIB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "presets"))

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [mock.patch.object(preset, "PRESETS", os.path.join(self.tmp, "no-creator-library")),
                        mock.patch.object(preset, "KIT_PRESETS", self.KIT_LIB, create=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_shipped_preset_lints_clean(self):
        self.assertGreaterEqual(len(preset.names()), 12)
        self.assertEqual(preset.lint(), [])

    def test_no_signature_set_pieces_ship(self):
        for n in preset.names():
            self.assertIsNone(preset.load(n)[1].get("signature"), n)

    def test_the_catalog_lists_every_shipped_preset(self):
        catalog = preset.read(os.path.join(self.KIT_LIB, "CATALOG.md"))
        for n in preset.names():
            self.assertIn(f"`{n}`", catalog)

    def test_no_footage_ships(self):
        import numpy as np
        from PIL import Image

        def data(p):
            with open(p, "rb") as fh:
                return fh.read()
        grain = os.path.join(self.KIT_LIB, "..", "fx", "mood-curtain", "grain.png")
        for root, _, files in os.walk(self.KIT_LIB):
            for f in files:
                p, ext = os.path.join(root, f), os.path.splitext(f)[1].lower()
                self.assertNotIn(ext, (".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm", ".wav", ".m4a"), p)
                if ext != ".png":
                    continue
                if f == "grain.png":                                 # the seeded noise tile: the kit effect's own file
                    self.assertEqual(data(p), data(grain), p)
                    continue
                with Image.open(p) as im:
                    a = np.asarray(im)
                flat = a.reshape(-1, a.shape[-1]) if a.ndim == 3 else a.reshape(-1, 1)
                self.assertTrue((flat == flat[0]).all(), f"{p}: a mask in the kit is one flat value (a generator's --blank)")


if __name__ == "__main__":
    unittest.main()
