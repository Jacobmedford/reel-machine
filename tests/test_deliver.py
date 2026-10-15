"""where render.py delivers the final and its phone copy: the project folder for a project intake.py made (its takes
sit in raw/, out of sight), else next to the source clip, as before"""
import contextlib, io, os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import render  # noqa: E402


class Deliver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-deliver-")
        self.final = os.path.join(self.tmp, "renders", "lab-v1.mp4")
        os.makedirs(os.path.dirname(self.final))
        for f in (self.final, self.final.replace(".mp4", "-phone.mp4")):
            open(f, "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def deliver(self, src):
        os.makedirs(os.path.dirname(src), exist_ok=True)
        open(src, "w").close()
        with contextlib.redirect_stdout(io.StringIO()):
            render.deliver(types.SimpleNamespace(SRC=src, TITLE="My: Video"), "lab-v1", self.final)

    def test_an_intake_project_gets_them_in_the_project_folder(self):
        proj = os.path.join(self.tmp, "projects", "lab")
        os.makedirs(os.path.join(proj, "raw"))
        open(os.path.join(proj, "intake.json"), "w").close()
        self.deliver(os.path.join(proj, "raw", "joined.mov"))
        self.assertEqual(sorted(f for f in os.listdir(proj) if f.endswith(".mp4")),
                         ["My Video v1 (phone).mp4", "My Video v1.mp4"])
        self.assertFalse([f for f in os.listdir(os.path.join(proj, "raw")) if f.startswith("My Video")])

    def test_a_clip_anywhere_else_gets_them_beside_it(self):
        clips = os.path.join(self.tmp, "Desktop", "raw")             # a folder named raw, but no intake.json above it
        self.deliver(os.path.join(clips, "take.mov"))
        self.assertIn("My Video v1.mp4", os.listdir(clips))
        self.assertIn("My Video v1 (phone).mp4", os.listdir(clips))


if __name__ == "__main__":
    unittest.main()
