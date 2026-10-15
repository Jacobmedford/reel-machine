"""the fixes from the release review: setup never crashes on a Python that can't make a venv, downloads are kept only
when their checksums match, --check fetches nothing, names stay inside their folders, and symlinks never ship"""
import contextlib, importlib.util, io, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(KIT, "pipeline")


def load(rel, env=None, argv=None):
    spec = importlib.util.spec_from_file_location("hard_" + os.path.basename(rel)[:-3], os.path.join(KIT, rel))
    m = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env or {}), mock.patch.object(sys, "argv", argv or [rel]):
        spec.loader.exec_module(m)
    return m


class Setup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-hard-")
        self.home = os.path.join(self.tmp, "home")
        self.m = load("setup/setup.py", {"REEL_MACHINE_HOME": self.home})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_python_without_venv_support_is_missing_not_a_crash(self):
        def no_venv(cmd, **kw):
            os.makedirs(self.m.VENV, exist_ok=True)               # venv makes the folder before ensurepip fails
            return subprocess.CompletedProcess(cmd, 1, "", "The virtual environment was not created successfully "
                                                           "because ensurepip is not available.")
        out = io.StringIO()
        with mock.patch.object(self.m, "run", side_effect=no_venv), contextlib.redirect_stdout(out):
            self.assertFalse(self.m.make_venv("/usr/bin/python3"))
        self.assertIn("ensurepip is not available", out.getvalue())
        self.assertFalse(os.path.exists(self.m.VENV))               # the next run starts clean
        self.assertIn("python3-venv", self.m.FIX["venv"]["linux"])

    def test_gsap_is_kept_only_when_its_checksum_matches(self):
        def fetch(body):
            def retrieve(url, dest):
                with open(dest, "wb") as fh:
                    fh.write(body)
            with mock.patch.object(self.m.urllib.request, "urlretrieve", side_effect=retrieve), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.m.fetch_gsap()
        fetch(b"/* not gsap */")
        self.assertFalse(os.path.exists(self.m.GSAP_PATH))
        self.assertFalse(os.path.exists(self.m.GSAP_PATH + ".part"))
        good = b"/*! GSAP 3.15.0 */"
        import hashlib
        with mock.patch.object(self.m, "GSAP_SHA256", hashlib.sha256(good).hexdigest()):
            fetch(good)
        with open(self.m.GSAP_PATH, "rb") as fh:
            self.assertEqual(fh.read(), good)

    def test_check_runs_only_what_is_installed(self):
        m = load("setup/setup.py", {"REEL_MACHINE_HOME": self.home}, ["setup.py", "--check"])
        self.assertIn("--yes=false", m.HF_RUN)
        self.assertNotIn("-y", m.HF_RUN)
        self.assertIn("-y", self.m.HF_RUN)                        # a real run installs as before


class Names(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-hard-")
        self.env = dict(os.environ, REEL_MACHINE_HOME=os.path.join(self.tmp, "home"),
                        REEL_KIT_HOME=os.path.join(self.tmp, "home"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_py(self, *args):
        return subprocess.run([sys.executable, *args], capture_output=True, text=True, env=self.env)

    def test_a_project_slug_stays_inside_projects(self):
        for slug in ("../escape", "/tmp/escape", "a/b", ".."):
            r = self.run_py(os.path.join(PIPE, "new.py"), slug, os.path.join(self.tmp, "x.mov"), "T", "--mode", "lofi")
            self.assertNotEqual(r.returncode, 0, slug)
            self.assertIn("can't name a project folder", r.stderr, slug)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escape")))

    def test_a_render_name_stays_inside_renders(self):
        proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(proj, "style"))
        with open(os.path.join(proj, "edit.py"), "w") as fh:
            fh.write('TITLE = "T"\nSTYLE = "lofi"\nSRC = "x.mov"\n')
        with open(os.path.join(proj, "style", "style.json"), "w") as fh:
            fh.write("{}")
        for name in ("../../escape", "a/b", "..", ".hidden"):
            r = self.run_py(os.path.join(PIPE, "render.py"), proj, name)
            self.assertNotEqual(r.returncode, 0, name)
            self.assertIn("can't name a render", r.stderr, name)


class Symlinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-hard-")
        self.outside = os.path.join(self.tmp, "private.txt")
        with open(self.outside, "w") as fh:
            fh.write("private\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_zip_leaves_a_symlink_out(self):
        kit = os.path.join(self.tmp, "kit")
        os.makedirs(kit)
        open(os.path.join(kit, "SKILL.md"), "w").close()
        os.symlink(self.outside, os.path.join(kit, "notes.txt"))
        pkg = load("setup/package.py")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            got = pkg.candidates(kit)
        self.assertEqual(got, ["SKILL.md"])
        self.assertIn("skipped a symlink", out.getvalue())

    def test_the_release_scan_flags_a_tracked_symlink(self):
        repo = os.path.join(self.tmp, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        os.symlink(self.outside, os.path.join(repo, "notes.txt"))
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        rc = load("dev/release_check.py")
        hits = rc.scan(repo, [])
        self.assertEqual([(f, what.split(" (")[0]) for f, _, what in hits], [("notes.txt", "a symlink")])


if __name__ == "__main__":
    unittest.main()
