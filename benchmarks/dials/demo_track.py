"""Make the demo track the docs and preview use: an 85-second, 124 BPM
dance track synthesized from scratch (drums, bass, pad and a lead melody),
so it can ship with the repo. It has what the controls react to: a quiet
intro, a verse, a build-up into a loud chorus, a breakdown, the chorus
again (a repeat) and an outro.

    python benchmarks/dials/demo_track.py      # -> examples/BeatSmith Demo/beatsmith-demo.ogg
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

SR = 44100
BPM = 124
BEAT = 60 / BPM
BAR = 4 * BEAT
S16 = BEAT / 4
OUT = Path(__file__).resolve().parents[2] / "examples" / "BeatSmith Demo" / "beatsmith-demo.ogg"
rng = np.random.default_rng(124)


def midi(n: str) -> float:
    names = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    semi = names[n[0]] + (1 if "#" in n else 0)
    octave = int(n[-1])
    return 440 * 2 ** ((semi + 12 * (octave + 1) - 69) / 12)


def env(n, a=0.005, d=0.1, s=0.0, r=0.05, length=None):
    t = np.arange(n) / SR
    e = np.where(t < a, t / a, s + (1 - s) * np.exp(-(t - a) / d))
    if length:
        rel = t > length
        e[rel] *= np.exp(-(t[rel] - length) / r)
    return e


def lp(x, hz, order=2):
    b, a = butter(order, hz / (SR / 2), "low")
    return lfilter(b, a, x)


def hp(x, hz, order=2):
    b, a = butter(order, hz / (SR / 2), "high")
    return lfilter(b, a, x)


def bp(x, lo, hi):
    b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], "band")
    return lfilter(b, a, x)


def kick():
    n = int(0.4 * SR)
    t = np.arange(n) / SR
    f = 45 + 90 * np.exp(-t / 0.035)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.18)


def snare():
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    noise = bp(rng.standard_normal(n), 1200, 7000) * env(n, 0.001, 0.07)
    tone = np.sin(2 * np.pi * 185 * t) * env(n, 0.001, 0.05)
    return 0.7 * noise + 0.5 * tone


def hat(open_=False):
    n = int((0.25 if open_ else 0.06) * SR)
    return hp(rng.standard_normal(n), 7000) * env(n, 0.001, 0.08 if open_ else 0.018) * 0.5


def saw(freq, n, detune=0.0):
    t = np.arange(n) / SR
    ph = (freq * (1 + detune)) * t
    return 2 * (ph - np.floor(ph + 0.5))


def tone(freq, length, kind="lead"):
    n = int((length + 0.15) * SR)
    t = np.arange(n) / SR
    if kind == "lead":
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.2, 0, 1)
        ph = np.cumsum(freq * vib) / SR
        x = 0.6 * np.sign(np.sin(2 * np.pi * ph)) + 0.4 * (2 * (ph - np.floor(ph + 0.5)))
        x = lp(x, 3200)
        return x * env(n, 0.01, 0.4, 0.55, 0.06, length)
    if kind == "bass":
        x = lp(saw(freq, n) + 0.5 * np.sin(2 * np.pi * freq / 2 * t), 700)
        return x * env(n, 0.004, 0.12, 0.5, 0.03, length)
    # pad
    x = sum(saw(freq, n, d) for d in (-0.006, 0.0, 0.007)) / 3
    return lp(x, 1500) * env(n, 0.35, 1.5, 0.8, 0.3, length)


CHORDS = [("A2", "A3", "C4", "E4"), ("F2", "F3", "A3", "C4"), ("C3", "G3", "C4", "E4"), ("G2", "G3", "B3", "D4")]
# melodies: (16th within the 2 bars, note, length in 16ths)
VERSE = [(0, "E4", 6), (8, "D4", 2), (10, "C4", 2), (12, "A3", 4), (16, "C4", 4), (22, "D4", 2), (24, "E4", 8)]
CHORUS = [(0, "A4", 2), (3, "C5", 1), (4, "E5", 2), (6, "D5", 2), (10, "C5", 2), (12, "A4", 3), (15, "G4", 1),
          (16, "F4", 2), (18, "A4", 2), (20, "C5", 2), (23, "D5", 1), (24, "E5", 4), (28, "G5", 2), (30, "E5", 2)]
BREAK = [(0, "E5", 8), (8, "D5", 4), (12, "C5", 4), (16, "A4", 12), (28, "G4", 4)]

# bar -> section
PLAN = ["intro"] * 8 + ["verse"] * 8 + ["build"] * 4 + ["chorus"] * 8 + ["break"] * 4 + ["chorus"] * 8 + ["outro"] * 4


def render() -> np.ndarray:
    lead_in = 0.5
    total = lead_in + len(PLAN) * BAR + 2.0
    mix = {k: np.zeros(int(total * SR) + SR) for k in ("drums", "bass", "pad", "lead", "fx")}

    def put(track, t, x, gain=1.0):
        i = int((lead_in + t) * SR)
        mix[track][i:i + len(x)] += gain * x[:len(mix[track]) - i]

    K, SN = kick(), snare()
    for b, sec in enumerate(PLAN):
        t0 = b * BAR
        chord = CHORDS[b % 4]
        loud = {"intro": 0.35, "verse": 0.5, "build": 0.8, "chorus": 1.0, "break": 0.3, "outro": 0.45}[sec]
        # pad: every section, softer in the loud ones
        for note in chord[1:]:
            put("pad", t0, tone(midi(note), BAR - 0.05, "pad"), 0.10 if sec in ("chorus", "verse") else 0.16)
        # drums
        if sec in ("chorus", "outro") or (sec == "build" and b != PLAN.index("build") + 3):
            for k in range(4):
                put("drums", t0 + k * BEAT, K, 0.95 * loud)
        if sec == "verse":                            # half-time: kick on 1 and the "and" of 2, snare on 3
            for k in (0, 6):
                put("drums", t0 + k * BEAT / 2, K, 0.8 * loud)
            put("drums", t0 + 2 * BEAT, SN, 0.5 * loud)
        if sec == "chorus":
            for k in (1, 3):
                put("drums", t0 + k * BEAT, SN, 0.7)
                put("drums", t0 + k * BEAT + 0.012, SN, 0.35)       # a clap layer
        if sec != "break":
            for k in range(8):
                put("drums", t0 + k * BEAT / 2, hat(open_=(sec == "chorus" and k % 2 == 1)),
                    (0.25 if k % 2 else 0.15) * loud)
        if sec == "chorus":
            for k in (14, 15):                        # a 16th pickup on the hats
                put("drums", t0 + k * S16, hat(), 0.12)
        if sec == "build":
            i = PLAN.index("build")
            div = [4, 8, 16, 16][b - i]               # snare roll speeds up
            for k in range(div):
                put("drums", t0 + k * BAR / div, SN, 0.25 + 0.5 * (b - i + k / div) / 4)
            n = int(BAR * SR)
            sweep = hp(rng.standard_normal(n), 2000 + 2000 * (b - i)) * np.linspace(0.02, 0.12, n) * (b - i + 1) / 2
            put("fx", t0, sweep)
        if sec == "chorus" and PLAN[b - 1] != "chorus":
            put("fx", t0, hp(rng.standard_normal(int(1.5 * SR)), 4000) * env(int(1.5 * SR), 0.001, 0.5) * 0.3)
        # bass on the off-beats in the verse, driving 8ths in the chorus
        if sec in ("verse", "chorus", "build"):
            root = midi(chord[0])
            steps = range(1, 8, 2) if sec == "verse" else range(8)
            for k in steps:
                put("bass", t0 + k * BEAT / 2, tone(root * (2 if sec == "chorus" and k % 4 == 3 else 1),
                                                   BEAT / 2 - 0.03, "bass"), 0.45 * loud)
        # melody, two bars at a time
        mel = {"verse": VERSE, "chorus": CHORUS, "break": BREAK}.get(sec)
        start = next(i for i in range(b, -1, -1) if i == 0 or PLAN[i - 1] != sec)
        if mel and (b - start) % 2 == 0:
            for pos, note, ln in mel:
                put("lead", t0 + pos * S16, tone(midi(note), ln * S16 - 0.02, "lead"),
                    0.22 if sec != "break" else 0.18)
    out = (mix["drums"] * 0.9 + mix["bass"] + mix["pad"] + mix["lead"] + mix["fx"])
    # outro fades
    n_out = int(4 * BAR * SR)
    end = int((lead_in + len(PLAN) * BAR) * SR)
    out[end - n_out:end] *= np.linspace(1, 0.2, n_out)
    out[end:] *= np.exp(-np.arange(len(out) - end) / (0.5 * SR))
    out = np.tanh(1.4 * out / (np.percentile(np.abs(out), 99.9) + 1e-9)) * 0.85
    stereo = np.stack([out, out], 1)
    return stereo[: int(total * SR)]


def main():
    y = render()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "demo.wav"
        sf.write(wav, y, SR)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "5",
                        "-metadata", "title=BeatSmith Demo", "-metadata", "artist=BeatSmith (synthesized)", str(OUT)],
                       check=True)
    print(f"wrote {OUT} ({len(y) / SR:.1f} s)")


if __name__ == "__main__":
    main()
