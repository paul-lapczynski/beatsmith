"""Bounded rhythm following for the separated lead-instrument stem.

This measures attacks, not pitches. No model or extra download is needed.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.signal import find_peaks


class TracedNotes(list):
    def __init__(self, notes, trace):
        super().__init__(notes)
        self.melody_trace = trace


def attack_times(env, sr, hop):
    """One candidate per clear peak; don't turn a sustained envelope into rows."""
    if not len(env) or float(np.max(env)) < 1e-6:
        return np.array([], dtype=float)
    peaks, _ = find_peaks(np.pad(env, (1, 1)), height=0.12, prominence=0.08,
                          distance=max(1, round(0.065 * sr / hop)))
    # Flux peaks lag the audio attack. Match the analysis beat-phase correction.
    return np.maximum(0, (peaks - 1) * hop / sr - 0.016)


def follow_at(a, row):
    return float(a.follow[int(np.clip(row // 16, 0, len(a.follow) - 1))]) if a.follow is not None else 0.0


def supported(a, row):
    if a.lead_attacks is None or not len(a.lead_attacks):
        return False
    t = a.t0 + row * a.spb / 4
    i = np.searchsorted(a.lead_attacks, t)
    return any(abs(float(a.lead_attacks[j]) - t) <= min(0.075, a.spb / 4 * 0.55)
               for j in (i - 1, i) if 0 <= j < len(a.lead_attacks))


def fits(note, chosen, gap, max_nps):
    if any(abs(note.row - p.row) < gap for p in chosen):
        return False
    # A notes/sec cap is a one-second window, not a minimum interval between
    # every two notes: a short pair can fit without becoming a nonstop stream.
    near = sorted([note.time] + [p.time for p in chosen if abs(p.time - note.time) < 1])
    return all(sum(start <= t < start + 1 - 1e-7 for t in near) <= max(1, math.ceil(max_nps))
               for start in near)


def place(a, spec, beat_notes, Note):
    """Use a difficulty-sized budget, never fill a missing lead attack quota."""
    dt = a.spb / 4
    step = max(1, 4 // spec.grid)
    candidates = {}
    previous = -math.inf
    phrase_bars = set()
    for t in a.lead_attacks:
        row = int(round((float(t) - a.t0) / dt / step)) * step
        tm = a.t0 + row * dt
        phrase = float(t) - previous >= 1.5 * a.spb
        previous = float(t)
        if row < 0 or not a.music_start <= tm <= a.music_end - 0.25 or not supported(a, row):
            continue
        bar = row // 16
        starts = np.flatnonzero(a.section_start[:bar + 1] > 0)
        origin = int(starts[-1]) if len(starts) else 0
        if (bar - origin) % 4 == 0 and row % 16 < 4 and bar not in phrase_bars:
            phrase = True
            phrase_bars.add(bar)
        strength = a.peak(a.melody_env, float(t) + 0.016, 0.025)
        f = follow_at(a, row)
        if f <= 0:
            continue
        note = Note(row, tm, strength, a.peak(a.low_env, tm), phrase_start=phrase)
        score = strength * (0.4 + 0.6 * f) * (2.5 if phrase else 1.0)
        if row not in candidates or score > candidates[row][0]:
            candidates[row] = (score, note)
    # At low follow, the beat remains a deliberate part of the mix. At high
    # follow, a drum hit alone cannot stand in for a lead-instrument attack.
    for n in beat_notes:
        f = follow_at(a, n.row)
        if n.row >= 0 and a.music_start <= n.time <= a.music_end - 0.25 and n.row not in candidates and f < 0.75:
            candidates[n.row] = (n.strength * (1 - f), n)
    span = max(1, a.music_end - a.music_start)
    target = int(min(spec.density * span / a.spb, spec.max_nps * span))
    by_bar = {}
    for score, n in candidates.values():
        by_bar.setdefault(n.row // 16, []).append((score, n))
    # Share the budget across the actual attacks. No carry-over into silence.
    weights = {m: (1 - spec.energy_follow) + spec.energy_follow * a.bar_intensity(m)
               for m in by_bar}
    total = sum(weights.values()) or 1
    chosen = []
    gap = max(1, round(spec.min_gap * 4))
    carry = 0.0
    for m in sorted(by_bar):
        want = target * weights[m] / total + carry
        got = 0
        for _, n in sorted(by_bar[m], key=lambda c: (-c[0], c[1].row)):
            if got >= round(want) or len(chosen) >= target:
                break
            if not fits(n, chosen, gap, spec.max_nps):
                continue
            chosen.append(n)
            got += 1
        carry = min(1, max(0, want - got))
    return sorted(chosen, key=lambda n: n.row)


def constrain(a, notes, spec):
    """Later passes may thin attacks but cannot invent new lead-only rows."""
    if a.melody_source != 'lead' or a.follow is None or not a.follow.any():
        return notes
    eligible = [n for n in notes if follow_at(a, n.row) < 0.75 or supported(a, n.row)]
    gap = max(1, round(spec.min_gap * 4))
    target = int(min(spec.density * max(1, a.music_end - a.music_start) / a.spb,
                     spec.max_nps * max(1, a.music_end - a.music_start)))
    kept = []
    for n in sorted(eligible, key=lambda n: (not n.phrase_start, -n.strength, n.row)):
        if len(kept) < target and fits(n, kept, gap, spec.max_nps):
            kept.append(n)
    return sorted(kept, key=lambda n: n.row)


def stage(trace, name, notes):
    rows = {n.row for n in notes}
    anchors = trace['selected_phrase_rows']
    retained = [r for r in anchors if r in rows]
    trace['stages'].append({'stage': name, 'steps': len(notes), 'retained_phrase_rows': retained,
                            'missing_phrase_rows': [r for r in anchors if r not in rows]})


def alignment(a, notes):
    if a.melody_source != 'lead' or not notes:
        return 0.0
    active = [n for n in notes if follow_at(a, n.row) > 0]
    if not active:
        return 0.0
    return sum(supported(a, n.row) for n in active) / len(active)


def selection_score(a, notes, groove):
    # Keep the existing groove score exactly for Singing. A full-follow lead
    # chart can earn up to 40 points for final attack alignment.
    strength = float(np.mean(a.follow)) if a.follow is not None else 0.0
    return groove + 40 * strength * alignment(a, notes)
