"""Pictures of a few bars of arrows, as SVG (with PNG copies), drawn the way
StepMania shows them: four lanes, time going down, arrows coloured by note
length (beat red, half-beat blue, quarter-beat yellow), freezes in green.

    python dialtest.py images      # every comparison in docs/img/
"""
from __future__ import annotations

import html
from pathlib import Path

import numpy as np

import harness
from harness import stepgen

R = stepgen.ROWS_PER_BEAT
DOCS = harness.STEPGEN_DIR / "docs"
IMG = DOCS / "img"

# a left-pointing arrow in a 64 x 64 box; the other lanes are this rotated
ARROW = "M5 32 L29 8 Q32 5 35 8 L39 12 Q42 15 39 18 L30 26 L57 26 Q61 26 61 30 L61 34 Q61 38 57 38 L30 38 L39 46 Q42 49 39 52 L35 56 Q32 59 29 56 Z"
ROTATE = {0: 0, 1: -90, 2: 90, 3: 180}            # Left, Down, Up, Right
SNAP = {0: ("#ff4b5c", "#a3121f"),                 # beat (4th)
        2: ("#4d8dff", "#1b3f99"),                 # half-beat (8th)
        1: ("#ffd23f", "#9c7a00"), 3: ("#ffd23f", "#9c7a00")}   # quarter-beat (16th)
HOLD = ("#4fdc7a", "#1f7a3c")
BG, LANE, BEAT_LINE, BAR_LINE, TEXT, SUB = "#14161c", "#1d2029", "#2a2e3a", "#5a6075", "#eef0f6", "#9aa1b5"

LANE_W, BEAT_H, PAD_TOP, PAD_SIDE, ARROW_PX = 48, 44, 76, 34, 40


def bars_to_show(song: harness.Song, n: int = 4) -> int:
    """First bar of n bars worth showing: the loudest returning chorus if
    the song repeats one, else the loudest n bars; starts on a phrase."""
    a = song.a
    inten = a.intensity
    best, start = -1.0, 0
    cands = [t + k for t, _s, length in song.repeats for k in range(0, max(1, length - n + 1), 4)]
    if not cands:
        cands = list(range(0, max(1, len(inten) - n), 4))
    for m in cands:
        v = float(np.mean(inten[m:m + n])) if m + n <= len(inten) else -1
        if v > best:
            best, start = v, m
    return int(start)


def _arrow(x: float, y: float, panel: int, row: int, size: float = ARROW_PX, hold: bool = False) -> str:
    fill, edge = HOLD if hold else SNAP[row % R]
    s = size / 64
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.3f}) rotate({ROTATE[panel]}) translate(-32,-32)">'
            f'<path d="{ARROW}" fill="{fill}" stroke="{edge}" stroke-width="5" stroke-linejoin="round"/>'
            f'<path d="{ARROW}" fill="none" stroke="#ffffff" stroke-opacity=".45" stroke-width="2" '
            f'transform="translate(32,32) scale(.72) translate(-32,-32)"/></g>')


def _receptor(x: float, y: float, panel: int) -> str:
    s = ARROW_PX / 64
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.3f}) rotate({ROTATE[panel]}) translate(-32,-32)">'
            f'<path d="{ARROW}" fill="none" stroke="{SUB}" stroke-width="4" stroke-linejoin="round"/></g>')


def column(notes: list, bar0: int, n_bars: int, x0: float, title: str, sub: str = "") -> tuple[str, float]:
    """One chart's lanes for bars bar0..bar0+n_bars as SVG elements, with a
    title above; returns (svg, width)."""
    w = 4 * LANE_W
    h = n_bars * 4 * BEAT_H
    out = [f'<rect x="{x0}" y="{PAD_TOP}" width="{w}" height="{h}" rx="6" fill="{LANE}"/>']
    for b in range(n_bars * 4 + 1):
        y = PAD_TOP + b * BEAT_H
        col, sw = (BAR_LINE, 1.5) if b % 4 == 0 else (BEAT_LINE, 1)
        out.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{y}" y2="{y}" stroke="{col}" stroke-width="{sw}"/>')
    out.append(f'<text x="{x0 + w / 2}" y="22" fill="{TEXT}" font-size="15" font-weight="600" '
               f'text-anchor="middle">{html.escape(title)}</text>')
    for k, line in enumerate(sub.split("\n") if sub else []):
        out.append(f'<text x="{x0 + w / 2}" y="{40 + 14 * k}" fill="{SUB}" font-size="11.5" '
                   f'text-anchor="middle">{html.escape(line)}</text>')
    r0, r1 = bar0 * 16, (bar0 + n_bars) * 16
    cx = lambda p: x0 + LANE_W * (p + 0.5)
    cy = lambda r: PAD_TOP + (r - r0) / R * BEAT_H
    holds, heads = [], []
    for nt in sorted(notes, key=lambda n: n.row):
        end = nt.row + nt.hold_rows
        if end < r0 or nt.row >= r1:
            continue
        for p in nt.panels:
            if nt.hold_rows:
                y1, y2 = max(cy(nt.row), PAD_TOP), min(cy(end), PAD_TOP + h)
                holds.append(f'<rect x="{cx(p) - 11}" y="{y1:.1f}" width="22" height="{max(0, y2 - y1):.1f}" '
                             f'rx="5" fill="{HOLD[0]}" fill-opacity=".55" stroke="{HOLD[1]}" stroke-width="1.5"/>')
                if end < r1:
                    holds.append(f'<rect x="{cx(p) - 13}" y="{y2 - 4:.1f}" width="26" height="8" rx="3" '
                                 f'fill="{HOLD[0]}" stroke="{HOLD[1]}" stroke-width="1.5"/>')
            if nt.row >= r0:
                heads.append(_arrow(cx(p), cy(nt.row), p, nt.row, hold=bool(nt.hold_rows)))
    return "".join(out + holds + heads), w


def comparison(panels: list[tuple[str, str, list]], bar0: int, n_bars: int = 4,
               heading: str = "", note: str = "") -> str:
    """Several charts side by side, the same bars: [(title, subtitle, notes)]."""
    gap = 26
    cols, x = [], PAD_SIDE
    for title, sub, notes in panels:
        svg, w = column(notes, bar0, n_bars, x, title, sub)
        cols.append(svg)
        x += w + gap
    width = x - gap + PAD_SIDE // 2
    height = PAD_TOP + n_bars * 4 * BEAT_H + (34 if note else 14)
    labels = "".join(f'<text x="{PAD_SIDE - 8}" y="{PAD_TOP + b * 4 * BEAT_H + 14}" fill="{SUB}" font-size="11" '
                     f'text-anchor="end">{bar0 + b + 1}</text>' for b in range(n_bars))
    foot = (f'<text x="{PAD_SIDE}" y="{height - 12}" fill="{SUB}" font-size="11.5">{html.escape(note)}</text>'
            if note else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
            f'<title>{html.escape(heading)}</title>'
            f'<rect width="100%" height="100%" rx="10" fill="{BG}"/>{labels}{"".join(cols)}{foot}</svg>')


def legend() -> str:
    items = [("Beat (4th)", 0, False), ("Half-beat (8th)", 2, False), ("Quarter-beat (16th)", 1, False)]
    x, parts = 16, []
    for label, row, _ in items:
        parts.append(_arrow(x + 14, 22, 2, row, 26))
        parts.append(f'<text x="{x + 34}" y="27" fill="{TEXT}" font-size="13">{label}</text>')
        x += 34 + 8 * len(label) + 22
    parts.append(f'<rect x="{x + 6}" y="10" width="16" height="24" rx="5" fill="{HOLD[0]}" fill-opacity=".55" '
                 f'stroke="{HOLD[1]}" stroke-width="1.5"/>')
    parts.append(f'<text x="{x + 30}" y="27" fill="{TEXT}" font-size="13">Freeze (hold)</text>')
    x += 30 + 8 * 13 + 16
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{x}" height="44" viewBox="0 0 {x} 44" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif"><rect width="100%" height="100%" rx="8" '
            f'fill="{BG}"/>{"".join(parts)}</svg>')


def to_png(svg_path: Path) -> Path | None:
    """A PNG copy at 2x, for places that don't show SVG."""
    png = svg_path.with_suffix(".png")
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(png), scale=2)
        return png
    except Exception:
        pass
    try:
        from playwright.sync_api import sync_playwright
        svg = svg_path.read_text(encoding="utf-8")
        import re
        w, h = (int(float(v)) for v in re.search(r'width="([\d.]+)" height="([\d.]+)"', svg).groups())
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            pg.set_content(f"<html><body style='margin:0;background:transparent'>{svg}</body></html>")
            pg.screenshot(path=str(png), omit_background=True)
            b.close()
        return png
    except Exception as e:
        print(f"  (no PNG for {svg_path.name}: {e})")
        return None


# --------------------------------------------------------------------------
# the comparisons shown in the docs
# --------------------------------------------------------------------------

FEEL_LABELS = {
    "energy": ("Energy / arc", "flat", "dramatic"), "jumps": ("Jumps", "none", "lots"),
    "speed": ("Speed", "on the beat", "busy, more 16ths"),
    "breathing": ("Breathing room", "nonstop runs", "pauses and stomps"),
    "footwork": ("Footwork", "simple", "technical"), "holds": ("Holds", "none", "lots"),
    "repetition": ("Repetition", "always fresh", "choruses identical"),
}


def _sub(song, notes) -> str:
    n = len(notes)
    j = sum(len(x.panels) > 1 for x in notes)
    h = sum(1 for x in notes if x.hold_rows)
    return (f"meter {stepgen.estimate_meter(notes, song.a.spb):.1f} · {n} steps\n"
            f"{100 * j / max(n, 1):.0f}% jumps · {h} freezes")


def sets_to_draw():
    """(file name, heading, [(column title, Config)]) for every picture."""
    C = harness.Config
    hard = dict(profile="konami", seed=1)
    out = []
    for s, (label, lo, hi) in FEEL_LABELS.items():
        out.append((f"feel-{s}", f"{label}: 25% / 50% / 75%",
                    [(f"{label} {v}%", C(**hard, feel=((s, v),))) for v in (25, 50, 75)]))
    out.append(("groove", "Groove: off / 25% / 50% / 75%",
                [(f"Groove {'off' if v == 0 else f'{v}%'}", C(**hard, groove=v)) for v in (0, 25, 50, 75)]))
    out.append(("difficulty", "Hard aimed at 3 / 5 / 7 / 9",
                [(f"Difficulty {m}", C(**hard, targets=(("Easy", 3.0), ("Medium", 6.0), ("Hard", float(m)))))
                 for m in (3, 5, 7, 9)]))
    out.append(("follow", "Arrows follow: the beat / 50% / the tune",
                [(f"Follow {v}%", C(**hard, follow=v)) for v in (0, 50, 100)]))
    out.append(("ai", "Steps placed by: rules / 50% / AI model",
                [(f"AI assist {v}%", C(**hard, ai=v)) for v in (0, 50, 100)]))
    out.append(("targets-off", "No target: the profile's own Hard at Speed 25 / 50 / 75%",
                [(f"Speed {v}%, no target", C(**hard, targets=None, feel=(("speed", v),))) for v in (25, 50, 75)]))
    return out


def all_images(song_path: Path, song_name: str, diff: str = "Hard"):
    IMG.mkdir(parents=True, exist_ok=True)
    song = harness.load_song(song_path, song_name.replace(" ", "_").lower())
    bar0 = bars_to_show(song)
    (IMG / "legend.svg").write_text(legend(), encoding="utf-8")
    to_png(IMG / "legend.svg")
    made = {}
    for fname, heading, cols in sets_to_draw():
        panels = []
        for title, cfg in cols:
            ch = [c for c in harness.make_charts(song, cfg) if c.diff == diff][0]
            panels.append((title, _sub(song, ch.notes), ch.notes))
        note = f"{song_name}, {diff}, konami profile, seed 1, bars {bar0 + 1}-{bar0 + 4}"
        p = IMG / f"{fname}.svg"
        p.write_text(comparison(panels, bar0, 4, heading, note), encoding="utf-8")
        to_png(p)
        made[fname] = p
        print(f"  {p.relative_to(harness.STEPGEN_DIR)}")
    return made
