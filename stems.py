"""Split a song into stems (vocals, drums, bass, other) with Demucs, so
stepgen can follow the vocal or lead line instead of everything tonal.

    python stems.py "My Song.ogg"            # writes My Song.stems/ next to it
    python stems.py "My Song.mp3" out_dir

Optional: needs `pip install demucs soundfile` (pulls in PyTorch, about
1 GB); the app can download all of it for you (Options > Vocal separation). The
first run downloads the htdemucs model (~80 MB). Separation takes roughly
one to three minutes per song on a normal CPU; the result is cached, so
each song is only separated once.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

STEMS = ("vocals", "drums", "bass", "other")
MODEL = "htdemucs"


def stems_dir_for(song_folder: Path) -> Path:
    """Where stepgen keeps a song's stems: a hidden folder in its song folder."""
    return song_folder / ".stems"


def have_stems(d: Path) -> bool:
    return all((d / f"{s}.ogg").is_file() for s in STEMS)


def demucs_available() -> bool:
    try:
        import demucs.apply  # noqa: F401
        import demucs.pretrained  # noqa: F401
        return True
    except Exception:
        return False


def _write_ogg(path: Path, data: np.ndarray, sr: int) -> None:
    import soundfile as sf
    with sf.SoundFile(str(path), "w", samplerate=sr, channels=data.shape[1],
                      format="OGG", subtype="VORBIS") as f:
        for i in range(0, len(data), sr * 10):            # blocks: big Vorbis writes can crash
            f.write(data[i:i + sr * 10])


def separate(audio: Path, out_dir: Path, log=print) -> Path:
    """Write vocals/drums/bass/other.ogg into out_dir (skipped if already there)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if have_stems(out_dir):
        return out_dir
    import soundfile as sf
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    log(f"progress: separating stems ({MODEL})")
    model = get_model(MODEL)
    model.eval()
    data, sr = sf.read(str(audio), dtype="float32", always_2d=True)   # .ogg/.wav/.flac
    y = data.T
    if y.shape[0] == 1:
        y = np.repeat(y, 2, axis=0)
    if sr != model.samplerate:
        import torchaudio.functional as AF
        y = AF.resample(torch.tensor(y), sr, model.samplerate).numpy()
        sr = model.samplerate
    wav = torch.tensor(y[:2], dtype=torch.float32)
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        out = apply_model(model, ((wav - mean) / std)[None], device="cpu", split=True,
                          overlap=0.25, progress=False)[0]
    out = out * std + mean
    for name, src in zip(model.sources, out):
        if name in STEMS:
            _write_ogg(out_dir / f"{name}.ogg", src.numpy().T.astype(np.float32), sr)
    return out_dir


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 1
    if not demucs_available():
        print("Demucs isn't installed. Run:  pip install demucs")
        return 1
    src = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else src.with_suffix(".stems")
    separate(src, out)
    print(f"stems in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
