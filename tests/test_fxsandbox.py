"""pipeline/fxsandbox.py prepare(): the sandbox builds in the project's own pack and never writes into its public/."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import fxsandbox  # noqa: E402


def touch(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


class Prepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = os.path.join(self.tmp, "proj")
        for f in ("edit.py", "words.json", "timeline.json", "style/style.json", "style/brand.css",
                  "public/clean.mp4", "public/brand.css", "public/fonts/a.ttf", "public/index.html"):
            touch(os.path.join(self.p, f))
        for d in ("fx", "assets", "audio"):
            os.makedirs(os.path.join(self.p, d))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_sandbox_builds_in_the_projects_own_pack(self):
        sb, pub = fxsandbox.prepare(self.p, "lab", fresh=True)
        self.assertTrue(os.path.islink(os.path.join(sb, "style")))
        self.assertEqual(os.path.realpath(os.path.join(sb, "style")), os.path.realpath(os.path.join(self.p, "style")))

    def test_the_build_cannot_write_into_the_projects_public(self):
        sb, pub = fxsandbox.prepare(self.p, "lab", fresh=True)
        for f in ("brand.css", "fonts"):                      # the build installs its own copies here
            self.assertFalse(os.path.lexists(os.path.join(pub, f)), f)
        self.assertTrue(os.path.islink(os.path.join(pub, "clean.mp4")))   # heavy media stay linked
        self.assertFalse(os.path.lexists(os.path.join(pub, "index.html")))

    def test_an_old_sandbox_loses_its_links_to_the_pack_files(self):
        sb = os.path.join(self.p, "work", "sandbox", "lab")
        os.makedirs(os.path.join(sb, "public"))
        os.symlink(os.path.join(self.p, "public", "brand.css"), os.path.join(sb, "public", "brand.css"))
        fxsandbox.prepare(self.p, "lab", fresh=False)
        self.assertFalse(os.path.islink(os.path.join(sb, "public", "brand.css")))
        self.assertTrue(os.path.exists(os.path.join(self.p, "public", "brand.css")))   # the project's own is untouched


if __name__ == "__main__":
    unittest.main()
