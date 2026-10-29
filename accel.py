"""Compatibility entry point; implementation lives in beatsmith.accel."""
import sys
from _bootstrap import load
if __name__ == "__main__":
    import runpy
    load("beatsmith")
    runpy.run_module("beatsmith.accel", run_name="__main__")
else:
    sys.modules[__name__] = load("beatsmith.accel")
