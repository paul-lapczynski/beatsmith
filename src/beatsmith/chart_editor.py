"""Chart editor for BeatSmith: play the song, watch the steps scroll, and edit
them with the mouse or the keyboard.

Runs as the app's Edit tab, or on its own:  python chart_editor.py song.sm

Mouse
  click an empty spot ........ add a step (snapped to the current snap)
  drag down from an empty spot  add a freeze arrow (hold) of that length
  click a step ............... select it (Ctrl+click adds to the selection)
  drag a selected step ....... move the selection (up/down in time, left/right
                               across arrows)
  right-click a step ......... delete it (or the whole selection it's in)
  drag in the beat ruler ..... select every step between two beats
  Shift+drag anywhere ........ box-select
  wheel / Ctrl+wheel ......... scroll / zoom

Keyboard
  Up/Down, PgUp/PgDn ......... move the cursor by the snap / by a measure
  Left/Right ................. snap 1/4 <-> 1/8 <-> 1/12 <-> 1/16 <-> 1/24 <-> 1/32
  1 2 3 4 .................... toggle Left/Down/Up/Right at the cursor; keep
                               the key held and press Down to stretch a hold
  Shift+Up/Down .............. select from where you started
  Ctrl+C / Ctrl+X / Ctrl+V ... copy / cut / paste at the cursor
  Ctrl+D ..................... duplicate the selection right after itself
  Ctrl+Up/Down ............... move the selection by the snap
  M .......................... mirror the selection (Left<->Right)
  Delete ..................... delete the selection
  Ctrl+A / Esc ............... select all / clear selection
  Ctrl+Z / Ctrl+Y ............ undo / redo
  Space ...................... play / pause from the cursor
  Ctrl+S ..................... save (the first save keeps a .bak of the file)
"""
from __future__ import annotations

from beatsmith.resources import bundle_root

import math
from collections import Counter
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from beatsmith.layout import find_sm, out_of, outer_of, side
from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget,
)

TPB = 48                    # ticks per beat: fine enough for 1/12, 1/16, 1/24, 1/32
TPM = TPB * 4               # ticks per measure
LEAD_IN = 3.0               # seconds of play test before the cursor
SNAPS = [("1/4", 48), ("1/8", 24), ("1/12", 16), ("1/16", 12), ("1/24", 8), ("1/32", 6)]
COLS = 4
LANE_NAMES = ("Left", "Down", "Up", "Right")
ARROW_ANGLE = (-90, 180, 0, 90)          # the shape points up; rotate per lane

# arrow colour by where the step falls (StepMania's note colours)
def quant_color(tick: int) -> QColor:
    for step, col in ((48, "#e8433f"), (24, "#3f7fe8"), (16, "#a55be8"), (12, "#e8c93f"),
                      (8, "#e85bb4"), (6, "#e8933f")):
        if tick % step == 0:
            return QColor(col)
    return QColor("#7fd16b")


# ---------------------------------------------------------------- .sm file

@dataclass(frozen=True)
class Step:
    tick: int
    col: int
    kind: str = "1"         # 1 tap, 2 hold, 4 roll, M mine
    length: int = 0         # hold/roll length in ticks

    @property
    def end(self) -> int:
        return self.tick + self.length


@dataclass
class ChartInfo:
    stype: str
    desc: str
    diff: str
    meter: str
    radar: str
    span: tuple[int, int]           # where the note data sits in the file text
    steps: list[Step]

    @property
    def label(self) -> str:
        return f"{self.diff} ({self.meter})" + ("" if self.stype == "dance-single" else f" [{self.stype}]")


class SMFile:
    def __init__(self, path: Path):
        self.path = path
        self.text = path.read_text(encoding="utf-8", errors="replace")
        self.tags = {m.group(1).upper(): m.group(2).strip()
                     for m in re.finditer(r"#([A-Za-z]+):([^;]*);", self.text) if m.group(1).upper() != "NOTES"}
        self.offset = float(self.tags.get("OFFSET", "0") or 0)
        self.bpms = sorted((float(b), float(v)) for b, v in
                           (p.split("=") for p in self.tags.get("BPMS", "0=120").split(",") if "=" in p))
        self.has_stops = bool(self.tags.get("STOPS", "").strip())
        self.charts = self._charts()

    def music_path(self) -> Path | None:
        m = self.tags.get("MUSIC", "")
        p = self.path.parent / m
        if m and p.is_file():
            return p
        for ext in (".ogg", ".mp3", ".wav", ".flac"):
            for f in self.path.parent.glob(f"*{ext}"):
                if not f.name.endswith(".clicks.wav"):
                    return f
        return None

    def _charts(self) -> list[ChartInfo]:
        out = []
        for m in re.finditer(r"#NOTES:", self.text):
            start = m.end()
            end = self.text.index(";", start)
            body = self.text[start:end]
            parts = body.split(":")
            if len(parts) < 6:
                continue
            stype, desc, diff, meter, radar = (p.strip() for p in parts[:5])
            notes_start = start + sum(len(p) + 1 for p in parts[:5])
            out.append(ChartInfo(stype, desc, diff, meter, radar, (notes_start, end),
                                 parse_notes(parts[5])))
        return out

    # beats <-> seconds (BPM changes are followed; stops are not)
    def time_at(self, beat: float) -> float:
        t, b0, bpm = -self.offset, self.bpms[0][0], self.bpms[0][1]
        for b, v in self.bpms[1:]:
            if beat <= b:
                break
            t += (b - b0) * 60 / bpm
            b0, bpm = b, v
        return t + (beat - b0) * 60 / bpm

    def beat_at(self, sec: float) -> float:
        t, b0, bpm = -self.offset, self.bpms[0][0], self.bpms[0][1]
        for b, v in self.bpms[1:]:
            seg = (b - b0) * 60 / bpm
            if sec <= t + seg:
                break
            t += seg
            b0, bpm = b, v
        return b0 + (sec - t) * bpm / 60

    def save(self, chart_index: int, steps: list[Step]) -> None:
        ch = self.charts[chart_index]
        a, b = ch.span
        new = "\n" + write_notes(steps) + "\n"
        self.text = self.text[:a] + new + self.text[b:]
        # the offset is the file's, shared by all its charts
        self.text = re.sub(r"#OFFSET:[^;]*;", f"#OFFSET:{self.offset:.3f};", self.text, count=1)
        bak = side_file(self.path, ".sm.bak")
        if not bak.exists():
            bak.write_bytes(self.path.read_bytes())
        self.path.write_text(self.text, encoding="utf-8")
        self.charts = self._charts()


def side_file(sm: Path, suffix: str) -> Path:
    """Where the editor keeps a file of its own for a chart: out of the
    StepMania folder when BeatSmith made the song (layout.py), else beside
    the chart, since a chart BeatSmith didn't make has no data folder."""
    p = side(sm, suffix)
    return p if p.parent.is_dir() else sm.parent / p.name


def parse_notes(data: str) -> list[Step]:
    data = re.sub(r"//[^\n]*", "", data)
    steps, open_holds = [], {}
    for mi, measure in enumerate(data.split(",")):
        rows = [r.strip() for r in measure.split("\n") if r.strip()]
        if not rows:
            continue
        for ri, row in enumerate(rows):
            tick = mi * TPM + round(ri * TPM / len(rows))
            for c, ch in enumerate(row[:COLS]):
                if ch in "124":
                    if ch in "24":
                        open_holds[c] = (tick, ch)
                    else:
                        steps.append(Step(tick, c))
                elif ch == "3" and c in open_holds:
                    t0, k = open_holds.pop(c)
                    steps.append(Step(t0, c, k, tick - t0))
                elif ch == "M":
                    steps.append(Step(tick, c, "M"))
    for c, (t0, k) in open_holds.items():          # unclosed hold: keep it as a tap
        steps.append(Step(t0, c))
    return sorted(steps, key=lambda s: (s.tick, s.col))


def write_notes(steps: list[Step]) -> str:
    rows: dict[int, list[str]] = {}

    def put(tick, col, ch):
        rows.setdefault(tick, ["0"] * COLS)[col] = ch
    for s in steps:
        if s.kind in "24" and s.length > 0:
            put(s.tick, s.col, s.kind)
            put(s.end, s.col, "3")
        else:
            put(s.tick, s.col, s.kind if s.kind == "M" else "1")
    if not rows:
        return "0000\n0000\n0000\n0000"
    n_meas = max(rows) // TPM + 1
    out = []
    for m in range(n_meas):
        ticks = [t - m * TPM for t in rows if m * TPM <= t < (m + 1) * TPM]
        res = next(r for r in (4, 8, 12, 16, 24, 32, 48, 64, 96, 192) if all(t % (TPM // r) == 0 for t in ticks))
        lines = ["".join(rows.get(m * TPM + i * (TPM // res), ["0"] * COLS)) for i in range(res)]
        out.append("\n".join(lines))
    return "\n,\n".join(out)


# ---------------------------------------------------------------- audio

class Player:
    """Plays the song from any point, at 0.5-1x speed, with an optional tick on
    every step. Uses sounddevice when it's installed; without it (or without
    a sound card) the clock still runs so the steps scroll in silence."""

    def __init__(self):
        self.data = np.zeros((1, 2), np.float32)
        self.sr = 44100
        self.pos = 0.0               # in frames of the song
        self.rate = 1.0
        self.playing = False
        self.ticks = np.zeros(0)     # step times in seconds
        self.tick_on = False
        self.volume = 0.9
        self.click = self._make_click()
        self.stream = None
        self.error = ""              # why there's no sound output at all
        self.load_error = ""         # why the current song couldn't be read
        self._clock0 = None
        self._last_cb = None         # (wall time, song frame) at the latest audio callback
        self._shown = 0.0            # last time handed out, so the clock never steps back
        try:
            import sounddevice  # noqa: F401
        except Exception as e:      # no PortAudio: silent clock
            self.error = ("no sound: install sounddevice (pip install sounddevice)"
                          if isinstance(e, ImportError) else f"no sound output found ({e})")

    def _make_click(self) -> np.ndarray:
        t = np.arange(int(0.03 * 44100)) / 44100
        return (0.6 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 160)).astype(np.float32)

    def load(self, path: Path | None) -> None:
        self.stop()
        self.data, self.sr = np.zeros((1, 2), np.float32), 44100   # no leftover song if this one fails
        if path is None:
            return
        import soundfile as sf
        try:
            data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        except Exception:
            # some MP3s (odd tags) and m4a/wma stop libsndfile; ffmpeg reads them
            ff = shutil.which("ffmpeg") or shutil.which(
                "ffmpeg", path=str(bundle_root() / "ffmpeg"))
            if ff is None:
                raise
            with tempfile.TemporaryDirectory() as d:
                wav = Path(d) / "a.wav"
                subprocess.run([ff, "-loglevel", "error", "-y", "-i", str(path), "-vn", str(wav)], check=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        self.data, self.sr = data[:, :2].copy(), sr
        if sr != 44100:
            t = np.arange(int(0.03 * sr)) / sr
            self.click = (0.6 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 160)).astype(np.float32)

    def envelope(self, hz: int = 200) -> np.ndarray:
        mono = np.abs(self.data).mean(1)
        w = max(1, self.sr // hz)
        n = len(mono) // w
        if n == 0:
            return np.zeros(1)
        e = mono[:n * w].reshape(n, w).max(1)
        return e / (e.max() + 1e-9)

    @property
    def seconds(self) -> float:
        if self.playing and self.stream is None and self._clock0 is not None:
            wall, start = self._clock0
            return start + (time.perf_counter() - wall) * self.rate
        lat = 0.0
        if self.stream is not None:
            try:
                lat = float(self.stream.latency) * self.rate
            except Exception:
                pass
        pos = self.pos
        cb = self._last_cb
        if self.playing and cb is not None:
            # the audio position only moves once per buffer (10-20 ms on
            # Windows), which makes scrolling judder; run a smooth clock
            # from the last buffer instead, never more than a buffer ahead
            wall, frame = cb
            pos = min(frame + (time.perf_counter() - wall) * self.sr * self.rate,
                      frame + 2 * self._block * self.rate)
        t = pos / self.sr - lat
        if self.playing:
            t = max(t, self._shown)
            self._shown = t
        return t

    def play(self, at_seconds: float) -> None:
        """Start at a song time; a negative time plays silence first (lead-in)."""
        self.stop()
        self.pos = at_seconds * self.sr
        self._last_cb, self._shown, self._block = None, -1e9, 512
        self.playing = True
        if self.error:
            self._clock0 = (time.perf_counter(), at_seconds)
            return
        try:
            import sounddevice as sd
            self.stream = sd.OutputStream(samplerate=self.sr, channels=2, dtype="float32",
                                          callback=self._callback, latency="low")
            self.stream.start()
        except Exception as e:
            self.error = f"audio didn't start ({e})"
            self.stream = None
            self._clock0 = (time.perf_counter(), at_seconds)

    def stop(self) -> None:
        if self.playing and self.stream is None and self._clock0 is not None:
            self.pos = self.seconds * self.sr
        self.playing = False
        self._clock0 = None
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _callback(self, out, frames, _time, _status):
        idx = self.pos + np.arange(frames) * self.rate
        n = len(self.data)
        if self.rate == 1.0 and self.pos >= 0:
            i0 = int(self.pos)
            chunk = self.data[i0:i0 + frames]
            buf = np.zeros((frames, 2), np.float32)
            buf[:len(chunk)] = chunk
        else:
            i = np.clip(idx, 0, n - 1)
            lo = i.astype(np.int64)
            hi = np.minimum(lo + 1, n - 1)
            f = (i - lo)[:, None].astype(np.float32)
            buf = self.data[lo] * (1 - f) + self.data[hi] * f
            buf[(idx >= n) | (idx < 0)] = 0                   # past the end, or lead-in silence
        if self.tick_on and len(self.ticks):
            t0, t1 = self.pos / self.sr, (self.pos + frames * self.rate) / self.sr
            for t in self.ticks[(self.ticks >= t0) & (self.ticks < t1)]:
                k = int((t - t0) * self.sr / self.rate)
                c = self.click[:frames - k]
                buf[k:k + len(c)] += c[:, None]
        out[:] = buf * self.volume
        self.pos += frames * self.rate
        self._block = frames
        self._last_cb = (time.perf_counter(), self.pos - frames * self.rate)
        if self.pos >= n:
            self.playing = False


# ---------------------------------------------------------------- play test

JUDGE = [("Marvelous", 0.0225, "#e8f4ff", 3), ("Perfect", 0.045, "#ffe14d", 2),
         ("Great", 0.090, "#5be37a", 1), ("Good", 0.135, "#4dc3ff", 0), ("Boo", 0.180, "#c77dff", -4)]
MISS_PTS, OK_PTS = -8, 6
PLAY_KEYS = {Qt.Key_Left: 0, Qt.Key_Down: 1, Qt.Key_Up: 2, Qt.Key_Right: 3,
             Qt.Key_D: 0, Qt.Key_F: 1, Qt.Key_J: 2, Qt.Key_K: 3}


class Game:
    """Play the chart with the keyboard and get StepMania-style judgements
    (the same timing windows as StepMania's default judge 4)."""

    def __init__(self, sm: SMFile, steps: list[Step], start_tick: int):
        self.notes = [{"s": s, "t": sm.time_at(s.tick / TPB), "end": sm.time_at(s.end / TPB),
                       "j": None, "hold": None}
                      for s in steps if s.kind != "M" and s.tick >= start_tick]
        self.counts = {name: 0 for name, *_ in JUDGE} | {"Miss": 0, "OK": 0, "NG": 0}
        self.combo = self.max_combo = 0
        self.points = 0
        self.active: dict[int, dict] = {}      # lane -> hold being held
        self.pressed: dict[int, float] = {}    # lane -> when its key went down
        self.flash = None                      # (text, colour, time)
        self.offsets: list[float] = []         # hit early (-) / late (+), seconds
        self.grooving: list[list[float]] = []  # [start, end] seconds while G was held

    def press(self, col: int, now: float):
        self.pressed[col] = now
        best = None
        for n in self.notes:
            if n["j"] is None and n["s"].col == col and abs(now - n["t"]) <= JUDGE[-1][1]:
                if best is None or abs(now - n["t"]) < abs(now - best["t"]):
                    best = n
        if best is None:
            return
        err = now - best["t"]
        name, _, colour, pts = next(j for j in JUDGE if abs(err) <= j[1])
        best["j"] = name
        self.counts[name] += 1
        self.points += pts
        self.offsets.append(err)
        self.combo = self.combo + 1 if name != "Boo" else 0
        self.max_combo = max(self.max_combo, self.combo)
        self.flash = (name, colour, now)
        if best["s"].kind in "24" and best["s"].length:
            best["hold"] = "held"
            self.active[col] = best

    def release(self, col: int, now: float):
        self.pressed.pop(col, None)
        n = self.active.pop(col, None)
        if n is not None and now < n["end"] - 0.12:
            n["hold"] = "NG"
            self.counts["NG"] += 1
            self.flash = ("NG", "#ff5b5b", now)

    def groove_key(self, down: bool, now: float):
        """G held: "I'm grooving here"."""
        if down and (not self.grooving or self.grooving[-1][1] is not None):
            self.grooving.append([now, None])
        elif not down and self.grooving and self.grooving[-1][1] is None:
            self.grooving[-1][1] = now

    def update(self, now: float):
        for n in self.notes:
            if n["j"] is None and now > n["t"] + JUDGE[-1][1]:
                n["j"] = "Miss"
                self.counts["Miss"] += 1
                self.points += MISS_PTS
                self.combo = 0
                self.flash = ("Miss", "#ff5b5b", now)
                if n["s"].kind in "24" and n["s"].length:
                    n["hold"] = "NG"
                    self.counts["NG"] += 1
        for col, n in list(self.active.items()):
            if now >= n["end"]:
                n["hold"] = "OK"
                self.counts["OK"] += 1
                self.points += OK_PTS
                del self.active[col]

    def done(self, now: float) -> bool:
        return all(n["j"] is not None for n in self.notes) and not self.active and \
            now > max((n["end"] for n in self.notes), default=0) + 1.0

    def percent(self) -> float:
        """Dance points so far, out of what the steps already passed were worth,
        so stopping a test early still gives a fair score."""
        top = sum(3 + (OK_PTS if n["s"].kind in "24" and n["s"].length and n["hold"] in ("OK", "NG") else 0)
                  for n in self.notes if n["j"] is not None)
        return max(0.0, 100 * self.points / top) if top else 0.0

    def summary(self) -> str:
        c = self.counts
        lines = [f"{self.percent():.2f}%   max combo {self.max_combo}", ""]
        lines += [f"{name}: {c[name]}" for name, *_ in JUDGE] + [f"Miss: {c['Miss']}", "",
                                                                  f"Holds OK: {c['OK']}   NG: {c['NG']}"]
        if len(self.offsets) >= 10:
            mean = 1000 * float(np.mean(self.offsets))
            lines += ["", f"Average timing: {abs(mean):.0f} ms {'late' if mean > 0 else 'early'}"
                      + ("\n(if that's steady, press \"Match my play test\" to move the steps to match)"
                         if abs(mean) > 25 else "")]
        return "\n".join(lines)


# ---------------------------------------------------------------- note field

class NoteField(QWidget):
    """The scrolling lanes. The cursor sits on the receptor line near the top;
    while playing, the steps scroll up into it."""
    changed = Signal()           # the steps changed
    moved = Signal()             # cursor / view moved

    RULER = 64
    LANE = 64
    RECEPT = 110
    COMPARE_GAP = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)     # paints every pixel: skip the panel behind it
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumWidth(self.RULER + COLS * self.LANE + 140)
        self.sm: SMFile | None = None
        self.steps: list[Step] = []
        self.sel: set[Step] = set()
        self.snap = 12
        self.ppb = 80.0                # pixels per beat
        self.cursor = 0                # tick at the receptor line
        self.play_beat: float | None = None
        self.env = np.zeros(1)
        self.env_hz = 200
        self.undo: list[list[Step]] = []
        self.redo: list[list[Step]] = []
        self.clip: list[Step] = []
        self.drag = None               # what the mouse is doing
        self.hover = None
        self.held_keys: dict[int, int] = {}   # lane -> tick where its key went down
        self.shift_anchor = None
        self.game: Game | None = None
        self.overview: QWidget | None = None
        self._sprites: dict[tuple, QPixmap] = {}
        self.clock = lambda: 0.0               # song time while play-testing
        self.game_over = None                  # called when a play test ends
        self.compare: list[Step] | None = None  # read-only steps shown in lanes beside the chart
        self.compare_names = ("", "")
        self._dx = 0.0                         # moves lane_x over to the compare lanes while painting
        self.groove = None                     # groove.Groove for the steps, when the song could be read
        self._end_key, self._end = None, 0     # song_end, worked out again only when it can change
        self._wave_key, self._wave = None, {}  # waveform tiles, drawn once per zoom

    # ---- geometry
    def song_end(self) -> int:
        """Last tick worth scrolling to: the end of the audio, or the last step."""
        key = (id(self.steps), len(self.steps), id(self.env), id(self.sm),
               self.sm and (self.sm.offset, tuple(self.sm.bpms)))
        if key != self._end_key:
            end = max((s.end for s in self.steps), default=0) + TPM
            if self.sm is not None and len(self.env) > 1:
                end = max(end, int(self.sm.beat_at(len(self.env) / self.env_hz) * TPB))
            self._end_key, self._end = key, end
        return self._end

    def view_beat(self) -> float:
        return self.play_beat if self.play_beat is not None else self.cursor / TPB

    def y_of(self, tick: float) -> float:
        return self.RECEPT + (tick / TPB - self.view_beat()) * self.ppb

    def tick_at(self, y: float, snap: bool = True) -> int:
        t = (self.view_beat() + (y - self.RECEPT) / self.ppb) * TPB
        return max(0, int(round(t / self.snap) * self.snap) if snap else int(t))

    def lane_x(self, col: int) -> float:
        return self.RULER + col * self.LANE + self._dx

    def set_compare(self, steps: list[Step] | None, names=("", "")) -> None:
        self.compare, self.compare_names = steps, names
        self.setMinimumWidth(self.RULER + COLS * self.LANE * (2 if steps is not None else 1)
                             + self.COMPARE_GAP + 140)
        self.update()

    def col_at(self, x: float) -> int | None:
        c = int((x - self.RULER) // self.LANE)
        return c if 0 <= c < COLS else None

    def step_at(self, x: float, y: float, strict: bool = False) -> Step | None:
        """The note under the mouse. strict (clicks): when notes sit close
        together, a note only wins if the mouse is nearer to it than to the
        empty snap slot under the mouse, so you can add a note right next to
        another one without zooming in. Hold bodies always count as the hold."""
        c = self.col_at(x)
        if c is None:
            return None
        best = None
        for s in self.steps:
            if s.col != c:
                continue
            y0, y1 = self.y_of(s.tick), self.y_of(s.end)
            if y0 - self.LANE * 0.4 <= y <= max(y1, y0) + self.LANE * 0.4:
                if best is None or abs(self.y_of(s.tick) - y) < abs(self.y_of(best.tick) - y):
                    best = s
        if best is None or not strict:
            return best
        y0, y1 = self.y_of(best.tick), self.y_of(best.end)
        if y1 > y0 and y0 + self.LANE * 0.4 < y <= y1:
            return best                                   # on the hold's body
        slot = self.tick_at(y)
        if slot != best.tick and abs(y - self.y_of(slot)) < abs(y - y0):
            return None                                   # the free slot is closer
        return best

    # ---- edits
    def set_steps(self, steps: list[Step], record: bool = True) -> None:
        if record:
            self.undo.append(list(self.steps))
            self.undo = self.undo[-300:]
            self.redo.clear()
        self.steps = sorted(set(steps), key=lambda s: (s.tick, s.col))
        self.sel &= set(self.steps)
        self.changed.emit()
        self.update()

    def load(self, sm: SMFile, steps: list[Step]) -> None:
        self.sm, self.steps, self.sel = sm, list(steps), set()
        self.undo.clear()
        self.redo.clear()
        self.cursor = 0
        self.update()

    def add(self, new: list[Step], base: list[Step] | None = None, record: bool = True) -> list[Step]:
        """Place steps, replacing whatever they overlap in the same lane."""
        keep = []
        for s in (self.steps if base is None else base):
            if any(n.col == s.col and n.tick <= s.end and s.tick <= n.end for n in new):
                continue
            keep.append(s)
        self.set_steps(keep + new, record)
        return new

    def toggle(self, tick: int, col: int) -> None:
        hit = [s for s in self.steps if s.col == col and s.tick == tick]
        if hit:
            self.set_steps([s for s in self.steps if s not in hit])
        else:
            self.add([Step(tick, col)])

    def delete(self, steps) -> None:
        steps = set(steps)
        if steps:
            self.set_steps([s for s in self.steps if s not in steps])

    def do_undo(self):
        if self.undo:
            self.redo.append(list(self.steps))
            self.set_steps(self.undo.pop(), record=False)

    def do_redo(self):
        if self.redo:
            self.undo.append(list(self.steps))
            self.set_steps(self.redo.pop(), record=False)

    def shifted(self, steps, dt: int, dc: int = 0, mirror: bool = False) -> list[Step] | None:
        out = []
        for s in steps:
            c = (COLS - 1 - s.col) if mirror else s.col + dc
            if not 0 <= c < COLS or s.tick + dt < 0:
                return None
            out.append(replace(s, tick=s.tick + dt, col=c))
        return out

    def move_selection(self, dt: int, dc: int = 0) -> None:
        moved = self.shifted(self.sel, dt, dc)
        if moved is None:
            return
        base = [s for s in self.steps if s not in self.sel]
        self.add(moved, base)
        self.sel = set(moved)

    def copy(self):
        if self.sel:
            t0 = min(s.tick for s in self.sel)
            self.clip = [replace(s, tick=s.tick - t0) for s in self.sel]

    def paste(self, at: int):
        if self.clip:
            new = [replace(s, tick=s.tick + at) for s in self.clip]
            self.add(new)
            self.sel = set(new)
            self.update()

    def duplicate(self):
        if not self.sel:
            return
        t0 = min(s.tick for s in self.sel)
        t1 = max(s.end for s in self.sel)
        span = math.ceil((t1 - t0 + 1) / self.snap) * self.snap
        span = max(span, TPB) if span < TPB else span
        new = [replace(s, tick=s.tick + span) for s in self.sel]
        self.add(new)
        self.sel = set(new)
        self.update()

    def mirror(self):
        if self.sel:
            new = self.shifted(self.sel, 0, mirror=True)
            base = [s for s in self.steps if s not in self.sel]
            self.add(new, base)
            self.sel = set(new)
            self.update()

    def select_range(self, t0: int, t1: int, add: bool = False):
        lo, hi = min(t0, t1), max(t0, t1)
        found = {s for s in self.steps if lo <= s.tick <= hi}
        self.sel = (self.sel | found) if add else found
        self.update()

    # ---- painting
    def paintEvent(self, _ev):
        if self.overview is not None and self.play_beat is None:
            self.overview.update()         # keep the song strip in step (playback updates it itself)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#16131f"))
        lanes_w = COLS * self.LANE
        p.fillRect(QRectF(self.RULER, 0, lanes_w, h), QColor("#1d1a29"))
        first = self.tick_at(0, snap=False)
        last = self.tick_at(h, snap=False) + TPB

        comparing = self.compare is not None and self.game is None
        cx0 = self.RULER + lanes_w + self.COMPARE_GAP      # where the compare lanes start
        if comparing:
            p.fillRect(QRectF(cx0, 0, lanes_w, h), QColor("#1a1824"))

        # waveform strip at the right: drawn once into tiles, then only slid along
        wx = (cx0 + lanes_w if comparing else self.RULER + lanes_w) + 12
        ww = int(min(w - wx - 8, 260))
        if self.sm is not None and len(self.env) > 1 and ww > 10:
            y0 = self.RECEPT - self.view_beat() * self.ppb        # where beat 0 sits
            T = self.WAVE_TILE
            for k in range(math.floor(-y0 / T), math.floor((h - y0) / T) + 1):
                p.drawPixmap(QPointF(wx, y0 + k * T), self._wave_tile(k, ww))

        # grid: snap lines faint, beats brighter, measures with numbers
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        t = (first // self.snap) * self.snap
        while t <= last:
            y = self.y_of(t)
            if t % TPM == 0:
                p.setPen(QPen(QColor("#8c84b5"), 1.5))
                p.drawText(QRectF(4, y - 9, self.RULER - 10, 18), Qt.AlignRight | Qt.AlignVCenter,
                           f"{t // TPM + 1}")
            else:
                # grid lines take the colour of the steps that land on them
                c = quant_color(t)
                c.setAlpha(110 if t % TPB == 0 else 55)
                p.setPen(QPen(c, 1))
            p.drawLine(QPointF(self.RULER, y), QPointF(self.RULER + lanes_w, y))
            if comparing:
                p.drawLine(QPointF(cx0, y), QPointF(cx0 + lanes_w, y))
            t += self.snap
        p.setPen(QPen(QColor("#2c2840"), 1))
        for c in range(COLS + 1):
            x = self.lane_x(c)
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            if comparing:
                p.drawLine(QPointF(x - self.RULER + cx0, 0), QPointF(x - self.RULER + cx0, h))

        # ruler range selection in progress
        if self.drag and self.drag[0] in ("range", "box"):
            p.setPen(QPen(QColor("#6fa8ff"), 1, Qt.DashLine))
            p.setBrush(QColor(111, 168, 255, 40))
            if self.drag[0] == "range":
                y0, y1 = self.y_of(self.drag[1]), self.y_of(self.drag[2])
                p.drawRect(QRectF(self.RULER, min(y0, y1), lanes_w, abs(y1 - y0)))
            else:
                (x0, y0), (x1, y1) = self.drag[1], self.drag[2]
                p.drawRect(QRectF(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)))

        # receptors
        for c in range(COLS):
            self._arrow(p, c, self.RECEPT, QColor(0, 0, 0, 0), QColor("#9a93c4"), 1.0)

        # steps (and a ghost of a move in progress)
        moving = None
        if self.drag and self.drag[0] == "move" and (self.drag[3] or self.drag[4]):
            moving = self.shifted(self.sel, self.drag[3], self.drag[4])
        draw = [(s, s in self.sel and moving is None, 1.0 if not (moving and s in self.sel) else 0.35)
                for s in self.steps if s.end >= first - TPB and s.tick <= last]
        if moving:
            draw += [(s, True, 1.0) for s in moving]
        if self.drag and self.drag[0] == "place" and self.drag[3] > 0:
            draw.append((Step(self.drag[1], self.drag[2], "2", self.drag[3]), False, 0.6))
        if self.game is not None:
            g = self.game
            draw = []
            for n in g.notes:
                s = n["s"]
                if n["hold"] == "held":
                    # the hold body shrinks into the receptor while it's held
                    rest = max(0, s.end - int(self.view_beat() * TPB))
                    draw.append((replace(s, tick=s.end - rest, length=rest), False, 1.0))
                elif s.tick > last or s.end < first - TPB:
                    continue                                  # off screen
                elif n["j"] is None or (n["j"] == "Miss" and s.tick > (self.view_beat() - 4) * TPB):
                    draw.append((s, False, 1.0 if n["j"] is None else 0.3))
        for s, selected, alpha in draw:
            self._step(p, s, selected, alpha)
        if comparing:
            # the other version, read-only: steps on a beat both versions use are
            # dimmed, so where the rhythm differs stands out
            mine = {s.tick for s in self.steps}
            self._dx = cx0 - self.RULER
            for c in range(COLS):
                self._arrow(p, c, self.RECEPT, QColor(0, 0, 0, 0), QColor("#6d6790"), 1.0)
            for s in self.compare:
                if s.end >= first - TPB and s.tick <= last:
                    self._step(p, s, False, 0.35 if s.tick in mine else 1.0)
            self._dx = 0.0
            p.setPen(QColor("#b9b3dd"))
            for x0, name in ((self.RULER, self.compare_names[0]), (cx0, self.compare_names[1])):
                p.fillRect(QRectF(x0, 0, lanes_w, 22), QColor(22, 19, 31, 220))
                p.drawText(QRectF(x0, 0, lanes_w, 22), Qt.AlignCenter, name)
        if self.game is not None:
            self._paint_game(p)

        # hover ghost
        # (a ring on the note a click would grab, a ghost where a click would add)
        if self.hover and not self.drag and self.play_beat is None:
            tick, c = self.hover
            hs = getattr(self, "hover_step", None)
            if hs is not None:
                p.setPen(QPen(QColor(255, 255, 255, 160), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(self.lane_x(hs.col) + self.LANE / 2, self.y_of(hs.tick)),
                              self.LANE * 0.48, self.LANE * 0.48)
            else:
                col = quant_color(tick)
                col.setAlpha(70)
                self._arrow(p, c, self.y_of(tick), col, QColor(255, 255, 255, 70), 0.9)

        # cursor / playhead line
        # the cursor shows the current snap's colour, like StepMania's editor
        p.setPen(QPen(quant_color(self.snap) if self.play_beat is None else QColor("#4dff9a"), 2))
        p.drawLine(QPointF(self.RULER - 8, self.RECEPT),
                   QPointF((cx0 if comparing else self.RULER) + lanes_w + 8, self.RECEPT))
        p.end()

    WAVE_TILE = 512              # pixels of waveform per tile

    def _wave_tile(self, k: int, ww: int) -> QPixmap:
        """Tile k of the waveform: beats k*WAVE_TILE/ppb onwards, at this zoom."""
        dpr = self.devicePixelRatioF()
        key = (ww, self.ppb, dpr, id(self.env), id(self.sm), self.sm.offset, tuple(self.sm.bpms))
        if key != self._wave_key or len(self._wave) > 64:
            self._wave_key, self._wave = key, {}
        pm = self._wave.get(k)
        if pm is None:
            T = self.WAVE_TILE
            pm = QPixmap(int(ww * dpr), int(T * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            # time is piecewise linear in beats, so one interp covers every row
            knots = [-1e4] + [b for b, _ in self.sm.bpms[1:]] + [1e5]
            ys = np.arange(0, T, 2)
            t = np.interp((k * T + ys) / self.ppb, knots, [self.sm.time_at(b) for b in knots])
            i = (t * self.env_hz).astype(int)
            ok = (i >= 0) & (i < len(self.env))
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing)
            q.setPen(Qt.NoPen)
            q.setBrush(QColor("#4b3f7a"))
            q.drawRects([QRectF(ww / 2 - a * ww / 2, y, a * ww, 2) for y, a in zip(ys[ok], self.env[i[ok]])])
            q.end()
            self._wave[k] = pm
        return pm

    def _paint_game(self, p: QPainter):
        g, now = self.game, self.clock()
        for c in g.pressed:
            self._arrow(p, c, self.RECEPT, QColor(255, 255, 255, 90), QColor("white"), 1.05)
        cx = self.RULER + COLS * self.LANE / 2
        if g.flash and now - g.flash[2] < 0.6:
            name, colour, t = g.flash
            f = QFont()
            f.setPointSize(26)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(colour))
            p.drawText(QRectF(self.RULER, self.RECEPT + 150, COLS * self.LANE, 50), Qt.AlignCenter, name)
        if g.combo >= 4:
            f = QFont()
            f.setPointSize(18)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(self.RULER, self.RECEPT + 205, COLS * self.LANE, 36), Qt.AlignCenter,
                       f"{g.combo} combo")
        f = QFont()
        f.setPointSize(12)
        p.setFont(f)
        p.setPen(QColor("#cfc8ff"))
        p.drawText(QRectF(self.RULER, 6, COLS * self.LANE, 24), Qt.AlignCenter, f"{g.percent():.2f}%")
        if g.grooving and g.grooving[-1][1] is None:
            p.setPen(QColor("#4dff9a"))
            p.drawText(QRectF(self.RULER, 30, COLS * self.LANE, 22), Qt.AlignCenter, "♪ grooving")

    def _step(self, p: QPainter, s: Step, selected: bool, alpha: float):
        y = self.y_of(s.tick)
        x = self.lane_x(s.col)
        if s.kind in "24" and s.length:
            y1 = self.y_of(s.end)
            body = QColor("#5ccf6a" if s.kind == "2" else "#e0a23a")
            body.setAlphaF(0.75 * alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(body)
            p.drawRoundedRect(QRectF(x + self.LANE * 0.22, y, self.LANE * 0.56, y1 - y + self.LANE * 0.2), 6, 6)
        if s.kind == "M":
            p.setBrush(QColor(220, 60, 60, int(255 * alpha)))
            p.setPen(QPen(QColor("white"), 2))
            p.drawEllipse(QPointF(x + self.LANE / 2, y), self.LANE * 0.25, self.LANE * 0.25)
        else:
            col = quant_color(s.tick)
            col.setAlphaF(alpha)
            self._arrow(p, s.col, y, col, QColor(255, 255, 255, int(255 * alpha)), 0.9)
        if selected:
            p.setPen(QPen(QColor("#6fa8ff"), 3))
            p.setBrush(Qt.NoBrush)
            r = self.LANE * 0.47
            p.drawRoundedRect(QRectF(x + self.LANE / 2 - r, y - r, 2 * r, 2 * r), 8, 8)

    def _arrow(self, p: QPainter, col: int, y: float, fill: QColor, edge: QColor, scale: float):
        """Arrows are drawn once per look into a small picture and then just
        copied, which is far cheaper than redrawing the shape every frame."""
        dpr = self.devicePixelRatioF()
        key = (col, fill.rgba(), edge.rgba(), scale, dpr)
        pm = self._sprites.get(key)
        if pm is None:
            size = int(self.LANE * scale) + 6
            pm = QPixmap(int(size * dpr), int(size * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing)
            self._arrow_shape(q, col, size / 2, size / 2, fill, edge, scale)
            q.end()
            if len(self._sprites) > 400:
                self._sprites.clear()
            self._sprites[key] = pm
        half = pm.width() / dpr / 2
        p.drawPixmap(QPointF(self.lane_x(col) + self.LANE / 2 - half, y - half), pm)

    def _arrow_shape(self, p: QPainter, col: int, cx: float, y: float, fill: QColor, edge: QColor,
                     scale: float):
        pts = [(0, -1), (0.9, -0.1), (0.38, -0.1), (0.38, 0.9), (-0.38, 0.9), (-0.38, -0.1), (-0.9, -0.1)]
        a = math.radians(ARROW_ANGLE[col])
        s = self.LANE * 0.4 * scale
        poly = QPolygonF([QPointF(cx + s * (px * math.cos(a) - py * math.sin(a)),
                                  y + s * (px * math.sin(a) + py * math.cos(a))) for px, py in pts])
        p.setPen(QPen(edge, 2))
        p.setBrush(fill)
        p.drawPolygon(poly)

    # ---- mouse
    def mousePressEvent(self, ev):
        self.setFocus()
        if self.game is not None:
            return
        x, y = ev.position().x(), ev.position().y()
        tick, col = self.tick_at(y), self.col_at(x)
        if ev.button() == Qt.RightButton:
            s = self.step_at(x, y, strict=True)
            if s is not None:
                self.delete(self.sel if s in self.sel else [s])
            else:
                self._context_menu(ev, tick)
            return
        if ev.button() != Qt.LeftButton:
            return
        if x < self.RULER:
            self.drag = ["range", tick, tick, bool(ev.modifiers() & Qt.ControlModifier)]
            return
        if ev.modifiers() & Qt.ShiftModifier:
            self.drag = ["box", (x, y), (x, y), bool(ev.modifiers() & Qt.ControlModifier)]
            return
        if col is None:
            return
        s = self.step_at(x, y, strict=True)
        if s is not None:
            if ev.modifiers() & Qt.ControlModifier:
                self.sel ^= {s}
            elif s not in self.sel:
                self.sel = {s}
            self.drag = ["move", s.tick, s.col, 0, 0]
        else:
            self.sel = set()
            self.drag = ["place", tick, col, 0]
        self.update()

    def mouseMoveEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        tick, col = self.tick_at(y), self.col_at(x)
        self.hover = (tick, col) if col is not None else None
        self.hover_step = self.step_at(x, y, strict=True) if col is not None else None
        d = self.drag
        if d is None:
            self.update()
            return
        if d[0] == "range":
            d[2] = tick
        elif d[0] == "box":
            d[2] = (x, y)
        elif d[0] == "move":
            d[3] = tick - self.tick_at(self.y_of(d[1]))
            d[4] = (col if col is not None else d[2]) - d[2]
        elif d[0] == "place":
            d[3] = max(0, tick - d[1])
        self.update()

    def mouseReleaseEvent(self, ev):
        d, self.drag = self.drag, None
        if d is None:
            return
        if d[0] == "range":
            self.select_range(d[1], d[2], add=d[3])
            self.cursor = min(d[1], d[2])
            self.moved.emit()
        elif d[0] == "box":
            (x0, y0), (x1, y1) = d[1], d[2]
            t0, t1 = self.tick_at(min(y0, y1), False), self.tick_at(max(y0, y1), False)
            c0, c1 = self.col_at(max(min(x0, x1), self.RULER)), self.col_at(min(max(x0, x1), self.RULER + COLS * self.LANE - 1))
            found = {s for s in self.steps if t0 <= s.tick <= t1 and c0 is not None and c1 is not None
                     and c0 <= s.col <= c1}
            self.sel = (self.sel | found) if d[3] else found
        elif d[0] == "move" and (d[3] or d[4]):
            self.move_selection(d[3], d[4])
        elif d[0] == "place":
            if d[3] >= self.snap:
                self.add([Step(d[1], d[2], "2", d[3])])
            else:
                self.toggle(d[1], d[2])
        self.update()

    def mouseDoubleClickEvent(self, ev):
        # double-click a hold to turn it into a roll and back
        s = self.step_at(ev.position().x(), ev.position().y())
        if s is not None and s.kind in "24":
            self.add([replace(s, kind="4" if s.kind == "2" else "2")], [x for x in self.steps if x != s])

    def leaveEvent(self, _ev):
        self.hover = None
        self.update()

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        if ev.modifiers() & Qt.ControlModifier:
            self.ppb = float(np.clip(self.ppb * (1.15 if dy > 0 else 1 / 1.15), 20, 600))
        elif self.play_beat is None:
            step = TPM if ev.modifiers() & Qt.ShiftModifier else self.snap
            self.cursor = min(self.song_end(), max(0, self.cursor + (-step if dy > 0 else step)))
            self.moved.emit()
        self.update()

    def _context_menu(self, ev, tick):
        m = QMenu(self)
        m.addAction("Paste here", lambda: self.paste(tick)).setEnabled(bool(self.clip))
        m.addAction("Select all", lambda: (setattr(self, "sel", set(self.steps)), self.update()))
        m.addAction("Insert a beat here", lambda: self.shift_from(tick, TPB))
        m.addAction("Delete a beat here", lambda: self.shift_from(tick, -TPB))
        m.exec(ev.globalPosition().toPoint())

    def shift_from(self, tick: int, dt: int):
        """Insert (or remove) time at a point, pushing later steps along."""
        out = []
        for s in self.steps:
            if s.tick >= tick:
                if dt < 0 and s.tick < tick - dt:
                    continue
                out.append(replace(s, tick=s.tick + dt))
            else:
                out.append(s)
        self.set_steps(out)

    # ---- keyboard
    def keyPressEvent(self, ev):
        k, mods = ev.key(), ev.modifiers()
        if self.game is not None:
            if k in PLAY_KEYS and not ev.isAutoRepeat():
                self.game.press(PLAY_KEYS[k], self.clock())
            elif k == Qt.Key_G and not ev.isAutoRepeat():
                self.game.groove_key(True, self.clock())
            elif k == Qt.Key_Escape and self.game_over:
                self.game_over()
            return
        ctrl, shift = bool(mods & Qt.ControlModifier), bool(mods & Qt.ShiftModifier)
        lane_keys = {Qt.Key_1: 0, Qt.Key_2: 1, Qt.Key_3: 2, Qt.Key_4: 3}
        if k in lane_keys and not ctrl:
            if not ev.isAutoRepeat():
                c = lane_keys[k]
                self.held_keys[c] = self.cursor
                self.toggle(self.cursor, c)
            return
        if k in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End):
            step = {Qt.Key_Up: -self.snap, Qt.Key_Down: self.snap,
                    Qt.Key_PageUp: -TPM, Qt.Key_PageDown: TPM}.get(k, 0)
            if ctrl and k in (Qt.Key_Up, Qt.Key_Down):
                self.move_selection(step)
                return
            before = self.cursor
            if k == Qt.Key_Home:
                self.cursor = 0
            elif k == Qt.Key_End:
                self.cursor = max((s.end for s in self.steps), default=0)
            else:
                self.cursor = max(0, self.cursor + step)
            if shift:
                if self.shift_anchor is None:
                    self.shift_anchor = before
                self.select_range(self.shift_anchor, self.cursor)
            # a lane key held while moving down stretches a hold
            for c, t0 in self.held_keys.items():
                if self.cursor > t0:
                    self.add([Step(t0, c, "2", self.cursor - t0)], record=False)
            self.moved.emit()
            self.update()
            return
        if k in (Qt.Key_Left, Qt.Key_Right):
            i = [s for _, s in SNAPS].index(self.snap) if self.snap in [s for _, s in SNAPS] else 3
            i = max(0, min(len(SNAPS) - 1, i + (1 if k == Qt.Key_Right else -1)))
            self.snap = SNAPS[i][1]
            self.cursor = round(self.cursor / self.snap) * self.snap
            self.moved.emit()
            self.update()
            return
        if ctrl and k == Qt.Key_C:
            self.copy()
        elif ctrl and k == Qt.Key_X:
            self.copy()
            self.delete(self.sel)
        elif ctrl and k == Qt.Key_V:
            self.paste(self.cursor)
        elif ctrl and k == Qt.Key_D:
            self.duplicate()
        elif ctrl and k == Qt.Key_A:
            self.sel = set(self.steps)
        elif ctrl and k == Qt.Key_Z:
            self.do_redo() if shift else self.do_undo()
        elif ctrl and k == Qt.Key_Y:
            self.do_redo()
        elif k == Qt.Key_M and not ctrl:
            self.mirror()
        elif k in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete(self.sel)
        elif k == Qt.Key_Escape:
            self.sel = set()
        else:
            super().keyPressEvent(ev)
            return
        self.update()

    def keyReleaseEvent(self, ev):
        if self.game is not None:
            if ev.key() in PLAY_KEYS and not ev.isAutoRepeat():
                self.game.release(PLAY_KEYS[ev.key()], self.clock())
            elif ev.key() == Qt.Key_G and not ev.isAutoRepeat():
                self.game.groove_key(False, self.clock())
            return
        lane_keys = {Qt.Key_1: 0, Qt.Key_2: 1, Qt.Key_3: 2, Qt.Key_4: 3}
        if ev.key() in lane_keys and not ev.isAutoRepeat():
            # the press already saved an undo step, so a stretched hold undoes in one go
            self.held_keys.pop(lane_keys[ev.key()], None)
        if ev.key() == Qt.Key_Shift:
            self.shift_anchor = None
        super().keyReleaseEvent(ev)


# ---------------------------------------------------------------- song overview

class ChartMap(QWidget):
    """The whole chart squeezed into a strip beside the lanes, like a scroll
    bar: the box is what's on screen; click or drag anywhere to jump there."""
    WIDTH = 92
    GROOVE_W = 6                 # the groove column at the right edge

    def __init__(self, field: "NoteField", parent=None):
        super().__init__(parent)
        self.field = field
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFixedWidth(self.WIDTH)
        self.setCursor(Qt.PointingHandCursor)
        self._key, self._pm = None, None
        self.setMouseTracking(True)
        self.setToolTip("Whole song: click or drag to jump. Shift+wheel on the lanes scrolls a measure.")

    def _draw_steps(self, dpr: float) -> QPixmap:
        f = self.field
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor("#15151b"))
        p = QPainter(pm)
        end, lane = f.song_end(), (self.WIDTH - 30 - self.GROOVE_W - 2) / COLS
        p.setFont(QFont("Sans", 7))
        for m in range(0, end // TPM + 1, 4):
            y = self._y(m * TPM)
            p.setPen(QColor("#2c2c36"))
            p.drawLine(QPointF(26, y), QPointF(self.WIDTH, y))
            if m % 8 == 0 and self._scale() * TPM * 8 > 12:
                p.setPen(QColor("#777"))
                p.drawText(QRectF(0, y - 6, 24, 12), Qt.AlignRight | Qt.AlignVCenter, str(m + 1))
        for st in f.steps:
            c = QColor("#ffffff") if st in f.sel else quant_color(st.tick)
            x, y0 = 28 + st.col * lane, self._y(st.tick)
            p.fillRect(QRectF(x, y0, lane - 2, max(1.5, self._y(st.end) - y0)), c)
        # groove per measure: red (awkward) through amber to green (grooves)
        g = f.groove
        if g is not None:
            gx = self.WIDTH - self.GROOVE_W
            for m, v in enumerate(g.measures):
                if not np.isnan(v):
                    c = QColor.fromHsvF(float(np.clip((v - 45) / 45, 0, 1)) / 3, 0.8, 0.9)
                    p.fillRect(QRectF(gx, self._y(m * TPM), self.GROOVE_W, max(1.0, self._y(TPM) - self._y(0))), c)
        p.end()
        return pm

    def _scale(self) -> float:
        return max(self.height() - 8, 1) / max(self.field.song_end(), 1)

    def _y(self, tick: float) -> float:
        return 4 + tick * self._scale()

    def paintEvent(self, _ev):
        f, p = self.field, QPainter(self)
        if f.sm is None:
            p.fillRect(self.rect(), QColor("#15151b"))
            p.end()
            return
        # the steps only change on edits, so they're drawn once into a picture
        dpr = self.devicePixelRatioF()
        key = (id(f.steps), len(f.steps), hash(frozenset(f.sel)), self.width(), self.height(),
               f.song_end(), dpr, id(f.groove))
        if key != self._key:
            self._key, self._pm = key, self._draw_steps(dpr)
        p.drawPixmap(0, 0, self._pm)
        # what's on screen
        top, bot = self._y(max(0, f.tick_at(0, False))), self._y(f.tick_at(f.height(), False))
        p.setPen(QPen(QColor(255, 255, 255, 170), 1))
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRect(QRectF(26, top, self.WIDTH - 27, max(4, bot - top)))
        beat = f.view_beat()
        p.setPen(QPen(QColor("#4dff9a") if f.play_beat is not None else quant_color(f.snap), 2))
        y = self._y(beat * TPB)
        p.drawLine(QPointF(24, y), QPointF(self.WIDTH, y))
        p.end()

    def _jump(self, y: float):
        f = self.field
        if f.play_beat is not None or f.sm is None:
            return
        t = (y - 4) / self._scale()
        f.cursor = int(min(f.song_end(), max(0, round(t / f.snap) * f.snap)))
        f.moved.emit()
        f.update()
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._jump(ev.position().y())

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            self._jump(ev.position().y())
        elif self.field.groove is not None:
            # what the groove meter thinks of the measure under the mouse
            from PySide6.QtWidgets import QToolTip
            m = int(((ev.position().y() - 4) / self._scale()) // TPM)
            QToolTip.showText(ev.globalPosition().toPoint(),
                              self.field.groove.explain(m) + "\nClick or drag to jump.", self)

    def wheelEvent(self, ev):
        self.field.wheelEvent(ev)


# ---------------------------------------------------------------- editor panel

class EditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sm: SMFile | None = None
        self.chart_i = 0
        self.dirty = False
        self.player = Player()
        self.field = NoteField()
        self.field.changed.connect(self._changed)
        self.field.moved.connect(self._status)
        self.field.clock = lambda: self.player.seconds
        self.field.game_over = self.end_game

        top = QHBoxLayout()
        self.open_btn = QPushButton("Open chart…")
        self.open_btn.clicked.connect(self.pick_file)
        self.chart_box = QComboBox()
        self.chart_box.currentIndexChanged.connect(self._switch_chart)
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)
        self.snap_box = QComboBox()
        self.snap_box.addItems([n for n, _ in SNAPS])
        for i, (_, ticks) in enumerate(SNAPS):
            self.snap_box.setItemData(i, quant_color(ticks), Qt.ForegroundRole)
        self.snap_box.setCurrentIndex(3)
        self.snap_box.currentIndexChanged.connect(self._snap_from_box)
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.toggle_play)
        self.rate_box = QComboBox()
        self.rate_box.addItems(["1x", "0.75x", "0.5x"])
        self.rate_box.currentIndexChanged.connect(
            lambda i: setattr(self.player, "rate", (1.0, 0.75, 0.5)[i]))
        self.test_btn = QPushButton("🎮 Play test")
        self.test_btn.setToolTip("Play the chart from the cursor with the arrow keys (or D F J K). "
                                 "Esc stops and shows your score.")
        self.test_btn.clicked.connect(lambda: self.toggle_game())
        self.test_cmp_btn = QPushButton("🎮 Play test it")
        self.test_cmp_btn.setToolTip("Play test the chart picked under Compare instead of this one "
                                     "(read-only: it stays as it is).")
        self.test_cmp_btn.clicked.connect(lambda: self.toggle_game(compare=True))
        self.test_cmp_btn.setEnabled(False)
        self._testing_compare = False
        self.tick_box = QCheckBox("Tick on steps")
        self.tick_box.toggled.connect(lambda on: setattr(self.player, "tick_on", on))
        self.compare_box = QComboBox()
        self.compare_box.setToolTip(
            "Show another chart beside this one, scrolling and playing along (read-only): another "
            "difficulty of this song, or, for charts made with Follow the melody, the same chart "
            "following only the beat. Its steps at a moment this chart also steps on are dimmed, "
            "so the bright ones are where the two differ.")
        self.compare_box.currentIndexChanged.connect(lambda _i: self._load_compare())
        self.compare_sm: SMFile | None = None
        self.twin_sm: SMFile | None = None      # the "(no AI)" version of the song, or the AI one
        self.twin_name = ""
        for wdg in (self.open_btn, self.chart_box, self.save_btn, QLabel("  Snap"), self.snap_box,
                    QLabel("  "), self.play_btn, self.rate_box, self.tick_box, QLabel("  "), self.test_btn,
                    QLabel("  Compare"), self.compare_box, self.test_cmp_btn):
            top.addWidget(wdg)
        top.addStretch()
        # volume: remembered between runs; squared so the slider feels even to the ear
        self.vol = QSlider(Qt.Horizontal, minimum=0, maximum=100)
        self.vol.setFixedWidth(110)
        self.vol.valueChanged.connect(self._volume)
        self.vol.setValue(int(QSettings("BeatSmith", "BeatSmith").value("editor/volume", 50)))
        self._volume(self.vol.value())
        top.addWidget(QLabel("🔊"))
        top.addWidget(self.vol)

        # sync: move every step against the music when the whole chart is early or late
        sync = QHBoxLayout()
        self.offset_box = QDoubleSpinBox(minimum=-30, maximum=30, decimals=3, singleStep=0.005, suffix=" s")
        self.offset_box.setToolTip("The song's #OFFSET. Changing it moves every step (in all of this "
                                   "song's charts) against the music. Saved with Save.")
        self.offset_box.valueChanged.connect(self._offset_edited)
        sync.addWidget(QLabel("Sync  offset"))
        sync.addWidget(self.offset_box)
        for text, tip, fn in (
                ("◀ 10 ms", "Steps 10 ms earlier", lambda: self.shift_steps(-0.010)),
                ("10 ms ▶", "Steps 10 ms later", lambda: self.shift_steps(0.010)),
                ("◀◀ one snap", "Steps one snap step earlier (a quarter beat at 1/16, a beat at 1/4)",
                 lambda: self.shift_steps(-self._snap_seconds())),
                ("one snap ▶▶", "Steps one snap step later (a quarter beat at 1/16, a beat at 1/4)",
                 lambda: self.shift_steps(self._snap_seconds()))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            sync.addWidget(b)
        self.fix_btn = QPushButton("Match my play test")
        self.fix_btn.setToolTip("After a play test, move the steps by your average timing, so where "
                                "you naturally step is dead on.")
        self.fix_btn.setEnabled(False)
        self.fix_btn.clicked.connect(self._apply_test_timing)
        sync.addWidget(self.fix_btn)
        self.tap_btn = QPushButton("👆 Tap sync")
        self.tap_btn.setToolTip("Plays the song from the cursor: tap T on every quarter note (the beat "
                                "you'd clap to). Press the button again and the steps shift onto your taps.")
        self.tap_btn.clicked.connect(self.toggle_tap)
        sync.addWidget(self.tap_btn)
        sync.addStretch()
        self._taps: list[float] | None = None
        self._test_mean = None

        self.info = QLabel()
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        help_lbl = QLabel(
            "<b>Mouse</b>: click to add, drag down for a hold, click a step to select, drag to move, "
            "right-click to delete, drag in the ruler or Shift+drag to select, Ctrl+wheel to zoom, Shift+wheel scrolls a measure, the strip on the right jumps anywhere.<br>"
            "<b>Keys</b>: 1-4 toggle arrows, ↑↓ move, ←→ change snap, Space play, Ctrl+C/X/V/D, "
            "PgUp/PgDn a measure, Home/End, M mirror, Del, Ctrl+Z/Y, Ctrl+S save, T taps during Tap sync.<br>"
            "<b>Play test</b>: arrow keys or D F J K step, hold G while you feel the groove, Esc stops. "
            "Starts three seconds before the cursor.<br>"
            "<b>Groove</b>: the coloured edge of the song strip, green where the chart grooves; "
            "hover it for why.")
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #888;")

        v = QVBoxLayout(self)
        v.addLayout(top)
        v.addLayout(sync)
        self.map = ChartMap(self.field)
        self.field.overview = self.map
        self.field.changed.connect(self.map.update)
        self.field.moved.connect(self.map.update)
        lanes = QHBoxLayout()
        lanes.addWidget(self.field, 1)
        lanes.addWidget(self.map)
        v.addLayout(lanes, 1)
        v.addWidget(self.info)
        v.addWidget(help_lbl)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self._tick)
        self.save_act = QAction(self)
        self.save_act.setShortcut(QKeySequence.Save)
        self.save_act.triggered.connect(self.save)
        self.addAction(self.save_act)
        self.play_act = QAction(self)
        self.play_act.setShortcut(Qt.Key_Space)
        self.play_act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.play_act.triggered.connect(self.toggle_play)
        self.addAction(self.play_act)
        self.tap_act = QAction(self)
        self.tap_act.setShortcut(Qt.Key_T)
        self.tap_act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.tap_act.triggered.connect(self._tap)
        self.addAction(self.tap_act)
        self._status()

    # ---- file
    def pick_file(self):
        if not self.confirm_discard():
            return
        f, _ = QFileDialog.getOpenFileName(self, "Open a chart", "", "StepMania charts (*.sm)")
        if f:
            self.open(Path(f))

    def open(self, path: Path):
        self.stop()
        try:
            self.sm = SMFile(path)
        except Exception as e:
            QMessageBox.warning(self, "Editor", f"Couldn't read {path.name}: {e}")
            return
        music = self.sm.music_path()
        self.player.load_error = ""
        try:
            self.player.load(music)
        except Exception as e:
            self.player.load_error = f"couldn't load the song: {e}"
        self.field.env = self.player.envelope(self.field.env_hz)
        try:                                 # the song's hits, for the groove meter
            from beatsmith import groove
            self.onset = groove.onset_env(self.player.data[::2], self.player.sr // 2)
        except Exception:
            self.onset = None
        # BeatSmith keeps a beat-only version of melody-following charts beside the song
        cmp = outer_of(path) / ".compare" / path.name
        try:
            self.compare_sm = SMFile(cmp) if cmp.is_file() else None
        except Exception:
            self.compare_sm = None
        # temporary: BeatSmith makes "<title> (no AI)" beside songs made with AI assist
        self.twin_sm, self.twin_name = None, ""
        stem, tag = path.stem, " (no AI)"
        twin, self.twin_name = (stem[:-len(tag)], "With AI") if stem.endswith(tag) else (stem + tag, "No AI")
        twin_sm = find_sm(out_of(path) / twin, twin)
        try:
            self.twin_sm = SMFile(twin_sm) if twin_sm.is_file() else None
        except Exception:
            self.twin_sm = None
        self.offset_box.blockSignals(True)
        self.offset_box.setValue(self.sm.offset)
        self.offset_box.blockSignals(False)
        self._test_mean = None
        self.fix_btn.setEnabled(False)
        self.chart_box.blockSignals(True)
        self.chart_box.clear()
        self.chart_box.addItems([c.label for c in self.sm.charts])
        pick = max(range(len(self.sm.charts)), key=lambda i: self.sm.charts[i].diff == "Hard", default=0)
        self.chart_box.setCurrentIndex(pick)
        self.chart_box.blockSignals(False)
        self._switch_chart(pick, force=True)

    def _compare_options(self) -> dict[str, "ChartInfo"]:
        """What this chart can be shown beside: the song's other charts, and
        its beat-only version when BeatSmith kept one."""
        out: dict[str, ChartInfo] = {}
        if self.sm is None or not self.sm.charts:
            return out
        me = self.sm.charts[self.chart_i]
        if self.compare_sm is not None:
            beat = next((c for c in self.compare_sm.charts if c.stype == me.stype and c.diff == me.diff), None)
            if beat is not None:
                out["Beat only"] = beat
        if self.twin_sm is not None:
            twin = next((c for c in self.twin_sm.charts if c.stype == me.stype and c.diff == me.diff), None)
            if twin is not None:
                out[self.twin_name] = twin
        for i, c in enumerate(self.sm.charts):
            if i != self.chart_i and c.stype == me.stype:
                out[c.label] = c
        return out

    def _load_compare(self):
        opts = self._compare_options()
        want = self.compare_box.currentText() or "Off"
        names = ["Off"] + list(opts)
        if [self.compare_box.itemText(i) for i in range(self.compare_box.count())] != names:
            self.compare_box.blockSignals(True)
            self.compare_box.clear()
            self.compare_box.addItems(names)
            self.compare_box.setCurrentIndex(names.index(want) if want in names else 0)
            self.compare_box.blockSignals(False)
        other = opts.get(self.compare_box.currentText())
        if other is not None and self.sm is not None and other is not self.sm.charts[self.chart_i]:
            steps = list(other.steps)
            self.field.set_compare(steps, (f"This chart · {len(self.field.steps)} steps",
                                           f"{self.compare_box.currentText()} · {len(steps)} steps"))
        else:
            self.field.set_compare(None)
        self.test_cmp_btn.setEnabled(self.field.compare is not None and self.field.game is None)

    def _volume(self, v: int):
        self.player.volume = (v / 100) ** 2
        self.vol.setToolTip(f"Volume {v}%")
        QSettings("BeatSmith", "BeatSmith").setValue("editor/volume", v)

    # ---- tap sync
    def toggle_tap(self):
        if self._taps is not None:
            self.finish_tap()
            return
        if self.sm is None or self.field.game is not None:
            return
        if self.player.playing:
            self.stop()
        self._taps = []
        self.tap_btn.setText("✓ Done tapping (0)")
        self.toggle_play()
        self.field.setFocus()
        self.info.setText("Tap T on every quarter note, the beat you'd clap to. 8 or more taps, "
                          "then press Done (or Space).")

    def _tap(self):
        if self._taps is None or not self.player.playing:
            return
        self._taps.append(self.player.seconds)
        self.tap_btn.setText(f"✓ Done tapping ({len(self._taps)})")
        if len(self._taps) >= 4:
            shift, *_ = self._tap_fit(self._taps)
            self.info.setText(f"{len(self._taps)} taps: the steps are {abs(shift) * 1000:.0f} ms "
                              f"{'early' if shift > 0 else 'late'} against your taps. Keep going, "
                              "then press Done.")

    def _tap_fit(self, taps: list[float]) -> tuple[float, float, float | None]:
        """(seconds to move the steps later, how steady the taps were 0..1,
        the BPM the taps suggest). Uses how far each tap lands from the
        nearest beat, averaged around the circle so +0.49 and -0.49 agree."""
        beats = np.array([self.sm.beat_at(t) for t in taps])
        ang = 2 * np.pi * (beats % 1)
        c, s_ = np.cos(ang).mean(), np.sin(ang).mean()
        phase = math.atan2(s_, c) / (2 * np.pi)                   # -0.5..0.5 beats
        steady = float(math.hypot(c, s_))
        mid = float(np.median(beats))
        spb = self.sm.time_at(mid + 1) - self.sm.time_at(mid)
        gaps = np.diff(taps)
        tap_bpm = None
        if len(gaps) >= 4:
            g = np.median(gaps)
            gaps = gaps[(gaps > 0.6 * g) & (gaps < 1.6 * g)]
            tap_bpm = 60 / float(np.median(gaps)) if len(gaps) else None
        return phase * spb, steady, tap_bpm

    def finish_tap(self):
        taps, self._taps = self._taps or [], None
        self.tap_btn.setText("👆 Tap sync")
        self.stop()
        if len(taps) < 6:
            self.info.setText("Tap sync needs at least 6 taps; nothing was changed.")
            return
        shift, steady, tap_bpm = self._tap_fit(taps)
        mid = self.sm.beat_at(float(np.median(taps)))
        bpm = 60 / (self.sm.time_at(mid + 1) - self.sm.time_at(mid))
        wrong_tempo = tap_bpm and min(abs(tap_bpm / bpm - r) for r in (0.5, 1, 2)) > 0.04
        tempo_note = (f"Your taps were at about {tap_bpm:.0f} BPM but the chart is {bpm:g} BPM, so the "
                      "chart's tempo looks wrong and no offset can fix all of it. Regenerate the song "
                      f"with BPM set to {tap_bpm:.0f} in the queue.") if wrong_tempo else ""
        if steady < 0.6:
            QMessageBox.information(self, "Tap sync", "Nothing was changed: " + (
                tempo_note or "your taps didn't agree with each other. Try again on a part with a "
                              "clear beat."))
            return
        self.shift_steps(shift)
        msg = (f"Moved the steps {abs(shift) * 1000:.0f} ms {'later' if shift > 0 else 'earlier'} "
               f"to sit on your taps ({len(taps)} taps). Save to keep it.")
        if wrong_tempo:
            msg += "\n\n" + tempo_note
        QMessageBox.information(self, "Tap sync", msg)

    # ---- sync
    def _snap_seconds(self) -> float:
        beat = self.field.view_beat()
        return self.sm.time_at(beat + self.field.snap / TPB) - self.sm.time_at(beat) if self.sm else 0.0

    def shift_steps(self, dt: float):
        """Steps dt seconds later (negative: earlier) against the music."""
        if self.sm is not None:
            self.offset_box.setValue(self.sm.offset - dt)

    def _offset_edited(self, v: float):
        if self.sm is None or abs(v - self.sm.offset) < 1e-9:
            return
        self.sm.offset = v
        self.dirty = True
        self.field.update()
        self._status()

    def _apply_test_timing(self):
        if self._test_mean is not None:
            self.shift_steps(self._test_mean)      # you hit late: the steps came early, move them later
            self._test_mean = None
            self.fix_btn.setEnabled(False)

    def _switch_chart(self, i: int, force: bool = False):
        if self.sm is None or i < 0:
            return
        if not force and not self.confirm_discard():
            self.chart_box.blockSignals(True)
            self.chart_box.setCurrentIndex(self.chart_i)
            self.chart_box.blockSignals(False)
            return
        self.chart_i = i
        self.field.load(self.sm, self.sm.charts[i].steps)
        self._load_compare()
        self.dirty = False
        self._changed(mark=False)
        self.field.setFocus()

    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Editor", "Save the changes to this chart first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            self.save()
            return True
        return r == QMessageBox.Discard

    def save(self):
        if self.sm is None:
            return
        try:
            self.sm.save(self.chart_i, self.field.steps)
        except OSError as e:
            QMessageBox.warning(self, "Editor", f"Couldn't save: {e}")
            return
        self.dirty = False
        self._status(saved=True)

    # ---- play
    def toggle_game(self, compare: bool = False):
        if self.field.game is not None:
            self.end_game()
            return
        if self.sm is None or (compare and self.field.compare is None):
            return
        self.stop()
        start = self.field.cursor
        self._testing_compare = compare
        self.field.game = Game(self.sm, self.field.compare if compare else self.field.steps, start)
        self.field.sel = set()
        self.player.ticks = np.zeros(0)
        # a lead-in before the first note, even at the very start of the song
        # (the audio waits in silence until its own time comes)
        self.player.play(self.sm.time_at(start / TPB) - LEAD_IN)
        (self.test_cmp_btn if compare else self.test_btn).setText("■ Stop test")
        for w in (self.play_btn, self.chart_box, self.open_btn, self.save_btn, self.compare_box,
                  self.test_btn if compare else self.test_cmp_btn):
            w.setEnabled(False)
        self._start_timer()
        self.field.setFocus()

    def end_game(self):
        g = self.field.game
        if g is None:
            return
        self.stop()
        self.field.game = None
        self.test_btn.setText("🎮 Play test")
        self.test_cmp_btn.setText("🎮 Play test it")
        for w in (self.play_btn, self.chart_box, self.open_btn, self.save_btn, self.compare_box, self.test_btn):
            w.setEnabled(True)
        self.test_cmp_btn.setEnabled(self.field.compare is not None)
        self.field.update()
        if self._testing_compare:
            # someone else's chart: no timing fix or groove marks for this one
            self._testing_compare = False
            if any(n["j"] for n in g.notes):
                QMessageBox.information(self, "Play test", f"{self.compare_box.currentText()}\n\n" + g.summary())
            return
        if len(g.offsets) >= 10:
            self._test_mean = float(np.median(g.offsets))
            self.fix_btn.setEnabled(abs(self._test_mean) >= 0.005)
            self.fix_btn.setToolTip(f"Move the steps {abs(self._test_mean) * 1000:.0f} ms "
                                    f"{'later' if self._test_mean > 0 else 'earlier'}, to where you "
                                    "stepped on average in the last play test.")
        if any(n["j"] for n in g.notes):
            QMessageBox.information(self, "Play test", g.summary() + self._groove_marks(g))

    def toggle_play(self):
        if self.field.game is not None:
            self.end_game()
            return
        if self.player.playing:
            self.stop()
        elif self.sm is not None:
            self.player.ticks = np.array(sorted({self.sm.time_at(s.tick / TPB) for s in self.field.steps
                                                 if s.kind != "M"}))
            self.player.play(max(0.0, self.sm.time_at(self.field.cursor / TPB)))
            self.play_btn.setText("❚❚ Pause")
            self._start_timer()

    def _start_timer(self):
        # one frame per screen refresh: drawing faster than the screen shows
        # only costs CPU, which slower PCs don't have to spare
        hz = self.screen().refreshRate() if self.screen() else 60.0
        self.timer.setInterval(max(8, int(1000 / max(hz, 30.0))))   # 125 fps at most
        self.timer.start()

    def stop(self):
        if self._taps is not None:
            self.finish_tap()
            return
        was = self.player.playing or self.field.play_beat is not None
        self.player.stop()
        self.timer.stop()
        self.play_btn.setText("▶ Play")
        if was and self.sm is not None and self.field.play_beat is not None:
            snap = self.field.snap
            self.field.cursor = max(0, round(self.field.play_beat * TPB / snap) * snap)
        self.field.play_beat = None
        self.field.update()
        self._status()

    def _tick(self):
        g = self.field.game
        if g is not None:
            now = self.player.seconds
            g.update(now)
            if g.done(now) or not self.player.playing:
                self.end_game()
                return
        elif not self.player.playing:
            self.stop()
            return
        self.field.play_beat = self.sm.beat_at(self.player.seconds)
        self.field.update()
        self.map.update()
        # new status text re-lays out the whole panel, so it's updated a few times
        # a second while playing rather than every frame
        now = time.perf_counter()
        if now - getattr(self, "_status_at", 0.0) > 0.1:
            self._status_at = now
            self._status()

    # ---- status
    def _snap_from_box(self, i):
        self.field.snap = SNAPS[i][1]
        self.field.cursor = round(self.field.cursor / self.field.snap) * self.field.snap
        self.field.update()
        self.field.setFocus()

    def _changed(self, mark: bool = True):
        if mark:
            self.dirty = True
        self._rating = self.rating()
        self.field.groove = self.groove()
        if self.field.compare is not None:
            self._load_compare()          # keep the step counts current
        self._status()

    def _status(self, saved: bool = False):
        i = [s for _, s in SNAPS].index(self.field.snap)
        if self.snap_box.currentIndex() != i:
            self.snap_box.blockSignals(True)
            self.snap_box.setCurrentIndex(i)
            self.snap_box.blockSignals(False)
        if self.sm is None:
            self.info.setText("Open a .sm chart to edit it, or pick a finished song in the Generate tab "
                              "and press Edit chart.")
            return
        beat = self.field.view_beat()
        steps = self.field.steps
        # this runs every frame while playing; the counts only change on edits
        key = (id(steps), len(steps))
        if getattr(self, "_counts_key", None) != key:
            per_row = Counter(s.tick for s in steps if s.kind != "M")
            self._counts_key = key
            self._counts = (f"{len(steps)} arrows, {sum(n > 1 for n in per_row.values())} jumps, "
                            f"{sum(s.kind in '24' for s in steps)} holds")
        rating = getattr(self, "_rating", 0.0)
        parts = [f"measure {int(beat // 4) + 1}, beat {beat % 4 + 1:.2f}",
                 f"{max(0.0, self.sm.time_at(beat)):.2f}s",
                 self._counts,
                 f"rates about {rating:.1f}" if rating else "",
                 f"groove {self.field.groove.total:.0f}" if self.field.groove else "",
                 f"{len(self.field.sel)} selected" if self.field.sel else "",
                 "unsaved changes" if self.dirty else ("saved" if saved else ""),
                 "has stops: they're ignored while editing" if self.sm.has_stops else "",
                 self.player.error or self.player.load_error]
        self.info.setText("   ·   ".join(p for p in parts if p))

    def groove(self):
        """The groove meter for the chart as it is now (see groove.py)."""
        try:
            from beatsmith import groove
        except Exception:
            return None
        rows: dict[int, list[int]] = {}
        for s in self.field.steps:
            if s.kind != "M":
                rows.setdefault(s.tick, []).append(s.col)
        if len(rows) < 20 or self.sm is None:
            return None
        return groove.score([(t / TPB, tuple(sorted(c))) for t, c in sorted(rows.items())],
                            self.sm.time_at, getattr(self, "onset", None),
                            self.field.env if len(self.field.env) > 1 else None, self.field.env_hz)

    def _groove_marks(self, g: Game) -> str:
        """Where you held G in the play test, against the groove meter; kept
        beside the chart in <title>.groove-marks.json to check the meter by."""
        marks = [(a, b if b is not None else self.player.seconds) for a, b in g.grooving]
        gr = self.field.groove
        if not marks or gr is None or self.sm is None:
            return ""
        judged = [n for n in g.notes if n["j"] is not None]
        if not judged:
            return ""
        m0 = int(self.sm.beat_at(judged[0]["t"]) // 4)
        m1 = int(self.sm.beat_at(judged[-1]["t"]) // 4)
        marked = set()
        for a, b in marks:
            marked.update(range(int(self.sm.beat_at(a) // 4), int((self.sm.beat_at(b) - 0.01) // 4) + 1))
        tested = [m for m in range(m0, m1 + 1) if m < len(gr.measures) and not np.isnan(gr.measures[m])]
        yes = [gr.measures[m] for m in tested if m in marked]
        no = [gr.measures[m] for m in tested if m not in marked]
        try:
            import datetime
            import json
            path = side_file(self.sm.path, ".groove-marks.json")
            log = json.loads(path.read_text()) if path.is_file() else []
            log.append({"when": datetime.datetime.now().isoformat(timespec="seconds"),
                        "chart": self.sm.charts[self.chart_i].label,
                        "measures_tested": [m0 + 1, m1 + 1],
                        "marked_grooving": sorted(m + 1 for m in marked if m0 <= m <= m1),
                        "meter": {str(m + 1): {"groove": round(float(gr.measures[m]), 1)}
                                  | {p: round(float(gr.parts[p][m]), 2) for p in gr.parts
                                     if not np.isnan(gr.parts[p][m])} for m in tested}})
            path.write_text(json.dumps(log, indent=1))
        except Exception:
            pass
        text = f"\n\nYou marked {len(yes)} of {len(tested)} measures as grooving (G)."
        if yes and no:
            text += (f"\nGroove meter: {np.mean(yes):.0f} where you marked, {np.mean(no):.0f} elsewhere"
                     + (" (agrees)" if np.mean(yes) > np.mean(no) + 3 else
                        " (disagrees: the meter needs tuning)" if np.mean(yes) < np.mean(no) - 3 else ""))
        return text

    def rating(self) -> float:
        """BeatSmith's Konami-fitted difficulty estimate for the chart as it is now."""
        try:
            from beatsmith import stepgen
        except Exception:
            return 0.0
        rows: dict[int, list[int]] = {}
        for s in self.field.steps:
            if s.kind != "M":
                rows.setdefault(s.tick, []).append(s.col)
        if len(rows) < 20:
            return 0.0
        bpm = self.sm.bpms[0][1]
        notes = []
        for t, cols in sorted(rows.items()):
            held = any(s.tick == t and s.kind in "24" for s in self.field.steps)
            # BeatSmith rates on a 16th grid
            notes.append(stepgen.Note(row=round(t * 4 / TPB), time=0, strength=0, kick=0,
                                      panels=cols, hold_rows=1 if held else 0))
        return stepgen.estimate_meter(notes, 60 / bpm)


def main():
    app = QApplication(sys.argv)
    from beatsmith.form_controls import protect_form_wheels
    protect_form_wheels(app)
    win = QMainWindow()
    ed = EditorWidget()
    win.setCentralWidget(ed)
    win.resize(900, 900)
    win.setWindowTitle("BeatSmith editor")
    win.show()
    if len(sys.argv) > 1:
        ed.open(Path(sys.argv[1]))
    sys.exit(app.exec())


if __name__ == "__main__":

    main()
