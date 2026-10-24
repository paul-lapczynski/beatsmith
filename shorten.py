"""Shorten a song toward a target length (about 1:30 or 2:00), the way
arcade cuts of full songs are made, so it's still the song.

A cut is a jump: from just before bar i, straight on to bar j later in the
song, where the music around j sounds like the music around i (the same
chords on the same beats, the same sound, as loud). Repeated parts of a song
are exactly that, so a jump from the start of the second chorus to the start
of the third skips a verse and a chorus without anyone hearing a seam. Only
jumps whose two places match closely enough are used, both are on the same
spot of the 4-bar phrase, and every piece is whole bars on one beat grid, so
the beat carries straight through. No clean jumps, no shortening: the song
is left as it is.

Which jumps: the fewest, cleanest ones that bring the song near the target,
that keep the start and the ending, and that skip music the song plays again
elsewhere rather than parts it only has once (a bridge, a solo).

With keep_verses, a jump may only skip choruses, the intro and outro, and
quiet breakdowns: every other part (the verses, and anything that might be
one, since telling a verse from a build or bridge is a guess) stays. When
the sections were named from the lyrics (verses.py), only the verses and
the bridge are kept that way.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

MATCH = 0.7             # how alike the music around the two ends of a jump must be (-1..1)
SLACK = 8.0             # "about": this many seconds either side of the target is fine
CONTEXT = (-2, -1, 0, 1)  # bars compared around a jump (2 before it, 2 after)


@dataclass
class Plan:
    keep: list[tuple[int, int]]       # bar ranges [start, end) kept, in order
    jumps: list[tuple[int, int, float]]  # (from bar, to bar, how alike)
    sections: list[dict]              # the song's sections, each with "kept" bars
    full: float                       # seconds, before
    short: float                      # seconds, after

    def describe(self) -> str:
        bits = []
        for s in self.sections:
            n, k = s["end"] - s["start"], s["kept"]
            what = "kept" if k == n else "cut" if k == 0 else f"{k} of {n} bars"
            bits.append(f"{s['letter']} {s['label']} {what}")
        jumps = ", ".join(f"bar {i + 1} to {j + 1} ({round(100 * m)}% alike)" for i, j, m in self.jumps)
        return f"shortened {clock(self.full)} -> {clock(self.short)} by jumping {jumps}: " + ", ".join(bits)


    def remap(self, words: list, a) -> list:
        """[start, end, word] in the full song's seconds -> in the shortened
        song's, dropping the words in the parts that were cut."""
        measure = 4 * a.spb
        first = self.keep[0][0]
        spans, done = [], 0
        for k, (b, e) in enumerate(self.keep):
            lo = -1e9 if k == 0 else a.t0 + b * measure
            hi = 1e9 if k == len(self.keep) - 1 else a.t0 + e * measure
            spans.append((lo, hi, a.t0 + (first + done - b) * measure))   # add to go to the new time
            done += e - b
        out = []
        for st, en, w in words:
            for lo, hi, add in spans:
                if lo <= st < hi:
                    out.append([st + add, en + add, w])
                    break
        return out


def clock(t: float) -> str:
    return f"{int(t // 60)}:{int(round(t % 60)):02d}"


def _alike(Z: np.ndarray, i: int, j: int) -> float:
    """How much the bars around i sound like the bars around j."""
    ks = [k for k in CONTEXT if 0 <= i + k < len(Z) and 0 <= j + k < len(Z)]
    return float(np.mean([Z[i + k] @ Z[j + k] for k in ks])) if len(ks) >= 3 else -1.0


def plan(a, sections: list[dict], target: float, keep_verses: bool = False) -> Plan | None:
    """Which bars to keep to get the song near `target` seconds, using only
    clean jumps. None when it's already short enough or no clean jumps fit."""
    measure = 4 * a.spb
    Z = a.bar_feats
    n = len(Z)
    if not sections or n < 16:
        return None
    first = sections[0]["start"]
    end = min(n, sections[-1]["end"])
    head = max(0.0, a.t0 + first * measure)                  # before bar 1: kept as it is
    tail = max(0.0, a.duration - (a.t0 + end * measure))     # after the last bar: the song's own ending
    full = head + tail + (end - first) * measure
    if full <= target + SLACK:
        return None

    # how much each bar is heard elsewhere in the song: skipping a bar that
    # comes back costs little, skipping one that's only there once costs a lot
    S = Z @ Z.T
    again = np.array([max([S[m, k] for k in range(first, end) if abs(k - m) >= 4] or [0.0])
                      for m in range(n)])
    lose = np.clip(1 - again, 0, 1) + 0.15

    # the jumps that sound clean: same spot of the phrase, at least 4 bars
    # skipped, the start and the last 4 bars kept
    skippable = np.ones(n, bool)
    if keep_verses:
        from_lyrics = any("sung" in s for s in sections)
        for s in sections:
            if (s["label"] in ("verse", "bridge") if from_lyrics
                    else s["label"] not in ("chorus", "intro", "outro", "breakdown")):
                skippable[s["start"]:s["end"]] = False
    jumps: dict[int, list[tuple[int, float]]] = {}
    for i in range(first + 4, end - 4, 4):
        for j in range(i + 4, end - 4, 4):
            if not skippable[i:j].all():
                break                                 # a verse in the way: no later landing either
            m = _alike(Z, i, j)
            if m >= MATCH:
                jumps.setdefault(i, []).append((j, m))
    if not jumps:
        return None

    # cheapest way through the song: (bar, bars kept) -> cost, how we got there
    target_bars = (target - head - tail) / measure
    starts = {s["start"] for s in sections}           # jumping from a section line sounds most natural
    INF = float("inf")
    cost = {(first, 0): 0.0}
    back: dict[tuple[int, int], tuple[int, int, float] | None] = {(first, 0): None}
    for i in range(first, end):
        for L in range(0, i - first + 1):
            c = cost.get((i, L))
            if c is None:
                continue
            for nxt, extra, how in [((i + 1, L + 1), 0.0, None)] + [
                    # after landing, at least 4 bars play before the next jump
                    ((j + 4, L + 4), 1.0 + 8 * (1 - m) + 0.1 * float(lose[i:j].sum())
                     + (0.0 if i in starts or j in starts else 0.8), (i, j, m))
                    for j, m in jumps.get(i, [])]:
                if c + extra < cost.get(nxt, INF):
                    cost[nxt] = c + extra
                    back[nxt] = (i, L, how) if how is None else (i, L, how)
    best, best_c = None, INF
    for (i, L), c in cost.items():
        if i != end:
            continue
        got = head + tail + L * measure
        # near the target matters more than a slightly cleaner cut; far
        # under it is worse than a bit over
        total = c + 1.0 * max(0.0, (target - 2 * SLACK) - got) + 0.5 * max(0.0, got - (target + SLACK))
        if total < best_c:
            best, best_c = (i, L), total
    if best is None or (end - first - best[1]) * measure < 15:
        return None                                   # nothing worth the cut
    # walk back
    taken, state = [], best
    while back.get(state) is not None:
        i, L, how = back[state]
        if how is not None:
            taken.append(how)
        state = (i, L)
    taken.reverse()
    if not taken:
        return None
    keep, start = [], first
    for i, j, _ in taken:
        keep.append((start, i))
        start = j
    keep.append((start, end))

    secs = []
    for s in sections:
        kept = sum(max(0, min(s["end"], e) - max(s["start"], b)) for b, e in keep)
        secs.append(dict(s, kept=kept))
    short = head + tail + measure * sum(e - b for b, e in keep)
    return Plan(keep, taken, secs, full, short)


def render(audio: np.ndarray, sr: int, a, p: Plan) -> np.ndarray:
    """The kept bars of `audio` (samples x channels), joined. The first piece
    starts at the top of the file and the last runs to its end, so the
    chart's tempo and offset carry over. Each join is a half-beat equal-power
    crossfade that finishes just before the downbeat, so the downbeat itself
    comes whole from after the jump."""
    measure = 4 * a.spb
    x = max(2, int(a.spb / 2 * sr))
    h = x // 2
    lead = h + int(0.01 * sr)                         # crossfade centre: this far before the downbeat
    at = lambda m: int(round((a.t0 + m * measure) * sr)) - lead
    ramp = np.sin(np.linspace(0, np.pi / 2, x))[:, None]
    parts = []
    for k, (b, e) in enumerate(p.keep):
        s = 0 if k == 0 else at(b)
        stop = len(audio) if k == len(p.keep) - 1 else at(e)
        lo = s if k == 0 else s + h
        hi = stop if k == len(p.keep) - 1 else stop - h
        if k > 0:
            pe = at(p.keep[k - 1][1])
            a_tail = audio[max(0, pe - h):pe + h]
            b_head = audio[max(0, s - h):s + h]
            n = min(len(a_tail), len(b_head), x)
            parts.append(a_tail[:n] * ramp[::-1][:n] + b_head[:n] * ramp[:n])
        parts.append(audio[max(0, lo):max(0, hi)])
    return np.concatenate(parts)


def shorten_file(src: Path, dst: Path, a, sections: list[dict], target: float,
                 keep_verses: bool = False) -> Plan | None:
    """Write the shortened song to dst (a .wav). None if it wasn't shortened."""
    import soundfile as sf
    p = plan(a, sections, target, keep_verses)
    if p is None:
        return None
    try:
        audio, sr = sf.read(str(src), always_2d=True, dtype="float32")
    except Exception:
        import librosa
        y, sr = librosa.load(str(src), sr=None, mono=False)
        audio = np.atleast_2d(y).T.astype(np.float32)
    sf.write(str(dst), render(audio, sr, a, p), sr)
    return p


def cut_stems(src: Path, dst: Path, a, p: Plan) -> Path:
    """The separated stems (vocals.ogg...) cut the same way as the song."""
    import soundfile as sf
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.ogg"):
        audio, sr = sf.read(str(f), always_2d=True, dtype="float32")
        out = render(audio, sr, a, p)
        with sf.SoundFile(str(dst / f.name), "w", samplerate=sr, channels=out.shape[1],
                          format="OGG", subtype="VORBIS") as o:
            for i in range(0, len(out), sr * 10):        # blocks: big Vorbis writes can crash
                o.write(out[i:i + sr * 10])
    return dst
