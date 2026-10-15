"""cut.leads: J_LEADS overrides join by join; None keeps the kit's rule (J_LEAD, fitted to a source cut) there."""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import cut  # noqa: E402


class Leads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "work"))
        self.cuts([])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cuts(self, cuts):                       # the source's own hard cuts, as cut.source_cuts caches them
        with open(os.path.join(self.tmp, "work", "source_cuts.json"), "w") as fh:
            json.dump({"src": "take.mov", "cuts": cuts}, fh)

    def edit(self, j_leads):
        return types.SimpleNamespace(PROJECT=self.tmp, SRC="take.mov", KEEP=[(0.0, 1.0), (2.0, 3.0), (4.0, 5.0)],
                                     J_LEAD=0.3, J_LEADS=j_leads)

    def test_no_override_is_the_kit_lead(self):
        self.assertEqual(cut.leads(self.edit(None)), [0.3, 0.3])

    def test_all_numbers_are_used_as_given(self):
        self.assertEqual(cut.leads(self.edit([0.1, 0.2])), [0.1, 0.2])

    def test_none_keeps_the_kit_lead_for_that_join(self):
        self.assertEqual(cut.leads(self.edit([0.0, None])), [0.0, 0.3])

    def test_none_still_fits_a_source_cut(self):
        self.cuts([3.1])                         # the source is pre-cut in the pause after the second range
        self.assertEqual(cut.leads(self.edit([0.0, None])), [0.0, round(3.1 - 3.0 - 0.5 / 30, 4)])

    def test_wrong_length_stops(self):
        with self.assertRaises(SystemExit):
            cut.leads(self.edit([0.0]))


if __name__ == "__main__":
    unittest.main()
