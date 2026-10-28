"""Make charts the way stepgen.generate() does, without writing any files,
so thousands of settings can be tried quickly.

A song is analysed once and cached (benchmarks/dials/cache/<name>.pkl); after that a
chart takes well under a second. The per-chart loop below mirrors the one in
stepgen.generate() (follow, AI assist, target, groove tries): if that loop
changes, change this one too.
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import pickle
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STEPGEN_DIR = HERE.parents[1]
sys.path.insert(0, str(STEPGEN_DIR))
sys.path.insert(0, str(STEPGEN_DIR / "src"))
import stepgen  # noqa: E402

import os
WORK = Path(os.environ.get("DIALTEST_WORK", HERE))     # where the cache and results go
CACHE = WORK / "cache"


def _frame(self, t: float) -> int:
    # BeatSmith's Analysis.frame without np.clip on a scalar (same result, ~10x
    # faster); half the time of a chart went there
    return min(max(int(round(t * stepgen.SR / stepgen.HOP)), 0), len(self.onset_env) - 1)


stepgen.Analysis.frame = _frame
DIFFS = ("Easy", "Medium", "Hard")
APP_TARGETS = {"Easy": 3.0, "Medium": 6.0, "Hard": 8.0}      # the app's defaults
FEEL = ("energy", "jumps", "speed", "breathing", "footwork", "holds", "repetition")


@dataclass
class Song:
    name: str
    path: Path
    a: stepgen.Analysis
    repeats: list
    sections: list
    onset: np.ndarray | None
    audio: np.ndarray | None = None        # loaded only when AI assist is used
    _ai: dict = field(default_factory=dict)

    def ai_env(self, meter: float) -> np.ndarray | None:
        from beatsmith import ai_assist
        if not ai_assist.available():
            return None
        key = round(meter, 1)
        if key not in self._ai:
            if self.audio is None:
                self.audio = stepgen.load_audio(self.path)
            self._ai[key] = ai_assist.ai_env(self.audio, self.a, key)
        return self._ai[key]


def load_song(path: Path, name: str | None = None, bpm: float | None = None,
              stems: Path | None = None) -> Song:
    """The song's analysis, from the cache when the file hasn't changed.
    With stems (a folder of vocals/drums/bass/other.ogg), the melody comes
    from them, as with stepgen --stems."""
    path = Path(path)
    name = name or path.stem
    CACHE.mkdir(exist_ok=True)
    st = path.stat()
    # a new cache when the song or BeatSmith's analysis code changes
    import inspect
    code = inspect.getsource(stepgen.analyze) + inspect.getsource(stepgen.refine_bpm)
    key = hashlib.md5(f"{path.resolve()}|{st.st_size}|{st.st_mtime}|{bpm}|{stems}|{code}".encode()).hexdigest()[:10]
    cache = CACHE / f"{name}-{key}.pkl"
    if cache.is_file():
        with open(cache, "rb") as f:
            a, onset = pickle.load(f)
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            a = stepgen.analyze(path, bpm, stems)
            onset = stepgen.song_onsets(path)
        with open(cache, "wb") as f:
            pickle.dump((a, onset), f)
    repeats = stepgen.find_repeats(a)
    sections = stepgen.find_sections(a, repeats)
    return Song(name, path, a, repeats, sections, onset)


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """One run's settings, in the app's own terms."""
    profile: str = "konami"
    groove: float = 0.0                    # app scale 0 (off) .. 100
    feel: tuple = ()                       # ((slider, 0..100), ...); missing = 50
    targets: tuple | None = tuple(APP_TARGETS.items())   # ((diff, meter), ...) or None = off
    follow: float = 0.0                    # 0..100
    ai: float = 0.0                        # 0..100
    sets: tuple = ()                       # exact Advanced values, "Hard.jump=0.5"
    seed: int = 1

    def easy(self) -> dict[str, float]:
        out = {k: v / 100 for k, v in self.feel if v != 50}
        if self.groove:
            out["groove"] = 0.5 + self.groove / 200        # beatsmith_app.groove_easy
        return out

    def run_sets(self) -> list[str]:
        out = [f"{d}.target_meter={m:g}" for d, m in (self.targets or ())]
        if self.follow:
            out += [f"{d}.melody_follow={self.follow / 100:g}" for d in DIFFS]
        if self.ai:
            out += [f"{d}.ai_assist={self.ai / 100:g}" for d in DIFFS]
        return out + list(self.sets)

    def specs(self) -> list[stepgen.DiffSpec]:
        path = stepgen.resolve_profile(self.profile)
        with contextlib.redirect_stdout(io.StringIO()):
            specs = stepgen.load_patterns(path, self.run_sets(), self.easy() or None)
        return [s for s in specs if s.name in DIFFS]

    def with_(self, **kw) -> "Config":
        if "feel" in kw and isinstance(kw["feel"], dict):
            kw["feel"] = tuple(sorted(kw["feel"].items()))
        if "targets" in kw and isinstance(kw["targets"], dict):
            kw["targets"] = tuple(kw["targets"].items())
        return dataclasses.replace(self, **kw)

    def label(self) -> str:
        bits = [self.profile]
        if self.groove:
            bits.append(f"groove {self.groove:g}")
        bits += [f"{k} {v:g}" for k, v in self.feel if v != 50]
        bits.append("targets " + ("/".join(f"{m:g}" for _, m in self.targets) if self.targets else "off"))
        if self.follow:
            bits.append(f"follow {self.follow:g}")
        if self.ai:
            bits.append(f"AI {self.ai:g}")
        bits += list(self.sets)
        bits.append(f"seed {self.seed}")
        return ", ".join(bits)


@dataclass
class Chart:
    diff: str
    asked: stepgen.DiffSpec               # settings after profile, sliders and pins
    used: stepgen.DiffSpec                # settings the chart was made with (after the target)
    notes: list
    ac: stepgen.Analysis                  # the analysis as this chart saw it (follow, AI)


def make_charts(song: Song, cfg: Config, diffs=DIFFS) -> list[Chart]:
    """Easy, Medium and Hard for these settings, as stepgen.generate() makes
    them (one random generator through the charts in order)."""
    a = song.a
    rng = random.Random(cfg.seed)
    out = []
    with contextlib.redirect_stdout(io.StringIO()):
        for spec in cfg.specs():
            fol = stepgen.follow_for(a, [dict(s) for s in song.sections], spec, None)
            ac = stepgen.with_follow(a, fol)
            if spec.ai_assist > 0:
                from beatsmith import ai_assist
                env = song.ai_env(ai_assist.meter_for(spec))
                ac = stepgen.with_ai(ac, env, spec.ai_assist)
            if spec.target_meter > 0:
                made, notes = stepgen.aim_for_meter(ac, spec, song.repeats, rng)
            else:
                made, notes = spec, stepgen.make_chart(ac, spec, song.repeats, rng)
            if spec.groove_tries > 1:
                first = stepgen.estimate_meter(notes, a.spb)
                best = (stepgen.groove_of(a, notes, song.onset).total, made, notes)
                for k in range(1, spec.groove_tries):
                    alt = random.Random(f"{cfg.seed}-{spec.name}-{k}")
                    if spec.target_meter > 0:
                        m2, n2 = stepgen.aim_for_meter(ac, spec, song.repeats, alt)
                    else:
                        m2, n2 = spec, stepgen.make_chart(ac, spec, song.repeats, alt)
                    if abs(stepgen.estimate_meter(n2, a.spb) - first) > 0.4:
                        continue
                    g = stepgen.groove_of(a, n2, song.onset).total
                    if g > best[0]:
                        best = (g, m2, n2)
                _, made, notes = best
            if spec.name in diffs:
                out.append(Chart(spec.name, spec, made, notes, ac))
    return out
