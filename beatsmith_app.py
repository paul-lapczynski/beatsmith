"""Compatibility entry point; implementation lives in beatsmith.beatsmith_app."""
import sys
from _bootstrap import load
module = load("beatsmith.beatsmith_app")
if __name__ == "__main__":
    if sys.argv[1:] == ["--check-gui"]:
        raise SystemExit(load("beatsmith.smoke_gui").main())
    raise SystemExit(module.main())
sys.modules[__name__] = module
