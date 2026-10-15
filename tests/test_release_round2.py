"""the second release review: a pack answers a contrast check on purpose and only that one goes quiet, a build keeps
only the fonts its CSS uses, and a matte model already on disk must match its checksum before it is loaded"""
import contextlib, hashlib, io, json, os, shutil, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import style as ST  # noqa: E402
import pack as P  # noqa: E402
import matte as M  # noqa: E402


class AnsweredChecks(unittest.TestCase):
    def pack(self, **extra):
        S = ST.merge(ST.DEFAULT, extra)
        S["colors"] = dict(S["colors"], caption_box=S["colors"]["accent"])     # the slab is the accent
        return S

    def test_an_accent_slab_warns_until_the_pack_answers_it(self):
        name = "accent words inside the caption box"
        self.assertTrue([w for w in ST.check(self.pack()) if w.startswith(name)])
        answered = ST.check(self.pack(checks={name: "ink on a light chip"}))
        self.assertFalse([w for w in answered if w.startswith(name)])

    def test_an_answer_quiets_only_its_own_check(self):
        S = self.pack(checks={"accent words inside the caption box": "chip"})
        S["colors"] = dict(S["colors"], ink=S["colors"]["light"])              # ink on light: unreadable
        self.assertTrue([w for w in ST.check(S) if w.startswith("ink on light")])


class FontsAreRebuilt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-fonts-")
        self.pack = os.path.join(self.tmp, "mine")
        os.makedirs(os.path.join(self.pack, "local-fonts"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def use(self, family, file):
        fonts = {r: {"family": family, "italic": False, "weight": 400} for r in P.ROLES}
        with open(os.path.join(self.pack, "style.json"), "w") as fh:
            json.dump({"fonts": fonts}, fh)
        with open(os.path.join(self.pack, "local-fonts", file), "wb") as fh:
            fh.write(b"\0\1\0\0 font")
        with contextlib.redirect_stdout(io.StringIO()):
            P.build(self.pack)
        return sorted(os.listdir(os.path.join(self.pack, "fonts")))

    def test_a_font_the_pack_no_longer_uses_is_not_kept(self):
        self.assertEqual(self.use("Oldface", "Oldface-Regular.ttf"), ["Oldface-Regular.ttf"])
        os.rename(os.path.join(self.pack, "local-fonts", "Oldface-Regular.ttf"),
                  os.path.join(self.tmp, "Oldface-Regular.ttf"))                # the creator swapped the face
        self.assertEqual(self.use("Newface", "Newface-Regular.ttf"), ["Newface-Regular.ttf"])


class MatteModel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-rvm-")
        self.model = os.path.join(self.tmp, "rvm.torchscript")
        with open(self.model, "wb") as fh:
            fh.write(b"a model")
        self.good = hashlib.sha256(b"a model").hexdigest()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def verify(self, digest):
        with mock.patch.object(M, "MODEL", self.model), mock.patch.object(M, "MODEL_SHA256", digest), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            M.verify_model()
        return out.getvalue()

    def test_a_matching_model_stays(self):
        self.assertEqual(self.verify(self.good), "")
        self.assertTrue(os.path.exists(self.model))

    def test_a_model_that_differs_is_set_aside_not_loaded(self):
        said = self.verify("0" * 64)
        self.assertFalse(os.path.exists(self.model))
        aside = [f for f in os.listdir(self.tmp) if ".mismatch-" in f]
        self.assertEqual(len(aside), 1)                                         # kept under a new name, never deleted
        self.assertIn("did not match its checksum", said)

    def test_a_second_mismatch_the_same_day_keeps_both(self):
        self.verify("0" * 64)
        with open(self.model, "wb") as fh:
            fh.write(b"another bad model")
        self.verify("0" * 64)
        kept = sorted(f for f in os.listdir(self.tmp) if ".mismatch-" in f)
        self.assertEqual(len(kept), 2, kept)
        bodies = set()
        for f in kept:
            with open(os.path.join(self.tmp, f), "rb") as fh:
                bodies.add(fh.read())
        self.assertEqual(bodies, {b"a model", b"another bad model"})


if __name__ == "__main__":
    unittest.main()
