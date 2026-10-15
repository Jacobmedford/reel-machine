"""the two install paths a public kit must get right: setup stops when the home folder is the kit itself (a clone
made in ~/reel-machine, the default home), and the release zip holds only the kit's own files"""
import contextlib, importlib.util, io, os, shutil, sys, tempfile, unittest, zipfile
from unittest import mock

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel, env):
    spec = importlib.util.spec_from_file_location("guard_" + os.path.basename(rel)[:-3], os.path.join(KIT, rel))
    m = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env):
        spec.loader.exec_module(m)
    return m


class HomeInKit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-guard-")
        self.kit = os.path.join(self.tmp, "reel-machine")
        os.makedirs(os.path.join(self.kit, "projects"))
        self.setup = load("setup/setup.py", {"REEL_MACHINE_HOME": os.path.join(self.tmp, "home")})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_kit_itself_or_a_folder_inside_it_is_not_a_home(self):
        g = self.setup.home_in_kit
        self.assertTrue(g(self.kit, self.kit))
        self.assertTrue(g(os.path.join(self.kit, "projects"), self.kit))
        self.assertFalse(g(os.path.join(self.tmp, "home"), self.kit))
        self.assertFalse(g(self.kit + "-home", self.kit))              # a sibling that starts with the same name
        link = os.path.join(self.tmp, "link")
        os.symlink(self.kit, link)
        self.assertTrue(g(link, self.kit))

    def test_the_fix_moves_the_clone_into_a_skills_folder(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("REEL_MACHINE_HOME", "REEL_KIT_HOME"):
                os.environ.pop(k, None)
            fix = self.setup.home_fix()
        self.assertIn("~/.claude/skills/reel-machine", fix)
        self.assertIn("~/.agents/skills/reel-machine", fix)
        self.assertIn("setup/setup.py", fix)

    def test_setup_stops_before_it_installs_anything(self):
        m = load("setup/setup.py", {"REEL_MACHINE_HOME": KIT})               # a home pointed at this very kit
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"REEL_MACHINE_HOME": KIT}), \
                mock.patch.object(m.subprocess, "run", side_effect=AssertionError("ran a command")), \
                mock.patch.object(m.os, "makedirs", side_effect=AssertionError("made a folder")), \
                contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as stop:
            m.main()
        self.assertEqual(stop.exception.code, 1)
        text = out.getvalue()
        self.assertIn("STATUS home", text)
        self.assertIn("MISSING", text)
        self.assertIn("REEL_MACHINE_HOME", text)                       # the variable points at the kit: the fix names it
        self.assertIn("NOT READY", text)


class ReleaseZip(unittest.TestCase):
    def setUp(self):
        self.pkg = load("setup/package.py", {})

    def test_only_the_kits_own_files(self):
        keep = self.pkg.keep
        for rel in ("SKILL.md", "pipeline/intake.py", "packs/harbor/local-fonts/OFL.txt", "presets/CATALOG.md",
                    "storyboard/examples/hifi.mp4", "docs/img/styles.jpg"):
            self.assertTrue(keep(rel), rel)
        for rel in (".superpowers/notes/report.md", "dev/standin.py", "packs/harbor/brand.css",
                    "pipeline/__pycache__/x.pyc", "examples/packs/default/fonts/a.ttf", "packs/film/board/board.jpg",
                    ".venv/bin/python", "style/.hidden/x"):
            self.assertFalse(keep(rel), rel)

    def test_a_checkout_packs_what_git_tracks(self):
        got = self.pkg.candidates()
        self.assertIn("SKILL.md", got)
        self.assertIn("LICENSE", got)
        self.assertFalse([f for f in got if f.startswith(".superpowers")])

    def test_a_plain_folder_skips_hidden_folders(self):
        tmp = tempfile.mkdtemp(prefix="reel-machine-zip-")
        try:
            for rel in ("SKILL.md", "pipeline/a.py", ".notes/private.md", "pipeline/.cache/x"):
                os.makedirs(os.path.dirname(os.path.join(tmp, rel)) or tmp, exist_ok=True)
                open(os.path.join(tmp, rel), "w").close()
            self.assertEqual(sorted(self.pkg.candidates(tmp)), ["SKILL.md", os.path.join("pipeline", "a.py")])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_zip_has_one_top_folder_and_no_hidden_files(self):
        tmp = tempfile.mkdtemp(prefix="reel-machine-zip-")
        try:
            out = os.path.join(tmp, "reel-machine.zip")
            with contextlib.redirect_stdout(io.StringIO()):
                self.pkg.main(out)
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
            self.assertIn("reel-machine/SKILL.md", names)
            self.assertFalse([n for n in names if not n.startswith("reel-machine/")])
            self.assertFalse([n for n in names if n.startswith("reel-machine/.superpowers")])
            self.assertFalse([n for n in names if "/dev/" in n])
            self.assertIn("reel-machine/docs/img/styles.jpg", names)          # the README's images travel with it
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
