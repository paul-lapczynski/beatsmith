"""One version for local installers, CI and the bundled application."""
from __future__ import annotations

import os
from pathlib import Path
import re


def build_version(root: Path | None = None) -> str:
    root = root or Path(__file__).resolve().parent.parent
    recorded = (root / "version.txt").read_text(encoding="utf-8").strip()
    value = os.environ.get("BEATSMITH_VERSION") or recorded
    value = value.removeprefix("v")
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError(f"Invalid BeatSmith installer version: {value!r}")
    major, minor, patch = map(int, value.split("."))
    if major > 255 or minor > 255 or patch > 65535:
        raise ValueError("BeatSmith version exceeds Windows installer limits")
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/v") and (value != ref[11:] or value != recorded):
        raise ValueError("Release tag, version.txt and build version must agree")
    return value


if __name__ == "__main__":
    print(build_version())
