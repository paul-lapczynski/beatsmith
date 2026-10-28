"""Start the actual frozen runtime without changing settings or opening a window."""
from pathlib import Path
import os
import subprocess
import sys


def check(executable: Path) -> None:
    executable = executable.resolve(strict=True)
    result = subprocess.run([str(executable), "--run-stepgen", "--help"],
                            cwd=executable.parent, env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    if result.returncode or "StepMania" not in result.stdout or "--stems" not in result.stdout:
        raise RuntimeError(f"Frozen app failed startup ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    print(f"Frozen app startup passed: {executable}")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
