"""Compatibility contracts for source layout and legacy launchers."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from beatsmith import resources

AUDIO_READY = all(importlib.util.find_spec(n) for n in ('numpy', 'librosa', 'soundfile'))


class ResourceTests(unittest.TestCase):
    def test_source_resources_stay_at_existing_root(self):
        self.assertEqual(resources.source_root(), ROOT)
        self.assertTrue((resources.bundle_root() / 'patterns.toml').is_file())
        self.assertTrue((resources.bundle_root() / 'profiles/konami.toml').is_file())

    def test_frozen_resources_use_bundle_root(self):
        with patch.object(sys, '_MEIPASS', 'bundle-fixture', create=True):
            self.assertEqual(resources.bundle_root(), Path('bundle-fixture'))

    def test_source_user_data_location_does_not_follow_module_move(self):
        from beatsmith import layout
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(layout.songs_data(), ROOT / 'song-data')

    @unittest.skipUnless(AUDIO_READY, 'After audio dependencies are installed')
    def test_legacy_import_alias_preserves_globals(self):
        import stepgen
        from beatsmith import stepgen as canonical
        self.assertIs(stepgen, canonical)
        self.assertEqual(stepgen.DEFAULT_PATTERNS, ROOT / 'patterns.toml')
        self.assertEqual(stepgen.PROFILES_DIR, ROOT / 'profiles')

    @unittest.skipUnless(AUDIO_READY, 'After audio dependencies are installed')
    def test_legacy_commands_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            for entry, args, expected in (
                ('stepgen.py', ['--list-profiles'], 'konami'),
                ('beatsmith_app.py', ['--run-stepgen', '--list-profiles'], 'konami'),
                ('chartstats.py', ['--help'], '--audio'),
                ('llm_review.py', ['--help'], '--prompt-only'),
            ):
                with self.subTest(entry=entry):
                    p = subprocess.run([sys.executable, str(ROOT / entry), *args], cwd=tmp,
                                       capture_output=True, text=True, timeout=45)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    self.assertIn(expected, p.stdout)

    @unittest.skipUnless(AUDIO_READY, 'After audio dependencies are installed')
    def test_workers_start_in_isolated_python(self):
        for entry, expected in (('stems.py', 'Split a song'), ('lyrics.py', 'Read the words')):
            p = subprocess.run([sys.executable, '-I', str(ROOT / entry)], capture_output=True,
                               text=True, timeout=30)
            # No arguments prints the worker's usage and exits 1, as before.
            self.assertEqual(p.returncode, 1, p.stderr)
            self.assertIn(expected, p.stdout + p.stderr)
            self.assertNotIn('Traceback', p.stderr)
