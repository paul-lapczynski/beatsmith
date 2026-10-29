"""Compatibility entry point; implementation lives in workers.lyrics."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))
from _bootstrap import load
if __name__ == "__main__":
    import runpy
    load("workers")
    runpy.run_module("workers.lyrics", run_name="__main__")
else:
    sys.modules[__name__] = load("workers.lyrics")
