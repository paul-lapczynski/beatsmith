"""Start the actual frozen runtime without changing settings or opening a window."""
from pathlib import Path
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave


def check(executable: Path) -> None:
    executable = executable.resolve(strict=True)
    result = subprocess.run([str(executable), "--run-stepgen", "--help"],
                            cwd=executable.parent, env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    if result.returncode or "StepMania" not in result.stdout or "--stems" not in result.stdout:
        raise RuntimeError(f"Frozen app failed startup ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    print(f"Frozen app startup passed: {executable}")


def full_check(executable: Path) -> None:
    """Exercise frozen imports, resources, generation and actual GUI startup."""
    executable = executable.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='beatsmith-frozen-check-') as tmp:
        work = Path(tmp)
        audio = work / 'fixture.wav'
        sr = 22050
        samples = []
        for i in range(sr * 8):
            phase = (i % (sr // 2)) / sr
            amplitude = math.sin(2 * math.pi * 220 * i / sr) * math.exp(-phase * 35)
            samples.append(struct.pack('<h', round(16000 * amplitude)))
        with wave.open(str(audio), 'wb') as output:
            output.setparams((1, 2, sr, 0, 'NONE', 'not compressed'))
            output.writeframes(b''.join(samples))
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', BEATSMITH_DATA=str(work / 'data'))
        roots = [executable.parent / '_internal', executable.parent.parent / 'Resources',
                 executable.parent.parent / 'Frameworks']
        payload = next((p for p in roots if (p / 'stems.py').is_file()), None)
        if payload is None or not (payload / 'models/step_placement_v1.onnx').is_file():
            raise RuntimeError('Frozen payload is missing worker scripts or bundled model')
        for worker, expected in (('stems.py', 'Split a song'), ('lyrics.py', 'Read the words')):
            p = subprocess.run([sys.executable, '-I', str(payload / worker)], env=env,
                               capture_output=True, text=True, timeout=45)
            if p.returncode != 1 or expected not in p.stdout + p.stderr or 'Traceback' in p.stderr:
                raise RuntimeError(f'Bundled worker cannot start: {worker}\n{p.stdout}\n{p.stderr}')
        for args, expected in (
            (['--run-stepgen', str(audio), '--out', str(work / 'songs'), '--bpm', '120',
              '--profile', 'konami', '--keep-format', '--no-art', '--ai', '0.25', '--device', 'cpu'], 'fixture:'),
            (['--check-gui'], 'Frozen GUI and editor construction passed'),
        ):
            p = subprocess.run([str(executable), *args], cwd=work, env=env, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=180)
            if p.returncode or expected not in p.stdout:
                raise RuntimeError(f'Frozen full check failed: {p.returncode}\n{p.stdout}\n{p.stderr}')
            if args[0] == '--run-stepgen' and 'without AI:' not in p.stdout:
                raise RuntimeError(f'Frozen generation did not exercise the bundled model:\n{p.stdout}')
        if not list((work / 'songs').rglob('*.sm')):
            raise RuntimeError('Frozen generator did not write a chart')
    print('Frozen generation, bundled profiles and GUI/editor checks passed')


if __name__ == "__main__":
    check(Path(sys.argv[1]))
    if '--full' in sys.argv[2:]:
        full_check(Path(sys.argv[1]))
