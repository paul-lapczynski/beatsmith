from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tempo import validate_bpm


class TempoTests(unittest.TestCase):
    def test_automatic(self):
        self.assertIsNone(validate_bpm(None))
        self.assertIsNone(validate_bpm(0))

    def test_musical_overrides(self):
        for bpm in (20, 60, 120, 119.75, 400, 600):
            self.assertEqual(validate_bpm(bpm), bpm)

    def test_reject_accidental_and_nonfinite_values(self):
        for bpm in (1, -1, 19.99, float('nan'), float('inf')):
            with self.subTest(bpm=bpm), self.assertRaisesRegex(ValueError, 'detect/auto'):
                validate_bpm(bpm)
