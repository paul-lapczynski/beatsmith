"""Arrows follow, again, with separated stems (the main dial test ran on the
full mix). For each song, charts are made from the plain analysis and from
the stems analysis at Follow 0/25/50/75/100, with and without difficulty
targets, three seeds each. Every chart is measured against the stems'
melody (vocal note starts while someone sings, plus the lead line), so
both kinds are scored against the same idea of where the tune is.

    python dialtest/follow_stems.py "Song.ogg=Song/.stems" ...   [--jobs 4]

Writes results/follow-stems.jsonl and prints the summary tables; the stems
are only read (make them with stems.py or the app first).
"""
from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

import harness
import metrics

OUT = harness.WORK / "results" / "follow-stems.jsonl"
FOLLOW = (0, 25, 50, 75, 100)
SEEDS = (1, 2, 3)
KEEP = ("melody_lock", "drum_lock", "pitch_follow", "steps", "jump_pct", "lr_pct", "half_pct")
SONGS: dict[str, tuple] = {}            # name -> (plain Song, stems Song); filled before the pool forks


def jobs():
    for name in SONGS:
        for stems in (False, True):
            for targets in (True, False):
                for fo in FOLLOW:
                    for seed in SEEDS:
                        yield name, stems, targets, fo, {}, seed
        # does Footwork survive following with stems?
        for fo in (0, 100):
            for fw in (25, 75):
                for seed in SEEDS:
                    yield name, True, True, fo, {"footwork": fw}, seed


def run(job):
    name, stems, targets, fo, feel, seed = job
    plain, stem = SONGS[name]
    cfg = harness.Config(follow=fo, feel=tuple(sorted(feel.items())), seed=seed,
                         targets=harness.Config().targets if targets else None)
    base = harness.make_charts(stem if stems else plain, cfg.with_(follow=0))
    charts = harness.make_charts(stem if stems else plain, cfg)
    rows = []
    for ch, b in zip(charts, base):
        f = metrics.fingerprint(stem, ch.notes)            # always scored against the stems' melody
        row = {"song": name, "stems": stems, "targets": targets, "follow": fo, "seed": seed,
               "diff": ch.diff, "footwork": feel.get("footwork", 50)}
        row.update({k: f.get(k, float("nan")) for k in KEEP})
        row["moved"] = 100 - metrics.overlap(b.notes, ch.notes)[0]
        rows.append(row)
    return rows


def summary(df: pd.DataFrame) -> str:
    out = []
    plain = df[df.footwork == 50]
    for col, what in (("melody_lock", "steps on melody note starts (percentile, 50 = random)"),
                      ("moved", "% of step positions that differ from Follow 0"),
                      ("pitch_follow", "arrows move right as the tune rises (rank corr.)"),
                      ("drum_lock", "steps on drum hits (percentile)")):
        t = plain.pivot_table(index=["targets", "stems"], columns="follow", values=col, aggfunc="mean")
        out.append(f"\n## {col}: {what}\n\n{t.round(1).to_string()}")
        t = plain[plain.targets].pivot_table(index=["song", "stems"], columns="follow", values=col, aggfunc="mean")
        out.append(f"\nper song, targets on:\n{t.round(1).to_string()}")
    # seed noise for melody_lock at follow 0
    sd = plain[plain.follow == 0].groupby(["song", "stems", "targets", "diff"]).melody_lock.std().mean()
    out.append(f"\nseed-to-seed spread of melody_lock: {sd:.1f}")
    fw = df[(df.stems) & (df.targets) & (df.footwork != 50)]
    t = fw.pivot_table(index="follow", columns="footwork", values="lr_pct", aggfunc="mean")
    t["effect"] = t[75] - t[25]
    out.append(f"\n## Footwork (Left-Right moves per 100 steps) with stems, targets on\n\n{t.round(1).to_string()}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("songs", nargs="*", help='"audio.ogg=stems_dir" pairs')
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--report", action="store_true", help="only print the summary of earlier runs")
    args = ap.parse_args(argv)
    if not args.report:
        for pair in args.songs:
            audio, d = pair.split("=", 1)
            audio = Path(audio)
            plain = harness.load_song(audio, audio.stem)
            stem = harness.load_song(audio, audio.stem + " stems", stems=Path(d))
            assert abs(plain.a.spb - stem.a.spb) < 1e-9 and abs(plain.a.t0 - stem.a.t0) < 1e-9, audio
            SONGS[audio.stem] = (plain, stem)
            print(f"loaded {audio.stem}", flush=True)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        todo = list(jobs())
        with Pool(args.jobs) as pool, open(OUT, "w", encoding="utf-8") as f:
            for i, rows in enumerate(pool.imap_unordered(run, todo), 1):
                for r in rows:
                    f.write(json.dumps(r) + "\n")
                if i % 20 == 0:
                    print(f"{i}/{len(todo)}", flush=True)
    df = pd.DataFrame([json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines()])
    print(summary(df))


if __name__ == "__main__":
    sys.exit(main())
