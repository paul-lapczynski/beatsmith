"""Groove meter: how much a chart lets you groove, measure by measure.

Five things, each 0..1 per measure, averaged into a score out of 100:

  locked     steps land on the song's hits, not just on the grid
  pattern    the bar's rhythm comes back in the bars around it, so your
             body learns it (small variations still count a lot)
  breathing  runs end and you get a moment; a run through the measure of
             10 steps or fewer is fine, 30 or more scores 0
  footing    the steps alternate feet without crossing over, double
             stepping or fast jacks
  effort     the chart is busy where the song is loud and calm where it's
             quiet

Only needs the steps and the song's audio, so it works on any chart (the
editor, BeatSmith's own output, Konami's). The weights are a first guess:
marking where you actually groove in play tests (hold G) is how they get
checked.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PARTS = ("locked", "pattern", "breathing", "footing", "effort")
WEIGHTS = {"locked": 1.0, "pattern": 1.0, "breathing": 1.0, "footing": 1.0, "effort": 1.0}
HZ = 100                       # onset envelope frames per second


def onset_env(data: np.ndarray, sr: int) -> np.ndarray:
    """Spectral flux of the song at HZ frames/s, 0..1: high where something
    hits (a drum, a note starting), low in between."""
    mono = data.mean(1) if data.ndim == 2 else data
    hop, win = max(1, sr // HZ), 2048
    n = max(0, (len(mono) - win) // hop)
    if n < 4:
        return np.zeros(1)
    flux = np.zeros(n + 1, np.float32)
    window = np.hanning(win).astype(np.float32)
    prev = None
    for i0 in range(0, n, 2048):                # in chunks, to keep memory small
        idx = np.arange(i0, min(n, i0 + 2048))[:, None] * hop + np.arange(win)
        mag = np.log1p(10 * np.abs(np.fft.rfft(mono[idx] * window, axis=1)[:, :400]))
        d = np.diff(mag, axis=0, prepend=mag[:1] if prev is None else prev[None])
        flux[i0 + 1:i0 + 1 + len(mag)] = np.maximum(d, 0).sum(1)
        prev = mag[-1]
    flux -= np.convolve(flux, np.ones(50) / 50, "same")       # local mean out: hits stand up
    flux = np.maximum(flux, 0)
    return flux / (np.percentile(flux, 99.5) + 1e-9)


@dataclass
class Groove:
    total: float                       # 0..100 for the whole chart
    measures: np.ndarray               # 0..100 per measure (nan where there are no steps)
    parts: dict[str, np.ndarray]       # each part 0..1 per measure (nan where it doesn't apply)

    def explain(self, m: int) -> str:
        if not 0 <= m < len(self.measures) or np.isnan(self.measures[m]):
            return f"Measure {m + 1}: no steps"
        bits = ", ".join(f"{p} {round(100 * self.parts[p][m])}" for p in PARTS
                         if not np.isnan(self.parts[p][m]))
        return f"Measure {m + 1}: groove {round(self.measures[m])} ({bits})"


def score(steps: list[tuple[float, tuple[int, ...]]], time_at, onset: np.ndarray | None,
          loud: np.ndarray | None = None, loud_hz: int = 200) -> Groove:
    """steps: (beat, panels) per row, sorted; time_at: beat -> seconds.
    onset from onset_env (None skips "locked"); loud is any loudness envelope
    at loud_hz frames/s (None skips "effort")."""
    if not steps:
        return Groove(0.0, np.zeros(0), {p: np.zeros(0) for p in PARTS})
    beats = np.array([b for b, _ in steps])
    n_meas = int(beats[-1] // 4) + 1
    meas = (beats // 4).astype(int)
    nan = lambda: np.full(n_meas, np.nan)
    parts = {p: nan() for p in PARTS}

    # locked: share of steps on a real hit (the onset near the step beats
    # what the song has on most 8th-note grid points)
    if onset is not None and len(onset) > 4:
        def peak(t):
            i = int(round(t * HZ))
            return float(onset[max(0, i - 4):i + 5].max()) if 0 <= i < len(onset) else 0.0
        grid = [peak(time_at(b)) for b in np.arange(0, beats[-1] + 1, 0.5)]
        thr = float(np.percentile(grid, 60)) if grid else 0.0
        hit = np.array([peak(time_at(b)) > thr for b in beats], float)
        for m in range(n_meas):
            sel = meas == m
            if sel.any():
                # Konami's charts land about 2 in 3 steps on a clear hit (the
                # rest follow the beat through quieter spots): that's full marks
                parts["locked"][m] = min(1.0, hit[sel].mean() / 0.65)

    # pattern: the bar's rhythm (16th slots) against the bars around it
    rhythm = [set() for _ in range(n_meas)]
    for b in beats:
        rhythm[int(b // 4)].add(int(round((b % 4) * 4)))
    for m in range(n_meas):
        if not rhythm[m]:
            continue
        sims = [len(rhythm[m] & rhythm[k]) / len(rhythm[m] | rhythm[k])
                for k in (m - 4, m - 2, m - 1, m + 1, m + 2, m + 4) if 0 <= k < n_meas and rhythm[k]]
        parts["pattern"][m] = max(sims) if sims else 0.5

    # breathing: the longest run (steps half a beat apart or closer) through each measure
    run_len = np.ones(len(beats), int)
    i = 0
    while i < len(beats):
        j = i
        while j + 1 < len(beats) and beats[j + 1] - beats[j] <= 0.5 + 1e-6:
            j += 1
        run_len[i:j + 1] = j - i + 1
        i = j + 1
    for m in range(n_meas):
        sel = meas == m
        if sel.any():
            parts["breathing"][m] = float(np.clip(1 - (run_len[sel].max() - 10) / 20, 0, 1))

    # footing: alternate feet; Left is the left foot's, Right the right's.
    # A step that forces a crossover, a double step or a fast jack is awkward
    awk = np.zeros(len(beats))
    foot, last_panel, last_beat = None, None, -99.0
    for k, (b, panels) in enumerate(steps):
        gap = b - last_beat
        if len(panels) != 1 or gap >= 1.0:
            # a jump or a rest: both feet free again
            foot = None if len(panels) != 1 else ("L" if panels[0] == 0 else "R" if panels[0] == 3 else None)
            last_panel, last_beat = (panels[0] if len(panels) == 1 else None), b
            continue
        p = panels[0]
        if p == last_panel and gap <= 0.5:
            awk[k] = 0.5 if gap >= 0.5 else 1.0              # jack: ok-ish on 8ths, bad faster
            last_beat = b
            continue
        nxt = {"L": "R", "R": "L", None: None}[foot]
        if nxt is None:
            nxt = "L" if p == 0 else "R" if p == 3 else None
        elif (nxt == "L" and p == 3) or (nxt == "R" and p == 0):
            awk[k] = 1.0                                     # crossover or double step
            nxt = "R" if p == 3 else "L"                     # the dancer recovers on the next one
        foot, last_panel, last_beat = nxt, p, b
    for m in range(n_meas):
        sel = meas == m
        if sel.sum() >= 2:
            parts["footing"][m] = float(np.clip(1 - 2 * awk[sel].mean(), 0, 1))

    # effort: busy where loud, calm where quiet (ranks across the song)
    if loud is not None and len(loud) > 1:
        counts = np.bincount(meas, minlength=n_meas).astype(float)
        def level(m):
            seg = loud[max(0, int(time_at(4 * m) * loud_hz)):max(0, int(time_at(4 * m + 4) * loud_hz))]
            return float(seg.mean()) if len(seg) else 0.0
        lv = np.array([level(m) for m in range(n_meas)])
        has = counts > 0
        if has.sum() >= 4:
            rank = lambda x: (np.argsort(np.argsort(x)) / max(len(x) - 1, 1))
            rd, rl = rank(counts[has]), rank(lv[has])
            parts["effort"][has] = np.clip(1 - 1.5 * np.abs(rd - rl), 0, 1)

    stack = np.array([parts[p] * WEIGHTS[p] for p in PARTS])
    wsum = np.array([np.where(np.isnan(parts[p]), 0, WEIGHTS[p]) for p in PARTS]).sum(0)
    with np.errstate(invalid="ignore"):
        per = 100 * np.nansum(stack, 0) / np.where(wsum > 0, wsum, np.nan)
    has_steps = np.bincount(meas, minlength=n_meas) > 0
    per[~has_steps] = np.nan
    # the whole chart: each measure counts by how many steps it has
    w = np.bincount(meas, minlength=n_meas)[has_steps]
    total = float(np.average(per[has_steps], weights=w)) if w.sum() else 0.0
    return Groove(total, per, parts)
