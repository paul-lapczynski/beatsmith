"""Compatibility entry point; implementation lives in beatsmith.chart_editor."""
import sys
from _bootstrap import load
module = load("beatsmith.chart_editor")
if __name__ == "__main__":
    raise SystemExit(module.main())
sys.modules[__name__] = module
