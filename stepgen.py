"""Compatibility entry point; implementation lives in beatsmith.stepgen."""
import sys
from _bootstrap import load
module = load("beatsmith.stepgen")
if __name__ == "__main__":
    raise SystemExit(module.main())
sys.modules[__name__] = module
