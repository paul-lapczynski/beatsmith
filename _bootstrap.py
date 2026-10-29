"""Bootstrap legacy source commands and frozen module imports."""
import importlib
from pathlib import Path
import sys

def load(name):
    src = Path(__file__).resolve().parent / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return importlib.import_module(name)
