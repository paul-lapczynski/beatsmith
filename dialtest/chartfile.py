"""Read StepMania charts (.sm, .ssc, .dwi) for find-preset.

Per dance-single chart: the beats and seconds of every step (taps, hold and
roll heads, lifts), which panels, and the song's timing. Mines, fakes and
tails are ignored. Only reads; nothing is written next to the charts.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_EXT = (".ogg", ".mp3", ".wav", ".flac", ".oga")

# every name packs use for a difficulty -> one of ours
DIFF_NAMES = {
    "beginner": "beginner",
    "basic": "easy", "light": "easy", "easy": "easy",
    "another": "medium", "trick": "medium", "standard": "medium", "medium": "medium",
    "maniac": "hard", "heavy": "hard", "hard": "hard",
    "smaniac": "challenge", "challenge": "challenge", "oni": "challenge", "expert": "challenge",
    "edit": "edit",
}


class GimmickTiming(Exception):
    """Warps, negative BPMs or stops: timing we drop rather than guess at."""


@dataclass
class Timing:
    offset: float                          # #OFFSET: beat 0 is at -offset seconds
    bpms: list[tuple[float, float]]        # (beat, bpm), sorted, first at beat 0
    stops: list[tuple[float, float]] = field(default_factory=list)   # (beat, seconds), after the beat's notes
    delays: list[tuple[float, float]] = field(default_factory=list)  # (beat, seconds), before the beat's notes

    def __post_init__(self):
        if not self.bpms:
            raise GimmickTiming("no BPM")
        self.bpms.sort()
        if self.bpms[0][0] > 0:
            self.bpms.insert(0, (0.0, self.bpms[0][1]))
        if any(b <= 0 for _, b in self.bpms) or any(s < 0 for _, s in self.stops + self.delays):
            raise GimmickTiming("negative BPM or stop")
        # seconds at the start of each BPM segment, before stops
        self._seg_beats = [b for b, _ in self.bpms]
        self._seg_secs = [0.0]
        for (b0, bpm), (b1, _) in zip(self.bpms, self.bpms[1:]):
            self._seg_secs.append(self._seg_secs[-1] + (b1 - b0) * 60.0 / bpm)

    def seconds(self, beat: float) -> float:
        i = bisect_right(self._seg_beats, beat) - 1
        b0, bpm = self.bpms[max(i, 0)]
        t = self._seg_secs[max(i, 0)] + (beat - b0) * 60.0 / bpm
        t += sum(s for b, s in self.stops if b < beat - 1e-6)
        t += sum(s for b, s in self.delays if b <= beat + 1e-6)
        return t - self.offset

    def main_bpm(self, last_beat: float) -> float:
        """The BPM held for the most beats, for the meter estimate."""
        spans: dict[float, float] = {}
        ends = [b for b, _ in self.bpms[1:]] + [max(last_beat, self.bpms[-1][0])]
        for (b0, bpm), b1 in zip(self.bpms, ends):
            spans[round(bpm, 2)] = spans.get(round(bpm, 2), 0) + max(b1 - b0, 0)
        return max(spans, key=spans.get)


@dataclass
class Chart:
    difficulty: str        # beginner / easy / medium / hard / challenge / edit
    raw_difficulty: str    # as the file says it
    meter: int             # the pack's own number
    credit: str
    beats: list[float]     # beat of each step row, sorted
    panels: list[list[int]]  # panels stepped on per row (0 L, 1 D, 2 U, 3 R)
    holds: list[bool]      # does the row start a hold or roll
    timing: Timing

    def times(self) -> list[float]:
        return [self.timing.seconds(b) for b in self.beats]


@dataclass
class Song:
    path: Path             # the chart file
    title: str
    artist: str
    music: Path | None
    charts: list[Chart]
    stepgen: bool          # made by stepgen (any chart, or a .stepgen.json beside it)


def _tags(text: str) -> list[tuple[str, str]]:
    text = re.sub(r"//[^\n]*", "", text)
    return [(m.group(1).upper(), m.group(2)) for m in re.finditer(r"#([A-Za-z0-9]+):([^;]*);?", text)]


def _pairs(value: str) -> list[tuple[float, float]]:
    out = []
    for part in value.split(","):
        if "=" in part:
            a, b = part.split("=", 1)[:2]
            try:
                out.append((float(a.strip()), float(b.strip().split("=")[0])))
            except ValueError:
                pass
    return out


def _float(s: str, default: float = 0.0) -> float:
    try:
        return float(s.strip())
    except ValueError:
        return default


def _int(s: str) -> int:
    try:
        return int(float(s.strip()))
    except ValueError:
        return 0


def _find_audio(folder: Path, named: str) -> Path | None:
    files = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    if named and named.strip().lower() in files:
        p = files[named.strip().lower()]
        if p.suffix.lower() in AUDIO_EXT:
            return p
    audio = sorted(p for p in files.values() if p.suffix.lower() in AUDIO_EXT)
    return audio[0] if audio else None


def _sm_notes(body: str) -> tuple[list[float], list[list[int]], list[bool]]:
    """Measures of rows -> step beats. Only the first 4 columns (dance-single)."""
    beats, panels, holds = [], [], []
    body = re.sub(r"//[^\n]*", "", body)
    for m, measure in enumerate(body.split(",")):
        rows = [r.strip() for r in measure.split() if r.strip()]
        for i, row in enumerate(rows):
            cols = [j for j, c in enumerate(row[:4]) if c in "124L"]
            if cols:
                beats.append(m * 4 + i * 4 / len(rows))
                panels.append(cols)
                holds.append(any(row[j] in "24" for j in cols))
    return beats, panels, holds


def _timing_from(tags: dict[str, str], base: Timing | None = None) -> Timing:
    if _pairs(tags.get("WARPS", "")):
        raise GimmickTiming("warps")
    if base is not None and not any(k in tags for k in ("OFFSET", "BPMS", "STOPS", "DELAYS")):
        return base
    return Timing(offset=_float(tags.get("OFFSET", "0")) if "OFFSET" in tags or base is None else base.offset,
                  bpms=_pairs(tags.get("BPMS", "")) if "BPMS" in tags or base is None else list(base.bpms),
                  stops=_pairs(tags.get("STOPS", tags.get("FREEZES", ""))) if "STOPS" in tags or base is None
                  else list(base.stops),
                  delays=_pairs(tags.get("DELAYS", "")) if "DELAYS" in tags or base is None
                  else list(base.delays))


def read_sm(path: Path) -> Song:
    text = path.read_text(encoding="utf-8", errors="replace")
    tags = _tags(text)
    head = {k: v for k, v in tags if k != "NOTES"}
    timing = _timing_from(head)
    charts = []
    for k, v in tags:
        if k != "NOTES":
            continue
        f = v.split(":")
        if len(f) < 6 or f[0].strip() != "dance-single":
            continue
        raw = f[2].strip()
        beats, panels, holds = _sm_notes(f[5])
        charts.append(Chart(DIFF_NAMES.get(raw.lower(), "edit"), raw, _int(f[3]), f[1].strip(),
                            beats, panels, holds, timing))
    return _song(path, head, charts, text)


def read_ssc(path: Path) -> Song:
    text = path.read_text(encoding="utf-8", errors="replace")
    head_text, *blocks = re.split(r"#NOTEDATA:[^;]*;", text)
    head = dict(_tags(head_text))
    try:
        timing = _timing_from(head)
    except GimmickTiming as e:
        if "warps" in str(e):
            raise
        timing = None                      # every chart carries its own timing
    charts = []
    for blk in blocks:
        t = dict(_tags(blk))
        if t.get("STEPSTYPE", "").strip() != "dance-single":
            continue
        raw = t.get("DIFFICULTY", "").strip()
        beats, panels, holds = _sm_notes(t.get("NOTES", ""))
        charts.append(Chart(DIFF_NAMES.get(raw.lower(), "edit"), raw, _int(t.get("METER", "0")),
                            (t.get("CREDIT", "") + " " + t.get("DESCRIPTION", "")).strip(),
                            beats, panels, holds, _timing_from(t, timing)))
    return _song(path, head, charts, text)


# DWI panels: 4 L, 2 D, 8 U, 6 R, combos for jumps; 1/3/7/9 are corners (none in single)
_DWI = {"0": [], "1": [0, 1], "2": [1], "3": [1, 3], "4": [0], "6": [3], "7": [0, 2], "8": [2],
        "9": [2, 3], "A": [1, 2], "B": [0, 3]}
_DWI_STEP = {"(": 1 / 4, "[": 1 / 6, "{": 1 / 16, "`": 1 / 48}   # beats per char inside the brackets
_DWI_END = {")": "(", "]": "[", "}": "{", "'": "`"}


def _dwi_notes(steps: str) -> tuple[list[float], list[list[int]], list[bool]]:
    beats, panels, holds = [], [], []
    steps = re.sub(r"\s", "", steps)
    beat, step, i = 0.0, 0.5, 0          # default: one char per 8th note
    while i < len(steps):
        c = steps[i]
        if c in _DWI_STEP:
            step = _DWI_STEP[c]
        elif c in _DWI_END:
            step = 0.5
        elif c == "<":                   # all chars up to > land on one row
            j = steps.find(">", i)
            if j < 0:
                break
            cols, held = set(), False
            k = i + 1
            while k < j:
                cols.update(_DWI.get(steps[k].upper(), []))
                if k + 1 < j and steps[k + 1] == "!":
                    held, k = True, k + 2
                k += 1
            if cols:
                beats.append(beat), panels.append(sorted(cols)), holds.append(held)
            beat += step
            i = j
        else:
            cols = _DWI.get(c.upper(), [])
            held = i + 1 < len(steps) and steps[i + 1] == "!"
            if held:
                i += 2                   # "8!8": the char after ! says which arrows hold
            if cols:
                beats.append(beat), panels.append(cols), holds.append(held)
            beat += step
        i += 1
    return beats, panels, holds


def read_dwi(path: Path) -> Song:
    text = path.read_text(encoding="utf-8", errors="replace")
    tags = _tags(text)
    head = {k: v for k, v in tags if k not in ("SINGLE", "DOUBLE", "COUPLE", "SOLO")}
    bpm = _float(head.get("BPM", "0"))
    # CHANGEBPM and FREEZE positions are in 16th notes, freeze lengths in ms
    changes = [(b / 4, v) for b, v in _pairs(head.get("CHANGEBPM", ""))]
    freezes = [(b / 4, ms / 1000) for b, ms in _pairs(head.get("FREEZE", ""))]
    timing = Timing(offset=-_float(head.get("GAP", "0")) / 1000,   # GAP = ms until beat 0
                    bpms=[(0.0, bpm)] + changes, stops=freezes)
    charts = []
    for k, v in tags:
        if k != "SINGLE":
            continue
        f = v.split(":")
        if len(f) < 3:
            continue
        raw = f[0].strip()
        beats, panels, holds = _dwi_notes(f[2])
        charts.append(Chart(DIFF_NAMES.get(raw.lower(), "edit"), raw, _int(f[1]), "",
                            beats, panels, holds, timing))
    head.setdefault("MUSIC", head.get("FILE", ""))
    return _song(path, head, charts, text)


def _song(path: Path, head: dict[str, str], charts: list[Chart], text: str) -> Song:
    folder = path.parent
    stepgen = "stepgen" in text.lower() or any(p.name.lower().endswith(".stepgen.json") for p in folder.iterdir())
    return Song(path, head.get("TITLE", "").strip() or folder.name, head.get("ARTIST", "").strip(),
                _find_audio(folder, head.get("MUSIC", "")), charts, stepgen)


def chart_file(folder: Path) -> Path | None:
    """The chart file StepMania would read: .ssc over .sm over .dwi."""
    files = [p for p in folder.iterdir() if p.is_file()]
    for ext in (".ssc", ".sm", ".dwi"):
        hits = sorted(p for p in files if p.suffix.lower() == ext)
        if hits:
            return hits[0]
    return None


def read(path: Path) -> Song:
    return {".ssc": read_ssc, ".sm": read_sm, ".dwi": read_dwi}[path.suffix.lower()](path)
