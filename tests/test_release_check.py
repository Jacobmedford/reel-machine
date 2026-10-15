"""dev/release_check.py: every kind of thing a public repo must not carry is found, and a clean repo passes. The
planted values are built in pieces so this file passes the same scan."""
import contextlib, importlib.util, io, os, shutil, subprocess, tempfile, unittest

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("release_check", os.path.join(KIT, "dev", "release_check.py"))
RC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RC)

NAME = "Zan" + "zibarth"                      # a made-up person for the deny list
HOME_PATH = "/Us" + "ers/zanz/projects/a"
KEY = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2"


class Scan(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="reel-machine-release-")
        subprocess.run(["git", "init", "-q", self.repo], check=True)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def put(self, rel, data):
        p = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode())

    def scan(self, terms=(NAME,)):
        subprocess.run(["git", "-C", self.repo, "add", "-A"], check=True)
        return RC.scan(self.repo, list(terms))

    def test_a_clean_repo_passes(self):
        self.put("README.md", "A tool. Clone github.com/someone/tool and run setup.\n")
        self.put("packs/a/local-fonts/A-Regular.ttf", b"\0font")
        self.put("packs/a/local-fonts/OFL.txt", "SIL Open Font License\n")
        self.put("LICENSE", "MIT License\n\nCopyright (c) 2026 " + NAME + "\n")
        self.assertEqual(self.scan(), [])

    def test_every_kind_is_found(self):
        self.put("notes.md", f"made by {NAME.lower()}\nsaved in {HOME_PATH}\nkey {KEY}\na \u2014 dash\n")
        self.put("style.json", '{"display": "' + "Exten" + "da" + ' 30"}\n')
        self.put("fonts/B.otf", b"\0font")
        self.put("sfx/fav-" + "boom.wav", b"\0RIFF")
        self.put("img/a.jpg", b"\xff\xd8\0" + HOME_PATH.encode())
        self.put(".env", "X=1\n")
        kinds = " | ".join(what for _, _, what in self.scan())
        for want in ("a name on the deny list", "a home path", "an OpenAI-style key", "an em dash", "a private asset",
                     "a font with no OFL.txt", "a private sound", "binary holds", "an env file"):
            self.assertIn(want, kinds)

    def test_the_license_line_may_name_a_person(self):
        self.put("LICENSE", "Copyright (c) 2026 " + NAME + "\nPermission is granted, " + NAME + " says\n")
        hits = self.scan()
        self.assertEqual([(f, ln) for f, ln, _ in hits], [("LICENSE", 2)])

    def test_the_cli_exits_one_on_a_hit(self):
        self.put("a.md", HOME_PATH + "\n")
        subprocess.run(["git", "-C", self.repo, "add", "-A"], check=True)
        deny = os.path.join(self.repo, "..", os.path.basename(self.repo) + "-deny.txt")
        with open(deny, "w") as fh:
            fh.write("# test\n" + NAME + "\n")
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = RC.main(["--deny", deny, self.repo])
        finally:
            os.remove(deny)
        self.assertEqual(code, 1)
        self.assertIn("a.md:1: a home path", out.getvalue())


if __name__ == "__main__":
    unittest.main()
