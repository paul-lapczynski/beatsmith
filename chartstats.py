#!/usr/bin/env python3
"""chartstats: pattern statistics for dance-single charts in a .sm/.ssc file.

  python3 chartstats.py "Wrong Note.sm" [--audio "Wrong Note.ogg"] [--report stats.md]

Reports note density, subdivisions, jumps (and runs of back-to-back jumps),
jacks (same arrow repeated), side-to-side L<->R travel, flow (runs of steps
on 3+ different arrows without jumps or jacks), holds and what the free foot
does during them, and the StepMania groove radar (stream, voltage, air,
freeze, chaos). With --audio it also measures how well notes land on the
music's onsets and how density tracks loudness. --report out.md writes a
Markdown snapshot with tables and graphs.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass
class Row:
    beat: Fraction
    cols: str                  # 4 chars


@dataclass
class Chart:
    difficulty: str
    meter: str
    rows: list[Row]


def _tag(text: str, name: str) -> str | None:
    m = re.search(r"#" + name + r":([^;]*);", text)
    return m.group(1).strip() if m else None


def parse(path: Path) -> tuple[dict, list[Chart]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".dwi":
        return parse_dwi(text)
    text = re.sub(r"//[^\n]*", "", text)
    head = {"offset": float(_tag(text, "OFFSET") or 0),
            "bpms": _tag(text, "BPMS") or "", "music": _tag(text, "MUSIC") or ""}
    charts = []
    if path.suffix.lower() == ".ssc":
        for blk in text.split("#NOTEDATA:")[1:]:
            if (_tag(blk, "STEPSTYPE") or "") != "dance-single":
                continue
            notes = re.search(r"#NOTES:([^;]*);", blk).group(1)
            charts.append(Chart(_tag(blk, "DIFFICULTY") or "", _tag(blk, "METER") or "",
                                _measures(notes)))
    else:
        for m in re.finditer(r"#NOTES:([^;]*);", text):
            parts = m.group(1).split(":")
            if parts[0].strip() != "dance-single":
                continue
            charts.append(Chart(parts[2].strip(), parts[3].strip(), _measures(parts[5])))
    return head, charts


# DWI: one character per step, 8th notes by default; digits are numpad
# directions (4 left, 2 down, 8 up, 6 right, 7/9/1/3 diagonals pairs).
DWI_ARROWS = {"0": "", "1": "LD", "2": "D", "3": "DR", "4": "L", "6": "R", "7": "LU",
              "8": "U", "9": "UR", "A": "DU", "B": "LR"}
DWI_STEP = {"(": Fraction(1, 4), "[": Fraction(1, 6), "{": Fraction(1, 16), "`": Fraction(1, 48)}
DWI_CLOSE = {")": "(", "]": "[", "}": "{", "'": "`"}
DWI_DIFF = {"BEGINNER": "Beginner", "BASIC": "Easy", "ANOTHER": "Medium",
            "MANIAC": "Hard", "SMANIAC": "Challenge"}


def parse_dwi(text: str) -> tuple[dict, list[Chart]]:
    """DWI charts as Charts. A freeze is 'X!Y' (step X, freeze arrows Y) and
    lasts until that arrow next appears, which is its release."""
    head = {"offset": -float(_tag(text, "GAP") or 0) / 1000,      # GAP = ms to beat 0
            "bpms": "0=" + (_tag(text, "BPM") or "120")}
    charts = []
    for m in re.finditer(r"#SINGLE:(\w+):(\d+):([^;]*);", text):
        diff, meter, body = m.groups()
        body = re.sub(r"\s", "", body)
        beat, step, stack = Fraction(0), Fraction(1, 2), []
        rows: dict[Fraction, list[str]] = {}
        held: set[int] = set()
        i = 0
        while i < len(body):
            ch = body[i]
            if ch in DWI_STEP:
                stack.append(step)
                step = DWI_STEP[ch]
                i += 1
                continue
            if ch in DWI_CLOSE:
                step = stack.pop() if stack else Fraction(1, 2)
                i += 1
                continue
            cols = ["0"] * 4
            arrows = DWI_ARROWS.get(ch, "")
            freeze = ""
            if i + 2 < len(body) and body[i + 1] == "!":
                freeze = DWI_ARROWS.get(body[i + 2], "")
                i += 2
            for a in arrows:
                c = "LDUR".index(a)
                if c in held:                       # next appearance releases the freeze
                    cols[c] = "3"
                    held.discard(c)
                else:
                    cols[c] = "2" if a in freeze else "1"
                    if a in freeze:
                        held.add(c)
            if arrows:
                rows[beat] = cols
            beat += step
            i += 1
        charts.append(Chart(DWI_DIFF.get(diff, diff.title()), meter,
                            [Row(b, "".join(c)) for b, c in sorted(rows.items())]))
    return head, charts


def _measures(body: str) -> list[Row]:
    rows = []
    for mi, meas in enumerate(body.split(",")):
        lines = [l.strip() for l in meas.split() if l.strip()]
        for li, l in enumerate(lines):
            if l != "0000":
                rows.append(Row(Fraction(4 * mi) + Fraction(4 * li, len(lines)), l[:4]))
    return rows


def first_bpm(bpms: str) -> float:
    return float(bpms.split(",")[0].split("=")[1])


def subdivision(beat: Fraction) -> str:
    f = beat - int(beat)
    return {1: "4th", 2: "8th", 4: "16th"}.get(f.denominator, "other (12th/24th...)")


def stats(chart: Chart, bpm: float) -> dict:
    taps = [r for r in chart.rows if any(c in "124" for c in r.cols)]
    n = len(taps)
    if not n:
        return {}
    span_beats = float(taps[-1].beat - taps[0].beat) or 1.0
    arrows = [[i for i, c in enumerate(r.cols) if c in "124"] for r in taps]
    jumps = [len(a) >= 2 for a in arrows]
    out = {"steps (rows)": n,
           "arrows": sum(len(a) for a in arrows),
           "notes/sec": round(n / (span_beats * 60 / bpm), 2),
           "notes/beat": round(n / span_beats, 2)}
    out["subdivisions"] = dict(Counter(subdivision(r.beat) for r in taps).most_common())
    out["panel use L/D/U/R"] = [sum(i in a for a in arrows) for i in range(4)]

    # jumps
    out["jump %"] = round(100 * sum(jumps) / n, 1)
    out["jump types"] = dict(Counter("".join("LDUR"[i] for i in a)
                                     for a in arrows if len(a) >= 2).most_common())
    runs, cur = Counter(), 0
    for j in jumps + [False]:
        if j:
            cur += 1
        elif cur:
            runs[cur] += 1
            cur = 0
    out["jump run lengths"] = dict(sorted(runs.items()))
    gaps = Counter(str(taps[i].beat - taps[i - 1].beat) for i in range(1, n)
                   if jumps[i] and jumps[i - 1])
    out["gap between back-to-back jumps (beats)"] = dict(gaps.most_common())
    alt = sum(1 for i in range(1, n) if jumps[i] and jumps[i - 1]
              and set(arrows[i]) | set(arrows[i - 1]) == {0, 1, 2, 3}
              and not set(arrows[i]) & set(arrows[i - 1]))
    out["[1001][0110] style alternating jump pairs"] = alt

    # jacks: an arrow hit again on the next step within a beat, jumps
    # included ([1000][1100] repeats Left). A
    # step after a rest isn't one, and neither are taps by the free foot
    # while the other foot holds a freeze (it has to use the same arrows)
    singles = [(taps[i], a[0]) for i, a in enumerate(arrows) if len(a) == 1]
    held, start = [], {}
    for r in chart.rows:
        for i, c in enumerate(r.cols):
            if c in "24":
                start[i] = r.beat
            elif c == "3" and i in start:
                held.append((start.pop(i), r.beat))
    jack_runs, cur = Counter(), 1
    for i in range(1, n + 1):
        same = (i < n and set(arrows[i]) & set(arrows[i - 1])
                and taps[i].beat - taps[i - 1].beat <= 1
                and not any(h0 < taps[i - 1].beat and taps[i].beat <= h1 for h0, h1 in held))
        if same:
            cur += 1
        else:
            if cur > 1:
                jack_runs[cur] += 1
            cur = 1
    out["jack run lengths (same arrow N times)"] = dict(sorted(jack_runs.items()))
    trans = Counter()
    for i in range(1, len(singles)):
        a, b = singles[i - 1][1], singles[i][1]
        trans["LDUR"[a] + "LDUR"[b]] += 1
    lr = trans["LR"] + trans["RL"]
    out["L<->R side-to-side % of single-step moves"] = round(100 * lr / max(sum(trans.values()), 1), 1)
    out["top moves"] = dict(trans.most_common(8))

    # flow: maximal runs of single steps with no jacks, then how many arrows they visit
    flow_runs, cur, used = [], [singles[0][1]] if singles else [], None
    for i in range(1, len(singles)):
        close = singles[i][0].beat - singles[i - 1][0].beat <= 1
        if close and singles[i][1] != singles[i - 1][1]:
            cur.append(singles[i][1])
        else:
            flow_runs.append(cur)
            cur = [singles[i][1]]
    flow_runs.append(cur)
    long = [r for r in flow_runs if len(r) >= 4]
    out["flow runs (4+ steps, no jacks)"] = len(long)
    out["flow run avg length"] = round(sum(map(len, long)) / max(len(long), 1), 1)
    out["flow runs touching all 4 arrows %"] = round(100 * sum(len(set(r)) == 4 for r in long)
                                                    / max(len(long), 1))
    walks = 0
    for r in flow_runs:
        for k in range(len(r) - 3):
            w = r[k:k + 4]
            if len(set(w)) == 4 and (w == sorted(w) or w == sorted(w, reverse=True)):
                walks += 1
    out["walk-downs/ups (LDUR in order)"] = walks

    # holds
    holds = []
    open_ = {}
    for r in chart.rows:
        for i, c in enumerate(r.cols):
            if c in "24":
                open_[i] = r.beat
            elif c == "3" and i in open_:
                holds.append((open_.pop(i), r.beat, i))
    out["holds"] = len(holds)
    out["hold lengths (beats)"] = dict(Counter(str(e - s) for s, e, _ in holds).most_common())
    during = []
    for s, e, col in holds:
        inside = [t for t in taps if s < t.beat < e]
        gaps_in = [float(inside[k].beat - inside[k - 1].beat) for k in range(1, len(inside))]
        during.append((float(e - s), len(inside), min(gaps_in) if gaps_in else None))
    out["taps under each hold (len, taps, fastest gap)"] = during[:12]
    # holding Down/Up while the free foot hits both Left and Right means one
    # of those taps crosses the legs, whichever foot holds
    cross = 0
    for s, e, col in holds:
        hit = {i for t in taps if s < t.beat < e for i, c in enumerate(t.cols) if c in "124"}
        cross += col in (1, 2) and {0, 3} <= hit
    out["holds that force a crossover"] = cross
    return out


def audio_match(chart: Chart, head: dict, audio: Path) -> dict:
    import numpy as np
    import librosa
    y, sr = librosa.load(audio, sr=22050, mono=True)
    hop = 256
    _, y_p = librosa.effects.hpss(y)
    env = librosa.onset.onset_strength(y=y_p, sr=sr, hop_length=hop, aggregate=np.median)
    env = env / np.percentile(env, 99)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    bpm = first_bpm(head["bpms"])
    spb = 60 / bpm
    taps = [r for r in chart.rows if any(c in "124" for c in r.cols)]
    times = np.array([float(r.beat) * spb - head["offset"] for r in taps])
    fr = lambda t: np.clip(np.round(t * sr / hop).astype(int), 0, len(env) - 1)
    # onset strength at notes vs. at every 16th slot
    on_note = np.array([env[max(f - 3, 0):f + 4].max() for f in fr(times)])
    grid = np.arange(times[0], times[-1], spb / 4)
    on_grid = np.array([env[max(f - 3, 0):f + 4].max() for f in fr(grid)])
    # density per 4 measures vs loudness
    win = 16 * spb
    edges = np.arange(times[0], times[-1], win)
    dens = [((times >= e) & (times < e + win)).sum() for e in edges]
    loud = [rms[fr(np.array([e]))[0]:fr(np.array([e + win]))[0]].mean() for e in edges]
    corr = float(np.corrcoef(dens, loud)[0, 1]) if len(edges) > 2 else float("nan")
    return {"onset strength at notes / at all 16ths": round(float(on_note.mean() / on_grid.mean()), 2),
            "density vs loudness correlation (per 4 bars)": round(corr, 2),
            "notes per 4 bars": dens}


def radar(chart: Chart, bpm: float, seconds: float) -> dict:
    """StepMania 5's groove radar, same formulas as NoteDataUtil::CalculateRadarValues.

    stream   arrows per second / 7
    voltage  peak arrows in any 8-beat window, as arrows per second / 10
    air      jumps per second
    freeze   holds per second
    chaos    rows on a 16th or finer (quarter-beats, triplets...) per second / 2
    1.0 fills the graph; StepMania draws anything above that as full."""
    seconds = max(seconds, 1.0)
    arrows = []                                    # (beat) per arrow
    jumps = holds = chaos = 0
    for r in chart.rows:
        heads = [c for c in r.cols if c in "124"]
        if not heads:
            continue
        arrows += [r.beat] * len(heads)
        jumps += len(heads) >= 2
        holds += sum(c in "24" for c in r.cols)
        chaos += (r.beat - int(r.beat)).denominator > 2
    last_beat = float(chart.rows[-1].beat) if chart.rows else 0.0
    peak, lo = 0, 0
    for hi in range(len(arrows)):
        while arrows[hi] - arrows[lo] > 8:
            lo += 1
        peak = max(peak, hi - lo + 1)
    return {"stream": len(arrows) / seconds / 7,
            "voltage": peak / 8 * (last_beat / seconds) / 10,
            "air": jumps / seconds,
            "freeze": holds / seconds,
            "chaos": chaos / seconds * 0.5}


def _bar(v: float, width: int = 20) -> str:
    n = int(round(min(v, 1.0) * width))
    return "█" * n + "░" * (width - n) + (" +" if v > 1 else "")


def notes_per_measure(chart: Chart) -> list[int]:
    out: list[int] = []
    for r in chart.rows:
        if any(c in "124" for c in r.cols):
            m = int(r.beat // 4)
            out += [0] * (m + 1 - len(out))
            out[m] += 1
    return out


def report(chart_path: Path, seconds: float, intro: list[str] = (),
           loudness: list[float] | None = None) -> str:
    """Markdown snapshot of every dance-single chart in a file: stats table,
    groove radar bars and a density-over-the-song graph (Mermaid xychart)."""
    head, charts = parse(chart_path)
    bpm = first_bpm(head["bpms"])
    md = [f"# {chart_path.stem}", ""] + list(intro) + [""]
    md += ["## Charts", "",
           "| | " + " | ".join(f"{c.difficulty} ({c.meter})" for c in charts) + " |",
           "|---|" + "---|" * len(charts)]
    st = [stats(c, bpm) for c in charts]
    rows = [("Steps", "steps (rows)"), ("Notes/sec", "notes/sec"), ("Jumps %", "jump %"),
            ("[1001][0110] pairs", "[1001][0110] style alternating jump pairs"),
            ("Holds", "holds"), ("Crossover holds", "holds that force a crossover"),
            ("Left↔Right %", "L<->R side-to-side % of single-step moves"),
            ("Flow runs", "flow runs (4+ steps, no jacks)"),
            ("Walk-downs", "walk-downs/ups (LDUR in order)")]
    for label, key in rows:
        md.append(f"| {label} | " + " | ".join(str(x.get(key, "")) for x in st) + " |")
    md.append("| Beat / half / quarter-beat | " + " | ".join(
        "{} / {} / {}".format(*(x.get("subdivisions", {}).get(k, 0) for k in ("4th", "8th", "16th")))
        for x in st) + " |")
    md.append("| Jacks (2x/3x/4x+) | " + " | ".join(
        "{} / {} / {}".format(*(lambda j: (j.get(2, 0), j.get(3, 0), sum(v for k, v in j.items() if k >= 4)))(
            x.get("jack run lengths (same arrow N times)", {}))) for x in st) + " |")

    md += ["", "## Groove radar", "",
           "StepMania 5 formulas; a full bar is 1.0 (what the in-game graph tops out at).", ""]
    for c in charts:
        rv = radar(c, bpm, seconds)
        md += [f"**{c.difficulty} ({c.meter})**", "```"]
        md += [f"{k:<8} {_bar(v)} {v:.2f}" for k, v in rv.items()]
        md += ["```", ""]

    md += ["## Notes per measure", ""]
    dens = [notes_per_measure(c) for c in charts]
    n = max(map(len, dens)) if dens else 0
    md += ["```mermaid", "xychart-beta", '    title "Notes per measure"',
           f'    x-axis "measure" 1 --> {max(n, 2)}', '    y-axis "notes"']
    for c, d in zip(charts, dens):
        md.append(f"    line [{', '.join(str(v) for v in d + [0] * (n - len(d)))}]")
    md += ["```", "", "Lines in order: " + ", ".join(c.difficulty for c in charts) + "."]
    if loudness:
        md += ["", "Song loudness per measure:", "```",
               "".join(" ▁▂▃▄▅▆▇█"[min(8, int(v * 8.99))] for v in loudness), "```"]
    md += ["", "Density per measure (each row a difficulty, darker = more notes):", "```"]
    top = max((max(d) for d in dens if d), default=1)
    for c, d in zip(charts, dens):
        md.append(f"{c.difficulty[:6]:<6} " + "".join(" ▁▂▃▄▅▆▇█"[min(8, int(v / top * 8.99))] for v in d))
    md += ["```", ""]
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("chart", type=Path)
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--report", type=Path, help="also write a Markdown snapshot here")
    args = ap.parse_args()
    head, charts = parse(args.chart)
    bpm = first_bpm(head["bpms"])
    for ch in charts:
        print(f"== {ch.difficulty} ({ch.meter})  {bpm:g} BPM")
        for k, v in stats(ch, bpm).items():
            print(f"  {k}: {v}")
        if args.audio:
            for k, v in audio_match(ch, head, args.audio).items():
                print(f"  {k}: {v}")
        rv = radar(ch, bpm, _seconds(ch, head, args.audio))
        print("  groove radar: " + "  ".join(f"{k} {v:.2f}" for k, v in rv.items()))
    if args.report:
        sec = _seconds(charts[0], head, args.audio) if charts else 1.0
        args.report.write_text(report(args.chart, sec), encoding="utf-8")
        print(f"-> {args.report}")


def _seconds(chart: Chart, head: dict, audio: Path | None) -> float:
    if audio:
        import soundfile as sf
        try:
            return sf.info(str(audio)).duration
        except Exception:
            import librosa
            return librosa.get_duration(path=str(audio))
    last = max((float(r.beat) for r in chart.rows), default=0.0)
    return last * 60 / first_bpm(head["bpms"]) - head["offset"]


if __name__ == "__main__":
    main()
