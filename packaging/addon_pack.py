"""Build the add-on packs the installed app downloads (see addons.py): a
portable Python with the add-on installed, its model fetched and the whole
thing tested, packed as it should land in the add-ons folder.

    python packaging/addon_pack.py <out folder> [work folder]

writes, for the computer it runs on (the release workflow runs it on
Windows and on an Apple Silicon Mac):

    BeatSmith-addon-stems-<platform>.zip|.tar.gz    Python + Demucs + PyTorch + htdemucs
    BeatSmith-addon-lyrics-<platform>.zip|.tar.gz   faster-whisper + the Whisper model,
                                                    only what it adds to the first

Needs nothing but this Python's standard library; what goes in the packs is
downloaded into the work folder.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import addons  # noqa: E402


def run(*cmd, env=None):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, env=env)


def files(d: Path) -> dict[str, tuple[int, int]]:
    return {p.relative_to(d).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in d.rglob("*") if p.is_file() or p.is_symlink()}


def pack(d: Path, out: Path, only: set[str] | None = None) -> None:
    """d's files (or just `only`) into out, with paths relative to d. A Mac
    pack is a .tar.gz, which keeps Python's symlinks and executable bits."""
    names = sorted(only if only is not None else files(d))
    print(f"packing {len(names)} files into {out.name}", flush=True)
    if out.name.endswith(".zip"):
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for n in names:
                zf.write(d / n, n)
    else:
        with tarfile.open(out, "w:gz", compresslevel=6) as tf:
            for n in names:
                tf.add(d / n, n, recursive=False)
    print(f"  {out.stat().st_size >> 20} MB", flush=True)


def main(argv: list[str]) -> int:
    out = Path(argv[0]).resolve()
    work = Path(argv[1]).resolve() if len(argv) > 1 else out / "work"
    out.mkdir(parents=True, exist_ok=True)
    if work.exists():
        shutil.rmtree(work)
    d = work / "addons"                       # what lands in the user's add-ons folder
    d.mkdir(parents=True)

    # a portable Python: the tarball's one folder is python/
    tgz = work / "python.tar.gz"
    print(f"downloading {addons.pbs_python_url()}", flush=True)
    urllib.request.urlretrieve(addons.pbs_python_url(), tgz)
    with tarfile.open(tgz) as tf:
        tf.extractall(d, filter="tar")
    tgz.unlink()
    py = d / ("python/python.exe" if os.name == "nt" else "python/bin/python3")

    # models go in the pack's own cache folder (addons.run_env points there)
    (d / "cache").mkdir()
    env = dict(os.environ, HF_HOME=str(d / "cache" / "huggingface"), TORCH_HOME=str(d / "cache" / "torch"),
               PIP_NO_CACHE_DIR="1", PIP_DISABLE_PIP_VERSION_CHECK="1")

    # ---- vocal separation
    run(py, "-m", "pip", "install", "--no-warn-script-location", *addons.PACKAGES["stems"], env=env)
    run(py, "-c", "from demucs.pretrained import get_model; get_model('htdemucs')", env=env)
    # the test: separate two seconds of noise, run the way the app runs it
    clip, stems = work / "test.wav", work / "test.stems"
    run(py, "-c", "import numpy as np, soundfile as sf, sys; "
        "sf.write(sys.argv[1], np.random.default_rng(0).normal(0, .1, (88200, 2)).astype('float32'), 44100)",
        clip, env=env)
    run(py, "-I", ROOT / "stems.py", clip, stems, env=env)
    missing = [s for s in ("vocals", "drums", "bass", "other") if not (stems / f"{s}.ogg").is_file()]
    if missing:
        sys.exit(f"the stems test made no {', '.join(missing)}")
    # what's in the pack, kept as is by the next one so the two never mix versions
    pins = work / "pins.txt"
    pins.write_text(subprocess.run([str(py), "-m", "pip", "freeze"], check=True, capture_output=True,
                                   text=True, env=env).stdout)
    print(pins.read_text(), flush=True)
    shutil.rmtree(d / "cache" / "torch", ignore_errors=True)  # only kernels/temp; the model is in huggingface/
    (d / "stems.ok").write_text("ok")
    pack(d, out / addons.pack_name("stems"))
    before = files(d)

    # ---- AI verse detection: only what it adds goes in its pack
    run(py, "-m", "pip", "install", "--no-warn-script-location", "-c", pins, *addons.PACKAGES["lyrics"],
        env=env)
    model = d / "models" / "faster-whisper-small"
    run(py, "-I", ROOT / "lyrics.py", "fetch", model, env=env)
    run(py, "-c", "import sys; from faster_whisper import WhisperModel; "
        "WhisperModel(sys.argv[1], device='cpu', compute_type='int8')", model, env=env)
    if not (model / "model.bin").is_file():
        sys.exit("the Whisper model didn't download")
    (d / "lyrics.ok").write_text("ok")
    after = files(d)
    pack(d, out / addons.pack_name("lyrics"), {n for n, v in after.items() if before.get(n) != v})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
