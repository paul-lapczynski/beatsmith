#!/usr/bin/env python3
"""stepgen: turn a song into a StepMania .sm chart with Easy, Medium and Hard
dance-single (4 panel) difficulties.

Pipeline
  1. analyze   load audio, split harmonic/percussive, find a constant BPM,
               beat phase and downbeat (bar start), onset strength, loudness
  2. place     score every grid slot (4ths / 8ths / 16ths) by how strongly
               the music hits there, keep the best ones per difficulty
  3. arrange   assign arrows with a two-foot model (alternate feet, no
               crossovers), add jumps on big accents and holds on sustains
  4. write     .sm file + copy of the audio in a StepMania song folder

Usage
  python3 stepgen.py song.mp3 [--out songs/] [--title T] [--artist A]
                     [--bpm 128] [--seed 1] [--clicks]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))   # chartstats.py
from layout import song_dirs
import librosa
import soundfile as sf

SR = 22050
HOP = 256                      # ~11.6 ms frames, fine enough for 16ths
ROWS_PER_BEAT = 4              # 16th-note grid
BEATS_PER_MEASURE = 4
LEFT, DOWN, UP, RIGHT = 0, 1, 2, 3
# spectral-flux onset peaks land ~16 ms after the actual attack (measured on
# synthetic drums at several tempos); the beat phase is shifted back by this
ONSET_LATENCY = 0.016


# --------------------------------------------------------------------------
# 1. analysis
# --------------------------------------------------------------------------

@dataclass
class Analysis:
    duration: float
    bpm: float
    t0: float                  # time (s) of beat 0, a downbeat; may be < 0
    onset_env: np.ndarray      # percussive onset strength, normalized 0..1
    low_env: np.ndarray        # low-band (kick) onset strength, 0..1
    rms: np.ndarray            # overall loudness, normalized 0..1
    harm_rms: np.ndarray       # harmonic (sustained) loudness, 0..1
    harm_env: np.ndarray       # harmonic onset strength (new melody/chord notes), 0..1
    centroid: np.ndarray       # spectral centroid, for melodic up/down bias
    mel: np.ndarray            # drum mel spectrum (dB), to spot repeated hits
    music_start: float
    music_end: float
    beat_confidence: float
    bar_feats: np.ndarray      # per-measure harmony/timbre fingerprint, unit vectors
    intensity: np.ndarray      # per-measure section intensity 0..1 (drums, kick, loudness)
    section_start: np.ndarray  # per-measure 0..1: how strongly a new section begins here
    step_env: np.ndarray | None = None  # what a dancer steps to: kick, snare, lead; hi-hats barely
    beat_env: np.ndarray | None = None  # the drums alone (kick, snare)
    melody_env: np.ndarray | None = None  # vocal/lead note starts (from stems when separated)
    melody_cent: np.ndarray | None = None  # brightness of the melody, for up/down arrows
    vocals: np.ndarray | None = None    # per-measure 0..1: how much singing (stems only)
    follow: np.ndarray | None = None    # per-measure 0..1: beat (0) or melody (1), set per chart
    stems: bool = False
    ai: float = 0.0                     # how much of step_env is the AI model's, set per chart

    @property
    def hits(self) -> np.ndarray:
        return self.step_env if self.step_env is not None else self.onset_env

    def bar_intensity(self, m: int) -> float:
        return float(self.intensity[int(np.clip(m, 0, len(self.intensity) - 1))])

    @property
    def spb(self) -> float:
        return 60.0 / self.bpm

    def frame(self, t: float) -> int:
        return int(np.clip(round(t * SR / HOP), 0, len(self.onset_env) - 1))

    def peak(self, env: np.ndarray, t: float, win: float = 0.035) -> float:
        a, b = self.frame(t - win), self.frame(t + win)
        return float(env[a:b + 1].max())

    def mean(self, env: np.ndarray, t1: float, t2: float) -> float:
        a, b = self.frame(t1), self.frame(t2)
        return float(env[a:max(b, a + 1)].mean())


def load_audio(path: Path) -> np.ndarray:
    try:
        y, _ = librosa.load(path, sr=SR, mono=True)
        return y
    except Exception:
        # formats libsndfile can't read (m4a, wma, ...) go through ffmpeg
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "a.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(path),
                            "-ac", "1", "-ar", str(SR), str(wav)], check=True)
            y, _ = librosa.load(wav, sr=SR, mono=True)
            return y


def _norm(x: np.ndarray, q: float = 99.0) -> np.ndarray:
    ref = np.percentile(x, q)
    return np.clip(x / ref, 0, 1.5) if ref > 0 else x


def _comb_score(env: np.ndarray, bpm: float, phase: float, t_lo: float, t_hi: float) -> float:
    """Mean onset strength sampled on a constant beat grid."""
    spb = 60.0 / bpm
    ts = np.arange(phase, t_hi, spb)
    ts = ts[ts >= t_lo]
    if len(ts) == 0:
        return 0.0
    idx = np.clip(np.round(ts * SR / HOP).astype(int), 0, len(env) - 1)
    # take max over +-1 frame to tolerate tiny jitter
    v = np.maximum(env[idx], np.maximum(env[np.clip(idx - 1, 0, None)],
                                        env[np.clip(idx + 1, None, len(env) - 1)]))
    return float(v.mean())


def _eighths_fit(env: np.ndarray, bpm: float, t_lo: float, t_hi: float) -> float:
    """How well the onsets sit on this tempo's 8th-note grid (best phase)."""
    spb = 60.0 / bpm
    return max(_comb_score(env, 2 * bpm, p, t_lo, t_hi) for p in np.linspace(0, spb / 2, 24, endpoint=False))


def triplet_check(env, beat_env, bpm, ph, conf, t_lo, t_hi):
    """Beat trackers sometimes lock onto a tempo 3:2 away from the real one
    (a 150 BPM track read as 100), which puts every note on a triplet the
    chart can't show, so the steps feel completely off the beat. A sparse
    or loose intro can also pull them to 5:4 (a 137 BPM track read as 110).
    Try those tempos and switch when the music sits clearly better on
    their 8th-note grid."""
    best, best_fit = (bpm, ph, conf), _eighths_fit(env, bpm, t_lo, t_hi)
    for c in (bpm * 1.5, bpm / 1.5, bpm * 1.25, bpm / 1.25):
        while c < 90:
            c *= 2
        while c >= 200:
            c /= 2
        b, p, cf = refine_bpm(beat_env, np.array([]), c, t_lo, t_hi)
        fit = _eighths_fit(env, b, t_lo, t_hi)
        if fit > 1.25 * best_fit:
            best, best_fit = (b, p, cf), fit
    return best


def refine_bpm(env: np.ndarray, beat_times: np.ndarray, bpm0: float,
               t_lo: float, t_hi: float) -> tuple[float, float, float]:
    """Find the constant BPM + phase that best fits the onsets.

    Starts from a least-squares line through the tracked beats, then does a
    fine grid search of BPM and phase maximizing the comb score. Returns
    (bpm, phase_seconds, confidence)."""
    if len(beat_times) >= 8:
        n = np.arange(len(beat_times))
        slope, icpt = np.polyfit(n, beat_times, 1)
        resid = beat_times - (slope * n + icpt)
        keep = np.abs(resid) < 0.05
        if keep.sum() >= 8:
            slope, icpt = np.polyfit(n[keep], beat_times[keep], 1)
        bpm_ls = 60.0 / slope
    else:
        bpm_ls = bpm0
    best = (-1.0, bpm_ls, 0.0)
    for bpm in np.linspace(bpm_ls * 0.985, bpm_ls * 1.015, 121):
        spb = 60.0 / bpm
        for ph in np.linspace(0, spb, 48, endpoint=False):
            s = _comb_score(env, bpm, ph, t_lo, t_hi)
            if s > best[0]:
                best = (s, bpm, ph)
    score, bpm, ph = best
    # second, finer pass around the winner
    for b in np.linspace(bpm - 0.05, bpm + 0.05, 21):
        spb = 60.0 / b
        for p in np.linspace(ph - 0.012, ph + 0.012, 13):
            s = _comb_score(env, b, p % spb, t_lo, t_hi)
            if s > score:
                score, bpm, ph = s, b, p % spb
    # snap to a "nice" BPM (integer or .5) if it fits almost as well
    for nice in (round(bpm), round(bpm * 2) / 2):
        if abs(nice - bpm) < 0.2:
            spb = 60.0 / nice
            best_p, best_s = ph, -1
            for p in np.linspace(ph - 0.02, ph + 0.02, 41):
                s = _comb_score(env, nice, p % spb, t_lo, t_hi)
                if s > best_s:
                    best_s, best_p = s, p % spb
            if best_s >= 0.98 * score:
                bpm, ph, score = float(nice), best_p, best_s
                break
    # sub-frame phase: median offset of the actual onset peaks from the grid
    spb = 60.0 / bpm
    res = []
    for t in np.arange(ph, t_hi, spb):
        if t < t_lo:
            continue
        i = int(round(t * SR / HOP))
        if i < 4 or i + 4 >= len(env):
            continue
        k = i - 3 + int(np.argmax(env[i - 3:i + 4]))
        if env[k] < 0.3:
            continue
        y0, y1, y2 = env[k - 1], env[k], env[k + 1]
        den = y0 - 2 * y1 + y2
        frac = 0.5 * (y0 - y2) / den if den < 0 else 0.0
        res.append((k + frac) * HOP / SR - t)
    if len(res) >= 8:
        ph = (ph + float(np.median(res))) % spb
    # confidence: how much stronger onsets are on the grid than on average
    conf = score / (float(env.mean()) + 1e-9)
    return float(bpm), float(ph), float(conf)


STEP_MIX = {"kick": 0.4, "snare": 0.3, "lead": 0.3, "hats": 0.05}


def analyze(path: Path, bpm_override: float | None = None, stems: Path | None = None) -> Analysis:
    y = load_audio(path)
    duration = len(y) / SR
    y_h, y_p = librosa.effects.hpss(y)

    onset = librosa.onset.onset_strength(y=y_p, sr=SR, hop_length=HOP, aggregate=np.median)
    # kick drum band: onset strength of the 30-150 Hz mel bands
    S = librosa.feature.melspectrogram(y=y_p, sr=SR, hop_length=HOP, n_mels=64, fmax=8000)
    mel_f = librosa.mel_frequencies(n_mels=64, fmax=8000)
    low = librosa.onset.onset_strength(S=librosa.power_to_db(S[mel_f < 150]), sr=SR, hop_length=HOP)
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    harm = librosa.feature.rms(y=y_h, hop_length=HOP)[0]
    cent = librosa.feature.spectral_centroid(y=y_h, sr=SR, hop_length=HOP)[0]
    hon = librosa.onset.onset_strength(y=y_h, sr=SR, hop_length=HOP,
                                       feature=librosa.feature.chroma_stft)
    # band onsets: snare/body of the drums, hi-hats, and the lead melody
    snare = librosa.onset.onset_strength(S=librosa.power_to_db(S[(mel_f >= 150) & (mel_f < 2500)]),
                                         sr=SR, hop_length=HOP)
    hats = librosa.onset.onset_strength(S=librosa.power_to_db(S[mel_f >= 5000]), sr=SR, hop_length=HOP)
    Sh = librosa.feature.melspectrogram(y=y_h, sr=SR, hop_length=HOP, n_mels=64, fmax=8000)
    lead = librosa.onset.onset_strength(S=librosa.power_to_db(Sh[(mel_f >= 600) & (mel_f < 5000)]),
                                        sr=SR, hop_length=HOP)
    n = min(len(onset), len(low), len(rms), len(harm), len(cent), len(hon), S.shape[1],
            len(snare), len(hats), len(lead))
    onset, low, rms, harm, cent, hon, snare, hats, lead = (
        x[:n] for x in (onset, low, rms, harm, cent, hon, snare, hats, lead))
    # dancers step on the kick, snare and melody; steady off-beat hi-hats
    # are loud onsets but nobody dances to them
    step = _norm(STEP_MIX["kick"] * _norm(low) + STEP_MIX["snare"] * _norm(snare)
                 + STEP_MIX["lead"] * _norm(lead) + STEP_MIX["hats"] * _norm(hats))
    drums_only = _norm(0.55 * _norm(low) + 0.4 * _norm(snare) + 0.05 * _norm(hats))
    melody, mel_cent, voc_frames = _norm(lead), cent, None
    if stems is not None:
        melody, mel_cent, voc_frames = _stem_melody(stems, n)

    # where the music actually plays (trim leading/trailing silence)
    loud = rms > 0.05 * np.percentile(rms, 95)
    idx = np.flatnonzero(loud)
    music_start = idx[0] * HOP / SR if len(idx) else 0.0
    music_end = idx[-1] * HOP / SR if len(idx) else duration

    env = _norm(onset)
    # beat grid fits drums overall plus extra weight on the kick, so off-beat
    # hi-hats and bass (trance, house) can't pull the grid half a beat off
    beat_env = _norm(0.5 * env + _norm(low))
    if bpm_override:
        _, _, conf = refine_bpm(beat_env, np.array([]), bpm_override, music_start, music_end)
        bpm = bpm_override
        spb = 60.0 / bpm
        ph = max(np.linspace(0, spb, 240, endpoint=False),
                 key=lambda p: _comb_score(beat_env, bpm, p, music_start, music_end))
    else:
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=SR, hop_length=HOP,
                                               units="time")
        bpm0 = float(np.atleast_1d(tempo)[0])
        bpm, ph, conf = refine_bpm(beat_env, np.asarray(beats), bpm0, music_start, music_end)
        # dance charts read best between ~90 and ~200 BPM
        while bpm < 90:
            bpm *= 2
        while bpm >= 200:
            bpm /= 2
        bpm, ph, conf = triplet_check(env, beat_env, bpm, ph, conf, music_start, music_end)
        if abs(bpm - round(bpm)) < 1e-6:
            bpm = float(round(bpm))

    # downbeat: of the 4 possible bar phases, pick the one whose beats carry
    # the most kick energy and chord changes (bars usually start with both)
    spb = 60.0 / bpm
    lown = _norm(low)
    honn = _norm(hon)
    best_k, best_s = 0, -1.0
    for k in range(BEATS_PER_MEASURE):
        p = ph + k * spb
        s = _comb_score(lown, bpm / BEATS_PER_MEASURE, p, music_start, music_end) \
            + 0.5 * _comb_score(env, bpm / BEATS_PER_MEASURE, p, music_start, music_end) \
            + 0.7 * _comb_score(honn, bpm / BEATS_PER_MEASURE, p, music_start, music_end)
        if s > best_s:
            best_k, best_s = k, s
    t0 = ph + best_k * spb - ONSET_LATENCY
    measure = spb * BEATS_PER_MEASURE
    t0 -= math.ceil((t0 - 1e-9) / measure) * measure if t0 > 0 else 0.0   # t0 in (-measure, 0]

    # per-measure fingerprint for finding repeated sections: chroma for each
    # beat (harmony and its rhythm), average timbre (MFCC) and loudness
    chroma = librosa.feature.chroma_cqt(y=y_h, sr=SR, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=SR, hop_length=HOP, n_mfcc=13)
    fr = lambda t: int(np.clip(round(t * SR / HOP), 0, chroma.shape[1] - 1))
    feats, drums, kick, loud = [], [], [], []
    rms_n = _norm(rms)
    for m in range(int((music_end - t0) / measure) + 1):
        i0, i1 = fr(t0 + m * measure), fr(t0 + (m + 1) * measure)
        if m == 0:
            i1 = max(i1, i0 + 8)       # bar 1 can start before the song does (t0 < 0)
        if i1 - i0 < 8:
            break
        drums.append(env[i0:i1].mean())
        kick.append(lown[i0:i1].mean())
        loud.append(rms_n[i0:i1].mean())
        v = [chroma[:, i0 + (i1 - i0) * b // 4:i0 + (i1 - i0) * (b + 1) // 4].mean(1) for b in range(4)]
        v += [mfcc[1:, i0:i1].mean(1) / 50, [rms[i0:i1].mean()]]
        feats.append(np.concatenate(v))
    F = np.array(feats)
    Z = (F - F.mean(0)) / (F.std(0) + 1e-9)
    Z /= np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9

    # section intensity: drum activity and kick presence matter more than
    # loudness, so a loud-but-drumless breakdown reads as a low point even in
    # a flat-mastered song
    def unit(x):
        x = np.asarray(x, float)
        return np.clip(x / (np.percentile(x, 95) + 1e-9), 0, 1)
    inten = 0.4 * unit(drums) + 0.35 * unit(kick) + 0.25 * unit(loud)
    if len(inten) >= 3:                               # ignore one-bar blips
        inten = np.array([np.median(inten[max(0, m - 1):m + 2]) for m in range(len(inten))])
    inten = unit(inten)
    # section starts: the sound changes from the bars before, or intensity jumps up
    start = np.zeros(len(inten))
    for m in range(1, len(inten)):
        prev = Z[max(0, m - 2):m].mean(0)
        nov = 1 - float(Z[m] @ prev / (np.linalg.norm(prev) + 1e-9))
        rise = max(0.0, inten[m] - inten[max(0, m - 2):m].mean())
        start[m] = nov + 2 * rise
    start = np.clip(start / (np.percentile(start, 95) + 1e-9), 0, 1)
    # keep only local peaks, on 4-bar phrase boundaries where possible
    peaks = np.zeros(len(start))
    for m in range(1, len(start)):
        if start[m] >= 0.5 and start[m] == start[max(0, m - 2):m + 3].max():
            peaks[m] = start[m]

    vocals = None
    if voc_frames is not None:
        vocals = np.array([voc_frames[fr(t0 + m * measure):fr(t0 + (m + 1) * measure)].mean()
                           for m in range(len(inten))])
    return Analysis(duration=duration, bpm=bpm, t0=t0, onset_env=env, low_env=lown,
                    rms=_norm(rms), harm_rms=_norm(harm), harm_env=honn, centroid=cent,
                    mel=librosa.power_to_db(S[:, :n]) + 80, music_start=music_start,
                    music_end=music_end, beat_confidence=conf, bar_feats=Z,
                    intensity=inten, section_start=peaks, step_env=step, beat_env=drums_only,
                    melody_env=melody, melody_cent=mel_cent, vocals=vocals, stems=stems is not None)


def _stem_melody(stems: Path, n: int):
    """Melody from separated stems: vocal note starts while someone is
    singing, plus the lead line in the 'other' stem (synths, guitar) at a bit
    less weight. Returns (melody onsets, melody brightness, singing 0..1)."""
    def load(name):
        y = load_audio(stems / f"{name}.ogg")
        return y
    voc, oth = load("vocals"), load("other")
    fit = lambda x: np.pad(x[:n], (0, max(0, n - len(x))))
    v_on = fit(librosa.onset.onset_strength(y=voc, sr=SR, hop_length=HOP))
    v_rms = fit(librosa.feature.rms(y=voc, hop_length=HOP)[0])
    # singing = vocal stem clearly above its own bleed; smoothed over ~0.3 s
    sing = np.clip(v_rms / (np.percentile(v_rms, 90) + 1e-9), 0, 1)
    sing = np.convolve(sing, np.ones(25) / 25, mode="same")
    sing = np.clip((sing - 0.15) / 0.35, 0, 1)
    So = librosa.feature.melspectrogram(y=oth, sr=SR, hop_length=HOP, n_mels=64, fmax=8000)
    mel_f = librosa.mel_frequencies(n_mels=64, fmax=8000)
    o_on = fit(librosa.onset.onset_strength(S=librosa.power_to_db(So[(mel_f >= 300) & (mel_f < 5000)]),
                                            sr=SR, hop_length=HOP))
    melody = _norm(np.maximum(_norm(v_on) * sing, 0.6 * _norm(o_on) * (1 - 0.5 * sing)))
    c_v = fit(librosa.feature.spectral_centroid(y=voc, sr=SR, hop_length=HOP)[0])
    c_o = fit(librosa.feature.spectral_centroid(y=oth, sr=SR, hop_length=HOP)[0])
    cent = np.where(sing > 0.3, c_v, c_o)
    return melody, cent, sing


# --------------------------------------------------------------------------
# 2. note placement
# --------------------------------------------------------------------------

@dataclass
class DiffSpec:
    """One difficulty's settings; see patterns.toml for what each one does."""
    name: str
    density: float = 1.0
    max_nps: float = 4.0
    grid: int = 2
    min_gap: float = 0.5
    jump: float = 0.3
    jacks: float = 0.4
    jack_max: int = 3
    flow: float = 0.7
    side_to_side: float = 0.6
    flow_spice: float = 0.2
    energy_follow: float = 0.6
    half_beats: float = 0.3
    quarter_beats: float = 0.0
    sixteenths: float = 1.0     # 16th-note allowance: 0 none, 1 Konami-typical for the level, 2 double
    run_breaks: float = 0.0     # short pauses inside long runs (0 off, 0.5 Konami-like, 1 often)
    recovery: float = 0.0       # rest after a long or hard run (0 off, 1 up to about 3 beats)
    stomps: float = 0.0         # chance a pause on big beats becomes quarter-note jumps instead
    rhythm_lock: float = 0.0    # a bar takes the rhythm of the bar before when the music carries on alike
    groove_tries: int = 1       # make this many versions and keep the one the groove meter likes best
    hold_rate: float = 0.05
    hold_min: float = 2.0
    hold_max: float = 4.0
    hold_free_foot: float = 1.0
    hold_complexity: float = 0.5
    rhythm_repeat: float = 0.85
    arrow_repeat: float = 0.5
    intensity_variation: float = 0.5
    jump_clusters: float = 0.0
    jump_holds: float = 0.0
    flow_runs: float = 0.3
    phrase_shape: float = 0.0
    rest_bars: float = 0.0
    beat_backbone: float = 0.0
    crescendo: float = 0.0
    max_run16: int = 6
    meter_min: int = 1
    meter_max: int = 10
    target_meter: float = 0.0
    melody_follow: float = 0.0
    ai_assist: float = 0.0      # 0 stepgen's own onsets pick the step moments, 1 the trained model does


DEFAULT_PATTERNS = Path(__file__).with_name("patterns.toml")
PROFILE_NAME = "patterns"      # shown in the .sm credit and the stats file
RUN_SETS: list[str] = []       # --set overrides of this run, saved for llm_review.py
RUN_EASY: dict[str, float] = {}  # --easy sliders of this run


PROFILES_DIR = Path(__file__).with_name("profiles")
SM_DIFFICULTIES = ("Beginner", "Easy", "Medium", "Hard", "Challenge", "Edit")


def _read_settings(path: Path, seen: tuple = ()) -> dict[str, dict]:
    """Read a settings file, following `base = "other.toml"` so a profile only
    lists what it changes. `[all]` applies to every difficulty, and a table can
    start from another one with `extends = "Hard"`."""
    if path in seen:
        raise SystemExit(f"{path.name}: base files loop back on themselves")
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    data: dict[str, dict] = {}
    base = raw.pop("base", None)
    if base:
        bp = (path.parent / base) if (path.parent / base).exists() else Path(__file__).with_name(base)
        data = {k: dict(v) for k, v in _read_settings(bp, seen + (path,)).items()}
    common = raw.pop("all", {})
    for name in data:
        data[name].update(common)
    for name, vals in raw.items():
        if not isinstance(vals, dict):
            raise SystemExit(f"{path.name}: '{name}' should be a [table]")
        vals = dict(vals)
        ext = vals.pop("extends", None)
        merged = dict(data.get(ext, {}) if ext else data.get(name, {}))
        if ext and ext not in data:
            raise SystemExit(f"{path.name}: [{name}] extends unknown [{ext}]")
        merged.update(common)
        merged.update(vals)
        data[name] = merged
    return data


def resolve_profile(name_or_path: str | Path) -> Path:
    if str(name_or_path) in ("patterns", "default", "base"):
        return DEFAULT_PATTERNS
    p = Path(name_or_path)
    for cand in (p, PROFILES_DIR / p, PROFILES_DIR / f"{p}.toml"):
        if cand.is_file():
            return cand
    have = ", ".join(sorted(f.stem for f in PROFILES_DIR.glob("*.toml"))) or "none"
    raise SystemExit(f"no profile '{name_or_path}' (profiles: {have})")


def load_patterns(path: Path = DEFAULT_PATTERNS, overrides: list[str] = (),
                  easy: dict[str, float] | None = None) -> list[DiffSpec]:
    """The profile's difficulties, with Easy-mode sliders applied first and
    then any exact overrides like "Hard.jump=0.8", so an override always
    ends up as the value used."""
    data = _read_settings(Path(path))
    exact: dict[str, dict] = {}
    for ov in overrides:                                  # "Hard.jump=0.8"
        key, val = ov.split("=", 1)
        diff, param = key.split(".", 1)
        data.setdefault(diff, {})
        exact.setdefault(diff, {})[param] = float(val)
    specs = []
    for name, vals in data.items():
        if vals.pop("skip", False):                       # profile can drop a difficulty
            continue
        if name not in SM_DIFFICULTIES:
            raise SystemExit(f"{Path(path).name}: [{name}] isn't a StepMania difficulty "
                             f"({', '.join(SM_DIFFICULTIES)})")
        spec = DiffSpec(name)
        for k, v in vals.items():
            k = {"eighths": "half_beats", "repeat": "rhythm_repeat"}.get(k, k)   # older names
            if k == "repeat_variation":                  # older name, opposite sense
                k, v = "arrow_repeat", 1 - float(v)
            if not hasattr(spec, k):
                raise SystemExit(f"{Path(path).name}: unknown setting {name}.{k}")
            setattr(spec, k, type(getattr(spec, k))(v))
        if easy:
            spec = apply_easy([spec], easy)[0]
        for k, v in exact.get(name, {}).items():
            if not hasattr(spec, k):
                raise SystemExit(f"unknown setting {name}.{k}")
            setattr(spec, k, type(getattr(spec, k))(v))
        specs.append(spec)
    return specs


# Stomps (quarter-note jumps where a pause lands on big beats) top out
# here on the sliders, so more breathing room means more real gaps.
MAX_STOMPS = 0.4

# Settings the dial test (dialtest/REPORT.md) found no measurable effect
# for. Profiles that set them still load and are used as written, but no
# slider moves them and the app shows them as retired. max_nps is also
# set by the difficulty target, which turns it as part of density.
DEPRECATED = {"jack_max", "flow", "hold_complexity", "hold_free_foot",
              "intensity_variation", "max_run16", "max_nps", "meter_min", "meter_max"}

# Easy mode: a few plain sliders, each 0..1, where 0.5 leaves the profile as
# written. Each one pushes a group of settings toward their low or high end
# together. The app shows these; --easy NAME=VALUE does the same on the
# command line. (Difficulty is separate: it's target_meter per chart.)
EASY_SLIDERS = {
    # slider: [(setting, low end, high end), ...]
    # groove is the overall one: it goes first, so the sliders below still
    # have the last word on their own settings
    "groove":     [("rhythm_repeat", 0.5, 0.97), ("beat_backbone", 0.0, 0.8),
                   ("jacks", 0.6, 0.0), ("energy_follow", 0.2, 1.0), ("phrase_shape", 0.0, 0.8),
                   ("run_breaks", 0.0, 0.9), ("recovery", 0.0, 0.9), ("stomps", 0.0, MAX_STOMPS),
                   ("rhythm_lock", 0.0, 0.9), ("groove_tries", 1, 4)],
    "energy":     [("energy_follow", 0.0, 1.0), ("crescendo", 0.0, 1.0),
                   ("phrase_shape", 0.0, 1.0), ("rest_bars", 0.0, 0.8)],
    "jumps":      [("jump", 0.0, 0.9), ("jump_clusters", 0.0, 1.0), ("jump_holds", 0.0, 1.0)],
    "breathing":  [("run_breaks", 0.0, 1.0), ("recovery", 0.0, 1.0), ("stomps", 0.0, MAX_STOMPS)],
    "speed":      [("half_beats", 0.0, 1.0), ("quarter_beats", 0.0, 0.6), ("sixteenths", 0.0, 2.0),
                   ("flow_spice", 0.0, 0.6), ("beat_backbone", 1.0, 0.0)],
    "footwork":   [("flow_runs", 0.0, 1.0), ("side_to_side", 1.0, 0.0), ("jacks", 0.6, 0.0)],
    "holds":      [("hold_rate", 0.0, 0.4)],
    "repetition": [("rhythm_repeat", 0.0, 1.0), ("arrow_repeat", 0.0, 1.0)],
}


def apply_easy(specs: list[DiffSpec], sliders: dict[str, float]) -> list[DiffSpec]:
    """Slide each setting in a group from its profile value toward the
    group's low end (slider 0) or high end (slider 1), so 0.5 changes
    nothing and the profile's own character carries through."""
    out = []
    for spec in specs:
        d = dataclasses.replace(spec)
        for name, pos in sorted(sliders.items(), key=lambda kv: kv[0] != "groove"):
            if name not in EASY_SLIDERS:
                raise SystemExit(f"unknown Easy slider '{name}' (have: {', '.join(EASY_SLIDERS)})")
            pos = float(np.clip(pos, 0.0, 1.0))
            for key, low, high in EASY_SLIDERS[name]:
                v = getattr(spec, key)
                if key == "hold_free_foot" and v == 0:
                    continue                  # 0 means no taps under holds: a style, not a level
                v = getattr(d, key)              # after the overall groove slider's move
                end, t = (high, (pos - 0.5) * 2) if pos > 0.5 else (low, (0.5 - pos) * 2)
                setattr(d, key, type(v)(round(v + (end - v) * t) if isinstance(v, int) else v + (end - v) * t))
        out.append(d)
    return out


GRID_WEIGHT = {0: 1.0, 2: 0.72, 1: 0.5, 3: 0.5}   # row-in-beat -> weight (4th, 8th, 16ths)


@dataclass
class Note:
    row: int                   # global 16th-note row index (beat 0 = row 0)
    time: float
    strength: float
    kick: float
    panels: list[int] = field(default_factory=list)
    hold_rows: int = 0         # >0 makes this a freeze arrow
    stomp: bool = False        # a jump on a big beat, set by breathe()


def phrase_of(a: Analysis, m: int) -> int:
    """Bar position (0-3) inside its 4-bar phrase, counted from the latest
    section start (or the first bar)."""
    starts = [k for k in range(min(m, len(a.section_start) - 1) + 1) if a.section_start[k] > 0]
    return (m - (starts[-1] if starts else 0)) % 4


def find_builds(a: Analysis) -> list[tuple[int, int]]:
    """Build-ups: runs of 3+ measures where the section intensity keeps
    climbing (by 0.25 or more). Returns (first bar, climax bar), the climax
    being the bar the build tops out on, where the drop or big hit lands."""
    I = a.intensity
    out, m = [], 0
    while m < len(I) - 1:
        k = m
        while k + 1 < len(I) and I[k + 1] >= I[k] - 0.03:
            k += 1
        if k - m >= 3 and I[k] - I[m] >= 0.25:
            top = I[m:k + 1].max()
            climax = next(j for j in range(m, k + 1) if I[j] >= top - 0.03)
            if climax - m >= 3:
                out.append((m, climax))
        m = k + 1
    return out


def climax_bars(a: Analysis) -> list[int]:
    """Where a jump should land: the top of each build, and the last strong
    bar before the song falls away at the end."""
    bars = [c for _, c in find_builds(a)]
    I = a.intensity
    hi = [m for m in range(len(I)) if I[m] >= 0.75]
    if hi:
        bars.append(hi[-1])
    return sorted(set(bars))


# --------------------------------------------------------------------------
# song sections and how much each one follows the melody
# --------------------------------------------------------------------------

SECTION_MIN_BARS = 8           # pop/dance sections are 8 or 16 bars; intro/outro may be shorter
FOLLOW_BY_LABEL = {"chorus": 1.0, "verse": 0.6, "bridge": 0.6, "build": 0.3,
                   "intro": 0.3, "outro": 0.3, "breakdown": 0.4}


def find_sections(a: Analysis, repeats=()) -> list[dict]:
    """Cut the song into sections and give each a letter and a guessed name.

    Boundaries come from where the sound changes or the intensity jumps
    (section_start), and where repeated stretches begin and end, snapped to
    4-bar phrases and at least 4 bars apart. Sections that sound alike share
    a letter (A, B, C...). Names are a guess: the loudest letter that comes
    back is the chorus, quiet ends are intro/outro, a quiet middle is a
    breakdown, a section that climbs is a build, the rest are verses (a
    last one-off section between two choruses is the bridge)."""
    n = len(a.intensity)
    first = int(max(0, (a.music_start - a.t0) // (4 * a.spb)))
    cand = {m: float(a.section_start[m]) for m in range(n) if a.section_start[m] > 0}
    for t, src, length in repeats:
        for m in (t, t + length, src, src + length):
            if m < n:
                cand[m] = max(cand.get(m, 0.0), 0.8)
    cuts = [first]
    for m in sorted(cand, key=lambda m: -cand[m]):
        snapped = first + round((m - first) / 4) * 4 if abs((m - first) % 4) in (1, 3) else m
        if snapped <= first or snapped >= n:
            continue
        # 8 bars apart, but the first and last section (intro/outro) can be 4
        gap = lambda c: SECTION_MIN_BARS // 2 if first in (c, snapped) and min(c, snapped) == first \
            or n - max(c, snapped) < SECTION_MIN_BARS else SECTION_MIN_BARS
        if all(abs(snapped - c) >= gap(c) for c in cuts) and n - snapped >= SECTION_MIN_BARS // 2:
            cuts.append(snapped)
    cuts = sorted(cuts) + [n]
    secs = []
    for i in range(len(cuts) - 1):
        m0, m1 = cuts[i], cuts[i + 1]
        if m1 - m0 < 1:
            continue
        z = a.bar_feats[m0:m1].mean(0)
        secs.append({"start": m0, "end": m1, "z": z / (np.linalg.norm(z) + 1e-9),
                     "intensity": float(a.intensity[m0:m1].mean()),
                     "vocals": float(a.vocals[m0:m1].mean()) if a.vocals is not None else None})
    # letters: sections that sound alike, compared bar by bar from their starts
    Z = a.bar_feats

    def alike(x, y) -> float:
        k = min(x["end"] - x["start"], y["end"] - y["start"])
        return float(np.mean([Z[x["start"] + j] @ Z[y["start"] + j] for j in range(k)]))
    firsts: list[dict] = []
    for sec in secs:
        sims = [alike(sec, f) for f in firsts]
        if sims and max(sims) >= REPEAT_MATCH - 0.15:
            sec["letter"] = firsts[int(np.argmax(sims))]["letter"]
        else:
            sec["letter"] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[min(len(firsts), 25)]
            firsts.append(sec)
    # back-to-back sections with the same letter are one section
    merged = []
    for sec in secs:
        if merged and merged[-1]["letter"] == sec["letter"]:
            prev = merged[-1]
            w0, w1 = prev["end"] - prev["start"], sec["end"] - sec["start"]
            prev["intensity"] = (prev["intensity"] * w0 + sec["intensity"] * w1) / (w0 + w1)
            if prev["vocals"] is not None:
                prev["vocals"] = (prev["vocals"] * w0 + sec["vocals"] * w1) / (w0 + w1)
            prev["end"] = sec["end"]
        else:
            merged.append(sec)
    secs = merged
    # names
    count = {L: sum(x["letter"] == L for x in secs) for L in {x["letter"] for x in secs}}
    loud = {L: np.mean([x["intensity"] for x in secs if x["letter"] == L]) for L in count}
    back = [L for L in count if count[L] >= 2]
    chorus = max(back, key=lambda L: loud[L]) if back else max(loud, key=loud.get)
    builds = {m for b0, b1 in find_builds(a) for m in range(b0, b1 + 1)}
    # the bridge: the last one-off section with a chorus on both sides
    ch = [i for i, x in enumerate(secs) if x["letter"] == chorus]
    one_off = [i for i, x in enumerate(secs) if count[x["letter"]] == 1 and ch and ch[0] < i < ch[-1]]
    bridge = one_off[-1] if one_off else -1
    for i, sec in enumerate(secs):
        span = range(sec["start"], sec["end"])
        quiet = sec["intensity"] < 0.45
        if sec["letter"] == chorus and not quiet:
            label = "chorus"
        elif i == 0 and quiet:
            label = "intro"
        elif i == len(secs) - 1 and quiet:
            label = "outro"
        elif quiet:
            label = "breakdown"
        elif sum(m in builds for m in span) >= len(span) / 2:
            label = "build"
        elif i == bridge:
            label = "bridge"
        else:
            label = "verse"
        sec["label"] = label
        del sec["z"]
    return secs


def follow_for(a: Analysis, sections: list[dict], spec: DiffSpec,
               overrides: dict[str, float] | None = None) -> np.ndarray:
    """Per measure, how much the steps follow the melody (1) rather than the
    beat (0). Automatic: melody_follow scaled by the section's name (choruses
    follow most) and, with stems, by how much singing there is. Overrides
    pick sections by number (1, 2...), letter (A, B...), name (chorus) or
    'all', and win over the automatic value."""
    f = np.zeros(len(a.intensity))
    overrides = {(k.upper() if len(k) == 1 else k.lower()): v for k, v in (overrides or {}).items()}
    for i, sec in enumerate(sections):
        v = spec.melody_follow * FOLLOW_BY_LABEL.get(sec["label"], 0.5)
        if sec["vocals"] is not None:
            v *= 0.4 + 0.6 * min(1.0, sec["vocals"] / 0.4)
        for key in ("all", sec["label"], sec["letter"], str(i + 1)):
            if key in overrides:
                v = overrides[key]
        sec["follow"] = round(float(np.clip(v, 0, 1)), 2)
        f[sec["start"]:sec["end"]] = sec["follow"]
    return f


def with_follow(a: Analysis, follow: np.ndarray) -> Analysis:
    """The analysis as one chart sees it: in melody-following measures the
    step-worthy hits come from the melody (with a little drum to stay on
    the grid) instead of the usual drum-led mix."""
    if a.melody_env is None or not follow.any():
        return a
    frames = np.arange(len(a.step_env))
    m = np.clip(((frames * HOP / SR - a.t0) // (4 * a.spb)).astype(int), 0, len(follow) - 1)
    f = follow[m]
    hits = (1 - f) * a.step_env + f * (0.85 * a.melody_env + 0.15 * a.beat_env)
    return dataclasses.replace(a, step_env=hits, follow=follow)


def with_ai(a: Analysis, env: np.ndarray | None, k: float) -> Analysis:
    """The analysis with the AI model's step envelope blended in: k = 0
    leaves it as is, 1 lets the model alone decide where the steps go."""
    if k <= 0 or env is None:
        return a
    return dataclasses.replace(a, step_env=(1 - k) * a.hits + k * env, ai=k)


def phrase_weights(a: Analysis, spec: DiffSpec, bars: list[int]) -> np.ndarray:
    """Density shaping like hand-made charts.

    phrase_shape  inside each 4-bar phrase: bar 1 full, bars 2-3 a little
                  lighter, bar 4 busier as a fill into the next phrase
    rest_bars     in long stretches of full intensity, a lighter 2-4 bar
                  breather at a phrase boundary about every 24 bars"""
    shape = np.array([1.0, 0.85, 0.9, 1.25])
    w = np.ones(len(bars))
    if spec.phrase_shape > 0:
        for i, m in enumerate(bars):
            w[i] *= 1 + spec.phrase_shape * (shape[phrase_of(a, m)] - 1)
    if spec.rest_bars > 0:
        run = 0
        i = 0
        while i < len(bars):
            m = bars[i]
            run = run + 1 if a.bar_intensity(m) > 0.75 else 0
            if run >= 24 and phrase_of(a, m) == 0 and a.section_start[min(m, len(a.section_start) - 1)] == 0:
                n = 2 + int(round(2 * spec.rest_bars))
                w[i:i + n] *= 1 - 0.75 * spec.rest_bars
                i += n
                run = 0
                continue
            i += 1
    if spec.crescendo > 0:
        # steps climb through a build: light at its start, busiest in the
        # bars right before the climax, then full on the climax itself
        pos = {m: i for i, m in enumerate(bars)}
        for b0, top in find_builds(a):
            n = top - b0
            for k in range(n):
                if b0 + k in pos:
                    ramp = k / max(n - 1, 1)                 # 0 -> 1 across the build
                    w[pos[b0 + k]] *= (1 - 0.6 * spec.crescendo) + 1.0 * spec.crescendo * ramp
            if top in pos:
                w[pos[top]] *= 1 + 0.3 * spec.crescendo
    return w


EIGHTHS_BASE = 0.15          # with a target: off-beat 8ths at most this share of steps,
EIGHTHS_PER_HALF_BEAT = 0.5  # plus this much per unit of half_beats (Speed)


def cap_eighths(notes: list[Note], spec: DiffSpec) -> list[Note]:
    """With a target, keep off-beat 8ths to the share Speed asks for: the
    weakest extra ones go (holds and jumps stay), so the dial reaches the
    number with what Speed allows before it raises Speed itself."""
    if spec.target_meter <= 0:
        return notes
    share = EIGHTHS_BASE + EIGHTHS_PER_HALF_BEAT * spec.half_beats
    off = [n for n in notes if n.row % ROWS_PER_BEAT == 2 and not n.hold_rows and len(n.panels) < 2]
    n8 = sum(n.row % ROWS_PER_BEAT == 2 for n in notes)
    keep = int(share * (len(notes) - n8) / max(1e-6, 1 - share))     # share of what's left after
    extra = n8 - keep
    if extra <= 0 or share >= 1:
        return notes
    drop = set(map(id, sorted(off, key=lambda n: n.strength + n.kick)[:extra]))
    return [n for n in notes if id(n) not in drop]


def eighths_cap(spec: DiffSpec, steps: int) -> int:
    """Most off-beat 8ths a chart of `steps` steps may have: with a target
    the share Speed asks for, so the target's extra steps don't all become
    8ths; without one, no limit."""
    if spec.target_meter <= 0:
        return steps
    return int((EIGHTHS_BASE + EIGHTHS_PER_HALF_BEAT * spec.half_beats) * steps)


def place_notes(a: Analysis, spec: DiffSpec, rng: random.Random) -> list[Note]:
    spb = a.spb
    row_dt = spb / ROWS_PER_BEAT
    step = ROWS_PER_BEAT // spec.grid
    first = math.ceil((a.music_start - a.t0) / row_dt / step) * step
    last = int((a.music_end - 0.25 - a.t0) / row_dt)

    def energy(r: int) -> float:
        return a.bar_intensity(r // 16) ** 0.6

    # loudness per measure scales density: quiet intros/breakdowns get fewer notes
    cands = []
    for r in range(first, last + 1, step):
        t = a.t0 + r * row_dt
        s = a.peak(a.hits, t)
        if s < 0.08:
            continue
        gw = GRID_WEIGHT[r % ROWS_PER_BEAT]
        if r % ROWS_PER_BEAT == 2:
            gw *= 1 + 0.6 * spec.half_beats                  # sneak in off-beat 8ths
        # following the melody: the tune's rhythm decides, not the beat grid
        fol = float(a.follow[min(r // 16, len(a.follow) - 1)]) if a.follow is not None else 0.0
        fol = max(fol, a.ai)                              # the AI model knows the grid already
        gw **= 1 - 0.75 * fol
        score = s * gw * (0.35 + 0.65 * energy(r))
        if r % ROWS_PER_BEAT == 0 and s >= 0.15:
            score *= 1 + 4 * spec.beat_backbone * (1 - fol)   # steady beat notes first
        if r % 16 == 0:
            score *= 1.1                                  # downbeats
        cands.append((score, r, t, s))

    span = max(a.music_end - a.music_start, 1.0)
    target = int(min(spec.density * span / spb, spec.max_nps * span))
    min_gap_rows = max(1, int(round(spec.min_gap * ROWS_PER_BEAT)))

    # share the note budget out per measure by loudness (energy_follow 0 =
    # even density, 1 = loud parts get far more notes than quiet ones)
    by_measure: dict[int, list] = {}
    for c in cands:
        by_measure.setdefault(c[1] // 16, []).append(c)
    ms = sorted(by_measure)
    # higher energy_follow also sharpens the contrast, so a build-up ramps
    # the steps up with it instead of only nudging them
    e = np.array([energy(m * 16) ** (1.5 + 5 * spec.energy_follow) for m in ms]) + 1e-6
    w = (1 - spec.energy_follow) + spec.energy_follow * e / e.mean()
    w *= phrase_weights(a, spec, ms)
    budget = w / w.sum() * target
    taken: dict[int, tuple] = {}
    carry = 0.0

    for m, bud in zip(ms, budget):
        want = bud + carry
        got = 0
        for c in sorted(by_measure[m], key=lambda c: -c[0]):
            if got >= round(want):
                break
            r = c[1]
            if any((r + d) in taken for d in range(-min_gap_rows + 1, min_gap_rows)):
                continue
            taken[r] = c
            got += 1
        carry = want - got
        carry = min(carry, 4.0)                       # don't flood the next bar

    # half_beats: fill off-beat gaps between notes to stretch out 8th-note runs
    # in the busier parts, where there's at least a light hit to step on
    if spec.half_beats > 0 and spec.grid >= 2:
        fills = []
        for r in taken:
            q = r + 2
            if q % ROWS_PER_BEAT == 2 and q not in taken and (q + 2) in taken \
                    and (q - 1) not in taken and (q + 1) not in taken:
                t = a.t0 + q * row_dt
                s = a.peak(a.hits, t, 0.03)
                if s >= 0.03:
                    fills.append((s * energy(q), q, t, s))
        for f in sorted(fills, key=lambda f: -f[0])[:int(len(taken) * 0.15 * spec.half_beats)]:
            taken[f[1]] = f

    # quarter_beats: sneak in notes a quarter beat off, where the melody or
    # vocal (or a drum) starts a note there, like a syncopated 1, 1.25, 1.75, 2
    if spec.quarter_beats > 0 and spec.grid >= 2:
        qcands = []
        for q in range(first | 1, last + 1, 2):
            if q in taken or (q - 1) in taken and (q + 1) in taken:
                continue
            t = a.t0 + q * row_dt
            s = max(a.peak(a.harm_env, t, 0.025), a.peak(a.hits, t, 0.02))
            if s >= 0.35:
                qcands.append((s * energy(q), q, t, s))
        budget_q = int(len(taken) * 0.05 * spec.quarter_beats)
        added = 0
        for c in sorted(qcands, key=lambda c: -c[0]):
            if added >= budget_q:
                break
            q = c[1]
            beat0 = q - q % ROWS_PER_BEAT
            if sum(1 for r in range(beat0, beat0 + 4) if r % 2 and r in taken) >= 2:
                continue
            run, k = 1, q - 1
            while k in taken:
                run, k = run + 1, k - 1
            k = q + 1
            while k in taken:
                run, k = run + 1, k + 1
            if run > 3:                                   # 3 quick notes in a row at most
                continue
            taken[q] = c
            added += 1

    # flow spice: quick 2-3 note bursts one grid step finer, where the music has them
    fine = step // 2 if step > 1 else 0
    if spec.flow_spice > 0 and fine:
        bursts = []
        for r in sorted(taken):
            for d in (fine, -fine):                       # note right after / before r
                q = r + d
                if q in taken:
                    continue
                if any((q + k) in taken for k in range(-fine + 1, fine) if k):
                    continue
                t = a.t0 + q * row_dt
                s = a.peak(a.hits, t, 0.02)
                if s > 0.45:
                    bursts.append((s * (0.35 + 0.65 * energy(q)), q, t, s))
        budget = int(len(taken) * 0.12 * spec.flow_spice)
        added = 0
        for b in sorted(bursts, key=lambda b: -b[0]):
            if added >= budget:
                break
            q = b[1]
            # keep bursts short: at most 3 notes spaced `fine` apart
            run = 1
            k = q - fine
            while k in taken:
                run, k = run + 1, k - fine
            k = q + fine
            while k in taken:
                run, k = run + 1, k + fine
            if run > 3 or any((q + k2) in taken for k2 in range(-fine + 1, fine)):
                continue
            taken[q] = b
            added += 1

    # crescendo: a step lands on the downbeat each build tops out on (it
    # becomes a jump later), and on the final big hit before the song ends
    if spec.crescendo > 0:
        for m in climax_bars(a):
            r = m * 16
            if first <= r <= last and r not in taken:
                for d in range(-min_gap_rows + 1, min_gap_rows):
                    taken.pop(r + d, None)
                t = a.t0 + r * row_dt
                taken[r] = (1.0, r, t, max(a.peak(a.hits, t), 0.5))

    rows = sorted(taken)
    # keep sixteenth-note runs within reach
    if spec.max_run16:
        out, run = [], 1
        for i, r in enumerate(rows):
            if out and r - out[-1] == 1:
                run += 1
                if run > spec.max_run16:
                    run = 1 if i + 1 < len(rows) and rows[i + 1] - r == 1 else 0
                    continue
            else:
                run = 1
            out.append(r)
        rows = out

    return [Note(row=r, time=taken[r][2], strength=taken[r][3],
                 kick=a.peak(a.low_env, taken[r][2])) for r in rows]


# share of steps on 16ths in official Konami charts by difficulty (about the
# 75th percentile of 909 charts): none up to 5, then a few more per level
SIXTEENTH_SHARE = ((5, 0.0), (6, 0.02), (7, 0.06), (8, 0.11), (9, 0.16), (10, 0.2), (12, 0.25))


def limit_sixteenths(a: Analysis, notes: list[Note], spec: DiffSpec) -> list[Note]:
    """Keep 16th-note steps to what a chart of this difficulty would have,
    times spec.sixteenths (the Speed slider: 0 none, 1 typical, 2 double).
    Aiming at a high difficulty switches on the 16th grid, which can
    otherwise fill whole bars with 16ths; the weakest extra ones slide onto
    a free neighbouring 8th (or go, if there's no room), so the chart keeps
    its density."""
    odd = [n for n in notes if n.row % 2]
    level = spec.target_meter if spec.target_meter > 0 else estimate_meter(notes, a.spb)
    xs, ys = zip(*SIXTEENTH_SHARE)
    allowed = int(float(np.interp(level, xs, ys)) * spec.sixteenths * len(notes))
    if len(odd) <= allowed:
        return notes
    row_dt = a.spb / ROWS_PER_BEAT
    taken = {n.row for n in notes}
    drop = set()
    n8 = sum(n.row % ROWS_PER_BEAT == 2 for n in notes)
    max8 = eighths_cap(spec, len(notes))
    for n in sorted(odd, key=lambda n: n.strength)[:len(odd) - allowed]:
        if n.hold_rows:
            continue
        free = [r for r in (n.row - 1, n.row + 1) if r not in taken and r - 1 not in taken - {n.row}
                and r + 1 not in taken - {n.row}]
        if n8 >= max8:
            free = [r for r in free if r % ROWS_PER_BEAT != 2]   # Speed's 8th share is full
        taken.discard(n.row)
        if free:
            n.row = min(free, key=lambda r: -a.peak(a.hits, a.t0 + r * row_dt))
            n.time = a.t0 + n.row * row_dt
            taken.add(n.row)
            n8 += n.row % ROWS_PER_BEAT == 2
        else:
            drop.add(id(n))
    return [n for n in notes if id(n) not in drop]


# notes in a row before a short pause, by difficulty, at run_breaks 0.5. From
# official Konami charts: 90% of their runs are 5 steps or fewer up to 9
# (longer streams come in the big parts), then about a beat's rest
BREAK_EVERY = ((4, 4), (6, 5), (8, 7), (9, 8), (10, 10), (12, 13))


def settle_rhythm(a: Analysis, notes: list[Note], spec: DiffSpec, rng: random.Random) -> list[Note]:
    """A rhythm your body can learn: where the music carries on alike, a bar
    takes the rhythm of the bar before (or two before, for 2-bar patterns),
    by moving its steps onto the same spots, as long as the music has a hit
    there too. rhythm_lock is how often (0 never, 1 whenever it can). The
    step count stays the same; new sections keep their own rhythm."""
    if spec.rhythm_lock <= 0 or not notes:
        return notes
    row_dt = a.spb / ROWS_PER_BEAT
    held = {r for n in notes if n.hold_rows for r in range(n.row, n.row + n.hold_rows + 1)}
    bars: dict[int, dict[int, Note]] = {}
    for n in notes:
        bars.setdefault(n.row // 16, {})[n.row % 16] = n
    Z = a.bar_feats
    # "alike" relative to the song: the fingerprints are centred, so even
    # neighbouring bars of one groove can look only loosely similar
    near = [float(Z[m] @ Z[m - 1]) for m in range(1, len(Z))]
    alike = float(np.percentile(near, 40)) if near else 1.0
    for m in sorted(bars):
        if m >= len(Z) or a.section_start[min(m, len(a.section_start) - 1)] > 0.5:
            continue
        refs = [k for k in (m - 1, m - 2) if k in bars and 0 <= k < len(Z)]
        if not refs or rng.random() > spec.rhythm_lock:
            continue
        k = max(refs, key=lambda k: float(Z[m] @ Z[k]))
        if float(Z[m] @ Z[k]) < alike:
            continue                                  # the music changed: so may the steps
        cur, ref = bars[m], set(bars[k])
        extra = [s for s in cur if s not in ref and not cur[s].hold_rows and m * 16 + s not in held]
        missing = [s for s in ref if s not in cur and m * 16 + s not in held]
        for s in sorted(missing, key=lambda s: -a.peak(a.hits, a.t0 + (m * 16 + s) * row_dt)):
            if not extra:
                break
            src = min(extra, key=lambda e: abs(e - s))
            n = cur[src]
            t = a.t0 + (m * 16 + s) * row_dt
            if a.peak(a.hits, t) < 0.6 * n.strength:
                continue                              # nothing there to step to
            extra.remove(src)
            del cur[src]
            n.row, n.time = m * 16 + s, t
            n.strength, n.kick = a.peak(a.hits, t), a.peak(a.low_env, t)
            cur[s] = n
    return sorted(notes, key=lambda n: n.row)


def breathe(a: Analysis, notes: list[Note], spec: DiffSpec, rng: random.Random) -> list[Note]:
    """Room to breathe, like a dancer finding the groove.

    run_breaks  in a long run of 8ths/16ths, a pause of about a beat every so
                many steps (fewer at higher levels, jittered so it doesn't
                feel mechanical), placed where the dropped steps are weakest
    recovery    after a long run, a rest of up to about 3 beats; a freeze
                with nothing tapped under it counts as the rest
    stomps      where the pause lands on a row of big beats, those beats
                become quarter-note jumps instead ([1001][1001]): following
                the song and a break at once"""
    if not notes or (spec.run_breaks <= 0 and spec.recovery <= 0):
        return notes
    notes = sorted(notes, key=lambda n: n.row)
    level = spec.target_meter if spec.target_meter > 0 else estimate_meter(notes, a.spb)
    xs, ys = zip(*BREAK_EVERY)
    every = float(np.interp(level, xs, ys)) * 2 ** (1 - 2 * spec.run_breaks)
    power = lambda n: n.strength + n.kick
    on_beat = [power(n) for n in notes if n.row % ROWS_PER_BEAT == 0]
    big = float(np.percentile(on_beat, 65)) if on_beat else 1e9
    can_stomp = spec.stomps > 0 and spec.jump > 0 and level >= 5
    gone: set[int] = set()                 # ids of dropped notes

    def runs():
        """Runs of steps 8ths or closer, as lists of notes still in."""
        live = [n for n in notes if id(n) not in gone]
        out, cur = [], live[:1]
        for p, n in zip(live, live[1:]):
            if n.row - p.row <= 2 and not (p.hold_rows >= ROWS_PER_BEAT and n.row > p.row + 1):
                cur.append(n)
            else:
                out.append(cur)
                cur = [n]
        return out + [cur] if cur else out

    def pause_after(run, j, rows=ROWS_PER_BEAT):
        """The steps that go for a pause of `rows` after run[j], or None."""
        r0 = run[j].row
        drop = [n for n in run[j + 1:] if n.row < r0 + rows]
        if not drop or any(n.hold_rows for n in drop) or len(drop) >= len(run) - j - 1:
            return None
        return drop

    def stomp_at(run, lo, hi):
        """2-4 big beats in a row inside run[lo:hi], to turn into jumps."""
        by_row = {n.row: n for n in run}
        for j in range(lo, hi):
            n = run[j]
            if n.row % ROWS_PER_BEAT or power(n) < big or n.hold_rows:
                continue
            seq = [n]
            while len(seq) < 4:
                nxt = by_row.get(seq[-1].row + ROWS_PER_BEAT)
                if nxt is None or power(nxt) < big or nxt.hold_rows:
                    break
                seq.append(nxt)
            if len(seq) >= 2:
                return seq[:rng.randint(2, len(seq))]
        return None

    # 1. pauses inside long runs
    if spec.run_breaks > 0:
        for run in runs():
            start = 0
            while start < len(run):
                peak = a.bar_intensity(run[start].row // 16) > 0.85 and level >= 8
                limit = max(3, int(round(every * (1.6 if peak else 1.0) * rng.uniform(0.75, 1.3))))
                if len(run) - start <= limit + 2:
                    break
                lo, hi = start + max(2, limit - 2), min(len(run) - 3, start + limit + 1)
                seq = (stomp_at(run, start + 2, min(len(run) - 1, start + int(limit * 1.5) + 1))
                       if can_stomp and rng.random() < spec.stomps else None)
                if seq:
                    for n in seq:
                        n.stomp = True
                    first, last = seq[0].row, seq[-1].row
                    # a clean landing: nothing in the half beat before, or between
                    gone.update(id(n) for n in run if first - 2 <= n.row < last + 2 and n not in seq
                                and not n.hold_rows)
                    resume = seq[-1]
                else:
                    best = None
                    for j in range(lo, hi + 1):
                        drop = pause_after(run, j)
                        if drop is None:
                            continue
                        # weakest steps out; pausing after a beat note reads best
                        cost = sum(power(n) for n in drop) * (0.7 if run[j].row % ROWS_PER_BEAT == 0 else 1.0)
                        if best is None or cost < best[0]:
                            best = (cost, j, drop)
                    if best is None:
                        start = hi + 1
                        continue
                    gone.update(id(n) for n in best[2])
                    resume = run[best[1]]
                run = [n for n in run if id(n) not in gone]
                start = run.index(resume) + 1

    # 2. rest after the long or hard runs
    if spec.recovery > 0:
        live = [n for n in notes if id(n) not in gone]
        for run in runs():
            fast = sum(b.row - p.row == 1 for p, b in zip(run, run[1:]))
            if len(run) < max(6, 1.5 * every) and not (fast >= 3 and len(run) >= every):
                continue
            end = run[-1].row + run[-1].hold_rows
            rest = int(round(ROWS_PER_BEAT * (1 + spec.recovery * min(2.0, len(run) / 8))))
            after = [n for n in live if end < n.row < end + rest and id(n) not in gone]
            hold = next((n for n in after if n.hold_rows >= ROWS_PER_BEAT), None)
            if hold is not None:
                # a freeze is a rest too, as long as nothing is tapped under it
                gone.update(id(n) for n in live if hold.row < n.row <= hold.row + hold.hold_rows
                            and not n.hold_rows and not n.stomp)
                gone.update(id(n) for n in after if n.row < hold.row and not n.stomp)
            else:
                gone.update(id(n) for n in after if not n.hold_rows and not n.stomp)
    return [n for n in notes if id(n) not in gone]


def refill(a: Analysis, notes: list[Note], spec: DiffSpec, rng: random.Random) -> list[Note]:
    """Holds remove the steps under them; top the chart back up to its density
    target with the next-best notes outside the holds."""
    span = max(a.music_end - a.music_start, 1.0)
    target = int(min(spec.density * span / a.spb, spec.max_nps * span))
    missing = target - len(notes)
    if missing <= 0:
        return notes
    from dataclasses import replace
    extra = place_notes(a, replace(spec, density=spec.density * 1.5,
                                   max_nps=spec.max_nps * 1.5), random.Random(0))
    spans = [(n.row, n.row + n.hold_rows + 1) for n in notes if n.hold_rows]
    have = {n.row for n in notes}
    gap = max(1, int(round(spec.min_gap * ROWS_PER_BEAT)))
    max_run = 3 + int(round(4 * spec.half_beats))   # back-to-back half-beat notes

    def run_with(r: int) -> int:
        n, k = 1, r - 2
        while k in have:
            n, k = n + 1, k - 2
        k = r + 2
        while k in have:
            n, k = n + 1, k + 2
        return n

    def key(n: Note) -> float:
        on_beat = n.row % ROWS_PER_BEAT == 0
        lift = a.bar_intensity(n.row // 16) ** (4 * spec.energy_follow)   # top up where it's busy
        return -(n.strength + n.kick) * (1 + 4 * spec.beat_backbone * on_beat) * lift

    added = 0
    for c in sorted(extra, key=key):
        if added >= missing:
            break
        if any(s0 <= c.row <= e for s0, e in spans):
            continue
        if any((c.row + d) in have for d in range(-gap + 1, gap)):
            continue
        if c.row % 2 == 0 and run_with(c.row) > max_run:
            continue
        if a.bar_intensity(c.row // 16) < 0.6 * spec.energy_follow:
            continue                                   # don't pad quiet parts to hit the target
        notes.append(c)
        have.add(c.row)
        added += 1
    return sorted(notes, key=lambda n: n.row)


FREE_FOOT_MIN_GAP = 0.3   # seconds: one foot can't tap much faster than this for long


def free_foot_rows(a: Analysis, spec: DiffSpec) -> int:
    """Rows between free-foot taps under a hold, 0 for none. Never faster
    than 8ths, and slower than that at high BPM, so one foot never gets 16ths."""
    if spec.hold_free_foot <= 0:
        return 0
    rows = max(spec.hold_free_foot * ROWS_PER_BEAT, 2, FREE_FOOT_MIN_GAP / (a.spb / ROWS_PER_BEAT))
    return int(math.ceil(rows / 2 - 1e-9) * 2)                  # on the 8th grid


def choose_holds(a: Analysis, notes: list[Note], spec: DiffSpec) -> list[Note]:
    """Turn notes that start a sustained melody/chord note into freeze arrows.

    Hold length follows how long the harmonic sound stays up, between
    hold_min and hold_max beats. Under a hold the free foot only gets taps
    at least hold_free_foot beats apart (none if 0) and no jumps."""
    spb = a.spb
    row_dt = spb / ROWS_PER_BEAT
    quant = 2                                                       # 8th-note ends
    min_rows = int(round(spec.hold_min * ROWS_PER_BEAT))
    max_rows = int(round(spec.hold_max * ROWS_PER_BEAT))
    cands = []
    for i, nt in enumerate(notes):
        if nt.row % ROWS_PER_BEAT or a.peak(a.harm_env, nt.time, 0.05) < 0.35:
            continue
        level = a.mean(a.harm_rms, nt.time + 0.03, nt.time + 0.12)
        if level < 0.25:
            continue
        r = 1
        while r <= max_rows and \
                a.mean(a.harm_rms, nt.time + r * row_dt - 0.02, nt.time + r * row_dt) > 0.55 * level:
            r += 1
        rows = min((r - 1) // quant * quant, max_rows)
        if rows >= min_rows:
            # a hold silences the steps under it, so prefer spots where the
            # music has no strong hits of its own for that stretch
            covered = np.mean([a.peak(a.hits, nt.time + k * row_dt, 0.03)
                               for k in range(2, rows + 1, 2)])
            score = a.peak(a.harm_env, nt.time, 0.05) * rows / (1 + 3 * covered ** 2)
            cands.append((score, i, rows))
    budget = int(len(notes) * spec.hold_rate)
    climax_rows = [m * 16 for m in climax_bars(a)] if spec.crescendo > 0 else []
    chosen: dict[int, int] = {}
    for _, i, rows in sorted(cands, key=lambda c: -c[0]):
        if len(chosen) >= budget:
            break
        r0 = notes[i].row
        # the climax hit is a jump, so no hold may still be running into it
        if any(r0 < c <= r0 + rows + 1 for c in climax_rows):
            continue
        # holds don't overlap each other (one held foot at a time)
        if any(r0 <= j + chosen[j] + 2 and j <= r0 + rows + 2 for j in chosen):
            continue
        chosen[r0] = rows
    free_gap = free_foot_rows(a, spec)
    keep = []
    hold_start, hold_end, last_tap = -1, -1, -1
    for nt in notes:
        if nt.row in chosen:
            nt.hold_rows = chosen[nt.row]
            keep.append(nt)
            hold_start, hold_end = nt.row, nt.row + nt.hold_rows
            last_tap = nt.row
        elif nt.row == hold_end and nt.row - last_tap >= 2:
            keep.append(nt)            # free foot steps as the held one lets go
        elif hold_start < nt.row <= hold_end:
            # free foot: sparse taps only, and one 8th clear of the release
            if free_gap and nt.row - last_tap >= free_gap and hold_end - nt.row >= 2:
                keep.append(nt)
                last_tap = nt.row
        elif nt.row == hold_end + 1:
            continue
        else:
            keep.append(nt)
    return keep


# --------------------------------------------------------------------------
# 3. arrow assignment
# --------------------------------------------------------------------------

FOOT_PANELS = {"L": [LEFT, DOWN, UP], "R": [RIGHT, DOWN, UP]}
# jump shapes and base weights; LR is the classic, DU next
JUMP_TYPES = {(LEFT, RIGHT): 4.0, (DOWN, UP): 1.5, (LEFT, UP): 1.0, (LEFT, DOWN): 1.0,
              (DOWN, RIGHT): 1.0, (UP, RIGHT): 1.0}


def cluster_zone(a: Analysis, row: int) -> float:
    """0..1: how close a row is to the start of a section (decays over ~3 bars)."""
    m = row // 16
    best = 0.0
    for k in range(max(0, m - 4), m + 1):
        if k < len(a.section_start) and a.section_start[k] > 0:
            best = max(best, a.section_start[k] * math.exp(-(row - 16 * k) / 40))
    return best


def choose_jumps(notes: list[Note], spec: DiffSpec, a: Analysis | None = None) -> set[int]:
    """Pick which notes become jumps, from the `jump` leniency slider.

    jump sets: how many (up to ~25% of notes), how far apart separate jumps
    must be, whether back-to-back jumps may happen at all, how fast they may
    come and how long such a run may get."""
    j = spec.jump
    if j <= 0 or not notes:
        return set()
    n_jumps = int(len(notes) * 0.25 * j)
    spacing = (1 - j) * 6 * ROWS_PER_BEAT          # rows between unrelated jumps
    max_run = 1 + int(j * 4)                       # 0.25 -> 2, 0.5 -> 3, 0.75 -> 4
    b2b_gap = (ROWS_PER_BEAT if j < 0.6 else ROWS_PER_BEAT // 2)
    pos = {nt.row: i for i, nt in enumerate(notes)}
    chosen: set[int] = set()
    on = 1 if j >= 0.6 else ROWS_PER_BEAT          # very lenient -> 8th-note jumps too
    jc = spec.jump_clusters if a is not None else 0.0
    zone = {nt.row: cluster_zone(a, nt.row) for nt in notes} if jc else {}

    def score(i: int, nt: Note) -> float:
        sc = nt.kick + nt.strength
        if a is not None and spec.crescendo > 0:
            sc *= a.bar_intensity(nt.row // 16) ** (3 * spec.crescendo)   # save jumps for the big parts
        if jc:
            sc *= 1 + 3 * jc * zone[nt.row]               # jumps gather at section starts
        if spec.flow_runs and 0 < i < len(notes) - 1 and \
                nt.row - notes[i - 1].row <= ROWS_PER_BEAT and notes[i + 1].row - nt.row <= ROWS_PER_BEAT:
            sc *= 1 - 0.8 * spec.flow_runs                # don't break a running stream
        return sc

    held = {r for nt in notes if nt.hold_rows for r in range(nt.row + 1, nt.row + nt.hold_rows + 1)}
    if a is not None and spec.crescendo > 0:
        have = {nt.row for nt in notes if not nt.hold_rows}
        chosen |= {m * 16 for m in climax_bars(a) if m * 16 in have and m * 16 not in held}
    order = [nt for _, nt in sorted(((-score(i, nt), i), nt) for i, nt in enumerate(notes))]
    for nt in order:
        if len(chosen) >= n_jumps:
            break
        if nt.row % on or nt.row % 2 or nt.hold_rows or nt.row in held:
            continue
        i = pos[nt.row]
        z = zone.get(nt.row, 0.0)
        # run of back-to-back jumps this one would join
        lo = i
        while lo > 0 and notes[lo - 1].row in chosen:
            lo -= 1
        hi = i
        while hi + 1 < len(notes) and notes[hi + 1].row in chosen:
            hi += 1
        run = hi - lo + 1
        if run > 1:
            if run > max_run + (int(round(2 * jc)) if z > 0.3 else 0):
                continue
            if any(notes[k + 1].row - notes[k].row < b2b_gap for k in range(lo, hi)):
                continue
        neighbours = {notes[k].row for k in range(lo, hi + 1)}
        gap_needed = spacing * (1 - jc) if z > 0.3 else spacing
        if any(abs(nt.row - c) < gap_needed for c in chosen if c not in neighbours):
            continue
        chosen.add(nt.row)
    return chosen


def add_jump_holds(a: Analysis, notes: list[Note], spec: DiffSpec, rng: random.Random) -> list[Note]:
    """Turn some jumps on beats 1 and 3 into two-foot freezes when the music
    sustains there (the big held synth or chord hits). Both feet are busy, so
    any steps under the freeze are dropped."""
    if spec.jump_holds <= 0:
        return notes
    row_dt = a.spb / ROWS_PER_BEAT
    min_rows = int(round(min(spec.hold_min, 2.0) * ROWS_PER_BEAT))
    max_rows = int(round(spec.hold_max * ROWS_PER_BEAT))
    held_until = -1
    for nt in notes:
        if nt.hold_rows:
            held_until = max(held_until, nt.row + nt.hold_rows)
    jumps = [nt for nt in notes if len(nt.panels) >= 2 and not nt.hold_rows and nt.row % 8 == 0]
    cands = []
    for nt in jumps:
        level = a.mean(a.harm_rms, nt.time + 0.03, nt.time + 0.12)
        r = 1
        while r <= max_rows and a.mean(a.harm_rms, nt.time + r * row_dt - 0.02,
                                       nt.time + r * row_dt) > 0.45 * level:
            r += 1
        rows = (r - 1) // 2 * 2
        if rows >= min_rows and level > 0.2:
            # both feet stop, so only where the music itself goes quiet on top
            covered = np.mean([a.peak(a.hits, nt.time + k * row_dt, 0.03)
                               for k in range(2, rows + 1, 2)])
            if covered > 0.5:
                rows = min(rows, ROWS_PER_BEAT)     # busy music: a one-beat stab
                if rows < min_rows:
                    continue
            climax = 2.0 if spec.crescendo > 0 and nt.row % 16 == 0 and nt.row // 16 in climax_bars(a) else 0.0
            cands.append((nt.kick + nt.strength + cluster_zone(a, nt.row) - covered + climax, nt, rows))
    budget = int(round(len(jumps) * 0.6 * spec.jump_holds))
    picked = []
    for _, nt, rows in sorted(cands, key=lambda c: -c[0]):
        if len(picked) >= budget:
            break
        if any(p.row <= nt.row + rows + 2 and nt.row <= p.row + p.hold_rows + 2 for p in picked):
            continue
        # no single-foot hold may be running over it
        if any(o.hold_rows and o.row < nt.row <= o.row + o.hold_rows + 1 for o in notes):
            continue
        nt.hold_rows = rows
        picked.append(nt)
    spans = [(p.row, p.row + p.hold_rows + 1) for p in picked]
    return [n for n in notes if not any(s < n.row <= e for s, e in spans)
            and not (n.hold_rows and n not in picked and any(s < n.row + n.hold_rows and n.row < e for s, e in spans))]


_MEL_STATS: dict[int, tuple] = {}


def _similar(a: Analysis, t1: float, t2: float) -> float:
    """Similarity of the drum spectrum at two moments (same hit -> ~1). Each
    band is standardized over the song first; raw spectra of any two beats
    look ~99% alike, which says nothing."""
    key = id(a)
    if key not in _MEL_STATS:
        _MEL_STATS[key] = (a.mel.mean(1), a.mel.std(1) + 1e-6)
    mu, sd = _MEL_STATS[key]
    v1, v2 = (a.mel[:, a.frame(t1)] - mu) / sd, (a.mel[:, a.frame(t2)] - mu) / sd
    return float(v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))


def _jack_threshold(a: Analysis) -> float:
    """How alike two hits must be to count as "the same hit again": the
    song's own top quarter of beat-to-beat similarity."""
    ts = [a.t0 + k * a.spb for k in range(int((a.music_start - a.t0) / a.spb) + 2,
                                         int((a.music_end - a.t0) / a.spb))]
    if len(ts) < 8:
        return 0.9
    sims = [_similar(a, t, t - a.spb) for t in ts]
    return float(np.clip(np.percentile(sims, 75), 0.5, 0.97))


def arrange(a: Analysis, notes: list[Note], spec: DiffSpec, rng: random.Random,
            prefer: dict[int, list[int]] | None = None, locked: set[int] = frozenset()) -> None:
    """Assign arrows. `prefer` maps rows to arrows copied from an earlier,
    repeated section: they're followed whenever the foot model allows it.
    Rows in `locked` (repeated sections) only get jumps where `prefer` has one."""
    if not notes:
        return
    spb = a.spb
    prefer = prefer or {}
    climaxes = {m * 16 for m in climax_bars(a)} if spec.crescendo > 0 else set()
    jump_rows = {r for r in choose_jumps(notes, spec, a) if r // 16 not in locked or r in climaxes}
    jump_rows |= {r for r, p in prefer.items() if len(p) >= 2}
    jump_rows |= {nt.row for nt in notes if nt.stomp and nt.row // 16 not in locked}
    held_rows = set()
    for nt in notes:
        if nt.hold_rows:
            held_rows.update(range(nt.row + 1, nt.row + nt.hold_rows + 1))
    jump_rows -= held_rows

    feet = {"L": LEFT, "R": RIGHT}
    last_foot = None
    hist: list[int] = []                           # recent single-step panels
    jack = 1
    prev_jump = None
    hold_until = {"L": -1, "R": -1}
    hold_used: set[int] = set()                    # panels the free foot hit this hold
    centroid_med = np.median(a.centroid) + 1e-9
    melody_med = np.median(a.melody_cent) + 1e-9 if a.melody_cent is not None else centroid_med
    jack_thr = _jack_threshold(a) if spec.jacks > 0 else 1.0

    for i, nt in enumerate(notes):
        gap_beats = (nt.row - notes[i - 1].row) / ROWS_PER_BEAT if i else 99
        held = [f for f in "LR" if hold_until[f] >= nt.row]
        if not held:
            hold_used = set()

        if nt.row in jump_rows:
            types = dict(JUMP_TYPES)
            if prev_jump is not None and i and notes[i - 1].row in jump_rows:
                for t in types:
                    if not set(t) & set(prev_jump):
                        types[t] *= 0.05 + 0.3 * spec.jump   # [1001][0110] alternation
                    elif t == prev_jump:
                        types[t] *= 0.8
            if spec.jump < 0.3:
                types = {(LEFT, RIGHT): 1.0}
            pair = rng.choices(list(types), list(types.values()))[0]
            if nt.stomp:
                # stomps repeat the same jump, [1001][1001], like stamping the beat
                pair = prev_jump if prev_jump and i and notes[i - 1].stomp else (LEFT, RIGHT)
            if len(prefer.get(nt.row, ())) >= 2:
                pair = tuple(sorted(prefer[nt.row])[:2])
            nt.panels = list(pair)
            feet["L"], feet["R"] = pair
            prev_jump = pair
            last_foot, hist, jack = None, [], 1
            continue
        prev_jump = None

        last = hist[-1] if hist else None
        cands: list[tuple[str, int, float]] = []
        if held:
            foot_opts = ["R" if held[0] == "L" else "L"]
        elif last_foot is None or gap_beats >= 2:
            foot_opts = ["L", "R"]                  # after a rest either foot leads
        else:
            foot_opts = ["L" if last_foot == "R" else "R"]

        # jack: same foot, same arrow, when the music repeats the same hit
        # never on quarter-beat notes: two quick hits go to two feet
        if last is not None and last_foot and not held and jack < spec.jack_max \
                and spec.jacks > 0 and 0.5 <= gap_beats <= 1:
            sim = _similar(a, nt.time, notes[i - 1].time)
            if sim > jack_thr:
                # 2nd and 3rd repeat are normal; each one past 3 is far less likely
                fade = 0.15 ** max(0, jack + 1 - 3)
                wj = 3.0 * spec.jacks * fade * (0.5 + 0.5 * (sim - jack_thr) / (1 - jack_thr + 1e-9))
                if gap_beats < 1:
                    wj *= 0.15                          # half-beat jacks are rare and tiring
                in_stream = gap_beats <= 1 and i + 1 < len(notes) and \
                    notes[i + 1].row - nt.row <= ROWS_PER_BEAT
                if in_stream and cluster_zone(a, nt.row) < 0.3:
                    wj *= 1 - 0.85 * spec.flow_runs      # keep runs rolling
                if nt.row in prefer:
                    wj *= 40.0 if prefer[nt.row] == [last] else 0.3
                cands.append((last_foot, last, wj))

        fol = float(a.follow[min(nt.row // 16, len(a.follow) - 1)]) if a.follow is not None else 0.0
        src, med = (a.melody_cent, melody_med) if fol > 0 and a.melody_cent is not None else (a.centroid, centroid_med)
        c_now = a.mean(src, nt.time - 0.05, nt.time + 0.1)
        c_prev = a.mean(src, nt.time - spb, nt.time - 0.05)
        rising = (c_now - c_prev) / med
        for foot in foot_opts:
            other = "R" if foot == "L" else "L"
            for p in FOOT_PANELS[foot]:
                if p == feet[other] or (p == last and gap_beats < 2 and not held):
                    continue
                w = 1.0
                if held and hold_used and p not in hold_used:
                    # hold_complexity: 0 = free foot keeps tapping one arrow,
                    # 1 = it moves around freely
                    w *= min(1.0, 2 * spec.hold_complexity)
                    if w == 0:
                        continue
                if last is not None and gap_beats <= 1:
                    if {p, last} == {LEFT, RIGHT}:
                        w *= 1 - 0.9 * spec.side_to_side
                    if {p, last} == {DOWN, UP}:
                        w *= 1 - 0.6 * spec.side_to_side
                if p in (DOWN, UP) and feet[other] in (DOWN, UP):
                    w *= 0.5                            # both feet off their home side
                # flow ------------------------------------------------------
                if len(hist) >= 2:
                    d1, d2 = p - hist[-1], hist[-1] - hist[-2]
                    if abs(d1) == 1 and abs(d2) == 1 and d1 == d2:
                        w *= 1 + 3 * spec.flow          # walk: L D U R / R U D L
                    if p == hist[-2] and p != hist[-1]:
                        w *= 1 + 1.2 * spec.flow        # anchor: x y x ...
                        if len(hist) >= 4 and hist[-4] == p and hist[-3] == hist[-1]:
                            w *= 0.3                    # x y x y x: getting stale
                if p not in hist[-3:]:
                    w *= 1 + 0.8 * spec.flow            # fresh arrow keeps it moving
                w /= 1 + 0.25 * hist[-8:].count(p)      # spread use over the pad
                if p in (LEFT, RIGHT):
                    w *= 1.4                            # home panels; Down/Up are shared
                lean = 1.6 + 1.4 * fol                 # following the melody: lean harder
                if p == UP and rising > 0.08:
                    w *= lean
                if p == DOWN and rising < -0.08:
                    w *= lean
                if fol > 0.3 and last is not None and abs(rising) > 0.08:
                    # the tune climbs: step rightward along L D U R; it falls: leftward
                    order = (LEFT, DOWN, UP, RIGHT)
                    if (order.index(p) - order.index(last)) * rising > 0:
                        w *= 1 + fol
                if nt.row in prefer:
                    w *= 40.0 if prefer[nt.row] == [p] else 0.3
                cands.append((foot, p, w))

        # a copied arrow the expected foot can't reach (the feet came into the
        # repeat the other way round): let the other foot take it
        if nt.row in prefer and len(prefer[nt.row]) == 1 and not held \
                and not any(c[1] == prefer[nt.row][0] for c in cands):
            p = prefer[nt.row][0]
            for foot in "LR":
                other = "R" if foot == "L" else "L"
                if p in FOOT_PANELS[foot] and p != feet[other] and not (p == last and gap_beats < 1):
                    cands.append((foot, p, 40.0))
        if not cands:                                   # boxed in: tap where the free foot is
            foot = foot_opts[0]
            cands = [(foot, feet[foot], 1.0)]
        foot, p, _ = rng.choices(cands, [c[2] for c in cands])[0]
        jack = jack + 1 if (p == last and foot == last_foot) else 1
        nt.panels = [p]
        feet[foot] = p
        if held:
            hold_used.add(p)
        last_foot = foot
        hist = (hist + [p])[-8:]

        if nt.hold_rows:
            hold_until[foot] = nt.row + nt.hold_rows


# --------------------------------------------------------------------------
# 3b. repeated sections: same music, same (or similar) steps
# --------------------------------------------------------------------------

REPEAT_MATCH = 0.65            # fingerprint similarity that counts as "the same music"
REPEAT_MIN_BARS = 4


def find_repeats(a: Analysis) -> list[tuple[int, int, int]]:
    """Find stretches of measures that repeat earlier ones (a returning chorus,
    a second verse over the same beat). Returns (target, source, length) in
    measures; source < target, matches at least REPEAT_MIN_BARS long."""
    Z = a.bar_feats
    n = len(Z)
    if n < 2 * REPEAT_MIN_BARS:
        return []
    S = Z @ Z.T
    W = REPEAT_MIN_BARS
    best = {}
    for t in range(W, n):
        cand = None
        for s in range(0, t - W + 1):
            k0, k1 = max(-1, -s, -t), min(W - 1, n - 1 - t)
            sim = float(np.mean([S[t + k, s + k] for k in range(k0, k1 + 1)]))
            if sim >= REPEAT_MATCH and (cand is None or sim > cand[1]):
                cand = (s, sim)
        if cand:
            best[t] = cand[0]
    # join measures that copy with the same offset into segments
    segs, t = [], W
    while t < n:
        if t not in best:
            t += 1
            continue
        lag = t - best[t]
        u = t
        while u + 1 < n and (u + 1) in best and abs((u + 1) - best[u + 1] - lag) == 0:
            u += 1
        # a measure or two can wobble; let the segment run on with the same lag
        while u + 1 < n and float(S[u + 1, u + 1 - lag]) >= REPEAT_MATCH - 0.1:
            u += 1
        if u - t + 1 >= REPEAT_MIN_BARS:
            segs.append((t, t - lag, u - t + 1))
        t = u + 1
    return segs


MIRROR = {LEFT: RIGHT, RIGHT: LEFT, DOWN: DOWN, UP: UP}


REPEAT_HIT_MATCH = 0.6         # per-bar hit-pattern correlation needed to copy a bar


def _bar_hit_match(a: Analysis, m1: int, m2: int) -> float:
    v = [np.array([a.peak(a.hits, a.t0 + (m * 16 + r) * a.spb / ROWS_PER_BEAT)
                   for r in range(0, 16, 2)]) for m in (m1, m2)]
    if v[0].std() < 1e-6 or v[1].std() < 1e-6:
        return 1.0
    return float(np.corrcoef(v[0], v[1])[0, 1])


def apply_repeats(a: Analysis, notes: list[Note], segs, spec: DiffSpec,
                  rng: random.Random) -> list[Note]:
    """Copy timing and arrows from each source section into its repeat, then
    re-arrange with those arrows as strong preferences.

    rhythm_repeat        chance a detected repeat reuses the earlier timing
    arrow_repeat         share of the arrows copied along with it (plus a
                         mirrored Left/Right version now and then)
    intensity_variation  extra variation when the repeat is louder than the
                         original: more re-picked arrows and the louder
                         section's own extra notes kept"""
    if spec.rhythm_repeat <= 0 or not segs or not notes:
        return notes
    row_dt = a.spb / ROWS_PER_BEAT
    bars: dict[int, list[Note]] = {}
    for nt in notes:
        bars.setdefault(nt.row // 16, []).append(nt)
    bar_energy = a.bar_intensity
    prefer: dict[int, list[int]] = {}
    locked: set[int] = set()
    min_gap = max(1, int(round(spec.min_gap * ROWS_PER_BEAT)))
    used: list = []

    climaxes = set(climax_bars(a))
    for t, s, length in segs:
        if rng.random() >= spec.rhythm_repeat:
            continue
        used.append((t, s, length))
        e_t = np.mean([bar_energy(t + k) for k in range(length)])
        e_s = np.mean([bar_energy(s + k) for k in range(length)])
        lift = float(np.clip((e_t - e_s) / (e_s + 1e-9) * 4, 0, 1))
        var = min(1.0, (1 - spec.arrow_repeat) + spec.intensity_variation * lift)
        mirror = spec.arrow_repeat > 0 and rng.random() < 0.3 * var
        shift = (t - s) * 16
        for k in range(length):
            # bar by bar: only reuse the rhythm where the hits line up the same
            # way (a chorus over a new drum fill keeps its own steps there)
            if _bar_hit_match(a, s + k, t + k) < REPEAT_HIT_MATCH or \
                    (spec.crescendo > 0 and t + k in climaxes):
                continue
            src = bars.get(s + k, [])
            own = bars.get(t + k, [])
            copied = []
            dropped = 0
            for sn in src:
                r = sn.row + shift
                tm = a.t0 + r * row_dt
                here = a.peak(a.hits, tm)
                # the copy has to land on something in this part of the song
                # too; where the music differs, follow the music
                if here < 0.3 and here < 0.6 * sn.strength:
                    dropped += 1
                    continue
                nn = Note(row=r, time=tm, strength=here, kick=a.peak(a.low_env, tm),
                          hold_rows=sn.hold_rows)
                panels = [MIRROR[p] for p in sn.panels] if mirror else list(sn.panels)
                # same rhythm always; the arrows only with arrow_repeat
                if rng.random() >= var or (len(panels) > 1 and spec.arrow_repeat > 0):
                    prefer[r] = sorted(panels)
                copied.append(nn)
            # jumps belong to this section's own hits (section starts, drops),
            # so its own jumps stand in for the copied step nearest to them
            if spec.arrow_repeat < 1:
                for on in own:
                    if len(on.panels) < 2 or on.hold_rows:
                        continue
                    near = [c for c in copied if abs(c.row - on.row) < min_gap]
                    if near and rng.random() < 1 - spec.arrow_repeat:
                        for c in near:
                            copied.remove(c)
                            prefer.pop(c.row, None)
                        copied.append(Note(on.row, on.time, on.strength, on.kick))
                        prefer[on.row] = sorted(on.panels)
            # copies that found nothing to land on make way for this part's own hits
            rows = {c.row for c in copied}
            for on in sorted(own, key=lambda n: -n.strength):
                if dropped <= 0:
                    break
                if not on.hold_rows and not any(abs(on.row - r) < min_gap for r in rows):
                    copied.append(Note(on.row, on.time, on.strength, on.kick))
                    rows.add(on.row)
                    dropped -= 1
            # a louder repeat keeps some of its own extra notes
            if lift > 0.25:
                rows = {c.row for c in copied}
                held = {x for c in copied if c.hold_rows for x in range(c.row, c.row + c.hold_rows + 2)}
                for on in own:
                    if on.row in held or any(abs(on.row - r) < min_gap for r in rows):
                        continue
                    if rng.random() < 0.5 * spec.intensity_variation * lift:
                        copied.append(Note(on.row, on.time, on.strength, on.kick))
            bars[t + k] = sorted(copied, key=lambda n: n.row)
            locked.add(t + k)

    # everything outside the repeats keeps the arrows it already has, so the
    # sources stay exactly what got copied
    for m, b in bars.items():
        if m not in locked:
            for nt in b:
                prefer[nt.row] = sorted(nt.panels)
    locked |= set(bars)
    out = sorted((n for b in bars.values() for n in b), key=lambda n: n.row)
    # tidy the seams where a copied section meets its neighbours
    clean: list[Note] = []
    for nt in out:
        if clean and nt.row - clean[-1].row < 1:
            continue
        if clean and clean[-1].hold_rows and spec.hold_free_foot == 0 and \
                (nt.row < clean[-1].row + clean[-1].hold_rows or
                 nt.row == clean[-1].row + clean[-1].hold_rows + 1 or
                 (len(prefer.get(clean[-1].row, ())) > 1 and nt.row <= clean[-1].row + clean[-1].hold_rows)):
            continue
        clean.append(nt)
    for nt in clean:
        nt.panels = []
    arrange(a, clean, spec, rng, prefer, locked)
    return clean


# Difficulty rating, fitted on 909 official Konami pad charts (PS2/arcade
# mixes, meters 1-10): within one foot of Konami's number 70% of the time,
# about 0.8 off on average. It reads what makes a chart hard: steps/sec over
# the song and in its busiest bars, jumps/sec, off-beat and quarter-beat
# steps/sec, the longest unbroken 8th-note run and holds/sec. It runs a bit
# low on 9-10 charts, whose difficulty is in things it can't see (speed
# changes, stamina over a whole long song).
METER_FEATURES = ("nps", "p80", "p95", "jps", "offps", "qps", "stream", "holds")
METER_WEIGHTS = (-1.2435, 0.707, -0.3459, -0.1604, 0.7624, -1.324, 0.0662, -0.0112, 0.5052,
                 1.006, 1.1374, 0.6853, -0.2054, 2.7929, 0.6438, 0.2652, 0.7356)


def chart_features(notes: list[Note], spb: float) -> dict[str, float] | None:
    if len(notes) < 20:
        return None
    rows = np.array(sorted(n.row for n in notes))
    beats = rows / ROWS_PER_BEAT
    span = max((beats[-1] - beats[0]) * spb, 1.0)
    per_bar = np.bincount(rows // 16)
    per_bar = per_bar[per_bar > 0] / (4 * spb)
    run = best = 0
    for g in np.diff(beats):
        run = run + 1 if g <= 0.5 + 1e-6 else 0
        best = max(best, run)
    n = len(notes)
    jumps = sum(len(nt.panels) > 1 for nt in notes)
    return {"nps": n / span, "p80": float(np.percentile(per_bar, 80)),
            "p95": float(np.percentile(per_bar, 95)), "jps": jumps / span,
            "offps": np.sum(rows % ROWS_PER_BEAT != 0) / span,
            "qps": np.sum(rows % 2 != 0) / span, "stream": best,
            "holds": sum(len(nt.panels) for nt in notes if nt.hold_rows) / span}


# the fit above squeezes the top: Konami's own 8s rate 8.0 on it (median),
# but their 9s only 8.4 and their 10s 9.4. Past 8 it's stretched back so a
# chart like their 9s rates 9 (and like their 10s, 10)
METER_TOP = ((8.0, 8.0), (8.42, 9.0), (9.42, 10.0))


def estimate_meter(notes: list[Note], spb: float) -> float:
    """The difficulty Konami would likely give this chart, as a decimal."""
    f = chart_features(notes, spb)
    if f is None:
        return 1.0
    x = np.array([f[k] for k in METER_FEATURES], float)
    v = np.concatenate([[1.0], x, np.sqrt(np.abs(x))])
    raw = float(max(1.0, v @ np.array(METER_WEIGHTS)))
    (r0, _), *_, (r1, m1) = METER_TOP
    if raw <= r0:
        return raw
    if raw >= r1:
        return m1 + raw - r1
    return float(np.interp(raw, *zip(*METER_TOP)))


def meter_for(notes: list[Note], a: Analysis, spec: DiffSpec) -> int:
    # the honest rating, not clamped to a range: target_meter is the way to
    # aim for a number (meter_min/max are kept only so old profiles load)
    return int(np.clip(round(estimate_meter(notes, a.spb)), 1, 20))


KONAMI_K = 3.0   # the dial as far as Konami's own charts go
TOP_K = 4.5      # past that, for 9s and 10s: longer 16th streams, more 8ths
PAST_KONAMI_16THS = 1.0    # ... but no more 16ths than Konami's own 9s and 10s (16% at 9, 20% at 10)


def with_intensity(spec: DiffSpec, k: float, nps_8ths: float | None = None) -> DiffSpec:
    """One dial for the difficulty number, in stages so the Feel sliders
    keep their say as long as they can. k = 0 is the profile as written.

      -2..1  density: how many steps, the grid and spacing they sit on,
             the notes/sec cap, jumps and holds (those two keep turning
             to 2, as they always have). Speed's settings (8ths,
             quarter-beat bursts, 16ths, flow spice) stay where Speed put them.
       1..2  16th streams, a bit at a time, still within Speed's 16th
             allowance: the step count is held to nps_8ths (the notes/sec
             at 1) plus up to 60% more.
       2..3  density can't do more: Speed's settings rise, 8th runs first,
             then quarter-beat bursts.
       3..TOP_K  for 9s and 10s: longer 16th streams and more 8ths, past
             Speed's allowance (16ths still at most Konami's share).

    The profile's own feel (flow, repeats, the arc) is left alone."""
    c = lambda x: float(np.clip(x, 0.0, 1.0))
    d = dataclasses.replace(spec)
    kd = min(k, 1.0)                    # the density stage
    d.density = spec.density * 2 ** kd
    d.max_nps = max(spec.max_nps, 2.5 + 2 * kd) if k > 0 else spec.max_nps
    kj = min(k, 2.0)                    # jumps and holds keep turning a while longer
    d.jump = c(spec.jump + 0.12 * kj)
    d.hold_rate = c(spec.hold_rate * (1 - 0.4 * kj))
    if k < -0.4:                        # down to beat notes only
        d.grid, d.min_gap = 1, max(spec.min_gap, 1.0)
    elif k > 0:
        d.grid = max(spec.grid, 2)
        d.min_gap = min(spec.min_gap, 0.5)
    if k > 1.0 and nps_8ths:            # 16th streams
        t = min(k - 1.0, 1.0) + max(0.0, k - KONAMI_K)
        d.grid, d.min_gap = 4, min(spec.min_gap, 0.25)
        d.density = spec.density * (4 + 2 * max(0.0, k - KONAMI_K))
        d.max_nps = nps_8ths * (1 + 0.6 * t)
    if k > 2.0:                         # Speed's settings, only past what density reaches
        ks = min(k, KONAMI_K) - 2.0
        # 8ths keep rising past Konami too, so 9s and 10s aren't all 16ths
        d.half_beats = c(spec.half_beats + 0.6 * (k - 2.0))
        if ks > 0.6:                    # quarter-beat bursts on top of the 8ths
            d.quarter_beats = c(spec.quarter_beats + 0.5 * (ks - 0.6))
            d.flow_spice = c(spec.flow_spice + 0.3 * (ks - 0.6))
    if k > KONAMI_K:                    # past Konami-typical: more and longer 16th runs
        x = k - KONAMI_K
        d.sixteenths = max(spec.sixteenths, 1.0) * min(1 + x, PAST_KONAMI_16THS)
        d.max_run16 = spec.max_run16 + int(round(6 * x))
        # and less rest: shorter recovery after runs, pauses further apart
        d.recovery = spec.recovery * max(0.0, 1 - 0.5 * x)
        d.run_breaks = spec.run_breaks * max(0.0, 1 - 0.4 * x)
    return d


# --------------------------------------------------------------------------
# 4. .sm output
# --------------------------------------------------------------------------

def notes_to_measures(notes: list[Note]) -> str:
    if not notes:
        return "0000\n0000\n0000\n0000\n"
    end_row = max(n.row + n.hold_rows for n in notes)
    n_measures = end_row // 16 + 1
    grid = [["0"] * 4 for _ in range(n_measures * 16)]
    for n in notes:
        for p in n.panels:
            if n.hold_rows:
                grid[n.row][p] = "2"
                grid[n.row + n.hold_rows][p] = "3"
            else:
                grid[n.row][p] = "1"
    out = []
    for m in range(n_measures):
        rows = grid[m * 16:(m + 1) * 16]
        # write each measure at the coarsest resolution that holds its notes
        for res in (4, 8, 16):
            stride = 16 // res
            if all(r == ["0"] * 4 for i, r in enumerate(rows) if i % stride):
                break
        out.append("\n".join("".join(r) for r in rows[::16 // res]))
    return "\n,\n".join(out) + "\n"


def sm_escape(s: str) -> str:
    return s.replace(":", "\\:").replace(";", "\\;").replace("#", "\\#")


def write_sm(path: Path, title: str, artist: str, music: str, a: Analysis,
             charts: list[tuple[DiffSpec, list[Note], int]], art: dict[str, str] | None = None) -> None:
    # preview: the loudest 12 s window
    win = int(12 * SR / HOP)
    csum = np.convolve(a.rms, np.ones(win), "valid")
    sample_start = float(np.argmax(csum) * HOP / SR) if len(csum) else 0.0
    head = [
        f"#TITLE:{sm_escape(title)};",
        "#SUBTITLE:;",
        f"#ARTIST:{sm_escape(artist)};",
        f"#CREDIT:stepgen {PROFILE_NAME};",
        f"#BANNER:{sm_escape((art or {}).get('BANNER', ''))};",
        f"#BACKGROUND:{sm_escape((art or {}).get('BACKGROUND', ''))};",
        "#CDTITLE:;",
        *([f"#JACKET:{sm_escape(art['JACKET'])};"] if art and art.get("JACKET") else []),
        f"#MUSIC:{music};",
        f"#OFFSET:{-a.t0:.3f};",
        f"#SAMPLESTART:{sample_start:.3f};",
        "#SAMPLELENGTH:12.000;",
        "#SELECTABLE:YES;",
        f"#DISPLAYBPM:{a.bpm:g};",
        f"#BPMS:0.000={a.bpm:.3f};",
        "#STOPS:;",
    ]
    body = []
    import chartstats
    for spec, notes, meter in charts:
        rows = [chartstats.Row(Fraction(n.row, ROWS_PER_BEAT), "".join(
            ("2" if n.hold_rows else "1") if p in n.panels else "0" for p in range(4))) for n in notes]
        rv = chartstats.radar(chartstats.Chart(spec.name, str(meter), rows), a.bpm, a.duration)
        radar = ",".join(f"{rv[k]:.3f}" for k in ("stream", "voltage", "air", "freeze", "chaos"))
        body.append(
            f"//---------------dance-single - {spec.name}----------------\n"
            f"#NOTES:\n     dance-single:\n     stepgen:\n     {spec.name}:\n"
            f"     {meter}:\n     {radar}:\n{notes_to_measures(notes)};\n")
    path.write_text("\n".join(head) + "\n\n" + "\n".join(body), encoding="utf-8")


def write_stats(path: Path, sm: Path, a: Analysis, repeats, seed: int,
                sections=(), follows=None, ais=None, made_with=None) -> None:
    """Markdown snapshot next to the .sm: song analysis, repeated sections,
    per-chart stats, groove radar and density graphs (via chartstats)."""
    import chartstats
    measure = a.spb * BEATS_PER_MEASURE
    n_bars = int((a.music_end - a.t0) / measure) + 1
    loud = [a.mean(a.rms, a.t0 + m * measure, a.t0 + (m + 1) * measure) for m in range(n_bars)]
    top = max(loud) or 1.0
    intro = [f"Generated by stepgen, profile **{PROFILE_NAME}**, seed {seed}.", "",
             "## Song", "",
             f"- BPM **{a.bpm:g}**, offset {-a.t0:.3f} s, beat confidence {a.beat_confidence:.1f}",
             f"- Music from {a.music_start:.1f} s to {a.music_end:.1f} s, {n_bars} measures"]
    if repeats:
        intro += ["- Repeated sections (same music, steps reused):"]
        intro += [f"  - measures {t + 1}-{t + n} repeat {s + 1}-{s + n}" for t, s, n in repeats]
    else:
        intro += ["- No repeated sections found"]
    if ais:
        import ai_assist
        intro += [f"- AI assist ({ai_assist.MODEL.stem}): "
                  + ", ".join(f"{d} {k:g}" for d, k in ais.items())]
    if sections:
        diffs = list(follows or {})
        intro += ["", "## Sections", "",
                  "Follow melody: 0 = steps follow the beat, 1 = they follow the melody"
                  + (" (from separated stems)." if a.stems else " (the whole tonal mix; no stems)."), "",
                  "| # | Section | Measures | Intensity | Singing | " + " | ".join(f"Follow {d}" for d in diffs) + " |",
                  "|---|---|---|---|---|" + "---|" * len(diffs)]
        for i, sec in enumerate(sections):
            voc = f"{sec['vocals']:.2f}" if sec["vocals"] is not None else "-"
            intro.append(f"| {i + 1} | {sec['letter']} {sec['label']} | {sec['start'] + 1}-{sec['end']} | "
                         f"{sec['intensity']:.2f} | {voc} | "
                         + " | ".join(f"{follows[d][i]:.2f}" for d in diffs) + " |")
    if made_with:
        intro += made_with_md(made_with)
    path.write_text(chartstats.report(sm, a.duration, intro, [v / top for v in loud]),
                    encoding="utf-8")


def made_with_md(made_with: dict) -> list[str]:
    """The stats file's "Made with" section: what the meter targets changed."""
    out = ["", "## Made with", ""]
    order = sorted(made_with, key=SM_DIFFICULTIES.index)
    for d in order:
        r = made_with[d]
        if r.get("cut_from"):
            out.append(f"- **{d}**: cut from the {r['cut_from']} chart, with its own settings")
        elif not r["changed"]:
            out.append(f"- **{d}**: made with the settings as asked")
        else:
            out.append(f"- **{d}**: the meter target changed {len(r['changed'])} settings"
                       + "".join(f"; {r[k]}" for k in ("speed", "breathing") if r.get(k)))
    keys = sorted({k for d in order for k in made_with[d]["changed"]})
    if keys:
        fmt = lambda v: f"{v:.3g}" if isinstance(v, (int, float)) else str(v)
        out += ["", "Settings as asked → as used (blank: unchanged):", "",
                "| Setting | " + " | ".join(order) + " |", "|---|" + "---|" * len(order)]
        for k in keys:
            cells = [(lambda c: f"{fmt(c[0])} → {fmt(c[1])}" if c else "")(made_with[d]["changed"].get(k))
                     for d in order]
            out.append(f"| `{k}` | " + " | ".join(cells) + " |")
    return out


def write_clicks(path: Path, src: Path, charts) -> None:
    """Mix a tick on every Hard note into the song, to check sync by ear."""
    y = load_audio(src)
    tick = np.sin(2 * np.pi * 2000 * np.arange(int(0.03 * SR)) / SR) * \
        np.exp(-np.arange(int(0.03 * SR)) / (0.006 * SR))
    for n in charts[-1][1]:
        i = int(n.time * SR)
        if 0 <= i < len(y) - len(tick):
            y[i:i + len(tick)] += 0.5 * tick
    sf.write(path, y / max(1.0, np.abs(y).max()), SR)


# --------------------------------------------------------------------------

def to_ogg(src: Path, dst: Path) -> None:
    """Write the song as Ogg Vorbis (plays everywhere StepMania runs).

    Uses soundfile (no extra install) and falls back to ffmpeg for formats it
    can't decode. Written in blocks: some libsndfile builds crash on one huge
    Vorbis write."""
    if src.suffix.lower() == ".ogg":
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return
    try:
        data, sr = sf.read(str(src), always_2d=True, dtype="float32")
        with sf.SoundFile(str(dst), "w", samplerate=sr, channels=data.shape[1],
                          format="OGG", subtype="VORBIS") as f:
            for i in range(0, len(data), sr * 10):
                f.write(data[i:i + sr * 10])
    except Exception:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src),
                        "-vn", "-c:a", "libvorbis", "-q:a", "6", str(dst)], check=True)


def make_chart(a: Analysis, spec: DiffSpec, repeats, rng: random.Random) -> list[Note]:
    notes = refill(a, choose_holds(a, place_notes(a, spec, rng), spec), spec, rng)
    notes = cap_eighths(notes, spec)
    notes = sorted(limit_sixteenths(a, notes, spec), key=lambda n: n.row)
    notes = settle_rhythm(a, notes, spec, rng)
    notes = breathe(a, notes, spec, rng)
    arrange(a, notes, spec, rng)
    notes = apply_repeats(a, notes, repeats, spec, rng)
    notes = add_jump_holds(a, notes, spec, rng)
    notes = clear_jump_neighbors(notes)
    for _ in range(3):                 # a fix can expose the next pair
        notes = fix_quick_repeats(notes)
    return notes


JUMP_PAIRS = ((0, 3), (1, 2), (0, 1), (2, 3), (0, 2), (1, 3))   # most to least comfortable


def fix_quick_repeats(notes: list[Note]) -> list[Note]:
    """Last check that no arrow is hit twice in quick succession, counting
    jumps as well as single steps: [1000][1100] half a beat apart repeats
    Left just like [1000][1000] does. A quarter beat apart is never allowed;
    half a beat apart is allowed only between two single steps (the jacks
    setting's rare half-beat jacks). The later step moves to a free arrow,
    or a jump to a pair that shares nothing with its neighbours."""
    notes = sorted(notes, key=lambda n: n.row)
    holds = [n for n in notes if n.hold_rows]

    def held_at(row: int) -> set[int]:
        return {p for h in holds if h.row < row <= h.row + h.hold_rows for p in h.panels}

    drop: set[int] = set()

    for i in range(1, len(notes)):
        x, y = notes[i - 1], notes[i]
        gap = y.row - x.row
        if not set(x.panels) & set(y.panels):
            continue
        if not (gap <= 1 or (gap <= 2 and (len(x.panels) > 1 or len(y.panels) > 1))):
            continue
        nxt = notes[i + 1] if i + 1 < len(notes) and notes[i + 1].row - y.row <= 2 else None
        avoid = set(x.panels) | set(nxt.panels if nxt else ()) | held_at(y.row)
        if y.hold_rows or x.hold_rows:
            # a freeze keeps its arrows: move the other step instead
            if x.hold_rows and y.hold_rows:
                continue
            mv, fixed = (x, y) if y.hold_rows else (y, x)
            j = i - 1 if mv is x else i
            others = [notes[k] for k in (j - 1, j + 1) if 0 <= k < len(notes) and k != i - 1 + i - j
                      and abs(notes[k].row - mv.row) <= 2]
            bad = set(fixed.panels) | {p for o in others for p in o.panels} | held_at(mv.row)
            if len(mv.panels) == 1:
                free = [p for p in (1, 2, 0, 3) if p not in bad]
                if free:
                    mv.panels = [free[0]]
                else:
                    drop.add(id(mv))            # boxed in by jumps: let it go
            else:
                pairs = [pr for pr in JUMP_PAIRS if not set(pr) & bad]
                if pairs:
                    mv.panels = list(pairs[0])
                else:
                    drop.add(id(mv))
            continue
        if len(y.panels) == 1:
            free = [p for p in (1, 2, 0, 3) if p not in avoid] or \
                   [p for p in (1, 2, 0, 3) if p not in set(x.panels) | held_at(y.row)]
            if free:
                # stay on the side the step was meant for when possible
                side = [p for p in free if (p == 0) == (y.panels[0] == 0) and (p == 3) == (y.panels[0] == 3)]
                y.panels = [(side or free)[0]]
        else:
            pairs = [pr for pr in JUMP_PAIRS if not set(pr) & avoid] or \
                    [pr for pr in JUMP_PAIRS if not set(pr) & (set(x.panels) | held_at(y.row))]
            if pairs:
                y.panels = list(pairs[0])
    return [n for n in notes if id(n) not in drop]


def clear_jump_neighbors(notes: list[Note]) -> list[Note]:
    """No jump right next to a quarter-beat note: landing both feet and
    stepping again a quarter beat away is too much at any level. Inside a
    run of steps the jump becomes a single step so the run keeps flowing;
    elsewhere (a jump on its own, a freeze, a climax hit) the quarter-beat
    note goes and the jump stays."""
    notes = sorted(notes, key=lambda n: n.row)
    drop: set[int] = set()
    for i, nt in enumerate(notes):
        if len(nt.panels) < 2:
            continue
        prev = notes[i - 1] if i > 0 and nt.row - notes[i - 1].row <= 1 else None
        nxt = notes[i + 1] if i + 1 < len(notes) and notes[i + 1].row - nt.row <= 1 else None
        if prev is None and nxt is None:
            continue
        before = notes[i - 1] if i > 0 else None
        after = notes[i + 1] if i + 1 < len(notes) else None
        in_run = (before is not None and after is not None and not nt.hold_rows
                  and nt.row - before.row <= 2 and after.row - nt.row <= 2
                  and len(before.panels) == 1 and len(after.panels) == 1)
        if in_run:
            # keep the panel that steps away from both neighbours
            near = set(before.panels) | set(after.panels)
            keep = [p for p in nt.panels if p not in near] or [p for p in nt.panels if p not in after.panels]
            nt.panels = [(keep or nt.panels)[0]]
        else:
            for nb in (prev, nxt):
                if nb is not None and len(nb.panels) == 1 and not nb.hold_rows:
                    drop.add(id(nb))
    return [n for n in notes if id(n) not in drop]


def made_record(asked: DiffSpec, used: DiffSpec) -> dict:
    """What a chart was really made with: every setting as used, and the ones
    the meter target changed from what was asked (asked, used). Breathing
    room is called out on its own, since easing it is a choice, not a dial."""
    used_v = {f.name: getattr(used, f.name) for f in dataclasses.fields(used) if f.name != "name"}
    changed = {k: [getattr(asked, k), v] for k, v in used_v.items()
               if not (isinstance(v, float) and math.isclose(v, getattr(asked, k), abs_tol=1e-6))
               and v != getattr(asked, k)}
    rec = {"used": used_v, "changed": changed}
    if any(k in changed for k in ("run_breaks", "recovery")):
        bits = [f"{label} {getattr(asked, k):.2f} → {getattr(used, k):.2f}"
                for k, label in (("run_breaks", "run breaks"), ("recovery", "recovery"))
                if getattr(asked, k) > 0]
        rec["breathing"] = (f"breathing room eased to {round(100 * breathing_share(asked, used))}% "
                            f"({', '.join(bits)}) to get to meter {asked.target_meter:g}")
    raised = [f"{label} {getattr(asked, k):.2f} → {getattr(used, k):.2f}"
              for k, label in (("half_beats", "8ths"), ("quarter_beats", "quarter-beat bursts"),
                               ("flow_spice", "flow spice"))
              if getattr(used, k) > getattr(asked, k) + 1e-6]
    if raised:
        rec["speed"] = (f"Speed raised ({', '.join(raised)}) to get to meter {asked.target_meter:g}"
                        + ("; 16th streams added" if used.grid >= 4 > asked.grid else ""))
    return rec


def breathing_share(asked: DiffSpec, used: DiffSpec) -> float:
    k = "run_breaks" if asked.run_breaks > 0 else "recovery"
    return getattr(used, k) / getattr(asked, k) if getattr(asked, k) > 0 else 1.0


def aim_for_meter(a: Analysis, spec: DiffSpec, repeats, rng: random.Random):
    """Turn the intensity dial (with_intensity) until the chart rates
    spec.target_meter. Each try starts from the same random state, so the
    dial is the only thing that changes between them. In order, each only
    when what came before can't reach the number: the dial as far as
    Konami's charts go, then half the breathing room, then past Konami
    (for 9s and 10s)."""
    state = rng.getstate()
    goal = spec.target_meter
    s, notes, est = _dial(a, spec, repeats, rng, state, KONAMI_K)
    if est < goal - 0.5 and (spec.run_breaks > 0 or spec.recovery > 0):
        # pauses cost steps: rather than miss the difficulty asked for, ease
        # the breathing room (never all the way off: the pauses are the groove)
        calm = dataclasses.replace(spec, run_breaks=spec.run_breaks * 0.5, recovery=spec.recovery * 0.5)
        got = _dial(a, calm, repeats, rng, state, KONAMI_K)
        if abs(got[2] - goal) < abs(est - goal):
            s, notes, est = got
            print(f"  {spec.name}: less breathing room (50%) to reach meter {goal:g}")
    if est < goal - 0.5 and goal >= 9:
        # still short of a 9 or 10: past what Konami's charts do, if it really gets closer
        base = dataclasses.replace(spec, run_breaks=s.run_breaks, recovery=s.recovery)
        got = _dial(a, base, repeats, rng, state, TOP_K, lo=KONAMI_K)
        if abs(got[2] - goal) < abs(est - goal) - 0.25:
            s, notes, est = got
            print(f"  {spec.name}: longer 16th streams than Konami's to reach meter {goal:g}")
    if abs(est - goal) > 0.75:
        print(f"  {spec.name}: couldn't reach meter {goal:g} on this song (closest {est:.1f})")
    return s, notes


def _dial(a: Analysis, spec: DiffSpec, repeats, rng: random.Random, state, top: float,
          lo: float | None = None):
    """The dial setting in [-2, top] whose chart rates closest to the target."""
    span = max(a.music_end - a.music_start, 1.0)
    nps = {}

    def run(k):
        if k > 1.0 and "8ths" not in nps:
            rng.setstate(state)
            nps["8ths"] = len(make_chart(a, with_intensity(spec, 1.0), repeats, rng)) / span
        rng.setstate(state)
        s = with_intensity(spec, k, nps.get("8ths"))
        notes = make_chart(a, s, repeats, rng)
        return s, notes, estimate_meter(notes, a.spb)

    goal = spec.target_meter
    if lo is not None:                  # searching on from lo (which fell short) to top
        best = run(top)
        if best[2] < goal:
            return best
        lo_, hi = lo, top
    else:
        best = run(0.0)
        lo_, hi = (-2.0, 0.0) if best[2] > goal else (0.0, 1.0)
        if best[2] < goal:
            # each stage only when the one before can't reach the number
            for k0, k1 in ((1.0, 2.0), (2.0, top)):
                got = run(k0)
                if got[2] >= goal:
                    if abs(got[2] - goal) < abs(best[2] - goal):
                        best = got
                    break
                lo_, hi, best = k0, k1, got
            else:
                got = run(top)
                if abs(got[2] - goal) < abs(best[2] - goal):
                    best = got
                if got[2] < goal:
                    return best
    for _ in range(8):
        if abs(best[2] - goal) <= 0.25:
            break
        mid = (lo_ + hi) / 2
        got = run(mid)
        if abs(got[2] - goal) < abs(best[2] - goal):
            best = got
        lo_, hi = (mid, hi) if got[2] < goal else (lo_, mid)
    return best


KEEP_8THS = 0.4     # share of the harder chart's 8ths an easier one keeps (at half_beats 0.3)
STRONG8 = 2.5       # how the 8ths it keeps rank against the beats (a beat is 2)
KEEP_16THS = 0.1    # and of its 16ths, at most (at sixteenths 1)


def back_off(a: Analysis, top: list[Note], spec: DiffSpec, rng: random.Random) -> list[Note]:
    """An easier chart cut out of a harder one, so two players on different
    difficulties dance the same song: the same steps, minus the hard ones.

    The steps that matter most to the music stay (downbeats, big hits, the
    beat, holds); 16ths go first, then weak off-beat 8ths, then weaker
    beats, keeping the lower chart's own spacing (min_gap). Jumps on a beat
    stay, at most 2 in a row at quarter-note spacing (3 otherwise); the
    others become single steps. Arrows follow the harder chart's
    wherever the feet allow. The cut is tuned to target_meter when set,
    else to the chart's usual step count."""
    if not top:
        return []
    row_dt = a.spb / ROWS_PER_BEAT
    gap = max(1, int(round(spec.min_gap * ROWS_PER_BEAT)))
    # How much of each kind this level keeps. Konami's Mediums keep about
    # 40% of their Hard's 8ths and hardly any of its 16ths; half_beats and
    # sixteenths move that. The strongest of those 8ths rank above the
    # beats, so reaching the meter thins the weaker beats rather than
    # clearing the 8ths (the rest of the 8ths still go before any beat).
    # Levels whose spacing allows no 8ths (min_gap of a beat) are cut the
    # old way.
    eighths = [n for n in top if n.row % ROWS_PER_BEAT == 2]
    share8 = float(np.clip(KEEP_8THS * (0.5 + spec.half_beats / 0.6), 0.0, 0.6)) if gap <= 2 else 0.0
    strong8 = set(map(id, sorted(eighths, key=lambda n: -(n.strength + n.kick))[:int(len(eighths) * share8)]))
    n16 = sum(n.row % 2 == 1 for n in top)
    max16 = int(round(n16 * KEEP_16THS * spec.sixteenths)) if gap <= 2 else n16

    def weight(n: Note) -> float:
        w = n.strength + n.kick + 0.05
        w *= {0: 2.0, 2: 1.0, 1: 0.35, 3: 0.35}[n.row % ROWS_PER_BEAT]
        if id(n) in strong8:
            w *= STRONG8
        elif n.row % 2 == 1 and gap <= 2:
            w *= 0.3                                  # 16ths: the first to go
        if n.row % 16 == 0:
            w *= 1.6                                  # downbeats carry the song
        if len(n.panels) > 1 or n.stomp:
            w *= 1.4
        if n.hold_rows:
            w *= 3.0                                  # holds are easy and part of the song's shape
        return w

    order = sorted(top, key=weight, reverse=True)
    rank = {id(n): i for i, n in enumerate(order)}
    hold_share = sum(n.hold_rows > 0 for n in top) / len(top)

    def build(keep: int) -> list[Note]:
        kept: list[Note] = []
        rows: set[int] = set()
        spans: list[tuple[int, int]] = []
        k16 = 0
        for n in order:
            if len(kept) >= keep:
                break
            if n.row % 2 == 1 and k16 >= max16:
                continue
            if any((n.row + d) in rows for d in range(-gap + 1, gap)):
                continue
            if any(s0 < n.row <= e for s0, e in spans) and (spec.hold_free_foot == 0 or spec.min_gap >= 1):
                continue                              # no taps under a freeze at this level
            if n.hold_rows and any(n.row < r <= n.row + n.hold_rows for r in rows):
                continue
            kept.append(n)
            rows.add(n.row)
            k16 += n.row % 2 == 1
            if n.hold_rows:
                spans.append((n.row, n.row + n.hold_rows))
        kept.sort(key=lambda n: n.row)
        # freezes in the same share as the harder chart (they were kept first)
        holds = sorted((n for n in kept if n.hold_rows), key=lambda n: rank[id(n)])
        short = set(map(id, holds[int(round(len(kept) * hold_share)):]))
        # jumps stay where they land on a beat (quarter notes), at most a few
        # in a row; the rest become single steps
        in_row = 2 if spec.min_gap >= 1 else 3
        keep_jump: set[int] = set()
        run: list[Note] = []

        def close_run():
            # too many back to back: keep the strongest ones, spread out
            if len(run) > in_row:
                for n in sorted(run, key=lambda n: rank[id(n)])[in_row:]:
                    keep_jump.discard(id(n))
            run.clear()
        prev = None
        for n in kept:
            if len(n.panels) > 1 and n.row % ROWS_PER_BEAT == 0:
                if not (run and prev is run[-1]):
                    close_run()
                keep_jump.add(id(n))
                run.append(n)
            else:
                close_run()
            prev = n
        close_run()
        prefer = {}
        out = []
        for n in kept:
            c = dataclasses.replace(n, panels=list(n.panels))
            if id(n) in short:
                c.hold_rows = 0
            if len(n.panels) > 1 and id(n) not in keep_jump:
                c.panels = [n.panels[0]]
                c.stomp = False
            prefer[c.row] = list(c.panels)
            out.append(c)
        arrange(a, out, dataclasses.replace(spec, jump=0.0), random.Random(rng.random()), prefer=prefer)
        out = clear_jump_neighbors(out)
        for _ in range(3):
            out = fix_quick_repeats(out)
        return out

    span = max(a.music_end - a.music_start, 1.0)
    if spec.target_meter <= 0:
        return build(min(len(top), int(min(spec.density * span / a.spb, spec.max_nps * span))))
    lo, hi = 1, len(top)
    best = build(hi)
    if estimate_meter(best, a.spb) <= spec.target_meter:
        return best                                  # the harder chart is already easy enough
    for _ in range(12):
        if hi - lo <= 1:
            break
        mid = (lo + hi) // 2
        got = build(mid)
        e = estimate_meter(got, a.spb)
        if abs(e - spec.target_meter) < abs(estimate_meter(best, a.spb) - spec.target_meter):
            best = got
        lo, hi = (mid, hi) if e < spec.target_meter else (lo, mid)
    return best


COMPARE_DIR = ".compare"     # beat-only versions of melody-following charts


def song_onsets(path: Path) -> np.ndarray | None:
    """The song's hits as the groove meter hears them, the same way the
    editor does, so both show the same groove number."""
    try:
        import groove
        y, _ = librosa.load(str(path), sr=SR, mono=True)
        return groove.onset_env(y, SR)
    except Exception:
        return None


def groove_of(a: Analysis, notes: list[Note], onset: np.ndarray | None):
    """The groove meter (groove.py) for a chart."""
    import groove
    fps = SR / HOP
    rows = sorted((n.row / ROWS_PER_BEAT, tuple(sorted(n.panels))) for n in notes if n.panels)
    return groove.score(rows, lambda b: a.t0 + b * a.spb, onset, a.rms, int(round(fps)))


def song_lyrics(stem_dir: Path | None) -> list | None:
    """The song's words with their times, read off the vocals stem by the
    lyrics add-on (cached as lyrics.json beside the stems). None if there's
    no vocals stem or the add-on isn't installed."""
    if stem_dir is None:
        print("  (AI verse detection needs vocal separation: naming sections from the music)")
        return None
    out = stem_dir / "lyrics.json"
    if not out.is_file():
        import addons
        if not addons.installed("lyrics"):
            print("  (AI verse detection isn't installed: naming sections from the music)")
            return None
        print("progress: reading the lyrics", file=sys.stderr, flush=True)
        if not addons.transcribe(stem_dir / "vocals.ogg", out, log=print):
            return None
    try:
        words = json.loads(out.read_text(encoding="utf-8"))["words"]
    except (OSError, ValueError, KeyError):
        return None
    print(f"  lyrics: {len(words)} words read")
    return words


def generate(src: Path, out_dir: Path, title: str | None = None, artist: str = "",
             bpm: float | None = None, seed: int = 1, clicks: bool = False,
             specs: list[DiffSpec] | None = None, keep_format: bool = False,
             stems: bool = False, follow: dict[str, float] | None = None, backoff: bool = False,
             shorten: float = 0.0, keep_verses: bool = False, lyrics: bool = False,
             art: bool = True, art_online: bool = False) -> Path:
    title = title or src.stem
    # the StepMania song folder holds only the chart and the song; stats,
    # settings, stems and the rest sit one level up (layout.py)
    folder, song = song_dirs(out_dir, title)
    song.mkdir(parents=True, exist_ok=True)
    # the chart is timed against the exact file StepMania will play
    keep_format = keep_format and not shorten        # a shortened song is a new file
    music = src.name if keep_format else f"{title}.ogg"
    if keep_format:
        if src.resolve() != (song / music).resolve():
            shutil.copy2(src, song / music)
    else:
        to_ogg(src, song / music)
    # vocal separation, of the whole song: for following the singing, and
    # for reading the lyrics (AI verse detection)
    full_stems = None
    if stems or lyrics:
        import addons
        from stems import have_stems, stems_dir_for
        d = stems_dir_for(folder)
        made_for = d / "made-for.json"           # stems of a shortened cut (older versions) don't fit
        if have_stems(d) and (made_for.read_text().strip() if made_for.is_file() else "null") != "null":
            shutil.rmtree(d, ignore_errors=True)
        if not have_stems(d):
            print("progress: separating vocals", file=sys.stderr, flush=True)
            if not addons.installed():
                print("  (vocal separation isn't installed: following the full mix instead)")
            else:
                addons.separate(song / music, d, log=print)
                if have_stems(d):
                    made_for.write_text("null")
        full_stems = d if have_stems(d) else None
    words = None
    if lyrics:
        words = song_lyrics(full_stems)
    all_words = words
    cut = None
    if shorten:
        # the song cut down toward `shorten` seconds (shorten.py); the chart
        # is made for the shortened file, at the same tempo
        import shorten as shortener
        print(f"progress: analyzing {title} to shorten it", file=sys.stderr, flush=True)
        a0 = analyze(song / music, bpm, full_stems if stems else None)
        secs0 = find_sections(a0, find_repeats(a0))
        if words:
            import verses
            secs0 = verses.relabel(a0, secs0, words)
        with tempfile.TemporaryDirectory() as tmp:
            cut = shortener.shorten_file(song / music, Path(tmp) / "short.wav", a0, secs0, shorten, keep_verses)
            if cut is not None:
                to_ogg(Path(tmp) / "short.wav", song / music)
        if cut is None:
            print(f"  not shortened: already about {shortener.clock(shorten)}, or no place in it "
                  "where a cut would be clean")
        else:
            print(f"  {cut.describe()}")
            bpm = a0.bpm
            if stems and full_stems:
                # the stems cut the same way, rather than separating again
                full_stems = shortener.cut_stems(full_stems, folder / ".stems-cut", a0, cut)
            if words:
                words = cut.remap(words, a0)
    stem_dir = full_stems if stems else None
    print(f"progress: analyzing {title}", file=sys.stderr, flush=True)
    a = analyze(song / music, bpm, stem_dir)
    rng = random.Random(seed)
    onset = song_onsets(song / music)
    repeats = find_repeats(a)
    sections = find_sections(a, repeats)
    if words:
        import verses
        sections = verses.relabel(a, sections, words, all_words)
    charts, follows, beat_only, ais = [], {}, [], {}
    made_with: dict[str, dict] = {}    # what each chart was really made with (made_record)
    no_ai = []                         # the same charts without AI assist, to compare (temporary)
    specs = list(specs or load_patterns())
    audio = None                       # the song for the AI model, loaded once if a chart uses it
    if any(sp.ai_assist > 0 for sp in specs):
        import ai_assist
        if ai_assist.available():
            audio = load_audio(song / music)
        else:
            print(f"  AI assist is off: needs {ai_assist.MODEL.name} in models/ and onnxruntime installed")
    if backoff:
        # hardest first: the others are cut out of it
        specs.sort(key=lambda sp: -SM_DIFFICULTIES.index(sp.name))
    for spec in specs:
        print(f"progress: charting {spec.name}", file=sys.stderr, flush=True)
        if backoff and charts:
            fol = follow_for(a, sections, spec, follow)
            follows[spec.name] = [sec["follow"] for sec in sections]
            rng_at = rng.getstate()
            notes = back_off(a, charts[0][1], spec, rng)
            charts.append((spec, notes, meter_for(notes, a, spec)))
            made_with[spec.name] = made_record(spec, spec) | {"cut_from": charts[0][0].name}
            if audio is not None:
                same = random.Random()
                same.setstate(rng_at)
                n0 = back_off(a, no_ai[0][1], spec, same)
                no_ai.append((spec, n0, meter_for(n0, a, spec)))
            if spec.target_meter > 0 and abs(estimate_meter(notes, a.spb) - spec.target_meter) > 0.75:
                print(f"  {spec.name}: cut from {charts[0][0].name} rates "
                      f"{estimate_meter(notes, a.spb):.1f}, not {spec.target_meter:g}")
            continue
        fol = follow_for(a, sections, spec, follow)
        ac = with_follow(a, fol)
        asked = spec
        if audio is not None and spec.ai_assist > 0:
            print(f"progress: AI assist for {spec.name}", file=sys.stderr, flush=True)
            ac = with_ai(ac, ai_assist.ai_env(audio, a, ai_assist.meter_for(spec)), spec.ai_assist)
            ais[spec.name] = ac.ai
        follows[spec.name] = [sec["follow"] for sec in sections]
        state = rng.getstate()
        if spec.target_meter > 0:
            made, notes = aim_for_meter(ac, spec, repeats, rng)
        else:
            made, notes = spec, make_chart(ac, spec, repeats, rng)
        if spec.groove_tries > 1:
            # a few more versions; keep the one the groove meter likes best,
            # as long as it's as hard as the first
            first = estimate_meter(notes, a.spb)
            best = (groove_of(a, notes, onset).total, made, notes, state)
            for k in range(1, spec.groove_tries):
                print(f"progress: charting {spec.name} (groove try {k + 1} of {spec.groove_tries})",
                      file=sys.stderr, flush=True)
                alt = random.Random(f"{seed}-{spec.name}-{k}")
                st = alt.getstate()
                if spec.target_meter > 0:
                    import contextlib, io
                    with contextlib.redirect_stdout(io.StringIO()):
                        m2, n2 = aim_for_meter(ac, spec, repeats, alt)
                else:
                    m2, n2 = spec, make_chart(ac, spec, repeats, alt)
                if abs(estimate_meter(n2, a.spb) - first) > 0.4:
                    continue
                g = groove_of(a, n2, onset).total
                if g > best[0]:
                    best = (g, m2, n2, st)
            _, made, notes, state = best
        spec = made
        charts.append((spec, notes, meter_for(notes, a, spec)))
        made_with[spec.name] = made_record(asked, made)
        if audio is not None:
            if spec.name in ais:
                # the same chart without AI assist: same settings, same dice
                import contextlib, io
                same = random.Random()
                same.setstate(state)
                plain_ac = with_follow(a, fol)
                if asked.target_meter > 0:
                    with contextlib.redirect_stdout(io.StringIO()):
                        _, n0 = aim_for_meter(plain_ac, asked, repeats, same)
                else:
                    n0 = make_chart(plain_ac, asked, repeats, same)
                no_ai.append((asked, n0, meter_for(n0, a, asked)))
            else:
                no_ai.append(charts[-1])
        if fol.any():
            # the same chart without following the melody, for the editor's
            # side-by-side compare: same settings, same dice
            same = random.Random()
            same.setstate(state)
            plain = make_chart(a, spec, repeats, same)
            beat_only.append((spec, plain, meter_for(plain, a, spec)))

    charts.sort(key=lambda c: SM_DIFFICULTIES.index(c[0].name))
    sm = song / f"{title}.sm"
    for old in (folder / f"{title}.sm", folder / music):
        # the same song made before the layout change: its copies move into the song folder
        if old.is_file() and old.resolve() != src.resolve() and (
                old.suffix != ".sm" or "#CREDIT:stepgen" in old.read_text(encoding="utf-8", errors="replace")[:4000]):
            old.unlink()
    # banner, background and jacket (artwork.py): the song's own cover art,
    # looked up online only when asked
    pics, art_from = {}, {"from": None}
    if art:
        import artwork
        try:
            pics, art_from = artwork.make(src, song, title, artist, art_online)
        except Exception as e:                   # never worth losing the chart over
            print(f"  artwork: skipped ({e})")
    write_sm(sm, title, artist, music, a, charts, pics)
    # kept in a subfolder so StepMania doesn't list it as a second song
    compare = folder / COMPARE_DIR / f"{title}.sm"
    if beat_only:
        compare.parent.mkdir(exist_ok=True)
        write_sm(compare, title, artist, f"../{title}/{music}", a, beat_only)
    elif compare.is_file():
        compare.unlink()
    if no_ai:
        # temporary: the whole song again without AI assist, as its own song
        # so both can be played and compared in StepMania
        t0 = f"{title} (no AI)"
        _, song0 = song_dirs(out_dir, t0)
        song0.mkdir(parents=True, exist_ok=True)
        if not (song0 / music).is_file() or (song0 / music).stat().st_size != (song / music).stat().st_size:
            shutil.copy2(song / music, song0 / music)
        for f in pics.values():
            shutil.copy2(song / f, song0 / f)
        no_ai.sort(key=lambda c: SM_DIFFICULTIES.index(c[0].name))
        write_sm(song0 / f"{t0}.sm", t0, artist, music, a, no_ai, pics)
        print("  without AI: " + ", ".join(f"{sp.name} meter {m}  {len(n)} notes" for sp, n, m in no_ai))
        print(f"  -> {song0 / f'{t0}.sm'}")
    if clicks:
        write_clicks(folder / f"{title}.clicks.wav", song / music, charts)
    write_stats(folder / f"{title}.stats.md", sm, a, repeats, seed, sections, follows, ais, made_with)
    # how this chart was made, so llm_review.py can suggest an exact re-run
    ai_info = {"ai_assist": ais, "ai_model": ai_assist.MODEL.stem} if ais else {}
    (folder / f"{title}.stepgen.json").write_text(json.dumps({
        "source": str(src.resolve()), "title": title, "artist": artist, "out": str(out_dir.resolve()),
        "profile": PROFILE_NAME, "seed": seed, "bpm": bpm, "set": RUN_SETS, "easy": RUN_EASY,
        "keep_format": keep_format, "stems": stems, "follow": follow or {}, "backoff": backoff,
        "shorten": {"target": shorten, "keep_verses": keep_verses, "kept_bars": cut.keep,
                    "summary": cut.describe()} if cut
        else ({"target": shorten, "keep_verses": keep_verses, "kept_bars": None} if shorten else None),
        "lyrics": bool(words), "art": {"on": art, "online": art_online} | art_from,
        "sections": [{k: sec[k] for k in ("start", "end", "letter", "label", "intensity", "vocals", "lyrics")
                      if k in sec}
                     | {"follow": {d: f[i] for d, f in follows.items()}} for i, sec in enumerate(sections)]}
        | ai_info | {"made_with": made_with}, indent=2))

    span = a.music_end - a.music_start
    print(f"{title}: {a.bpm:g} BPM, offset {-a.t0:.3f}s, beat confidence {a.beat_confidence:.2f}"
          f"{'  (low: consider --bpm)' if a.beat_confidence < 1.3 else ''}")
    for spec, notes, meter in charts:
        jumps = sum(len(n.panels) > 1 for n in notes)
        holds = sum(n.hold_rows > 0 for n in notes)
        try:
            gv = f"  groove {groove_of(a, notes, onset).total:.0f}" + (
                f" (best of {spec.groove_tries})" if spec.groove_tries > 1 else "")
        except Exception:
            gv = ""
        print(f"  {spec.name:<6} meter {meter:>2}  {len(notes):>4} notes  "
              f"{len(notes) / span:4.2f} nps  {jumps} jumps  {holds} holds{gv}")
    for t, s, length in repeats:
        print(f"  repeat: measures {t + 1}-{t + length} reuse {s + 1}-{s + length}")
    for i, sec in enumerate(sections):
        fol = " ".join(f"{d[0]}{f[i]:.1f}" for d, f in follows.items())
        voc = f"  singing {sec['vocals']:.1f}" if sec["vocals"] is not None else ""
        print(f"  section {i + 1} {sec['letter']} {sec['label']:<9} measures {sec['start'] + 1}-{sec['end']}"
              f"  follow melody {fol}{voc}" + (f'  "{sec["lyrics"]}"' if sec.get("lyrics") else ""))
    print(f"  -> {sm}")
    return sm


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path, nargs="*")
    ap.add_argument("--out", type=Path, default=Path("songs"))
    ap.add_argument("--title")
    ap.add_argument("--artist", default="")
    ap.add_argument("--bpm", type=float, help="force the BPM if detection is off")
    ap.add_argument("--seed", type=int, default=1, help="change for a different arrow layout")
    ap.add_argument("--clicks", action="store_true", help="also write a .clicks.wav sync check")
    ap.add_argument("--profile", "--patterns", dest="profile", default=None,
                    help="play-style profile: a name from profiles/ (e.g. flow) or any "
                         ".toml path. Default: patterns.toml next to this script")
    ap.add_argument("--keep-format", action="store_true",
                    help="copy the song as-is instead of converting it to .ogg")
    ap.add_argument("--list-profiles", action="store_true", help="show the profiles and exit")
    ap.add_argument("--set", action="append", default=[], metavar="DIFF.PARAM=VALUE",
                    help="override one setting, e.g. --set Hard.jump=0.8 (repeatable)")
    ap.add_argument("--easy", action="append", default=[], metavar="SLIDER=0..1",
                    help="Easy-mode slider, 0.5 = profile as written: "
                         + ", ".join(EASY_SLIDERS) + " (repeatable)")
    ap.add_argument("--stems", action="store_true",
                    help="separate vocals/drums/bass/other first (needs the vocal separation add-on) "
                         "so melody-following sections follow the singing")
    ap.add_argument("--follow", action="append", default=[], metavar="SECTION=0..1",
                    help="how much a section follows the melody instead of the beat: by number "
                         "(3=0.9), letter (B=0.8), name (chorus=1) or all=0.5 (repeatable)")
    ap.add_argument("--backoff", action="store_true",
                    help="make the hardest chart first and cut the easier ones out of it, so "
                         "players on different difficulties dance the same song")
    ap.add_argument("--shorten", type=float, default=0.0, metavar="SECONDS",
                    help="try to shorten the song to about this long (e.g. 90 or 120) by jumping "
                         "past repeated parts where the music on both sides is alike; the start and "
                         "ending stay. Left as it is when there's no clean place to cut. Writes "
                         "'<title> (short)'")
    ap.add_argument("--keep-verses", action="store_true",
                    help="with --shorten: only skip choruses, intro/outro and breakdowns, never a verse")
    ap.add_argument("--lyrics", action="store_true",
                    help="AI verse detection: read the lyrics off the separated vocals to tell the "
                         "chorus (the same words again) from the verses (needs the vocal separation "
                         "and lyrics add-ons)")
    ap.add_argument("--target", action="append", default=[], metavar="DIFF=METER",
                    help="aim a chart at a difficulty number, e.g. --target Hard=9 (repeatable)")
    ap.add_argument("--ai", type=float, default=0.0, metavar="0..1",
                    help="AI assist on every difficulty: how much the model trained on hand-made "
                         "charts decides where steps go (needs models/step_placement_v1.onnx)")
    ap.add_argument("--device", choices=("auto", "cpu"), default=None,
                    help="where vocal separation, AI verse detection and AI assist run: auto = "
                         "the GPU when there is one (NVIDIA or Apple Silicon), else the CPU "
                         "(the default; see accel.py)")
    ap.add_argument("--no-art", action="store_true",
                    help="leave the banner, background and jacket empty (by default they're made "
                         "from an image beside the song or the cover art in its tags)")
    ap.add_argument("--art-online", action="store_true",
                    help="when the song has no cover art, look it up by title and artist on "
                         "musicbrainz.org / coverartarchive.org, else itunes.apple.com (each "
                         "address is printed as it's fetched)")
    args = ap.parse_args(argv)
    if args.device:
        os.environ["STEPGEN_DEVICE"] = args.device       # the add-ons' own Python inherits it
    if args.list_profiles:
        for f in sorted(PROFILES_DIR.glob("*.toml")):
            first = next((l[1:].strip() for l in f.read_text().splitlines() if l.startswith("#")), "")
            print(f"  {f.stem:<12} {first}")
        return 0
    if not args.audio:
        ap.error("give at least one audio file")
    profile = resolve_profile(args.profile) if args.profile else DEFAULT_PATTERNS
    sets = list(args.set)
    for t in args.target:                         # --target Hard=9 is --set Hard.target_meter=9
        diff, val = t.split("=", 1)
        sets.append(f"{diff}.target_meter={val}")
    easy = {k: float(v) for k, v in (e.split("=", 1) for e in args.easy)}
    specs = load_patterns(profile, sets, easy)
    if args.ai > 0:
        # like a --set on every difficulty, but one given with --set still wins
        own = {s.split("=", 1)[0].split(".", 1)[0] for s in sets if s.split("=", 1)[0].endswith(".ai_assist")}
        for spec in specs:
            if spec.name not in own:
                spec.ai_assist = float(np.clip(args.ai, 0, 1))
        sets = sets + [f"{sp.name}.ai_assist={args.ai:g}" for sp in specs if sp.name not in own]
    global PROFILE_NAME, RUN_SETS, RUN_EASY
    PROFILE_NAME = profile.stem if profile != DEFAULT_PATTERNS else "patterns"
    RUN_SETS = sets
    RUN_EASY = easy
    for src in args.audio:
        title = args.title if len(args.audio) == 1 else None
        if args.shorten and not title:
            title = f"{src.stem} (short)"
        generate(src, args.out, title,
                 args.artist, args.bpm, args.seed, args.clicks, specs, args.keep_format,
                 args.stems, {k.strip(): float(v) for k, v in (f.split("=", 1) for f in args.follow)},
                 args.backoff, args.shorten, args.keep_verses, args.lyrics,
                 not args.no_art, args.art_online)
    return 0


if __name__ == "__main__":
    sys.exit(main())
