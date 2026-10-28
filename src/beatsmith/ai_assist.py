"""AI assist: the step-placement model trained on hand-made charts
(training/train.py), run with onnxruntime (on a GPU when accel.py finds one
it can use, else the CPU). It scores every frame by
how likely a chart maker would put a step there, at a given difficulty;
BeatSmith blends that into step_env by the ai_assist setting.

Needs numpy, librosa and onnxruntime (no PyTorch) and models/step_placement_v1.onnx.
The audio features below must match training/model.py exactly.
"""
from __future__ import annotations

from beatsmith.resources import bundle_root

import sys
from pathlib import Path

import numpy as np

_BASE = bundle_root()
MODEL = _BASE / "models" / "step_placement_v1.onnx"

SR, HOP, N_MELS, FFTS, FMIN = 22050, 256, 80, (1024, 2048, 4096), 27.5
BEAT_FEATS = 7

# the hand-made charts' typical meter per difficulty, for charts with no target
DEFAULT_METER = {"Beginner": 2.3, "Easy": 3.9, "Medium": 6.5, "Hard": 8.3, "Challenge": 9.6}

_session = None
_mel_cache: tuple[object, np.ndarray] | None = None     # (audio array, its log-mel)


def available() -> bool:
    """The model file is there and onnxruntime imports."""
    if not MODEL.is_file():
        return False
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def session():
    global _session
    if _session is None:
        import onnxruntime as ort

        from beatsmith import accel
        try:
            _session = ort.InferenceSession(str(MODEL), providers=accel.onnx_providers())
        except Exception:                   # a GPU provider that won't start: the CPU always works
            _session = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _session


def beat_features(beat: np.ndarray) -> np.ndarray:
    """(frames,) beat position -> (frames, BEAT_FEATS). Frames before the
    music starts or past the end still get a position; that's fine."""
    feats = []
    for k in (1, 2, 4):
        ph = 2 * np.pi * k * beat
        feats += [np.sin(ph), np.cos(ph)]
    # how close the frame is to any 16th-note slot, 1 on it, 0 halfway between
    d = np.abs(beat * 4 - np.round(beat * 4))
    feats.append(1 - 2 * d)
    return np.stack(feats, axis=1).astype(np.float32)


def log_mel(y: np.ndarray) -> np.ndarray:
    """Audio at SR -> (3, N_MELS, frames) float32, as ai_data.py computes it."""
    import librosa
    mels = []
    for n_fft in FFTS:
        m = librosa.feature.melspectrogram(y=y, sr=SR, n_fft=n_fft, hop_length=HOP, n_mels=N_MELS,
                                           fmin=FMIN, fmax=SR / 2)
        mels.append(np.log(m + 1e-6))
    n = min(x.shape[1] for x in mels)
    return np.stack([x[:, :n] for x in mels]).astype(np.float32)


def meter_for(spec) -> float:
    """The difficulty the model is asked for: the chart's target, else the
    usual meter for its difficulty name."""
    m = spec.target_meter if spec.target_meter > 0 else DEFAULT_METER.get(spec.name, 6.0)
    return float(np.clip(m, 1, 12))


def ai_env(y: np.ndarray, a, meter: float) -> np.ndarray:
    """Step probability per analysis frame (len(a.step_env)), normalized 0..1
    like BeatSmith's other envelopes. y is the song at SR, mono. The mel is
    kept for the last song, so each difficulty only runs the model."""
    global _mel_cache
    from beatsmith.stepgen import _norm
    if _mel_cache is None or _mel_cache[0] is not y:
        _mel_cache = (y, log_mel(y))
    mel = _mel_cache[1]
    t = np.arange(mel.shape[2]) * HOP / SR
    beat = (t - a.t0) / a.spb
    prob = session().run(None, {"mel": mel[None], "beat": beat_features(beat)[None],
                                "meter": np.array([[meter]], np.float32)})[0][0]
    env = _norm(prob.astype(np.float64))
    n = len(a.step_env)
    return np.pad(env[:n], (0, max(0, n - len(env))))
