"""Find preset: read a chart you like (.sm, .ssc or .dwi) and find the
settings that make BeatSmith chart its song the most like it, then save them
as a profile.

    python dialtest.py find-preset "Songs/Pack/Song/Song.sm" --name sandstorm-style

1. Measure the chart (the same fingerprint the dial test uses) against
   BeatSmith's analysis of its song.
2. First guess: the closest chart in the dial test's random sample
   (results/D.jsonl), if there is one, else the defaults.
3. Refine on the real thing: move one control at a time (25% steps, then
   12.5%), make the chart, keep the move when it gets closer.
4. Write profiles/<name>.toml (every setting per difficulty, sliders baked
   in, aimed at the chart's own difficulty) and <name>.find-preset.md next
   to it with how close each measurement got.

The chart file and its folder are only read, never written to.
"""
from __future__ import annotations

import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

import harness
import metrics
from harness import FEEL, stepgen

sys.path.insert(0, str(harness.STEPGEN_DIR))
import chartstats  # noqa: E402
import chartfile  # noqa: E402

R = stepgen.ROWS_PER_BEAT
CONTROLS = list(FEEL) + ["groove", "follow", "ai"]
# measurements matched, and how much each counts
MATCH = {"nps": 1.5, "jump_pct": 1.5, "half_pct": 1.5, "quarter_pct": 1.0, "stream": 0.7, "hold_pct": 1.2,
         "held_beats": 0.5, "under_holds": 0.5, "run_mean": 1.0, "long_runs": 0.7, "rests": 1.0,
         "jack_pct": 1.0, "lr_pct": 1.0, "walk_pct": 0.7, "arrow_entropy": 0.5, "energy_corr": 1.0,
         "energy_contrast": 0.8, "rep_rhythm": 0.8, "rep_arrows": 0.6, "jump_cluster": 0.5,
         "stomps": 0.4, "jump_holds": 0.4, "drum_lock": 0.6, "melody_lock": 0.6}
# a fallback size per measurement when there's no dial-test summary (about its seed noise)
SCALE = {"nps": 0.08, "jump_pct": 1.5, "half_pct": 2.0, "quarter_pct": 0.6, "stream": 3.0, "hold_pct": 1.0,
         "held_beats": 2.0, "under_holds": 1.0, "run_mean": 0.3, "long_runs": 0.8, "rests": 1.5,
         "jack_pct": 0.6, "lr_pct": 1.5, "walk_pct": 0.8, "arrow_entropy": 0.02, "energy_corr": 0.06,
         "energy_contrast": 0.2, "rep_rhythm": 3.0, "rep_arrows": 4.0, "jump_cluster": 4.0,
         "stomps": 2.0, "jump_holds": 2.0, "drum_lock": 1.5, "melody_lock": 1.5}
OURS = {"beginner": "Easy", "easy": "Easy", "medium": "Medium", "hard": "Hard", "challenge": "Hard"}


# --------------------------------------------------------------------------
# reading the chart
# --------------------------------------------------------------------------

def hold_lengths(path: Path) -> list[dict[float, dict[int, float]]]:
    """Per dance-single chart: beat -> {panel: hold length in beats}."""
    _head, charts = chartstats.parse(path)
    out = []
    for ch in charts:
        open_: dict[int, float] = {}
        lengths: dict[float, dict[int, float]] = {}
        for row in ch.rows:
            b = float(row.beat)
            for p, c in enumerate(row.cols[:4]):
                if c in "24":
                    open_[p] = b
                elif c == "3" and p in open_:
                    s = open_.pop(p)
                    lengths.setdefault(s, {})[p] = b - s
        out.append(lengths)
    return out


def read_chart(path: Path):
    song = chartfile.read(path)
    holds = hold_lengths(path) if path.suffix.lower() in (".sm", ".ssc") else [{} for _ in song.charts]
    return song, holds


def to_notes(sng: harness.Song, ch, lengths: dict) -> list:
    """The chart's steps as stepgen Notes on this song's analysis grid."""
    a = sng.a
    rows = []
    for beat, panels in zip(ch.beats, ch.panels):
        t = ch.timing.seconds(beat)
        r = int(round((t - a.t0) / a.spb * R))
        hl = max(lengths.get(beat, {}).values(), default=0.0)
        hold_rows = int(round(hl * 60 / bpm_at(ch, beat) / a.spb * R)) if hl else 0
        rows.append((r, tuple(sorted(panels)), hold_rows))
    seen, out = set(), []
    for r, p, h in sorted(rows):
        if r in seen:
            continue
        seen.add(r)
        out.append((r, p, h))
    return metrics.from_rows(sng, out)


def bpm_at(ch, beat: float) -> float:
    bpm = ch.timing.bpms[0][1]
    for b, v in ch.timing.bpms:
        if b <= beat:
            bpm = v
    return bpm


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------

def scales(diff: str) -> dict[str, float]:
    p = harness.HERE / "summary.json"
    out = dict(SCALE)
    if p.is_file():
        noise = json.loads(p.read_text(encoding="utf-8")).get("noise", {})
        for m in MATCH:
            v = noise.get(f"{diff}|True|{m}")
            if v:
                out[m] = max(float(v), SCALE[m] * 0.5)
    return out


def distance(fa: dict, fb: dict, sc: dict) -> float:
    tot, w = 0.0, 0.0
    for m, wt in MATCH.items():
        x, y = fa.get(m), fb.get(m)
        if x is None or y is None or (isinstance(x, float) and math.isnan(x)) or (isinstance(y, float) and math.isnan(y)):
            continue
        z = (x - y) / sc[m]
        tot += wt * min(z * z, 100.0)               # one wild measurement can't swamp the rest
        w += wt
    return tot / max(w, 1e-9)


# exact settings tuned after the sliders, for what the sliders can't reach:
# (step, low, high)
FINE = {"jacks": (0.15, 0, 1), "jack_max": (1, 2, 6), "run_breaks": (0.15, 0, 1), "recovery": (0.15, 0, 1),
        "stomps": (0.15, 0, 1), "rhythm_repeat": (0.15, 0, 1), "arrow_repeat": (0.15, 0, 1),
        "jump_clusters": (0.15, 0, 1), "jump_holds": (0.15, 0, 1), "hold_rate": (0.03, 0, 0.4),
        "hold_free_foot": (0.5, 0, 2), "flow": (0.15, 0, 1), "side_to_side": (0.15, 0, 1),
        "flow_runs": (0.15, 0, 1), "energy_follow": (0.15, 0, 1), "half_beats": (0.15, 0, 1)}


def config_of(x: dict, profile: str, diff: str, meter: float, seed: int = 1) -> harness.Config:
    """Slider keys are app positions 0..100; keys starting with '=' are exact settings."""
    targets = dict(harness.APP_TARGETS)
    targets[diff] = round(meter, 1)
    sets = tuple(f"{diff}.{k[1:]}={v:g}" for k, v in sorted(x.items()) if k.startswith("="))
    return harness.Config(profile=profile, groove=x["groove"], feel=tuple(sorted((k, x[k]) for k in FEEL)),
                          targets=tuple(targets.items()), follow=x["follow"], ai=x["ai"], sets=sets, seed=seed)


def first_guess(want: dict, diff: str, sc: dict) -> dict:
    x = {k: 50.0 for k in FEEL} | {"groove": 0.0, "follow": 0.0, "ai": 0.0}
    p = harness.WORK / "results" / "D.jsonl"
    if not p.is_file():
        return x
    best = None
    for line in p.open(encoding="utf-8"):
        r = json.loads(line)
        if r["diff"] != diff:
            continue
        d = distance(want, r, sc)
        if best is None or d < best[0]:
            best = (d, r)
    if best:
        cfg = best[1]["config"]
        import re
        for k in FEEL:
            m = re.search(rf"\b{k} (\d+)", cfg)
            x[k] = float(m.group(1)) if m else 50.0
        for k, pat in (("groove", r"groove (\d+)"), ("follow", r"follow (\d+)"), ("ai", r"AI (\d+)")):
            m = re.search(pat, cfg)
            x[k] = float(m.group(1)) if m else 0.0
    return x


def fit(sng: harness.Song, want: dict, diff: str, meter: float, tries: int, log, seeds=(1, 2)) -> tuple:
    """Steepest descent over the controls: each round tries every control
    one step up and down and keeps the best move; the step halves when
    nothing helps. Each setting is judged on the average of a few seeds, so
    it matches the chart's style rather than one lucky layout."""
    sc = scales(diff)
    cache = {}

    def score(x, profile):
        key = (tuple(sorted(x.items())), profile)
        if key not in cache:
            fs, made = [], None
            for seed in seeds:
                ch = next(c for c in harness.make_charts(sng, config_of(x, profile, diff, meter, seed))
                          if c.diff == diff)
                fs.append(metrics.fingerprint(sng, ch.notes))
                made = made or ch
            with np.errstate(all="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                f = {m: float(np.nanmean([g.get(m, np.nan) for g in fs])) for m in fs[0]}
            cache[key] = (distance(want, f, sc), f, made)
        return cache[key]

    x0 = first_guess(want, diff, sc)
    plain = {k: 50.0 for k in FEEL} | {"groove": 0.0, "follow": 0.0, "ai": 0.0}
    cands = [(score(x, p)[0], dict(x), p) for x in (x0, plain) for p in ("konami", "patterns")]
    d, x, profile = min(cands, key=lambda t: t[0])
    log(f"  {diff}: start {profile}, distance {d:.2f}")
    def descend(x, d, moves, budget):
        """moves: key -> (step, low, high); halves the steps twice."""
        scale = 1.0
        while scale >= 0.5 and len(cache) < budget:
            best = None
            for k, (st, lo, hi) in moves.items():
                for sgn in (1, -1):
                    y = dict(x)
                    v = y[k] + sgn * st * scale
                    y[k] = float(np.clip(round(v) if k == "=jack_max" else v, lo, hi))
                    if y[k] == x[k] or len(cache) >= budget:
                        continue
                    dy = score(y, profile)[0]
                    if best is None or dy < best[0]:
                        best = (dy, y, k)
            if best and best[0] < d - 0.02:
                d, x = best[0], best[1]
                log(f"    {best[2].lstrip('=')} {x[best[2]]:g}: distance {d:.2f}")
            else:
                scale /= 2
        return x, d

    # 1. the app's controls
    x, d = descend(x, d, {k: (25.0, 0, 100) for k in CONTROLS}, tries // 2)
    # 2. exact settings, starting from where the controls left them
    made = score(x, profile)[2].asked
    for k in FINE:
        x["=" + k] = float(getattr(made, k))
    log(f"  fine-tuning exact settings (distance {d:.2f})")
    start = {k: v for k, v in x.items() if k.startswith("=")}
    x, d = descend(x, d, {"=" + k: v for k, v in FINE.items()}, tries)
    x = {k: v for k, v in x.items() if not (k in start and start[k] == v)}     # keep only what moved
    _, f, ch = score(x, profile)
    return x, profile, d, f, ch, len(cache)


# --------------------------------------------------------------------------
# saving
# --------------------------------------------------------------------------

def write_profile(path: Path, title: str, source: Path, fits: dict):
    lines = [f"# Found from {source.name} ({title}) by dialtest find-preset",
             'base = "patterns.toml"', ""]
    skip = {"name", "meter_min", "meter_max"}
    for diff in harness.DIFFS:
        if diff not in fits:
            continue
        spec = fits[diff]["spec"]
        x = fits[diff]["x"]
        lines.append(f"[{diff}]")
        lines.append("# sliders: " + ", ".join(f"{k} {v:g}" for k, v in x.items() if not k.startswith("="))
                     + f" (from the {fits[diff]['profile']} profile)")
        for fld in stepgen.DiffSpec.__dataclass_fields__:
            if fld in skip:
                continue
            v = getattr(spec, fld)
            lines.append(f"{fld} = {v if isinstance(v, int) else round(float(v), 4)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(args):
    src = Path(args.chart)
    song, holds = read_chart(src)
    audio = Path(args.song) if args.song else song.music
    if audio is None or not Path(audio).is_file():
        raise SystemExit("couldn't find the song's audio: pass it with --song")
    bpms = {round(v, 2) for ch in song.charts for _, v in ch.timing.bpms}
    bpm = next(iter(bpms)) if len(bpms) == 1 else None
    if len(bpms) > 1:
        print(f"  the chart changes tempo ({', '.join(map(str, sorted(bpms)))} BPM): BeatSmith uses one tempo, "
              "so the match will be rough")
    print(f"analysing {audio.name} ...")
    sng = harness.load_song(Path(audio), "preset-" + Path(audio).stem.replace(" ", "_").lower()[:40], bpm)
    want_diffs = {d.lower() for d in (args.difficulty or [])}
    picked: dict[str, tuple] = {}
    for ch, hl in zip(song.charts, holds):
        ours = OURS.get(ch.difficulty)
        if not ours or (want_diffs and ch.difficulty not in want_diffs and ch.raw_difficulty.lower() not in want_diffs):
            continue
        if ours in picked and ch.difficulty != ours.lower():
            continue                       # prefer the real Easy/Medium/Hard over Beginner/Challenge
        picked[ours] = (ch, hl)
    if not picked:
        raise SystemExit("no dance-single Easy/Medium/Hard chart found")
    fits, report = {}, []
    for diff, (ch, hl) in sorted(picked.items(), key=lambda kv: harness.DIFFS.index(kv[0])):
        notes = to_notes(sng, ch, hl)
        want = metrics.fingerprint(sng, notes)
        meter = want["meter"]
        print(f"{diff} ({ch.raw_difficulty} {ch.meter}): {len(notes)} steps, BeatSmith rates it {meter:.1f}")
        x, profile, d, got, made, n = fit(sng, want, diff, meter, args.tries, print)
        fits[diff] = {"x": x, "profile": profile, "spec": made.asked, "distance": d}
        report.append((diff, ch, want, got, x, profile, d, n))
    name = args.name or "".join(c if c.isalnum() else "-" for c in song.title.lower()).strip("-")
    out = harness.STEPGEN_DIR / "profiles" / f"{name}.toml"
    write_profile(out, song.title, src, fits)
    md = out.with_suffix(".find-preset.md")
    lines = [f"# Preset found from {song.title}", "",
             f"Chart: `{src}`  ", f"Profile written: `profiles/{out.name}`", ""]
    for diff, ch, want, got, x, profile, d, n in report:
        lines += [f"## {diff} (the chart's {ch.raw_difficulty} {ch.meter})", "",
                  f"Started from the {profile} profile, {n} charts tried, distance {d:.2f} "
                  "(0 = identical fingerprint, 1 = about one seed's noise per measurement).", "",
                  "Sliders: " + ", ".join(f"**{k}** {v:g}" for k, v in x.items() if not k.startswith("=")), "",
                  "Exact settings it then tuned (the profile has them; the sliders alone can't get there): "
                  + (", ".join(f"`{k[1:]}` {v:g}" for k, v in x.items() if k.startswith("=")) or "none"), "",
                  "| Measurement | your chart | BeatSmith | gap (noise units) |", "|---|---|---|---|"]
        sc = scales(diff)
        for m in MATCH:
            a, b = want.get(m), got.get(m)
            if a is None or b is None or (isinstance(a, float) and math.isnan(a)):
                continue
            lines.append(f"| {metrics.DESCRIBE.get(m, m)} | {a:.2f} | {b:.2f} | {(b - a) / sc[m]:+.1f} |")
        lines.append("")
    lines.append("BeatSmith can't copy 12th/24th notes, mines, BPM changes or stops; those are ignored.")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}\n  and {md}")
    return out
