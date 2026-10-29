"""Compatibility entry point; implementation lives in tools.chartstats."""
import sys
from _bootstrap import load
module = load("tools.chartstats")
if __name__ == "__main__":
    raise SystemExit(module.main())
sys.modules[__name__] = module
