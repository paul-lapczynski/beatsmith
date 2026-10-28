"""Compatibility entry point; implementation lives in tools.llm_review."""
import sys
from _bootstrap import load
module = load("tools.llm_review")
if __name__ == "__main__":
    raise SystemExit(module.main())
sys.modules[__name__] = module
