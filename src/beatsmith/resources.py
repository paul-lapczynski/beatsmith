"""Existing resource and source-data locations, independent of module location."""
from pathlib import Path
import sys

def source_root() -> Path:
    return Path(__file__).resolve().parents[2]

def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", source_root()))

def launcher(name: str) -> Path:
    return source_root() / name
