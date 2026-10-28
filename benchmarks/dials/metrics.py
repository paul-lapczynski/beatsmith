"""The fingerprint: the same measurements for every chart, from its notes
and the song's analysis. Works on BeatSmith's own charts and, through
from_rows(), on any chart read from a .sm (find_preset.py)."""
from __future__ import annotations

import math

import numpy as np

import harness
from harness import stepgen

R = stepgen.ROWS_PER_BEAT          # rows per beat (4: 16th-note rows)
BAR = 4 * R

# measurement -> plain description, used by the report and find-preset
DESCRIBE = {
    "steps": "steps (rows with an arrow)",
    "nps": "steps per second",
    "meter": "BeatSmith's difficulty estimate",
    "jump_pct": "jumps per 100 steps",
    "jump_holds": "jump freezes",
    "jump_cluster": "share of jumps in the first 2 bars of a section",
    "stomps": "stomps (quarter-note jumps from breathing)",
    "beat_pct": "share of steps on the beat (%)",
    "half_pct": "share of steps on half-beats, 8ths (%)",
    "quarter_pct": "share of steps on quarter-beats, 16ths (%)",
    "stream": "longest run of 8th notes (steps)",
    "hold_pct": "freezes per 100 steps",
    "held_beats": "beats spent holding, per minute",
    "under_holds": "taps under freezes, per 100 steps",
    "run_mean": "average length of a run (steps half a beat apart or closer)",
    "long_runs": "runs longer than 8 steps, per minute",
    "rests": "rests of 2 beats or more, per minute",
    "jack_pct": "jacks (same arrow again) per 100 steps",
    "lr_pct": "Left<->Right or Down<->Up moves per 100 steps",
    "walk_pct": "walk-downs/ups across all 4 arrows per 100 steps",
    "arrow_entropy": "arrow variety: how unpredictable the next arrow is (0..1)",
    "energy_corr": "steps per bar follow the song's loudness (rank correlation)",
    "energy_contrast": "steps in the loudest quarter of bars / quietest quarter",
    "build_climb": "steps climb through build-ups (rank correlation)",
    "rep_rhythm": "repeated sections: same rhythm (%)",
    "rep_arrows": "repeated sections: same arrows (%)",
    "groove": "groove meter (0..100)",
    "g_locked": "groove: steps on the song's hits",
    "g_pattern": "groove: rhythm comes back bar to bar",
    "g_breathing": "groove: runs end, you get a moment",
    "g_footing": "groove: comfortable feet",
    "g_effort": "groove: busy where loud",
    "melody_lock": "steps on melody note starts (percentile, 50 = random)",
    "drum_lock": "steps on drum hits (percentile, 50 = random)",
    "pitch_follow": "arrows move right as the tune rises (rank correlation)",
    "ai_lock": "steps on the AI model's likeliest moments (percentile, 50 = random)",
}


def _spearman(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 4 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def fingerprint(song: "harness.Song", notes: list, ai_env=None) -> dict[str, float]:
    """All measurements for one chart (stepgen Notes)."""
    a = song.a
    notes = sorted(notes, key=lambda n: n.row)
    f: dict[str, float] = {}
    n = len(notes)
    if n < 8:
        return {"steps": n}
    span = max(a.music_end - a.music_start, 1.0)
    per_min = 60.0 / span
    rows = np.array([nt.row for nt in notes])
    panels = [tuple(sorted(nt.panels)) for nt in notes]
    single = np.array([len(p) == 1 for p in panels])
    f["steps"] = n
    f["nps"] = n / span
    f["meter"] = stepgen.estimate_meter(notes, a.spb)

    # jumps
    jumps = np.array([len(p) > 1 for p in panels])
    f["jump_pct"] = 100 * jumps.mean()
    f["jump_holds"] = sum(1 for nt in notes if len(nt.panels) > 1 and nt.hold_rows)
    f["stomps"] = sum(1 for nt in notes if getattr(nt, "stomp", False))
    starts = {s["start"] for s in song.sections}
    in_start = np.array([(r // BAR) in starts or (r // BAR - 1) in starts for r in rows])
    f["jump_cluster"] = 100 * float(in_start[jumps].mean()) if jumps.any() else float("nan")

    # note lengths
    f["beat_pct"] = 100 * float(np.mean(rows % R == 0))
    f["half_pct"] = 100 * float(np.mean(rows % R == R // 2))
    f["quarter_pct"] = 100 * float(np.mean(rows % 2 == 1))
    gaps = np.diff(rows)
    run = best = 0
    for g in gaps:
        run = run + 1 if g == R // 2 else 0
        best = max(best, run)
    f["stream"] = best + 1

    # holds
    holds = [nt for nt in notes if nt.hold_rows]
    f["hold_pct"] = 100 * len(holds) / n
    f["held_beats"] = sum(nt.hold_rows for nt in holds) / R * per_min
    spans = [(nt.row, nt.row + nt.hold_rows) for nt in holds]
    under = 0
    if spans:
        for r in rows:
            under += any(s < r < e for s, e in spans)
    f["under_holds"] = 100 * under / n

    # runs and rests
    runs, cur = [], 1
    for g in gaps:
        if g <= R // 2:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    runs.append(cur)
    real = [x for x in runs if x >= 2]
    f["run_mean"] = float(np.mean(real)) if real else 1.0
    f["long_runs"] = sum(x > 8 for x in runs) * per_min
    f["rests"] = int(np.sum(gaps >= 2 * R)) * per_min

    # footwork, over consecutive single steps
    jack = lr = walk = 0
    trans = []
    seq = [(r, p[0]) for r, p in zip(rows, panels) if len(p) == 1]
    for i in range(1, len(seq)):
        (r0, p0), (r1, p1) = seq[i - 1], seq[i]
        if r1 - r0 > 2 * R:
            continue
        trans.append((p0, p1))
        jack += p0 == p1
        lr += {p0, p1} in ({0, 3}, {1, 2})
    for i in range(3, len(seq)):
        ps = [seq[i - k][1] for k in (3, 2, 1, 0)]
        if ps in ([0, 1, 2, 3], [3, 2, 1, 0], [0, 2, 1, 3], [3, 1, 2, 0]) and seq[i][0] - seq[i - 3][0] <= 3 * R:
            walk += 1
    f["jack_pct"] = 100 * jack / n
    f["lr_pct"] = 100 * lr / n
    f["walk_pct"] = 100 * walk / n
    if trans:
        cnt = np.zeros((4, 4))
        for p0, p1 in trans:
            cnt[p0, p1] += 1
        h = 0.0
        for row in cnt:
            if row.sum():
                p = row[row > 0] / row.sum()
                h += row.sum() / cnt.sum() * float(-(p * np.log2(p)).sum())
        f["arrow_entropy"] = h / 2.0
    # energy: steps per bar against the song's section intensity
    bars = rows // BAR
    first = int(max(0, (a.music_start - a.t0) // (4 * a.spb)))
    last = int(min(len(a.intensity) - 1, (a.music_end - a.t0) // (4 * a.spb)))
    if last - first >= 8:
        counts = np.bincount(bars, minlength=last + 1)[first:last + 1].astype(float)
        inten = a.intensity[first:last + 1]
        f["energy_corr"] = _spearman(counts, inten)
        lo, hi = np.percentile(inten, 25), np.percentile(inten, 75)
        q, l_ = counts[inten <= lo].mean(), counts[inten >= hi].mean()
        f["energy_contrast"] = float(l_ / max(q, 0.5))
        climbs = []
        for b0, top in stepgen.find_builds(a):
            if top - b0 >= 3 and b0 >= first and top <= last:
                c = _spearman(np.arange(top - b0), counts[b0 - first:top - first])
                if not math.isnan(c):
                    climbs.append(c)
        f["build_climb"] = float(np.mean(climbs)) if climbs else float("nan")

    # repetition: in sections the song repeats, how much of the chart repeats
    by_bar: dict[int, dict[int, tuple]] = {}
    for r, p in zip(rows, panels):
        by_bar.setdefault(int(r // BAR), {})[int(r % BAR)] = p
    rr, ra = [], []
    for t, s, length in song.repeats:
        for i in range(length):
            x, y = by_bar.get(s + i, {}), by_bar.get(t + i, {})
            if not x and not y:
                continue
            both = set(x) & set(y)
            rr.append(len(both) / max(len(set(x) | set(y)), 1))
            if both:
                ra.append(sum(x[k] == y[k] for k in both) / len(both))
    f["rep_rhythm"] = 100 * float(np.mean(rr)) if rr else float("nan")
    f["rep_arrows"] = 100 * float(np.mean(ra)) if ra else float("nan")

    # groove meter
    try:
        g = stepgen.groove_of(a, notes, song.onset)
        f["groove"] = g.total
        for p in ("locked", "pattern", "breathing", "footing", "effort"):
            v = g.parts[p]
            f[f"g_{p}"] = 100 * float(np.nanmean(v)) if np.any(~np.isnan(v)) else float("nan")
    except Exception:
        pass

    # what the steps land on: each envelope at the steps vs its average on the 8th grid
    times = np.array([nt.time for nt in notes])

    def lock(env):
        """Average percentile of the envelope at the steps, against every
        16th slot of the song: 50 = no better than random slots."""
        if env is None:
            return float("nan")
        grid = np.arange(a.music_start, a.music_end, a.spb / 4)
        base = np.sort([a.peak(env, t, 0.02) for t in grid])
        at = np.array([a.peak(env, t, 0.02) for t in times])
        return float(100 * np.searchsorted(base, at, side="right").mean() / len(base))

    f["melody_lock"] = lock(a.melody_env)
    f["drum_lock"] = lock(a.beat_env)
    f["ai_lock"] = lock(ai_env)
    if a.melody_cent is not None:
        lane = {0: 0, 1: 1, 2: 2, 3: 3}
        xs = [a.peak(a.melody_cent, nt.time, 0.02) for nt, p in zip(notes, panels) if len(p) == 1]
        ys = [lane[p[0]] for p in panels if len(p) == 1]
        # arrows go up the lanes as the tune rises: compare successive changes
        dx, dy = np.diff(xs), np.diff(ys)
        keep = dy != 0
        f["pitch_follow"] = _spearman(dx[keep], dy[keep]) if keep.sum() > 10 else float("nan")
    return {k: float(v) for k, v in f.items()}


def overlap(n1: list, n2: list) -> tuple[float, float]:
    """How alike two charts are: share of step positions in common, and of
    those, share with the same arrows."""
    a = {nt.row: tuple(sorted(nt.panels)) for nt in n1}
    b = {nt.row: tuple(sorted(nt.panels)) for nt in n2}
    both = set(a) & set(b)
    pos = len(both) / max(len(set(a) | set(b)), 1)
    arr = sum(a[r] == b[r] for r in both) / max(len(both), 1)
    return 100 * pos, 100 * arr


def from_rows(song: "harness.Song", rows: list[tuple[int, tuple[int, ...], int]]) -> list:
    """(row, panels, hold_rows) from another chart -> stepgen Notes, so the
    same measurements work on charts BeatSmith didn't make. Rows are 16ths
    from beat 0 of *this song's* analysis."""
    a = song.a
    out = []
    for r, p, h in rows:
        t = a.t0 + r / R * a.spb
        out.append(stepgen.Note(row=int(r), time=t, strength=0.0, kick=0.0, panels=list(p), hold_rows=int(h)))
    return out
