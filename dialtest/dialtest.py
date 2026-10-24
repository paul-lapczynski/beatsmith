"""BeatSmith dial test: what every control actually does to a chart.

    python dialtest.py run [--quick] [--jobs 4] [--only A,B] SONG.ogg ...
    python dialtest.py report          # REPORT.md: grades and numbers
    python dialtest.py images          # docs/img/*.png: 4 bars per setting
    python dialtest.py docs            # docs/DIALS.md: the README section
    python dialtest.py preview         # docs/preview.html: the slider page
    python dialtest.py find-preset CHART.sm [--song SONG.ogg] [--name my-style]

With no songs, `run` uses the songs listed in SONGS below. Runs on the CPU
only. Results go to dialtest/results/ and a run picks up where it stopped.
See TESTPLAN.md for the design.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")          # CPU only

import harness  # noqa: E402
import metrics  # noqa: E402
import plan  # noqa: E402

RESULTS = harness.WORK / "results"
SG = harness.STEPGEN_DIR
SONGS = {
    "Wrong Note": SG / "examples" / "Wrong Note (stepgen)" / "Wrong Note (stepgen).ogg",
    "Sandstorm": SG / "generated" / "Sandstorm (stepgen)" / "Sandstorm (stepgen).ogg",
    "Yeah": SG / "generated" / "Yeah (stepgen konami 9)" / "Yeah (stepgen konami 9).ogg",
}
# the pictures and the preview use this one: synthesized by demo_track.py, so it can ship
# with the repo (the songs above are copyrighted and stay out of it)
DEMO = ("BeatSmith Demo", SG / "examples" / "BeatSmith Demo" / "beatsmith-demo.ogg")
# settings recorded per chart, as asked (after sliders and pins) and as used (after the target)
SPEC_KEYS = ("density", "max_nps", "grid", "min_gap", "jump", "hold_rate", "half_beats", "quarter_beats",
             "flow_spice", "sixteenths", "run_breaks", "recovery", "stomps", "jacks", "flow",
             "side_to_side", "energy_follow", "phrase_shape", "beat_backbone", "rhythm_repeat",
             "arrow_repeat", "jump_clusters", "jump_holds", "groove_tries")

_songs: dict[str, harness.Song] = {}
_paths: dict[str, Path] = {}


def _init(paths):
    _paths.update(paths)


def _song(name):
    if name not in _songs:
        _songs[name] = harness.load_song(_paths[name], name.replace(" ", "_").lower())
    return _songs[name]


def run_group(g: plan.Group) -> list[dict]:
    import ai_assist
    song = _song(g.song)
    rows, ref = [], {}
    for i, (cfg, tag) in enumerate(zip(g.configs, g.tags)):
        t = time.time()
        charts = harness.make_charts(song, cfg)
        for ch in charts:
            env = song.ai_env(ai_assist.meter_for(ch.asked))
            row = {"design": g.design, "key": g.key, "song": g.song, "i": i, **tag, "diff": ch.diff,
                   "seed": cfg.seed, "config": cfg.label(), "secs": round(time.time() - t, 2)}
            row.update(metrics.fingerprint(song, ch.notes, env))
            if i == 0:
                ref[ch.diff] = ch.notes
            if ch.diff in ref:
                row["same_pos"], row["same_arrows"] = metrics.overlap(ref[ch.diff], ch.notes)
            for k in SPEC_KEYS:
                row[f"asked.{k}"] = float(getattr(ch.asked, k))
                row[f"used.{k}"] = float(getattr(ch.used, k))
            row["target"] = float(ch.asked.target_meter)
            rows.append(row)
    return rows


def cmd_run(args):
    songs = {Path(p).stem: Path(p) for p in args.songs} if args.songs else dict(SONGS)
    missing = [str(p) for p in songs.values() if not Path(p).is_file()]
    if missing:
        raise SystemExit("missing song files: " + ", ".join(missing))
    RESULTS.mkdir(exist_ok=True)
    groups = plan.build(list(songs), args.quick)
    if args.only:
        keep = set(args.only.split(","))
        groups = [g for g in groups if g.design in keep or g.design[:1] in keep]
    done = set()
    for f in RESULTS.glob("*.jsonl"):
        for line in f.open(encoding="utf-8"):
            r = json.loads(line)
            done.add((r["design"], r["key"]))
    todo = [g for g in groups if (g.design, g.key) not in done]
    runs = sum(len(g.configs) for g in todo)
    print(f"{len(groups)} groups in the plan, {len(todo)} to do ({runs} runs, 3 charts each)")
    # analyse each song once up front, so the workers only read the cache
    for name, p in songs.items():
        print(f"analysing {name} ...", flush=True)
        harness.load_song(p, name.replace(" ", "_").lower())
    t0, n = time.time(), 0
    with Pool(args.jobs, initializer=_init, initargs=(songs,)) as pool:
        for rows in pool.imap_unordered(run_group, todo):
            with open(RESULTS / f"{rows[0]['design']}.jsonl", "a", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            n += 1
            if n % 10 == 0 or n == len(todo):
                el = time.time() - t0
                print(f"  {n}/{len(todo)} groups, {el / 60:.1f} min, about "
                      f"{el / n * (len(todo) - n) / 60:.0f} min to go", flush=True)


def _song_path(name: str) -> Path:
    return DEMO[1] if name == DEMO[0] else SONGS.get(name, Path(name))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("songs", nargs="*")
    r.add_argument("--quick", action="store_true", help="1 seed and a smaller random sample")
    r.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    r.add_argument("--only", help="designs to run, e.g. A,B or C2")
    sub.add_parser("report")
    i = sub.add_parser("images")
    i.add_argument("--song", default=DEMO[0])
    sub.add_parser("docs")
    p = sub.add_parser("preview")
    p.add_argument("--song", default=DEMO[0])
    f = sub.add_parser("find-preset")
    f.add_argument("chart", type=Path)
    f.add_argument("--song", type=Path, help="the song file (default: the chart's #MUSIC)")
    f.add_argument("--difficulty", action="append", help="which charts to copy (default: all)")
    f.add_argument("--name", help="profile name to save (default: the song's title)")
    f.add_argument("--tries", type=int, default=200, help="settings to try while refining (2 charts each)")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "report":
        import report
        return report.main()
    if a.cmd == "images":
        import render
        return render.all_images(_song_path(a.song), a.song)
    if a.cmd == "docs":
        import docs
        return docs.main()
    if a.cmd == "preview":
        import preview
        return preview.main(_song_path(a.song), a.song)
    if a.cmd == "find-preset":
        import find_preset
        return find_preset.main(a)


if __name__ == "__main__":
    main()
