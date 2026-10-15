"""where the creator's home folder is: $REEL_MACHINE_HOME, $REEL_KIT_HOME, ~/reel-machine, an old ~/reel-kit
that holds a style pack, else a new ~/reel-machine"""
import importlib.util, json, os, re, shutil, subprocess, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import common as C

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
X = lambda p: p.replace("~", "/h")                                  # noqa: E731

class Home(unittest.TestCase):
    def home(self, env=None, have=()):
        return C.resolve_home(env or {}, X, lambda p: p in have)

    def test_new_variable_wins(self):
        self.assertEqual(self.home({"REEL_MACHINE_HOME": "~/a", "REEL_KIT_HOME": "~/b"}), "/h/a")

    def test_old_variable_still_works(self):
        self.assertEqual(self.home({"REEL_KIT_HOME": "~/b"}), "/h/b")

    def test_new_folder_when_it_exists(self):
        self.assertEqual(self.home(have={"/h/reel-machine", "/h/reel-kit/style/style.json"}), "/h/reel-machine")

    def test_an_old_home_with_a_style_pack_is_kept(self):
        self.assertEqual(self.home(have={"/h/reel-kit/style/style.json"}), "/h/reel-kit")

    def test_an_empty_old_folder_is_not_a_home(self):
        self.assertEqual(self.home(have={"/h/reel-kit"}), "/h/reel-machine")

class Env(unittest.TestCase):
    def test_new_name_then_old(self):
        with mock.patch.dict(os.environ):                            # the shell's own values come back afterwards
            os.environ.pop("REEL_MACHINE_JOBS", None); os.environ["REEL_KIT_JOBS"] = "3"
            self.assertEqual(C.env("JOBS"), "3")
            os.environ["REEL_MACHINE_JOBS"] = "5"
            self.assertEqual(C.env("JOBS"), "5")
            os.environ.pop("REEL_MACHINE_JOBS"); os.environ.pop("REEL_KIT_JOBS")
            self.assertEqual(C.env("JOBS", "2"), "2")

class EveryReader(unittest.TestCase):
    """pack.py and style.py use the rule above. setup.py runs before anything is installed, and the magazine-cover
    mask and the storyboard-note card's two generators run from a project's copy, so none of them can import it: each
    keeps a copy, and every copy must give the same answer. Nothing here makes a folder: the homes are names only."""
    ENVS = ({}, {"REEL_MACHINE_HOME": "~/a"}, {"REEL_KIT_HOME": "~/b"}, {"REEL_MACHINE_HOME": "~/a", "REEL_KIT_HOME": "~/b"},
            {"REEL_MACHINE_HOME": "", "REEL_KIT_HOME": "~/b"})
    HAVE = (set(), {"/h/reel-machine"}, {"/h/reel-kit"}, {"/h/reel-kit/style/style.json"},
            {"/h/reel-machine", "/h/reel-kit/style/style.json"})

    def load(self, rel, env):
        spec = importlib.util.spec_from_file_location("copy_of_" + os.path.basename(rel)[:-3], os.path.join(KIT, rel))
        m = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, env):
            spec.loader.exec_module(m)
        return m

    def test_pack_reads_it_on_every_call(self):
        import pack as PK
        with mock.patch.dict(os.environ, {"REEL_MACHINE_HOME": "/nowhere/new", "REEL_KIT_HOME": "/nowhere/old"}):
            self.assertEqual(PK.home(), "/nowhere/new")
            del os.environ["REEL_MACHINE_HOME"]
            self.assertEqual(PK.home(), "/nowhere/old")

    def test_style_reads_both_names(self):
        clean = {k: v for k, v in os.environ.items() if k not in ("REEL_MACHINE_HOME", "REEL_KIT_HOME")}
        for name in ("REEL_MACHINE_HOME", "REEL_KIT_HOME"):
            r = subprocess.run([sys.executable, "-c", "import style; print(style.STYLE_DIR)"], capture_output=True,
                               text=True, cwd=os.path.join(KIT, "pipeline"), env=dict(clean, **{name: "/nowhere/home"}))
            self.assertEqual(r.stdout.strip(), os.path.join("/nowhere/home", "style"), (name, r.stderr))

    def test_the_copies_agree(self):
        for rel in ("setup/setup.py", "fx/magazine-cover/mask.py", "presets/card-storyboard-note/frame.py"):
            m = self.load(rel, {})
            for env in self.ENVS:
                for have in self.HAVE:
                    exists = lambda p: p in have                    # noqa: E731
                    self.assertEqual(m.resolve_home(env, X, exists), C.resolve_home(env, X, exists), (rel, env, have))

    def test_the_node_copy_agrees(self):
        """capture-storyboard.mjs: its resolveHome, run in node with the same names and folders"""
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        mjs = os.path.join(KIT, "presets", "card-storyboard-note", "capture-storyboard.mjs")
        with open(mjs, encoding="utf-8") as fh:
            src = fh.read()
        fn = re.search(r"^function resolveHome\(.*?^}$", src, re.S | re.M).group(0)
        cases = [(env, sorted(have)) for env in self.ENVS for have in self.HAVE]
        js = ("const path = require('path').posix; const HOME = '/h';\n" + fn + "\n"
              "const cases = " + json.dumps(cases) + ";\n"
              "console.log(JSON.stringify(cases.map(([env, have]) => resolveHome(env, (p) => have.includes(p)))));")
        r = subprocess.run([node, "-e", js], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        want = [C.resolve_home(env, X, lambda p, have=have: p in have) for env, have in cases]
        self.assertEqual(json.loads(r.stdout), want)

    def test_setup_installs_into_that_home(self):
        self.assertEqual(self.load("setup/setup.py", {"REEL_MACHINE_HOME": "/nowhere/new"}).VENV,
                         os.path.join("/nowhere/new", ".venv"))
