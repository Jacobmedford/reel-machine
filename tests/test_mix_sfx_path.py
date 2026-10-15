import json, os, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))

class SfxPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "proj"); os.makedirs(os.path.join(self.project, "audio"))
        self.home = os.path.join(self.tmp, "home"); os.makedirs(os.path.join(self.home, "sfx", "favorites"))
        os.makedirs(os.path.join(self.home, "sfx", "library"))
        self.libfile = os.path.join(self.tmp, "Lib Sound.wav"); open(self.libfile, "wb").close()
        json.dump([{"name": "lib-sound", "path": self.libfile}],
                  open(os.path.join(self.home, "sfx", "library", "index.json"), "w"))
        open(os.path.join(self.home, "sfx", "favorites", "fav-ding.wav"), "wb").close()

    def load(self):
        import importlib, mix
        importlib.reload(mix)
        return mix

    def test_kit_sound_still_resolves(self):
        mix = self.load()
        with mock.patch.object(mix, "SFX_HOME", os.path.join(self.home, "sfx")):
            self.assertTrue(mix.sfx_path(self.project, "whoosh").endswith(os.path.join("audio", "sfx", "whoosh.wav")))

    def test_favorite_resolves(self):
        mix = self.load()
        with mock.patch.object(mix, "SFX_HOME", os.path.join(self.home, "sfx")):
            self.assertEqual(mix.sfx_path(self.project, "fav-ding"),
                             os.path.join(self.home, "sfx", "favorites", "fav-ding.wav"))

    def test_library_index_resolves(self):
        mix = self.load()
        with mock.patch.object(mix, "SFX_HOME", os.path.join(self.home, "sfx")):
            self.assertEqual(mix.sfx_path(self.project, "lib-sound"), self.libfile)

    def test_project_audio_wins(self):
        mix = self.load()
        local = os.path.join(self.project, "audio", "fav-ding.wav"); open(local, "wb").close()
        with mock.patch.object(mix, "SFX_HOME", os.path.join(self.home, "sfx")):
            self.assertEqual(mix.sfx_path(self.project, "fav-ding"), local)

    def test_missing_name_lists_sources(self):
        mix = self.load()
        with mock.patch.object(mix, "SFX_HOME", os.path.join(self.home, "sfx")):
            with self.assertRaises(SystemExit) as e:
                mix.sfx_path(self.project, "nope")
        self.assertIn("fav-ding", str(e.exception))

if __name__ == "__main__":
    unittest.main()
