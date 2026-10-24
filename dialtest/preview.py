"""docs/preview.html: a one-file page with a slider per control. Moving it
swaps in the 4 bars stepgen made at that setting (pre-made here, nine
positions per slider) next to the same bars at the default, and Play runs
the song under them with a tick on every step.

    python dialtest.py preview [--song "Stepgen Demo"]
"""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from pathlib import Path

import harness
import render
from harness import FEEL, stepgen

R = stepgen.ROWS_PER_BEAT
POS = [0, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
TEMPLATE = Path(__file__).with_name("preview_template.html")


def dial_list():
    """(key, label, low end, high end, [(position label, Config)], default index, what it moves)."""
    C = harness.Config
    out = []
    for s in FEEL:
        label, lo, hi = render.FEEL_LABELS[s]
        moves = ", ".join(k for k, _, _ in stepgen.EASY_SLIDERS[s])
        out.append((s, label, lo, hi, [(f"{p:g}%", C(feel=((s, p),))) for p in POS], 4, moves))
    out.append(("groove", "Groove", "off", "made to groove",
                [("off" if p == 0 else f"{p:g}%", C(groove=p)) for p in POS], 0,
                ", ".join(k for k, _, _ in stepgen.EASY_SLIDERS["groove"])))
    out.append(("difficulty", "Difficulty", "1", "10",
                [(f"{m}", C(targets=(("Easy", float(m)), ("Medium", float(m)), ("Hard", float(m)))))
                 for m in range(1, 11)], 7,
                "density, max_nps, jump, hold_rate, half_beats, grid, quarter_beats, flow_spice, 16th streams"))
    out.append(("follow", "Arrows follow", "the beat", "the tune",
                [(f"{p:g}%", C(follow=p)) for p in POS], 0, "melody_follow"))
    out.append(("ai", "Steps placed by", "stepgen's rules", "the AI model",
                [(f"{p:g}%", C(ai=p)) for p in POS], 0, "ai_assist"))
    return out


def clip_notes(notes, bar0: int, n_bars: int = 4):
    r0, r1 = bar0 * 16, (bar0 + n_bars) * 16
    out = []
    for nt in sorted(notes, key=lambda n: n.row):
        if r0 <= nt.row < r1:
            mask = sum(1 << p for p in nt.panels)
            out.append([nt.row - r0, mask, min(nt.hold_rows, r1 - nt.row)])
    return out


def stats(song, notes) -> dict:
    n = max(len(notes), 1)
    rows = [x.row for x in notes]
    try:
        g = round(stepgen.groove_of(song.a, notes, song.onset).total)
    except Exception:
        g = None
    return {"meter": round(stepgen.estimate_meter(notes, song.a.spb), 1), "steps": len(notes),
            "jumps": round(100 * sum(len(x.panels) > 1 for x in notes) / n),
            "freezes": sum(1 for x in notes if x.hold_rows),
            "eighths": round(100 * sum(r % R == R // 2 for r in rows) / n),
            "sixteenths": round(100 * sum(r % 2 == 1 for r in rows) / n, 1), "groove": g}


def audio_clip(path: Path, start: float, end: float) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(path),
                        "-ac", "2", "-b:a", "128k", "-af", "afade=t=out:st={:.3f}:d=0.25".format(end - start - 0.25),
                        str(out)], check=True)
        return base64.b64encode(out.read_bytes()).decode()


def main(song_path: Path, song_name: str):
    song = harness.load_song(song_path, song_name.replace(" ", "_").lower())
    a = song.a
    bar0 = render.bars_to_show(song)
    lead = 1                                     # one bar of music before the 4 shown
    t_start = a.t0 + (bar0 - lead) * 4 * a.spb
    t_end = a.t0 + (bar0 + 4) * 4 * a.spb + 0.3
    t_start = max(0.0, t_start)
    summary = {}
    sp = harness.HERE / "summary.json"
    if sp.is_file():
        summary = json.loads(sp.read_text(encoding="utf-8")).get("ratings", {})
    dials = []
    cache = {}
    for key, label, lo, hi, positions, default, moves in dial_list():
        pos_data = []
        for plabel, cfg in positions:
            if cfg not in cache:
                cache[cfg] = harness.make_charts(song, cfg)
            charts = {c.diff: c for c in cache[cfg]}
            pos_data.append({"label": plabel, "charts": {
                d: {"notes": clip_notes(c.notes, bar0), "stats": stats(song, c.notes)} for d, c in charts.items()}})
        r = summary.get(key, {})
        dials.append({"key": key, "label": label, "lo": lo, "hi": hi, "default": default, "moves": moves,
                      "grade": r.get("grade"), "positions": pos_data})
        print(f"  {label}: {len(positions)} positions")
    data = {"song": song_name, "bpm": round(a.bpm, 2), "bar0": bar0, "lead": lead,
            "spb": a.spb, "clipStart": t_start, "beat0": a.t0 + bar0 * 4 * a.spb - t_start,
            "profile": "konami", "audio": audio_clip(song.path, t_start, t_end), "dials": dials}
    (harness.WORK / "preview-data.json").write_text(json.dumps(data), encoding="utf-8")
    return write_html(data)


def write_html(data: dict) -> Path:
    """The page from the data (also used to restyle it without making the charts again:
    write_html(json.load(open(WORK / "preview-data.json"))))."""
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    out = render.DOCS / "preview.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    # a whole page for GitHub Pages or opening from disk; the bare body is
    # what gets published as an Artifact (the host adds the skeleton)
    out.write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                   '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                   + html + "\n</html>\n", encoding="utf-8")
    harness.WORK.joinpath("preview-artifact.html").write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return out
