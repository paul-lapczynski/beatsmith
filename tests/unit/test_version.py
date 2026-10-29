"""Checks for the shared installer version and tag mismatch protection."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("build_version", Path(__file__).resolve().parents[2] / "packaging/version.py")
version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version)


class BuildVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "version.txt").write_text("1.1.0\n", encoding="utf-8")
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_recorded_version(self):
        self.assertEqual(version.build_version(self.root), "1.1.0")

    def test_local_override(self):
        os.environ["BEATSMITH_VERSION"] = "v1.2.3"
        self.assertEqual(version.build_version(self.root), "1.2.3")

    def test_matching_tag(self):
        os.environ["GITHUB_REF"] = "refs/tags/v1.1.0"
        self.assertEqual(version.build_version(self.root), "1.1.0")

    def test_tag_mismatch(self):
        os.environ["GITHUB_REF"] = "refs/tags/v1.2.0"
        with self.assertRaisesRegex(ValueError, "must agree"):
            version.build_version(self.root)

    def test_override_cannot_hide_mismatched_source(self):
        os.environ.update(GITHUB_REF="refs/tags/v1.2.0", BEATSMITH_VERSION="1.2.0")
        with self.assertRaisesRegex(ValueError, "must agree"):
            version.build_version(self.root)

    def test_invalid_versions(self):
        for value in ("1.2", "01.2.3", "1.2.3-beta.1", "1.2.3+build", "256.0.0", "1.256.0", "1.2.65536"):
            with self.subTest(value=value):
                os.environ["BEATSMITH_VERSION"] = value
                with self.assertRaises(ValueError):
                    version.build_version(self.root)


if __name__ == "__main__":
    unittest.main()
