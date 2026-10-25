"""Optional add-ons BeatSmith can download on request, kept out of the
installer:

  stems    vocal separation (Demucs + PyTorch, about 1 GB)
  lyrics   AI verse detection: reads the words off the separated vocals
           (faster-whisper + the Whisper "small" model, about 650 MB)
  gpu      NVIDIA GPU support for both (PyTorch's CUDA build, about 3 GB).
           Only offered when an NVIDIA card is found. A Mac needs no
           download: the regular PyTorch already uses Apple Silicon.

They share one private Python in the user's app-data folder, so the
installed app stays small and nothing touches a Python you may have. Every
place a download comes from is listed in SOURCES, shown before anything is
downloaded and printed again as it happens.

The installed app downloads them as ready-made packs attached to its own
GitHub release (packaging/addon_pack.py builds them there): a portable
Python with everything already installed and tested, unpacked as is, so
nothing is installed on the user's computer and Windows and Mac work alike.
Run from source, they're installed with pip as before. NVIDIA GPU support
is always a pip download, as PyTorch's CUDA build is too big for a release.

    python addons.py install [stems|lyrics|gpu]   # what the app's download buttons run
    python addons.py sources [stems|lyrics|gpu]
    python addons.py status
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

PY_VERSION = "3.12.7"
PY_EMBED = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"
PYPI = "https://pypi.org (package files from files.pythonhosted.org)"
PACKAGES = {"stems": ["demucs", "soundfile", "numpy"], "lyrics": ["faster-whisper"]}
DEMUCS_MODEL = "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th"
WHISPER_REPO = "Systran/faster-whisper-small"
WHISPER_URL = f"https://huggingface.co/{WHISPER_REPO}"
# PyTorch built for CUDA, tried in this order: CUDA 12 first, because
# faster-whisper (CTranslate2) uses the cuBLAS/cuDNN 12 libraries it ships
TORCH_CUDA = "https://download.pytorch.org/whl"
TORCH_CUDA_BUILDS = ("cu128", "cu126", "cu130")
NAMES = {"stems": "Vocal separation", "lyrics": "AI verse detection", "gpu": "NVIDIA GPU support"}
SIZES = {"stems": "about 250 MB", "lyrics": "about 550 MB", "gpu": "about 3 GB"}

# the packs: a portable CPython from python-build-standalone (the builds uv
# uses), pinned, with the add-on installed into it by the release workflow
PBS_RELEASE = "20261003"
PBS_PYTHON = "3.12.15"
PBS_URL = "https://github.com/astral-sh/python-build-standalone/releases/download"
RELEASES = "https://github.com/paul-lapczynski/beatsmith/releases/download"
PACK_KINDS = ("stems", "lyrics")


def platform_tag() -> str:
    """windows-x64, mac-arm64 or mac-x64: which pack fits this computer."""
    import platform
    arm = platform.machine().lower() in ("arm64", "aarch64")
    if os.name == "nt":
        return "windows-x64"
    return "mac-arm64" if arm else "mac-x64"


def pack_name(kind: str) -> str:
    return f"BeatSmith-addon-{kind}-{platform_tag()}" + (".zip" if os.name == "nt" else ".tar.gz")


def pbs_python_url() -> str:
    triple = {"windows-x64": "x86_64-pc-windows-msvc", "mac-arm64": "aarch64-apple-darwin",
              "mac-x64": "x86_64-apple-darwin"}[platform_tag()]
    return (f"{PBS_URL}/{PBS_RELEASE}/cpython-{PBS_PYTHON}+{PBS_RELEASE}-{triple}"
            "-install_only.tar.gz")


def app_version() -> str | None:
    """The installed app's version (version.txt, written by the build); None
    when run from source, which installs with pip instead of packs."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        return (_here() / "version.txt").read_text().strip() or None
    except OSError:
        return None


def pack_url(kind: str) -> str | None:
    v = app_version()
    return f"{RELEASES}/v{v}/{pack_name(kind)}" if v and kind in PACK_KINDS else None


def run_env() -> dict:
    """The environment the add-ons run in: a pack keeps its models in its own
    cache folder, so nothing is fetched at run time."""
    env = dict(os.environ)
    cache = addon_dir() / "cache"
    if cache.is_dir():
        env["HF_HOME"] = str(cache / "huggingface")
        env["TORCH_HOME"] = str(cache / "torch")
    return env


def sources(kind: str) -> list[tuple[str, str]]:
    """(what, where from) for everything installing `kind` downloads."""
    url = pack_url(kind)
    if url:
        what = {"stems": "Python, Demucs, PyTorch and the htdemucs separation model (Meta)",
                "lyrics": "faster-whisper and the Whisper 'small' speech model (Systran)"}[kind]
        return [(f"BeatSmith's ready-made pack for {NAMES[kind]}: {what}, built and "
                 "tested by BeatSmith's release on GitHub", url)]
    out = []
    if os.name == "nt" and not _addon_python().is_file():
        out += [(f"Python {PY_VERSION} (embeddable, from python.org)", PY_EMBED),
                ("pip, Python's package installer", GET_PIP)]
    if kind == "stems":
        out += [("Demucs, SoundFile, NumPy and PyTorch (Demucs needs it), from the Python "
                 "Package Index", PYPI),
                ("The htdemucs separation model (Meta)", DEMUCS_MODEL)]
    elif kind == "gpu":
        out += [("PyTorch and torchaudio built for NVIDIA CUDA, with the CUDA libraries they "
                 "need, replacing the CPU-only PyTorch (PyTorch's own package server; the first "
                 f"of {', '.join(TORCH_CUDA_BUILDS)} that installs)", f"{TORCH_CUDA}/{TORCH_CUDA_BUILDS[0]}")]
    else:
        out += [("faster-whisper and what it needs (CTranslate2, tokenizers, huggingface-hub, "
                 "PyAV, ONNX Runtime), from the Python Package Index", PYPI),
                ("The Whisper 'small' speech model, converted for faster-whisper (Systran, "
                 "from Hugging Face; the files come from its download servers)", WHISPER_URL)]
    return out


def addon_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    new, old = Path(base) / "BeatSmith" / "addons" / "stems", Path(base) / "stepgen" / "addons" / "stems"
    # downloaded before the rename to BeatSmith: used where it is, as its
    # Python may not work moved
    return old if old.is_dir() and not new.is_dir() else new


def whisper_dir() -> Path:
    return addon_dir() / "models" / "faster-whisper-small"


def _addon_python() -> Path:
    d = addon_dir() / "python"
    return d / ("python.exe" if os.name == "nt" else "bin/python3")


def _has_demucs(python: str) -> bool:
    try:
        r = subprocess.run([python, "-c", "import demucs.pretrained, soundfile"],
                           capture_output=True, timeout=120, **_no_window())
        return r.returncode == 0
    except Exception:
        return False


def _no_window() -> dict:
    return {"creationflags": 0x08000000} if os.name == "nt" else {}     # CREATE_NO_WINDOW


def stems_python() -> str | None:
    """A Python that can run stems.py, or None if the add-on isn't installed."""
    if not getattr(sys, "frozen", False):
        try:
            import demucs.pretrained  # noqa: F401
            return sys.executable
        except Exception:
            pass
    p = _addon_python()
    return str(p) if p.is_file() and _stems_done() else None


def _stems_done() -> bool:
    """Vocal separation finished installing: stems.ok, or (from before there
    was one) Demucs in the add-ons' Python while no install is under way. Its
    Python is there long before Demucs is, so that alone isn't enough."""
    d = addon_dir()
    if (d / "stems.ok").is_file():
        return True
    if (d / "stems.installing").is_file():
        return False
    return ((d / "python" / "Lib" / "site-packages" / "demucs").is_dir()
            or any(d.glob("python/lib/python3*/site-packages/demucs")))


def lyrics_python() -> str | None:
    """A Python that can run lyrics.py, or None if the add-on isn't installed."""
    if not (whisper_dir() / "model.bin").is_file():
        return None
    if not getattr(sys, "frozen", False):
        try:
            import faster_whisper  # noqa: F401
            return sys.executable
        except Exception:
            pass
    p = _addon_python()
    return str(p) if p.is_file() and (addon_dir() / "lyrics.ok").is_file() else None


def gpu_python() -> str | None:
    """The add-ons' Python if it has the CUDA build of PyTorch, else None."""
    p = stems_python()
    if p is None:
        return None
    if p != sys.executable and not (addon_dir() / "gpu.ok").is_file():
        return None
    try:
        r = subprocess.run([p, "-c", "import torch; print(torch.version.cuda or '')"],
                           capture_output=True, text=True, timeout=120, **_no_window())
        return p if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def installed(kind: str = "stems") -> bool:
    if kind == "gpu":
        return gpu_python() is not None
    return (stems_python() if kind == "stems" else lyrics_python()) is not None


def _download(url: str, dest: Path, log) -> None:
    log(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def _python(log) -> Path:
    """The add-ons' private Python, set up on first use."""
    d = addon_dir()
    d.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        py_dir = d / "python"
        py = py_dir / "python.exe"
        if not py.is_file():
            z = d / "python-embed.zip"
            _download(PY_EMBED, z, log)
            with zipfile.ZipFile(z) as zf:
                zf.extractall(py_dir)
            z.unlink()
            # the embeddable Python ignores site-packages until "import site" is on
            for pth in py_dir.glob("python*._pth"):
                pth.write_text(pth.read_text().replace("#import site", "import site"))
            gp = d / "get-pip.py"
            _download(GET_PIP, gp, log)
            log("setting up pip")
            subprocess.run([str(py), str(gp), "--no-warn-script-location"], check=True, **_no_window())
            gp.unlink()
    else:
        if getattr(sys, "frozen", False):
            # the packaged Mac app has no Python of its own to make a venv from
            raise RuntimeError("add-ons aren't available in the Mac app yet")
        py = _addon_python()
        if not py.is_file():
            log("creating a private Python environment")
            subprocess.run([sys.executable, "-m", "venv", str(d / "python")], check=True)
    return py


def _download_progress(url: str, dest: Path, log) -> None:
    log(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
        total, done, shown = int(r.headers.get("Content-Length") or 0), 0, -1
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total and done * 10 // total > shown:
                shown = done * 10 // total
                log(f"  {done >> 20} of {total >> 20} MB")


def _install_pack(kind: str, log) -> None:
    """Download the ready-made pack for this app version and unpack it into
    the add-ons folder. Vocal separation starts the folder afresh (its pack
    is the Python everything else goes into); AI verse detection's pack adds
    to it."""
    d = addon_dir()
    if kind == "stems" and d.exists():
        shutil.rmtree(d)          # an older pip install, or a pack from another version
    elif kind == "lyrics" and stems_python() is None:
        raise RuntimeError("download vocal separation first: the lyrics are read off the separated vocals")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{kind}.ok").unlink(missing_ok=True)
    (d / f"{kind}.installing").write_text("")
    archive = d / pack_name(kind)
    try:
        _download_progress(pack_url(kind), archive, log)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"there's no {NAMES[kind]} pack for this computer "
                               f"({platform_tag()}) in BeatSmith {app_version()}'s release") from e
        raise
    log("unpacking")
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(d)
    else:
        with tarfile.open(archive) as tf:
            tf.extractall(d, filter="tar")
    archive.unlink()
    (d / f"{kind}.ok").write_text("ok")
    (d / f"{kind}.installing").unlink(missing_ok=True)
    log(f"{NAMES[kind]} is ready")


def install(log=print, kind: str = "stems") -> None:
    log(f"{NAMES[kind]}: downloading from")
    for what, url in sources(kind):
        log(f"  {what}: {url}")
    if pack_url(kind):
        _install_pack(kind, log)
        return
    py = _python(log)
    if kind == "gpu":
        _install_cuda_torch(py, log)
        return
    if kind == "stems":
        (addon_dir() / "stems.ok").unlink(missing_ok=True)
        (addon_dir() / "stems.installing").write_text("")
    log(f"installing {', '.join(PACKAGES[kind])} from {PYPI} (this takes a while)")
    subprocess.run([str(py), "-m", "pip", "install", "--no-warn-script-location", *PACKAGES[kind]],
                   check=True, **_no_window())
    if kind == "stems":
        log(f"fetching the separation model from {DEMUCS_MODEL}")
        subprocess.run([str(py), "-c", "from demucs.pretrained import get_model; get_model('htdemucs')"],
                       check=True, **_no_window())
        (addon_dir() / "stems.ok").write_text("ok")
        (addon_dir() / "stems.installing").unlink(missing_ok=True)
        log("vocal separation is ready")
    else:
        log(f"fetching the Whisper model from {WHISPER_URL}")
        subprocess.run([str(py), str(_here() / "lyrics.py"), "fetch", str(whisper_dir())],
                       check=True, **_no_window())
        (addon_dir() / "lyrics.ok").write_text("ok")
        log("AI verse detection is ready")


def _install_cuda_torch(py: Path, log) -> None:
    """Swap the add-ons' CPU-only PyTorch for the CUDA build. Vocal separation
    has to be there first (it brings the rest of what Demucs needs)."""
    if stems_python() is None:
        raise RuntimeError("download vocal separation first: GPU support speeds it up")
    for build in TORCH_CUDA_BUILDS:
        url = f"{TORCH_CUDA}/{build}"
        log(f"installing PyTorch for CUDA ({build}) from {url} (this takes a while)")
        r = subprocess.run([str(py), "-m", "pip", "install", "--no-warn-script-location", "--upgrade",
                            "--force-reinstall", "torch", "torchaudio", "--index-url", url], **_no_window())
        if r.returncode == 0:
            break
        log(f"no {build} build for this Python; trying the next one")
    else:
        raise RuntimeError("no CUDA build of PyTorch installed")
    r = subprocess.run([str(py), "-c", "import torch; print(torch.cuda.get_device_name(0) "
                        "if torch.cuda.is_available() else '')"], capture_output=True, text=True, **_no_window())
    name = r.stdout.strip()
    (addon_dir() / "gpu.ok").write_text("ok")
    log(f"GPU support is ready: {name}" if name else
        "GPU support is installed, but PyTorch can't see the GPU (an old NVIDIA driver?); "
        "BeatSmith keeps using the CPU until it can")


def _here() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def separate(song: Path, out_dir: Path, log=print) -> bool:
    """Run stems.py with the add-on's Python. False if the add-on isn't there."""
    py = stems_python()
    if py is None:
        return False
    # -I: not the script's own folder first, which in the installed app holds
    # its compiled libraries, built for its own Python
    r = subprocess.run([py, "-I", str(_here() / "stems.py"), str(song), str(out_dir)],
                       capture_output=True, text=True, env=run_env(), **_no_window())
    if r.returncode != 0:
        lines = (r.stderr or r.stdout or "").strip().splitlines()
        log("stem separation failed: " + (lines[-1] if lines else "no output"))
        return False
    return True


def transcribe(vocals: Path, out_json: Path, log=print) -> bool:
    """Run lyrics.py on a vocals stem. False if the add-on isn't there or it failed."""
    py = lyrics_python()
    if py is None:
        return False
    r = subprocess.run([py, "-I", str(_here() / "lyrics.py"), str(vocals), str(out_json), str(whisper_dir())],
                       capture_output=True, text=True, env=run_env(), **_no_window())
    if r.returncode != 0:
        lines = (r.stderr or r.stdout or "").strip().splitlines()
        log("reading the lyrics failed: " + (lines[-1] if lines else "no output"))
        return False
    return True


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    kind = sys.argv[2] if len(sys.argv) > 2 else "stems"
    if cmd == "install":
        install(kind=kind)
    elif cmd == "sources":
        for what, url in sources(kind):
            print(f"{what}: {url}")
    else:
        for k in NAMES:
            print(NAMES[k], "installed" if installed(k) else "not installed")
        print(addon_dir())
