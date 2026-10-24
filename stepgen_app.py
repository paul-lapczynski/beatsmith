"""stepgen app: a window around stepgen.py.

Queue up songs (files, whole folders, or drag and drop), pick a style and
how hard each chart should be, and it writes one song folder per song into
the output folder you choose.

    python stepgen_app.py

Needs PySide6 on top of stepgen's own requirements (pip install PySide6).
"""
from __future__ import annotations

import html
import json
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import fields
from pathlib import Path

# the installed app runs stepgen itself in child processes: "stepgen.exe
# --run-stepgen <args>" is the command-line tool
if len(sys.argv) > 1 and sys.argv[1] == "--run-stepgen":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import stepgen
    sys.exit(stepgen.main(sys.argv[2:]))
if len(sys.argv) > 1 and sys.argv[1] in ("--install-stems", "--install-addon"):
    # an optional download (vocal separation, AI verse detection), run in a
    # child so the window stays live
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import addons
    addons.install(lambda m: print(m, flush=True), sys.argv[2] if len(sys.argv) > 2 else "stems")
    sys.exit(0)

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QSettings, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QProgressDialog,
    QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE))
import stepgen  # noqa: E402
from layout import file_name, find_sm, outer_of, side, song_dirs  # noqa: E402
import artwork  # noqa: E402
import export  # noqa: E402

APP_NAME = "stepgen"
AUDIO_EXT = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".aac", ".wma", ".opus"}
CHART_EXT = {".sm", ".ssc", ".dwi"}
DIFFS = ("Easy", "Medium", "Hard")
SECTION_KINDS = ("chorus", "verse", "bridge", "build", "breakdown", "intro", "outro")
SLIDER_LABELS = {
    "energy": ("Energy / arc", "flat", "dramatic"),
    "jumps": ("Jumps", "none", "lots"),
    "speed": ("Speed", "on the beat, no 16ths", "busy, more 16ths"),
    "breathing": ("Breathing room", "nonstop runs", "more pauses"),
    "footwork": ("Footwork", "simple", "technical"),
    "holds": ("Holds", "none", "lots"),
    "repetition": ("Repetition", "always fresh", "choruses identical"),
}
# columns of the queue
C_SONG, C_TITLE, C_ARTIST, C_BPM, C_STATUS, C_METERS, C_SETTINGS = range(7)
READY = "Ready"
DONE, FAILED, SKIPPED, CANCELLED = "Done", "Failed", "Skipped", "Cancelled"
EARLIER = "Made earlier"            # already in the output folder, shown by "Show songs already made"
MADE = (DONE, SKIPPED, EARLIER)


# Warnings the audio decoders (libmpg123, libsndfile) print straight to the
# console, such as "[...id3.c:process_comment():587] error: No comment text"
# for an untidy tag in an MP3. Harmless, so they go to decoder.log in the
# app's data folder instead of the song's log.
DECODER_NOISE = re.compile(r"^\[[^\]]*\.c:\w+\(\):\d+\]|^\[(?:src/)?libmpg123|^\[mpg123")


def internal_log(name: str, text: str) -> None:
    try:
        d = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "decoder.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {name}: {text}\n")
    except OSError:
        pass


def user_profiles_dir() -> Path:
    d = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile_paths() -> dict[str, Path]:
    """Built-in profiles plus the ones saved from the app."""
    out = {"default": stepgen.DEFAULT_PATTERNS}
    for d in (stepgen.PROFILES_DIR, user_profiles_dir()):
        for f in sorted(d.glob("*.toml")):
            out[f.stem] = f
    return out


def read_tags(path: Path) -> tuple[str, str]:
    """Title and artist from the file's tags, else the file name."""
    title, artist = path.stem, ""
    try:
        import mutagen
        tags = mutagen.File(str(path), easy=True)
        if tags:
            title = (tags.get("title") or [title])[0].strip() or title
            artist = (tags.get("artist") or [""])[0].strip()
    except Exception:
        pass
    m = re.match(r"^\s*(.+?)\s+-\s+(.+)$", path.stem)          # "Artist - Title.mp3"
    if title == path.stem and m and not artist:
        artist, title = m.group(1).strip(), m.group(2).strip()
    return title, artist


def safe_name(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", s).strip().rstrip(".") or "song"


def foreign_charts(folder: Path) -> list[Path]:
    """Charts in this folder (and one level down) that stepgen didn't write."""
    found = []
    if not folder.is_dir():
        return found
    for f in list(folder.glob("*")) + list(folder.glob("*/*")):
        if f.suffix.lower() in CHART_EXT:
            try:
                head = f.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                continue
            if "#CREDIT:stepgen" not in head:
                found.append(f)
    return found


class Job:
    def __init__(self, path: Path, title: str | None = None, artist: str = ""):
        self.path = path
        self.title, self.artist = (title, artist) if title else read_tags(path)
        self.bpm = 0.0
        self.status = READY
        self.settings: dict = {}       # this song's own settings (see Window.capture)
        self.force = False             # regenerate even if "skip done" would skip it
        self.log = ""
        self.partial = ""              # output after the last line break, waiting for the rest of its line
        self.meters: dict[str, str] = {}
        self.sm: Path | None = None
        self.proc: QProcess | None = None
        # artwork, found when the song is added (ArtFinder): "" not looked for,
        # "looking", "found" (art_image is the picture), "kept" (the song
        # folder already has art), "none", "cleared" (No artwork pressed)
        self.art_state = ""
        self.art_image: Path | None = None
        self.art_where: dict = {}
        self.art_log = ""


def song_info(path: Path) -> list[tuple[str, str]]:
    """What the song file says about itself, for the Details tab."""
    rows = [("File", str(path))]
    try:
        import mutagen
        f = mutagen.File(str(path), easy=True)
    except Exception:
        f = None
    if f is None:
        return rows
    tags = f.tags or {}
    for key, name in (("album", "Album"), ("date", "Year"), ("genre", "Genre"), ("tracknumber", "Track")):
        try:
            v = (tags.get(key) or [""])[0].strip()
        except Exception:
            v = ""
        if v:
            rows.append((name, v))
    info = getattr(f, "info", None)
    if info is not None:
        if getattr(info, "length", 0):
            m, sec = divmod(int(round(info.length)), 60)
            rows.append(("Length", f"{m}:{sec:02d}"))
        fmt = [path.suffix.lstrip(".").upper()]
        if getattr(info, "bitrate", 0):
            fmt.append(f"{info.bitrate // 1000} kbps")
        if getattr(info, "sample_rate", 0):
            fmt.append(f"{info.sample_rate / 1000:g} kHz")
        if getattr(info, "channels", 0):
            fmt.append({1: "mono", 2: "stereo"}.get(info.channels, f"{info.channels} channels"))
        rows.append(("Format", ", ".join(fmt)))
    return rows


class ArtFinder(QObject):
    """Finds each added song's artwork on one background thread, in the
    order they were added (one at a time also keeps to MusicBrainz's one
    request a second), and draws the banner, background and jacket."""
    done = Signal(object, object, object, str)          # job, picture file or None, where, log

    def __init__(self, folder: Path):
        super().__init__()
        self.folder = folder
        self.todo: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def find(self, job: Job, song: Path | None, online: bool, image: Path | None = None):
        self.todo.put((job, job.path, job.title, job.artist, song, online, image, out_title(job)))

    def _run(self):
        n = 0
        while True:
            job, src, title, artist, song, online, image, name = self.todo.get()
            lines = []
            try:
                if image is not None:
                    data, where = image.read_bytes(), {"from": "picked by hand", "file": image.name}
                else:
                    data, where = artwork.find(src, title, artist, song, online, lines.append, name)
                pic = None
                if data is not None:
                    n += 1
                    d = self.folder / str(n)
                    d.mkdir(parents=True, exist_ok=True)
                    pic = d / "picture"
                    pic.write_bytes(data)
                    artwork.draw(data, {tag: d / f"{tag}.png" for tag in ("BANNER", "BACKGROUND", "JACKET")})
            except Exception as e:
                pic, where = None, {"from": None}
                lines.append(f"  artwork: failed ({e})")
            self.done.emit(job, pic, where, "\n".join(lines))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("stepgen")
        self.resize(1250, 800)
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.jobs: list[Job] = []
        self.overrides: dict[str, float] = {}       # "Hard.jump" -> value, from Advanced
        self.running: list[Job] = []
        self.stopping = False
        self._loading = False           # true while the panel is being filled from a song
        self.defaults: dict = {}        # what new songs start with
        self.setAcceptDrops(True)

        root = QSplitter(Qt.Horizontal)
        root.addWidget(self._queue_panel())
        # the settings scroll when the window is shorter than they are
        settings = QScrollArea()
        settings.setWidget(self._settings_panel())
        settings.setWidgetResizable(True)
        settings.setFrameShape(QScrollArea.NoFrame)
        settings.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        settings.setMinimumWidth(settings.widget().minimumSizeHint().width()
                                 + settings.verticalScrollBar().sizeHint().width())
        root.addWidget(settings)
        root.setStretchFactor(0, 3)
        root.setStretchFactor(1, 2)
        from chart_editor import EditorWidget
        self.editor = EditorWidget()
        self.tabs = QTabWidget()
        self.tabs.addTab(root, "Generate")
        self.tabs.addTab(self.editor, "Edit")
        self.setCentralWidget(self.tabs)
        self._menus()
        self._load_settings()
        self.refresh_advanced()
        self.defaults = self.capture()
        self._watch_panel()
        self._scope()
        self.statusBar().showMessage("Add songs to get started: drop files or folders here.")

    # ---------------------------------------------------------------- layout
    def _menus(self):
        m = self.menuBar().addMenu("&File")
        for text, fn in (("Add songs…", self.add_files), ("Add folder…", self.add_folder),
                         ("Export songs…", self.export_songs),
                         ("Save settings as profile…", self.save_profile)):
            a = QAction(text, self)
            a.triggered.connect(fn)
            m.addAction(a)
        m.addSeparator()
        q = QAction("Quit", self)
        q.triggered.connect(self.close)
        m.addAction(q)
        h = self.menuBar().addMenu("&Help")
        a = QAction("Open README", self)
        a.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(HERE / "README.md"))))
        h.addAction(a)

    def _queue_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        bar = QHBoxLayout()
        for text, fn in (("Add songs…", self.add_files), ("Add folder…", self.add_folder),
                         ("Remove", self.remove_selected), ("Clear finished", self.clear_finished)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch()
        self.show_made = QCheckBox("Show songs already made")
        self.show_made.setToolTip("List the songs stepgen has already made in the output folder, "
                                  "with their meters and settings, so you can see what you have, "
                                  "open them in the editor or regenerate them.")
        self.show_made.toggled.connect(self.refresh_made)
        bar.addWidget(self.show_made)
        b = QPushButton("Export…")
        b.setToolTip("Copy made songs into StepMania's Songs folder (or a zip): just the chart, "
                     "the song and its pictures.")
        b.clicked.connect(self.export_songs)
        bar.addWidget(b)
        v.addLayout(bar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Song file", "Title", "Artist", "BPM", "Status",
                                              "Meters E/M/H", "Settings"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(C_SONG, QHeaderView.Stretch)
        hh.setSectionResizeMode(C_TITLE, QHeaderView.Stretch)
        for c in (C_ARTIST, C_BPM, C_STATUS, C_METERS, C_SETTINGS):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._cell_edited)
        self.table.itemSelectionChanged.connect(self.show_selected)
        self.table.setToolTip("Title, artist and BPM can be edited. BPM 'auto' detects it. Select "
                              "songs to see or change their settings on the right.")

        detail = QTabWidget()
        self.stats_view = QTextBrowser()
        self.stats_view.setOpenExternalLinks(True)
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setFont(QFont("Consolas", 9))
        detail.addTab(self._details_tab(), "Details")
        detail.addTab(self.stats_view, "Chart stats")
        detail.addTab(self.log_view, "Log")
        self.open_btn = QPushButton("Open song folder")
        self.open_btn.clicked.connect(self.open_selected)
        self.open_btn.setEnabled(False)
        self.edit_btn = QPushButton("Edit chart")
        self.edit_btn.clicked.connect(self.edit_selected)
        self.edit_btn.setEnabled(False)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        dw = QWidget()
        dv = QVBoxLayout(dw)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.addWidget(detail)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.edit_btn)
        btns.addWidget(self.open_btn)
        dv.addLayout(btns)
        split.addWidget(dw)
        split.setSizes([450, 300])
        v.addWidget(split)

        run = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setFormat("%v of %m songs")
        self.go_btn = QPushButton("Generate")
        self.go_btn.setDefault(True)
        self.go_btn.setMinimumWidth(130)
        self.go_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Cancel")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.cancel)
        run.addWidget(self.progress, 1)
        run.addWidget(self.stop_btn)
        run.addWidget(self.go_btn)
        v.addLayout(run)
        return w

    def _settings_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        # which songs the panel below is showing and changing
        self.scope_lbl = QLabel()
        self.scope_lbl.setWordWrap(True)
        self.scope_lbl.setStyleSheet("padding: 6px; border-radius: 4px;")
        self.regen_btn = QPushButton("Change settings and regenerate")
        self.regen_btn.setToolTip("Unlock this song so you can change its settings; Generate then "
                                  "makes it again, replacing the old charts.")
        self.regen_btn.clicked.connect(self.unlock_selected)
        sc = QHBoxLayout()
        sc.addWidget(self.scope_lbl, 1)
        sc.addWidget(self.regen_btn)
        v.addLayout(sc)

        out = QGroupBox("Where the charts go")
        f = QFormLayout(out)
        row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Pick a folder")
        self.out_edit.setToolTip("Each song gets a folder in here, and inside it a folder with just "
                                 "the chart and the song: copy that one into StepMania's Songs/<group>/. "
                                 "A song folder that already has charts stepgen didn't make is never touched.")
        b = QPushButton("Browse…")
        b.clicked.connect(self.pick_out_dir)
        row.addWidget(self.out_edit)
        row.addWidget(b)
        f.addRow("Output folder", row)
        self.out_edit.editingFinished.connect(self.refresh_made)
        self.skip_done = QCheckBox("Skip songs that already have stepgen charts there")
        self.skip_done.setChecked(True)
        f.addRow(self.skip_done)
        v.addWidget(out)

        style = QGroupBox("Style")
        g = QFormLayout(style)
        self.profile = QComboBox()
        self.profile.currentTextChanged.connect(self.refresh_advanced)
        g.addRow("Profile", self.profile)
        self.seed = QSpinBox(minimum=1, maximum=9999)
        self.seed.setToolTip("Same timing, a different arrow layout")
        g.addRow("Seed", self.seed)
        # the song's tempo, when detection gets it wrong (0 = detect it)
        self.bpm = QDoubleSpinBox(minimum=0, maximum=400, decimals=3, singleStep=1, value=0)
        self.bpm.setSpecialValueText("detect")
        self.bpm.setToolTip("The song's BPM, if stepgen reads it wrong (a tap sync in the Edit tab or an "
                            "online BPM finder tells you). Leave on 'detect' to let stepgen find it.")
        g.addRow("BPM", self.bpm)
        # optional: cut the song down the way arcade versions are (shorten.py)
        self.shorten = QComboBox()
        self.shorten.addItems([label for label, _ in SHORTEN])
        self.shorten.setToolTip("Try to shorten the song: it jumps past repeated parts, only where the "
                                "music on both sides of the jump is alike, so the beat and the chords carry "
                                "straight through. The start and the ending stay. A song with no clean "
                                "place to cut is left full length. Makes a separate '<title> (short)' "
                                "song; the full one isn't touched.")
        self.keep_verses = QCheckBox("Keep all verses")
        self.keep_verses.setToolTip("When shortening: only skip choruses, the intro and outro, and quiet "
                                    "breakdowns, so every verse stays. Uses AI verse detection (under "
                                    "Melody analysis) to know which parts are verses: from the music "
                                    "alone it can't tell, and would keep nearly everything.")
        row = QHBoxLayout()
        row.addWidget(self.shorten, 1)
        row.addWidget(self.keep_verses)
        g.addRow("Length", row)
        self.shorten.currentIndexChanged.connect(self._melody_state)
        self.keep_verses.setEnabled(False)
        v.addWidget(style)
        self.style_box = style

        tabs = QTabWidget()
        self.easy_page, self.adv_page = self._easy_tab(), self._advanced_tab()
        tabs.addTab(self.easy_page, "Easy")
        tabs.addTab(self.adv_page, "Advanced")
        tabs.addTab(self._options_tab(), "Options (all songs)")
        v.addWidget(tabs, 1)
        self.reload_profiles()
        return w

    def _easy_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.sliders: dict[str, QSlider] = {}
        # the overall one, on top of everything: moves many settings at once
        # toward charts you can groove to, and at the high end makes a few
        # versions of each chart and keeps the one the groove meter likes best
        gbox = QGroupBox("Groove (overall)")
        gg = QGridLayout(gbox)
        gs = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=0)
        gs.setTickInterval(25)
        gs.setTickPosition(QSlider.TicksBelow)
        gs.valueChanged.connect(self.refresh_advanced)
        gs.setToolTip("0 is off (the profile as it is). Right: rhythms that come back bar to bar, pauses in runs and rests after "
                      "hard parts, stomps on big beats, steps on the drums, comfy footwork, busy "
                      "where the song is loud. From about 20% it also makes 2-4 versions of each chart "
                      "and keeps the one with the best groove meter score (slower). The Feel "
                      "sliders below still have the last word.\nMoves: "
                      + ", ".join(k for k, _, _ in stepgen.EASY_SLIDERS["groove"]))
        self.groove = gs                # 0 off, 100 the most (not one of the Feel sliders)
        gg.addWidget(QLabel("<b>Groove</b>"), 0, 0)
        gg.addWidget(QLabel("off"), 0, 1, alignment=Qt.AlignRight)
        gg.addWidget(gs, 0, 2)
        gg.addWidget(QLabel("made to groove"), 0, 3)
        v.addWidget(gbox)
        diff = QGroupBox("Difficulty (Konami's 1-10 feet scale)")
        gl = QGridLayout(diff)
        self.target_on, self.target = {}, {}
        for i, (d, val) in enumerate(zip(DIFFS, (3, 6, 8))):
            cb = QCheckBox(d)
            cb.setChecked(True)
            sb = QDoubleSpinBox(minimum=1, maximum=10, singleStep=0.5, decimals=1, value=val)
            sb.setMaximumWidth(90)
            cb.toggled.connect(sb.setEnabled)
            cb.toggled.connect(self.refresh_advanced)
            sb.valueChanged.connect(self.refresh_advanced)
            self.target_on[d], self.target[d] = cb, sb
            gl.addWidget(cb, i, 0)
            gl.addWidget(sb, i, 1)
            gl.setColumnStretch(2, 1)
        unticked = QLabel("Unticked: the profile's own settings decide, and the chart "
                          "gets whatever rating they produce.")
        unticked.setWordWrap(True)
        gl.addWidget(unticked, 3, 0, 1, 3)
        self.backoff = QCheckBox("Cut the easier charts out of the hardest (backoff)")
        self.backoff.setToolTip("Hard is made first; Medium and Easy keep its steps and arrows and "
                                "only lose the harder ones (16ths, weak off-beats, extra jumps), so "
                                "two players on different difficulties dance the same song.")
        gl.addWidget(self.backoff, 4, 0, 1, 3)
        v.addWidget(diff)

        feel = QGroupBox("Feel (the middle leaves the profile as it is)")
        gl = QGridLayout(feel)
        for i, (key, (label, lo, hi)) in enumerate(SLIDER_LABELS.items()):
            s = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=50)
            s.setTickInterval(25)
            s.setTickPosition(QSlider.TicksBelow)
            s.valueChanged.connect(self.refresh_advanced)
            s.setToolTip("Moves: " + ", ".join(k for k, _, _ in stepgen.EASY_SLIDERS[key])
                         + ("\nNo effect on Easy: it has no runs to break up." if key == "breathing" else ""))
            self.sliders[key] = s
            gl.addWidget(QLabel(f"<b>{label}</b>" + ("<br><small>(not on Easy: no runs there)</small>"
                                                       if key == "breathing" else "")), i, 0)
            gl.addWidget(QLabel(lo), i, 1, alignment=Qt.AlignRight)
            gl.addWidget(s, i, 2)
            gl.addWidget(QLabel(hi), i, 3)
        reset = QPushButton("Reset sliders")
        reset.clicked.connect(lambda: [s.setValue(50) for s in self.sliders.values()])
        gl.addWidget(reset, len(SLIDER_LABELS), 2, alignment=Qt.AlignRight)
        # a difficulty of 9 or 10 is reached by pushing past these sliders
        self.high_warn = QLabel()
        self.high_warn.setWordWrap(True)
        self.high_warn.setStyleSheet("padding: 4px; border-radius: 4px; background: #fdebd0; color: #222;")
        self.high_warn.hide()
        gl.addWidget(self.high_warn, len(SLIDER_LABELS) + 1, 0, 1, 4)
        for d in DIFFS:
            self.target_on[d].toggled.connect(self._high_warning)
            self.target[d].valueChanged.connect(self._high_warning)
        feel_box = feel                 # added after the melody box, below

        mel = QGroupBox("Melody analysis (try it out)")
        gl = QGridLayout(mel)
        # one opt-in: it separates the vocals (a download the first time), and
        # everything below it reads the separated vocals
        self.stems_box = QCheckBox("Enable melody analysis (separates the vocals)")
        self.stems_box.setToolTip("So the arrows can follow the singing; about a minute per song. Uses Demucs to split each song into vocals, drums, bass and the rest. "
                                  "Arrows follow and AI verse detection work from the vocals. Kept in a "
                                  ".stems folder per song. The first time, it offers the download "
                                  "(about 1 GB) and shows where every part comes from.")
        self.stems_btn = QPushButton("Download melody analysis (about 1 GB)…")
        self.stems_btn.clicked.connect(lambda: self.install_addon("stems"))
        self.stems_box.toggled.connect(self._melody_toggled)
        gl.addWidget(self.stems_box, 0, 0, 1, 3)
        gl.addWidget(self.stems_btn, 0, 3)
        self.follow = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=0)
        self.follow.setTickInterval(25)
        self.follow.setTickPosition(QSlider.TicksBelow)
        self.follow.valueChanged.connect(self.refresh_advanced)
        self.follow.valueChanged.connect(self._follow_auto)
        self.follow.setToolTip("How much the arrows follow the tune instead of the drums. Each kind "
                               "of section takes its share of this; open \"Per section\" to see or "
                               "change it.")
        self.melody_widgets = [QLabel("<b>Arrows follow</b>"), QLabel("the beat"), self.follow, QLabel("the tune")]
        gl.addWidget(self.melody_widgets[0], 1, 0)
        gl.addWidget(self.melody_widgets[1], 1, 1, alignment=Qt.AlignRight)
        gl.addWidget(self.follow, 1, 2)
        gl.addWidget(self.melody_widgets[3], 1, 3)
        # per kind of section: follows the main slider (scaled) until moved by hand
        self.sec_toggle = QPushButton("Per section ▸")
        self.sec_toggle.setFlat(True)
        self.sec_toggle.setStyleSheet("text-align: left;")
        self.sec_toggle.setCheckable(True)
        gl.addWidget(self.sec_toggle, 2, 0, 1, 2, alignment=Qt.AlignLeft)
        self.melody_widgets.append(self.sec_toggle)
        self.sec_box = QWidget()
        sg = QGridLayout(self.sec_box)
        sg.setContentsMargins(16, 0, 0, 0)
        note = QLabel("Moving one of these sets that kind of section by hand; the rest keep "
                      "following the slider above. Section names are stepgen's best guess "
                      "(each song's stats list what it found).")
        note.setWordWrap(True)
        sg.addWidget(note, 0, 0, 1, 3)
        self.sec_sliders: dict[str, tuple[QSlider, QLabel, QLabel]] = {}
        self.sec_manual: set[str] = set()
        for i, kind in enumerate(SECTION_KINDS, 1):
            name = QLabel(kind.capitalize())
            sl = QSlider(Qt.Horizontal, minimum=0, maximum=100)
            val = QLabel()
            val.setMinimumWidth(110)
            sl.valueChanged.connect(lambda _v, k=kind: self._sec_moved(k))
            sg.addWidget(name, i, 0)
            sg.addWidget(sl, i, 1)
            sg.addWidget(val, i, 2)
            self.sec_sliders[kind] = (sl, name, val)
        auto = QPushButton("All back to automatic")
        auto.clicked.connect(lambda: (self.sec_manual.clear(), self._follow_auto()))
        sg.addWidget(auto, len(SECTION_KINDS) + 1, 1, alignment=Qt.AlignRight)
        self.sec_box.setVisible(False)
        self.sec_toggle.toggled.connect(lambda on: (self.sec_box.setVisible(on),
                                                     self.sec_toggle.setText("Per section " + ("▾" if on else "▸"))))
        gl.addWidget(self.sec_box, 3, 0, 1, 4)
        self.melody_widgets.append(self.sec_box)
        self._follow_auto()
        self.lyrics_box = QCheckBox("Use AI verse detection (reads the lyrics)")
        self.lyrics_box.setToolTip(
            "Reads the words off the separated vocals with a speech model (Whisper, on the CPU), so "
            "a part whose words come back is the chorus and new words are a verse. Sections are "
            "named from that: it changes how much each part follows the melody and what Shorten "
            "and Keep all verses treat as a verse. Part of melody analysis; about a minute per song, "
            "kept with the stems.")
        self.lyrics_btn = QPushButton("Download AI verse detection (about 650 MB)…")
        self.lyrics_btn.clicked.connect(lambda: self.install_addon("lyrics"))
        self.lyrics_box.toggled.connect(self._melody_state)
        gl.addWidget(self.lyrics_box, 4, 0, 1, 3)
        gl.addWidget(self.lyrics_btn, 4, 3)
        self._stems_ready()
        ai = QGroupBox("AI assist (trained on hand-made charts, try it out)")
        gl = QGridLayout(ai)
        self.ai = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=0)
        self.ai.setTickInterval(25)
        self.ai.setTickPosition(QSlider.TicksBelow)
        self.ai.valueChanged.connect(self.refresh_advanced)
        gl.addWidget(QLabel("<b>Steps placed by</b>"), 0, 0)
        gl.addWidget(QLabel("stepgen's rules"), 0, 1, alignment=Qt.AlignRight)
        gl.addWidget(self.ai, 0, 2)
        gl.addWidget(QLabel("the AI model"), 0, 3)
        if ai_ready():
            self.ai.setToolTip("Where the arrows go, learned from about 4,000 hand-made charts. The feel "
                               "sliders, targets and profiles still apply. Adds a second or two per song.")
        else:
            self.ai.setEnabled(False)
            self.ai.setToolTip("Needs models/step_placement_v1.onnx and onnxruntime "
                               "(pip install onnxruntime).")
        v.addWidget(mel)
        v.addWidget(ai)
        v.addWidget(feel_box)            # melody first, then the feel sliders on top of it
        v.addStretch()
        return w

    def _high_warning(self, *_):
        """Say so when a difficulty of 9 or 10 will push past the Feel sliders."""
        high = [f"{d} {self.target[d].value():g}" for d in DIFFS
                if self.target_on[d].isChecked() and self.target[d].value() >= 9]
        self.high_warn.setVisible(bool(high))
        if high:
            self.high_warn.setText(
                f"<b>{', '.join(high)}</b>: to reach a 9 or 10, that chart may not keep to these "
                "sliders. Speed, Breathing room and the 16th-note limits get pushed as far as it "
                "takes; the song's stats say what was changed.")

    def _follow_auto(self, *_):
        """Show each section kind's share of the main slider, except the ones set by hand."""
        for kind, (sl, name, val) in self.sec_sliders.items():
            manual = kind in self.sec_manual
            if not manual:
                sl.blockSignals(True)
                sl.setValue(round(self.follow.value() * stepgen.FOLLOW_BY_LABEL[kind]))
                sl.blockSignals(False)
            val.setText(f"{sl.value()}%" + ("  (set by you)" if manual else "  (automatic)"))
            f = name.font()
            f.setBold(manual)
            name.setFont(f)

    def _sec_moved(self, kind: str):
        self.sec_manual.add(kind)
        self._follow_auto()

    def _stems_ready(self) -> bool:
        import addons
        ok = addons.installed("stems")
        self._stems_ok = ok
        if not ok:
            self.stems_box.setChecked(False)
        self.stems_btn.setVisible(not ok)
        lyr = addons.installed("lyrics")
        self._lyrics_ok = ok and lyr
        if not (ok and lyr):
            self.lyrics_box.setChecked(False)
        self.lyrics_btn.setVisible(not lyr)
        self.lyrics_btn.setEnabled(ok)
        self.lyrics_btn.setToolTip("" if ok else "Download melody analysis first: the lyrics are read "
                                   "off the separated vocals.")
        self._melody_state()
        return ok

    def _melody_toggled(self, on: bool):
        """Turning melody analysis on without the add-on offers the download
        (it ticks itself once that's done)."""
        if on and not getattr(self, "_stems_ok", False):
            self.stems_box.blockSignals(True)
            self.stems_box.setChecked(False)
            self.stems_box.blockSignals(False)
            if not self._loading:
                self.install_addon("stems")
        self._melody_state()

    def _melody_state(self, *_):
        """What melody analysis being on or off makes usable: Arrows follow
        and AI verse detection read the separated vocals, and Keep all verses
        needs AI verse detection to know what a verse is."""
        if not hasattr(self, "lyrics_box") or not hasattr(self, "keep_verses"):
            return
        on = self.stems_box.isChecked()
        for wdg in getattr(self, "melody_widgets", []):
            wdg.setEnabled(on)
        self.lyrics_box.setEnabled(on and getattr(self, "_lyrics_ok", False))
        if not on:
            self.lyrics_box.setChecked(False)
        verses = self.shorten.currentIndex() > 0 and self.lyrics_box.isChecked()
        self.keep_verses.setEnabled(verses)
        if not verses:
            self.keep_verses.setChecked(False)

    def install_addon(self, kind: str):
        """Download an optional add-on, after showing exactly where every part
        of it comes from."""
        import addons
        name, size = addons.NAMES[kind], addons.SIZES[kind]
        btn = {"stems": self.stems_btn, "lyrics": self.lyrics_btn, "gpu": self.gpu_btn}[kind]
        rows = "".join(f"<li>{html.escape(what)}<br><code>{html.escape(url)}</code></li>"
                       for what, url in addons.sources(kind))
        box = QMessageBox(self)
        box.setWindowTitle(name)
        box.setTextFormat(Qt.RichText)
        box.setText(f"<b>{name}</b> downloads {size} into<br><code>{html.escape(str(addons.addon_dir()))}</code>"
                    f"<br>from these places, and nowhere else:<ul>{rows}</ul>"
                    "Nothing else on your computer is changed. Go ahead?")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        if box.exec() != QMessageBox.Yes:
            return
        btn.setEnabled(False)
        btn.setText("Downloading…")
        self.log_view.clear()
        p = QProcess(self)
        p.setProgram(sys.executable)
        p.setArguments((["--install-addon", kind] if getattr(sys, "frozen", False)
                        else [str(Path(__file__).resolve()), "--install-addon", kind]))
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(
            lambda: self.log_view.appendPlainText(bytes(p.readAllStandardOutput()).decode("utf-8", "replace").rstrip()))

        def done(code, _status):
            btn.setEnabled(True)
            btn.setText(f"Download {name.lower()} ({size})…")
            self._stems_ready()
            self._gpu_state(check_install=True)
            if addons.installed(kind):
                if kind != "gpu":
                    (self.stems_box if kind == "stems" else self.lyrics_box).setChecked(
                        kind == "stems" or self.stems_box.isChecked())
                self.statusBar().showMessage(f"{name} is ready.")
            else:
                self.statusBar().showMessage(f"{name} download failed (code {code}); see the log.")
        p.finished.connect(done)
        self._addon_proc = p
        p.start()
        self.statusBar().showMessage(f"Downloading {name.lower()}; the log shows where from and how far along.")

    def _advanced_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        intro = QLabel("Every setting, after the profile and the Easy sliders. Edit a "
                           "cell to set it exactly (shown in bold). What each one does is in "
                           "its tooltip. For a song that's been made, the \"made\" columns show "
                           "what each chart was really made with; a difficulty target changes "
                           "some settings to reach its number (highlighted).")
        intro.setWordWrap(True)                      # a long label must not set the window's width
        v.addWidget(intro)
        self.adv = QTableWidget(0, len(DIFFS))
        self.adv.setHorizontalHeaderLabels(list(DIFFS))
        self.adv.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.adv.itemChanged.connect(self._adv_edited)
        v.addWidget(self.adv)
        b = QPushButton("Clear exact settings")
        b.clicked.connect(lambda: (self.overrides.clear(), self.refresh_advanced(), self._panel_changed()))
        v.addWidget(b, alignment=Qt.AlignRight)
        self._docs = self._setting_docs()
        return w

    def _options_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.parallel = QSpinBox(minimum=1, maximum=max(1, os.cpu_count() or 1),
                                 value=max(1, min(4, (os.cpu_count() or 2) // 2)))
        self.parallel.setToolTip("Songs worked on at once. Each one uses a CPU core and about 1 GB of memory.")
        f.addRow("Songs at once", self.parallel)
        self.keep_format = QCheckBox("Copy the song as-is instead of converting to .ogg")
        f.addRow(self.keep_format)
        self.clicks = QCheckBox("Also write a click track (.clicks.wav) to check sync")
        f.addRow(self.clicks)
        # song artwork (artwork.py): the song's own cover art; online only when ticked
        import artwork
        self.art = QCheckBox("Add song artwork: banner, background and jacket")
        self.art.setChecked(True)
        self.art.setToolTip("Made from an image beside the song (the song's own name, or cover.jpg / "
                            "folder.jpg) or else the cover art inside the song file. Nothing is downloaded. "
                            "Art already in the song folder is kept, so you can replace it by hand.")
        f.addRow(self.art)
        self.art_online = QCheckBox("Look up artwork online when a song has none")
        self.art_online.setToolTip("Sends the song's title and artist to these sites and downloads the "
                                   "cover it finds. Each address is listed in the song's log.\n\n"
                                   + "\n".join(f"{what}: {where}" for what, where in artwork.ONLINE_SOURCES))
        f.addRow(self.art_online)
        self.art_sources = QLabel("Searches musicbrainz.org, itunes.apple.com and api.deezer.com; pictures "
                                  "come from coverartarchive.org (archive.org), Apple's mzstatic.com or "
                                  "Deezer's dzcdn.net.")
        self.art_sources.setWordWrap(True)
        self.art_sources.setStyleSheet("color: gray;")
        f.addRow(self.art_sources)
        self.art.toggled.connect(self.art_online.setEnabled)
        self.art.toggled.connect(lambda on: on and self.find_art_all())
        self.art_online.toggled.connect(lambda on: on and self.find_art_all())
        # hardware acceleration: only the neural-network parts can use a GPU (accel.py)
        self.device = QComboBox()
        self.device.addItem("Use the GPU when there is one", "auto")
        self.device.addItem("CPU only", "cpu")
        self.device.setToolTip("Vocal separation, AI verse detection and AI assist can run on an NVIDIA "
                               "GPU or an Apple Silicon GPU, which is much faster. Making the charts "
                               "themselves always runs on the CPU. If the GPU fails (out of memory, a "
                               "driver problem), that step runs on the CPU instead.")
        f.addRow("Hardware acceleration", self.device)
        self.gpu_label = QLabel()
        self.gpu_label.setWordWrap(True)
        self.gpu_btn = QPushButton("Download NVIDIA GPU support (about 3 GB)…")
        self.gpu_btn.clicked.connect(lambda: self.install_addon("gpu"))
        f.addRow(self.gpu_label)
        f.addRow(self.gpu_btn)
        self.device.currentIndexChanged.connect(lambda _: self._gpu_state())
        return w

    def _gpu_state(self, check_install: bool = False):
        """Say what GPU there is and what uses it; offer the NVIDIA download
        when that's what's missing."""
        import accel
        import addons
        nvidia = accel.nvidia_gpu()
        if check_install or not hasattr(self, "_gpu_ok"):
            self._gpu_ok = bool(nvidia) and addons.installed("gpu")
        stems_ok = addons.installed("stems")
        self.gpu_btn.setVisible(bool(nvidia) and not self._gpu_ok and sys.platform != "darwin")
        self.gpu_btn.setEnabled(stems_ok)
        self.gpu_btn.setToolTip("" if stems_ok else "Download melody analysis first: GPU support speeds it up.")
        if self.device.currentData() == "cpu":
            text = "Everything runs on the CPU."
        elif nvidia:
            uses = (["vocal separation", "AI verse detection"] if self._gpu_ok else [])
            text = (f"Found {nvidia}. " + (f"Used for {' and '.join(uses)}." if uses else
                    "Vocal separation and AI verse detection need GPU support to use it (a "
                    "one-time download, below)."))
        elif accel.apple_silicon():
            text = ("Found the Apple Silicon GPU: vocal separation and AI assist use it. AI verse "
                    "detection runs on the CPU (Whisper has no Apple GPU support).")
        else:
            text = "No GPU found that stepgen can use; everything runs on the CPU."
        self.gpu_label.setText(text)

    # ------------------------------------------------------------- settings
    def _setting_docs(self) -> dict[str, str]:
        """Tooltips from the comments in patterns.toml."""
        docs, cur = {}, None
        for line in stepgen.DEFAULT_PATTERNS.read_text().splitlines():
            m = re.match(r"#\s?(\w+)\s{2,}(.*)", line)
            if m and m.group(1) in {f.name for f in fields(stepgen.DiffSpec)}:
                cur = m.group(1)
                docs[cur] = m.group(2)
            elif cur and re.match(r"#\s{4,}\S", line):
                docs[cur] += " " + line.lstrip("# ").strip()
            else:
                cur = None
        return docs

    def reload_profiles(self, select: str | None = None):
        cur = select or self.profile.currentText() or "konami"
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItems(list(profile_paths()))
        i = self.profile.findText(cur)
        self.profile.setCurrentIndex(max(i, 0))
        self.profile.blockSignals(False)

    def easy_values(self) -> dict[str, float]:
        out = {k: s.value() / 100 for k, s in self.sliders.items() if s.value() != 50}
        if self.groove.value():
            out["groove"] = groove_easy(self.groove.value())
        return out

    def run_sets(self) -> list[str]:
        sets = [f"{d}.target_meter={self.target[d].value():g}" for d in DIFFS if self.target_on[d].isChecked()]
        if self.follow.value():
            sets += [f"{d}.melody_follow={self.follow.value() / 100:g}" for d in DIFFS]
        if self.ai.value():
            sets += [f"{d}.ai_assist={self.ai.value() / 100:g}" for d in DIFFS]
        return sets + [f"{k}={v:g}" for k, v in self.overrides.items()]

    def effective_specs(self) -> list[stepgen.DiffSpec]:
        path = profile_paths().get(self.profile.currentText(), stepgen.DEFAULT_PATTERNS)
        try:
            return stepgen.load_patterns(path, self.run_sets(), self.easy_values() or None)
        except SystemExit as e:
            self.statusBar().showMessage(f"Profile problem: {e}")
            return []

    def refresh_advanced(self, *_):
        if not hasattr(self, "adv"):
            return
        specs = [s for s in self.effective_specs() if s.name in DIFFS]
        skip = {"name", "meter_min", "meter_max"}
        names = [f.name for f in fields(stepgen.DiffSpec) if f.name not in skip]
        made = self._made_with()
        made_diffs = [d for d in DIFFS if d in made]
        self.adv.blockSignals(True)
        self.adv.setColumnCount(len(specs) + len(made_diffs))
        self.adv.setHorizontalHeaderLabels([s.name for s in specs] + [f"{d} (made)" for d in made_diffs])
        self.adv.setRowCount(len(names))
        self.adv.setVerticalHeaderLabels(names)
        bold = QFont()
        bold.setBold(True)
        retired = "Retired: the dial test found no measurable effect, so no slider moves it. " \
                  "Profiles that set it still load."
        for r, n in enumerate(names):
            old = n in stepgen.DEPRECATED
            head = self.adv.verticalHeaderItem(r)
            head.setText(f"{n} (retired)" if old else n)
            head.setToolTip(retired if old else self._docs.get(n, ""))
            for c, s in enumerate(specs):
                it = QTableWidgetItem(f"{getattr(s, n):g}")
                it.setData(Qt.UserRole, f"{s.name}.{n}")
                it.setToolTip(self._docs.get(n, ""))
                if f"{s.name}.{n}" in self.overrides:
                    it.setFont(bold)
                if old:
                    it.setFlags(it.flags() & ~(Qt.ItemIsEditable | Qt.ItemIsEnabled))
                    it.setToolTip(retired)
                self.adv.setItem(r, c, it)
            for c, d in enumerate(made_diffs, start=len(specs)):
                rec = made[d]
                v = rec.get("used", {}).get(n)
                it = QTableWidgetItem("" if v is None else f"{v:.3g}" if isinstance(v, float) else str(v))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setForeground(QColor("#222222"))
                if n in rec.get("changed", {}):
                    asked, used = rec["changed"][n]
                    it.setBackground(QColor("#fdebd0"))
                    it.setFont(bold)
                    it.setToolTip(f"Asked for {asked:.3g}, made with {used:.3g}: the {d} difficulty target "
                                  f"changed it to reach its number." + (f"\n{rec['breathing']}" if
                                                                       n in ("run_breaks", "recovery") and rec.get("breathing") else ""))
                else:
                    it.setBackground(QColor("#f2f2f2"))
                    it.setToolTip(f"{d} was made with this" + (f" (cut from the {rec['cut_from']} chart)"
                                                                if rec.get("cut_from") else ""))
                self.adv.setItem(r, c, it)
        self.adv.blockSignals(False)

    def _made_with(self) -> dict:
        """What the selected song's charts were really made with (its
        .stepgen.json), or {} for a song that isn't made yet."""
        jobs = self.selected_jobs() if hasattr(self, "table") else []
        sm = jobs[0].sm if jobs else None
        if not sm:
            return {}
        try:
            info = json.loads(side(sm, ".stepgen.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return info.get("made_with") or {}

    def _adv_edited(self, it: QTableWidgetItem):
        key = it.data(Qt.UserRole)
        if not key:
            return                                    # a "made" column: read-only
        try:
            self.overrides[key] = float(it.text())
        except ValueError:
            pass
        self.refresh_advanced()
        self._panel_changed()

    def save_profile(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save profile", "Name for this style:")
        if not ok or not safe_name(name):
            return
        specs = self.effective_specs()
        lines = [f"# {name}: saved from the stepgen app", ""]
        skip = {"name", "meter_min", "meter_max"}
        for s in specs:
            lines.append(f"[{s.name}]")
            lines += [f"{f.name} = {getattr(s, f.name)!r}" for f in fields(s) if f.name not in skip]
            lines.append("")
        path = user_profiles_dir() / f"{safe_name(name)}.toml"
        path.write_text("\n".join(lines))
        self.overrides.clear()
        for s in self.sliders.values():
            s.setValue(50)
        self.groove.setValue(0)             # saved into the profile like the Feel sliders
        self.reload_profiles(path.stem)
        self.refresh_advanced()
        self.statusBar().showMessage(f"Saved profile {path.stem} ({path})")

    def pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out_edit.text())
        if d:
            self.out_edit.setText(d)
            self.refresh_made()

    def export_songs(self):
        text = self.out_edit.text().strip()
        if not text or not Path(text).is_dir():
            QMessageBox.information(self, "stepgen", "Pick the output folder your songs were made in first.")
            return
        ExportDialog(Path(text), self.settings, self).exec()

    # --------------------------------------------------- per-song settings
    def capture(self) -> dict:
        """The panel's song settings as plain data, one copy per song."""
        return {"profile": self.profile.currentText(), "seed": self.seed.value(), "bpm": self.bpm.value(),
                "shorten": SHORTEN[self.shorten.currentIndex()][1],
                "keep_verses": self.keep_verses.isChecked(),
                "targets": {d: self.target[d].value() if self.target_on[d].isChecked() else None
                            for d in DIFFS},
                "sliders": {k: s.value() for k, s in self.sliders.items()},
                "groove": self.groove.value(),
                "follow": self.follow.value(),
                "ai": self.ai.value(),
                "sections": {k: self.sec_sliders[k][0].value() for k in sorted(self.sec_manual)},
                "stems": self.stems_box.isChecked(),
                "lyrics": self.lyrics_box.isChecked(),
                "backoff": self.backoff.isChecked(),
                "overrides": dict(self.overrides)}

    def restore(self, d: dict) -> None:
        """Fill the panel from a song's settings without writing back."""
        if not d:
            return
        self._loading = True
        try:
            self.reload_profiles(d.get("profile"))
            self.seed.setValue(int(d.get("seed", 1)))
            self.bpm.setValue(float(d.get("bpm") or 0))
            self.shorten.setCurrentIndex(next((i for i, (_, v) in enumerate(SHORTEN) if v == d.get("shorten", 0)), 0))
            for k, v in d.get("targets", {}).items():
                if k in self.target:
                    self.target_on[k].setChecked(v is not None)
                    if v is not None:
                        self.target[k].setValue(float(v))
            for k, v in d.get("sliders", {}).items():
                if k in self.sliders:
                    self.sliders[k].setValue(int(v))
            self.groove.setValue(old_groove(d))
            self.follow.setValue(int(d.get("follow", 0)))
            self.ai.setValue(int(d.get("ai", 0)) if usable(self.ai) else 0)
            self.sec_manual = set(d.get("sections", {}))
            for k, (sl, *_) in self.sec_sliders.items():
                if k in self.sec_manual:
                    sl.blockSignals(True)
                    sl.setValue(int(d["sections"][k]))
                    sl.blockSignals(False)
            self._follow_auto()
            self.stems_box.setChecked(bool(d.get("stems")) and self._stems_ok)
            self.lyrics_box.setChecked(bool(d.get("lyrics")) and self._lyrics_ok and self.stems_box.isChecked())
            self.keep_verses.setChecked(bool(d.get("keep_verses")) and self.keep_verses.isEnabled())
            self.backoff.setChecked(bool(d.get("backoff")))
            self.overrides = dict(d.get("overrides", {}))
            self.refresh_advanced()
        finally:
            self._loading = False

    def summary(self, d: dict) -> str:
        """One line for the queue's Settings column."""
        t = d.get("targets", {})
        parts = [d.get("profile", "?"),
                 "/".join(f"{v:g}" if v is not None else "-" for v in (t.get(x) for x in DIFFS))]
        moved = [f"{k} {v}%" for k, v in d.get("sliders", {}).items() if v != 50 and k != "groove"]
        if old_groove(d):
            moved.insert(0, f"groove {old_groove(d)}%")
        if moved:
            parts.append(", ".join(moved))
        if d.get("stems") and (d.get("follow") or d.get("sections")):
            parts.append(f"follow {d.get('follow', 0)}%" + ("*" if d.get("sections") else ""))
        if d.get("ai"):
            parts.append(f"AI {d['ai']}%")
        if d.get("stems"):
            parts.append("melody")
        if d.get("lyrics"):
            parts.append("AI verses")
        if d.get("backoff"):
            parts.append("backoff")
        if d.get("overrides"):
            parts.append(f"{len(d['overrides'])} exact")
        if d.get("bpm"):
            parts.append(f"{d['bpm']:g} BPM")
        if d.get("shorten"):
            parts.append(f"short {d['shorten'] // 60}:{d['shorten'] % 60:02d}"
                         + (", verses kept" if d.get("keep_verses") else ""))
        if d.get("seed", 1) != 1:
            parts.append(f"seed {d['seed']}")
        return " · ".join(parts)

    def args_for(self, d: dict) -> list[str]:
        """stepgen command-line arguments for one song's settings."""
        prof = profile_paths().get(d.get("profile"), stepgen.DEFAULT_PATTERNS)
        args = ["--profile", str(prof), "--seed", str(d.get("seed", 1))]
        if d.get("bpm"):
            args += ["--bpm", f"{d['bpm']:g}"]
        if d.get("shorten"):
            args += ["--shorten", str(d["shorten"])]
            if d.get("keep_verses") and d.get("lyrics") and d.get("stems"):
                args.append("--keep-verses")
        sets = [f"{k}.target_meter={v:g}" for k, v in d.get("targets", {}).items() if v is not None]
        if d.get("follow") and d.get("stems"):         # Arrows follow is part of melody analysis
            sets += [f"{x}.melody_follow={d['follow'] / 100:g}" for x in DIFFS]
        if d.get("ai"):
            sets += [f"{x}.ai_assist={d['ai'] / 100:g}" for x in DIFFS]
        sets += [f"{k}={v:g}" for k, v in d.get("overrides", {}).items()]
        for x in sets:
            args += ["--set", x]
        for k, v in d.get("sliders", {}).items():
            if v != 50 and k != "groove":
                args += ["--easy", f"{k}={v / 100:g}"]
        if old_groove(d):
            args += ["--easy", f"groove={groove_easy(old_groove(d)):g}"]
        if d.get("stems"):
            args.append("--stems")
        if d.get("lyrics") and d.get("stems"):
            args.append("--lyrics")
        if d.get("backoff"):
            args.append("--backoff")
        for k, v in (d.get("sections", {}) if d.get("stems") else {}).items():
            args += ["--follow", f"{k}={v / 100:g}"]
        if self.keep_format.isChecked():
            args.append("--keep-format")
        if self.clicks.isChecked():
            args.append("--clicks")
        if not self.art.isChecked():
            args.append("--no-art")
        elif self.art_online.isChecked():
            args.append("--art-online")
        return args

    def _watch_panel(self):
        """Every song setting control reports changes to _panel_changed."""
        self.profile.currentTextChanged.connect(self._panel_changed)
        self.seed.valueChanged.connect(self._panel_changed)
        self.bpm.valueChanged.connect(self._panel_changed)
        self.shorten.currentIndexChanged.connect(self._panel_changed)
        self.keep_verses.toggled.connect(self._panel_changed)
        for d in DIFFS:
            self.target_on[d].toggled.connect(self._panel_changed)
            self.target[d].valueChanged.connect(self._panel_changed)
        for s in list(self.sliders.values()) + [self.groove, self.follow, self.ai] + [v[0] for v in self.sec_sliders.values()]:
            s.valueChanged.connect(self._panel_changed)
        self.stems_box.toggled.connect(self._panel_changed)
        self.lyrics_box.toggled.connect(self._panel_changed)
        self.backoff.toggled.connect(self._panel_changed)

    def _editable(self, job: Job) -> bool:
        return job not in self.running and job.status not in MADE

    def _panel_changed(self, *_):
        if self._loading:
            return
        d = self.capture()
        jobs = self.selected_jobs()
        if not jobs:
            self.defaults = d
            return
        for j in jobs:
            if self._editable(j):
                j.settings = json.loads(json.dumps(d))
                self._show_settings(j)

    def _show_settings(self, job: Job):
        it = self.table.item(self._row(job), C_SETTINGS)
        if it is not None:
            self.table.blockSignals(True)
            it.setText(self.summary(job.settings))
            it.setToolTip(" ".join(self.args_for(job.settings)))
            self.table.blockSignals(False)

    def _scope(self):
        """Point the panel at the selected songs (or at new songs) and say so."""
        jobs = self.selected_jobs()
        if not jobs:
            self.restore(self.defaults)
            text, colour, locked = ("<b>Settings for songs you add next.</b> Select songs in the "
                                    "queue to see or change their own."), "#eef3fb", False
        else:
            first = jobs[0]
            self.restore(first.settings)
            same = all(j.settings == first.settings for j in jobs)
            locked = not self._editable(first)
            if locked:
                why = "being made now" if first in self.running else "already made"
                text = (f"<b>Settings used for {first.title}</b> ({why}, so they're locked). "
                        "To change them, regenerate the song.")
                if not first.settings:
                    text = (f"<b>{first.title}</b> was made before the app kept each song's settings, "
                            "so they aren't known (the stats below show what stepgen recorded). "
                            "To change them, regenerate the song.")
                colour = "#f2f2f2"
            elif len(jobs) == 1:
                text, colour = f"<b>Settings for {first.title}</b>: changes apply to this song.", "#e9f7ef"
            else:
                text = (f"<b>Settings for {len(jobs)} selected songs</b>: a change applies to all of them"
                        + ("." if same else " (they differ now; showing the first one's)."))
                colour = "#fef5e7"
        self.scope_lbl.setText(text)
        self.scope_lbl.setStyleSheet(f"padding: 6px; border-radius: 4px; background: {colour}; color: #222;")
        for wdg in (self.style_box, self.easy_page, self.adv_page):
            wdg.setEnabled(not locked)
        self.regen_btn.setVisible(bool(jobs) and locked and not any(j in self.running for j in jobs))

    def unlock_selected(self):
        for j in self.selected_jobs():
            if j not in self.running and j.status in MADE:
                if j.status == EARLIER and not j.path.is_file():
                    self.statusBar().showMessage(f"Can't regenerate {j.title}: its song file "
                                                 f"{j.path} isn't there any more. Add it again instead.")
                    continue
                j.force = True
                j.status = READY        # a queue song now: stays when the earlier list is hidden
                j.meters = {}
                self._set_status(j, READY, "#555555")
        self._scope()

    def _load_settings(self):
        st = self.settings
        self.out_edit.setText(st.value("out_dir", ""))
        self.reload_profiles(st.value("profile", "konami"))
        self.seed.setValue(int(st.value("seed", 1)))
        self.parallel.setValue(int(st.value("parallel", self.parallel.value())))
        self.skip_done.setChecked(st.value("skip_done", "true") == "true")
        self.show_made.setChecked(st.value("show_made", "false") == "true")
        for d in DIFFS:
            self.target_on[d].setChecked(st.value(f"target_on/{d}", "true") == "true")
            self.target[d].setValue(float(st.value(f"target/{d}", self.target[d].value())))
        for k, s in self.sliders.items():
            s.setValue(int(st.value(f"slider/{k}", 50)))
        self.groove.setValue(int(st.value("groove", max(0, 2 * (int(st.value("slider/groove", 50)) - 50)))))
        self.follow.setValue(int(st.value("follow", 0)))
        if usable(self.ai):
            self.ai.setValue(int(st.value("ai", 0)))
        manual = json.loads(st.value("follow_sections_v2", "{}"))
        for kind, v in manual.items():
            if kind in self.sec_sliders:
                self.sec_sliders[kind][0].setValue(int(v))      # marks it as set by hand
        self._follow_auto()
        self.stems_box.setChecked(st.value("stems", "false") == "true" and self._stems_ready())
        self.lyrics_box.setChecked(st.value("lyrics", "false") == "true" and self._lyrics_ok
                                   and self.stems_box.isChecked())
        self.backoff.setChecked(st.value("backoff", "false") == "true")
        self.overrides = json.loads(st.value("overrides", "{}"))
        self.device.setCurrentIndex(max(0, self.device.findData(st.value("device", "auto"))))
        self._gpu_state(check_install=True)
        self.art.setChecked(st.value("art", "true") == "true")
        self.art_online.setChecked(st.value("art_online", "false") == "true")

    def closeEvent(self, ev):
        if not self.editor.confirm_discard():
            ev.ignore()
            return
        self.editor.stop()
        if self.running and QMessageBox.question(
                self, "stepgen", "Songs are still being charted. Stop them and quit?") != QMessageBox.Yes:
            ev.ignore()
            return
        self.cancel()
        self.table.clearSelection()         # the panel back on the defaults before saving them
        self.restore(self.defaults)
        st = self.settings
        st.setValue("out_dir", self.out_edit.text())
        st.setValue("profile", self.profile.currentText())
        st.setValue("seed", self.seed.value())
        st.setValue("parallel", self.parallel.value())
        st.setValue("skip_done", "true" if self.skip_done.isChecked() else "false")
        st.setValue("show_made", "true" if self.show_made.isChecked() else "false")
        for d in DIFFS:
            st.setValue(f"target_on/{d}", "true" if self.target_on[d].isChecked() else "false")
            st.setValue(f"target/{d}", self.target[d].value())
        for k, s in self.sliders.items():
            st.setValue(f"slider/{k}", s.value())
        st.setValue("groove", self.groove.value())
        st.setValue("follow", self.follow.value())
        st.setValue("ai", self.ai.value())
        st.setValue("follow_sections_v2", json.dumps({k: self.sec_sliders[k][0].value() for k in self.sec_manual}))
        st.setValue("stems", "true" if self.stems_box.isChecked() else "false")
        st.setValue("lyrics", "true" if self.lyrics_box.isChecked() else "false")
        st.setValue("backoff", "true" if self.backoff.isChecked() else "false")
        st.setValue("overrides", json.dumps(self.overrides))
        st.setValue("device", self.device.currentData())
        st.setValue("art", "true" if self.art.isChecked() else "false")
        st.setValue("art_online", "true" if self.art_online.isChecked() else "false")
        shutil.rmtree(self._art_dir, ignore_errors=True)
        super().closeEvent(ev)

    # ---------------------------------------------------------------- queue
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        self.add_paths([Path(u.toLocalFile()) for u in ev.mimeData().urls()])

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add songs", self.settings.value("last_dir", ""),
            "Audio (" + " ".join(f"*{e}" for e in sorted(AUDIO_EXT)) + ")")
        if files:
            self.settings.setValue("last_dir", str(Path(files[0]).parent))
            self.add_paths([Path(f) for f in files])

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add a folder of songs (subfolders too)",
                                             self.settings.value("last_dir", ""))
        if d:
            self.settings.setValue("last_dir", d)
            self.add_paths([Path(d)])

    def add_paths(self, paths: list[Path]):
        have = {j.path.resolve() for j in self.jobs}
        added = 0
        for p in paths:
            files = sorted(f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXT) if p.is_dir() else [p]
            for f in files:
                if f.suffix.lower() not in AUDIO_EXT or f.resolve() in have:
                    continue
                if f.name.endswith(".clicks.wav"):
                    continue
                have.add(f.resolve())
                self.jobs.append(Job(f))
                self.jobs[-1].settings = json.loads(json.dumps(self.defaults))
                self._add_row(self.jobs[-1])
                self.find_art(self.jobs[-1])
                added += 1
        if added and self.show_made.isChecked():
            self.refresh_made()            # a song added again replaces its "made earlier" row
        self._progress_max()
        self.statusBar().showMessage(f"Added {added} song{'s' * (added != 1)}. {len(self.jobs)} in the queue.")

    def _add_row(self, job: Job):
        r = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(r)
        vals = [job.path.name, job.title, job.artist, f"{job.bpm:g}" if job.bpm else "auto", job.status, "",
                self.summary(job.settings)]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            if c in (C_SONG, C_STATUS, C_METERS, C_SETTINGS):
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if c == C_SONG:
                it.setToolTip(str(job.path))
            self.table.setItem(r, c, it)
        self.table.blockSignals(False)

    def refresh_made(self, *_):
        """Show (or hide) the songs already made in the output folder."""
        for job in reversed(list(self.jobs)):
            if job.status == EARLIER:
                r = self._row(job)
                self.jobs.pop(r)
                self.table.removeRow(r)
        text = self.out_edit.text().strip()
        if not self.show_made.isChecked() or not text or not Path(text).is_dir():
            self._progress_max()
            return
        queued = {out_title(j).lower() for j in self.jobs}
        found = 0
        for info in sorted(Path(text).glob("*/*.stepgen.json"), key=lambda f: f.parent.name.lower()):
            folder, title = info.parent, info.name[:-len(".stepgen.json")]
            sm = find_sm(folder, title)
            if title.lower() in queued or not sm.is_file():
                continue                   # already a row in the queue, or not finished
            try:
                made = json.loads(info.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                made = {}
            src = Path(made.get("source") or sm)
            # the title it was made with (the song file itself may be gone)
            job = Job(src, made.get("title") or title, made.get("artist", ""))
            job.status, job.sm, job.meters = EARLIER, sm, read_meters(sm)
            app_json = folder / f"{title}.app.json"
            if app_json.is_file():
                try:
                    job.settings = json.loads(app_json.read_text())
                except ValueError:
                    pass
            self.jobs.append(job)
            self._add_row(job)
            self._set_status(job, EARLIER, "#5d6d7e")
            if not job.settings:
                self.table.item(self._row(job), C_SETTINGS).setText("(not recorded)")
            found += 1
        self._progress_max()
        self.statusBar().showMessage(f"{found} song{'s' * (found != 1)} already made in {text}.")

    def _row(self, job: Job) -> int:
        return self.jobs.index(job)

    def _set_status(self, job: Job, status: str, color: str | None = None):
        job.status = status
        r = self._row(job)
        self.table.blockSignals(True)
        it = self.table.item(r, C_STATUS)
        it.setText(status)
        if color:
            it.setForeground(QColor(color))
        self.table.item(r, C_METERS).setText(" / ".join(job.meters.get(d, "-") for d in DIFFS)
                                             if job.meters else "")
        self.table.blockSignals(False)

    def _cell_edited(self, it: QTableWidgetItem):
        job = self.jobs[it.row()]
        if it.column() == C_TITLE:
            job.title = it.text().strip() or job.path.stem
        elif it.column() == C_ARTIST:
            job.artist = it.text().strip()
        if it.column() in (C_TITLE, C_ARTIST) and job.art_state in ("none", "kept") and job.status != EARLIER:
            self.find_art(job)          # a better name to search by, or a different song folder
        elif it.column() == C_BPM:
            try:
                job.bpm = max(0.0, float(it.text()))
            except ValueError:
                job.bpm = 0.0
            if not job.bpm:
                self.table.blockSignals(True)
                it.setText("auto")
                self.table.blockSignals(False)

    def selected_jobs(self) -> list[Job]:
        return [self.jobs[r] for r in sorted({i.row() for i in self.table.selectedIndexes()})]

    def remove_selected(self):
        jobs = [j for j in self.selected_jobs() if j not in self.running]
        # songs already made have a folder in the output folder, which "Show songs
        # already made" would list again: offer to put it in the Recycle Bin too
        made = [j for j in jobs if j.sm and j.sm.is_file()]
        trash = False
        if made:
            box = QMessageBox(self)
            box.setWindowTitle("Remove")
            names = ", ".join(j.title for j in made[:3]) + (f" and {len(made) - 3} more" if len(made) > 3 else "")
            box.setText(f"{names} {'has' if len(made) == 1 else 'have'} already been made.\n\n"
                        "Also move the song's folder in the output folder to the Recycle Bin? "
                        "Otherwise it's only taken off this list, and shows up again with "
                        "\"Show songs already made\". Copies in StepMania's Songs folder aren't touched.")
            both = box.addButton("Remove and move to Recycle Bin", QMessageBox.DestructiveRole)
            box.addButton("Only take off the list", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is box.button(QMessageBox.Cancel):
                return
            trash = box.clickedButton() is both
        failed = []
        for job in reversed(jobs):
            if trash and job in made and not self._trash_song(job):
                failed.append(job.title)
                continue
            r = self._row(job)
            self.jobs.pop(r)
            self.table.removeRow(r)
        self._progress_max()
        if failed:
            QMessageBox.warning(self, "Remove", "Couldn't move these to the Recycle Bin (open in the "
                                "Edit tab, or a file in use?): " + ", ".join(failed))

    def _trash_song(self, job: Job) -> bool:
        """Move a made song's folder (and its "(no AI)" twin) to the Recycle Bin.
        Not while it's open in the editor."""
        from PySide6.QtCore import QFile
        outer = outer_of(job.sm)
        open_sm = getattr(self.editor, "sm", None)
        if open_sm is not None and outer.resolve() in open_sm.path.resolve().parents:
            return False
        ok = True
        for d in (outer, outer.parent / f"{outer.name} (no AI)"):
            if d.is_dir():
                res = QFile.moveToTrash(str(d))
                ok = (res[0] if isinstance(res, tuple) else bool(res)) and ok
        return ok

    def clear_finished(self):
        for job in reversed(list(self.jobs)):
            if job.status in (DONE, SKIPPED):
                r = self._row(job)
                self.jobs.pop(r)
                self.table.removeRow(r)
        self._progress_max()
        self.progress.setValue(0)

    # ---------------------------------------------------------------- artwork
    def _details_tab(self) -> QWidget:
        self._art_dir = Path(tempfile.mkdtemp(prefix="beatsmith-art-"))
        self.art_finder = ArtFinder(self._art_dir)
        self.art_finder.done.connect(self._art_found)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        w = QWidget()
        v = QVBoxLayout(w)
        self.art_status = QLabel()
        self.art_status.setWordWrap(True)
        v.addWidget(self.art_status)
        pics = QHBoxLayout()
        self.art_views = {}
        for tag, (w_, h_), name in (("JACKET", (110, 110), "Jacket"), ("BANNER", (280, 110), "Banner"),
                                    ("BACKGROUND", (146, 110), "Background")):
            col = QVBoxLayout()
            lab = QLabel()
            lab.setFixedSize(w_, h_)
            lab.setAlignment(Qt.AlignCenter)
            lab.setStyleSheet("border: 1px solid #999; background: #222; color: #aaa;")
            col.addWidget(lab)
            col.addWidget(QLabel(name), alignment=Qt.AlignHCenter)
            col.addStretch()
            pics.addLayout(col)
            self.art_views[tag] = lab
        pics.addStretch()
        v.addLayout(pics)
        btns = QHBoxLayout()
        self.art_pick = QPushButton("Choose picture…")
        self.art_pick.setToolTip("Use a picture from your computer for this song's banner, background and jacket.")
        self.art_pick.clicked.connect(self._art_choose)
        self.art_lookup = QPushButton("Look up online")
        self.art_lookup.setToolTip("Sends this song's title and artist to these sites and downloads the cover "
                                   "it finds; each address is listed below.\n\n"
                                   + "\n".join(f"{what}: {where}" for what, where in artwork.ONLINE_SOURCES))
        self.art_lookup.clicked.connect(lambda: [self.find_art(j, online=True) for j in self.selected_jobs()
                                                 if j.status != EARLIER])
        self.art_clear = QPushButton("No artwork")
        self.art_clear.setToolTip("Leave this song's banner, background and jacket empty.")
        self.art_clear.clicked.connect(self._art_none)
        for b in (self.art_pick, self.art_lookup, self.art_clear):
            btns.addWidget(b)
        btns.addStretch()
        v.addLayout(btns)
        self.art_log_view = QLabel()
        self.art_log_view.setWordWrap(True)
        self.art_log_view.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.art_log_view.setStyleSheet("color: gray;")
        v.addWidget(self.art_log_view)
        self.info_label = QLabel()
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setWordWrap(True)
        v.addWidget(self.info_label)
        v.addStretch()
        sc.setWidget(w)
        return sc

    def _song_folder(self, job: Job) -> Path | None:
        text = self.out_edit.text().strip()
        return song_dirs(Path(text), out_title(job))[1] if text else None

    def find_art(self, job: Job, online: bool | None = None, image: Path | None = None):
        """Look for a song's artwork in the background (ArtFinder)."""
        if not self.art.isChecked() and image is None and not online:
            job.art_state = ""
            return
        job.art_state = "looking"
        online = self.art_online.isChecked() if online is None else online
        # a button press asks for a fresh picture, so art in the song folder doesn't count then
        song = None if (online or image) else self._song_folder(job)
        self.art_finder.find(job, song, online, image)
        if self.selected_jobs()[:1] == [job]:
            self.show_details(job)

    def find_art_all(self):
        for job in self.jobs:
            if job.status != EARLIER and job.art_state in ("", "none"):
                self.find_art(job)

    def _art_found(self, job: Job, pic, where: dict, log: str):
        if job not in self.jobs:
            return
        job.art_log = (job.art_log + "\n" + log).strip() if log else job.art_log
        if where.get("from") == artwork.KEPT:
            job.art_state, job.art_image = "kept", None
        elif pic is None:
            if job.art_state == "looking" and not job.art_image:
                job.art_state = "none"
            elif job.art_image:                    # nothing new found: keep what it had
                job.art_state = "found"
        else:
            job.art_state, job.art_image, job.art_where = "found", pic, where
        if self.selected_jobs()[:1] == [job]:
            self.show_details(job)

    def _art_from(self, job: Job) -> str:
        return artwork.describe(job.art_where)

    def _art_choose(self):
        jobs = [j for j in self.selected_jobs() if j.status != EARLIER]
        if not jobs:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Choose a picture", str(jobs[0].path.parent),
                                           "Pictures (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if f:
            for j in jobs:
                self.find_art(j, online=False, image=Path(f))

    def _art_none(self):
        for j in self.selected_jobs():
            if j.status != EARLIER:
                j.art_state, j.art_image, j.art_where = "cleared", None, {}
        self.show_details(self.selected_jobs()[0] if self.selected_jobs() else None)

    def show_details(self, job: Job | None):
        """The Details tab: what the song file says, and its artwork."""
        for b in (self.art_pick, self.art_lookup, self.art_clear):
            b.setEnabled(bool(job) and job.status != EARLIER)
        if job is None:
            self.info_label.setText("")
            self.art_status.setText("")
            self.art_log_view.setText("")
            for lab in self.art_views.values():
                lab.clear()
            return
        rows = [("Title", job.title), ("Artist", job.artist or "(none)")] + song_info(job.path)
        self.info_label.setText("<table>" + "".join(
            f"<tr><td><b>{html.escape(k)}</b>&nbsp;&nbsp;</td><td>{html.escape(v)}</td></tr>" for k, v in rows)
            + "</table>")
        # what to show: the song folder's art once it's made, else the picture found for it
        made = job.status in (DONE, EARLIER) and job.sm is not None
        files = {}
        if made or job.art_state == "kept":
            folder, title = (job.sm.parent, job.sm.stem) if made else (self._song_folder(job), out_title(job))
            names = artwork.file_names(title)
            if folder is not None and all((folder / n).is_file() for n in names.values()):
                files = {tag: folder / n for tag, n in names.items()}
        elif job.art_state == "found" and job.art_image:
            files = {tag: job.art_image.parent / f"{tag}.png" for tag in self.art_views}
        if made:
            status = "In the song folder." if files else "This song was made without artwork."
        else:
            status = {
                "": "Artwork is off (Options > Add song artwork)." if not self.art.isChecked() else "",
                "looking": "Looking for artwork…",
                "found": f"From {self._art_from(job)}. It's used when the charts are made.",
                "kept": "Already in the song folder from an earlier run; it's kept.",
                "none": "No artwork found: no picture beside the song or in its tags"
                        + ("" if self.art_online.isChecked() else ", and online lookup is off")
                        + ". Choose a picture or look it up online.",
                "cleared": "No artwork for this song.",
            }[job.art_state]
        self.art_status.setText(status)
        for tag, lab in self.art_views.items():
            f = files.get(tag)
            pm = QPixmap(str(f)) if f and f.is_file() else QPixmap()
            if pm.isNull():
                lab.clear()
                lab.setText("—")
            else:
                lab.setPixmap(pm.scaled(lab.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.art_log_view.setText(html.escape(job.art_log).replace("\n", "<br>"))

    def show_selected(self):
        jobs = self.selected_jobs()
        job = jobs[0] if jobs else None
        self._scope()
        self.refresh_advanced()                      # its "made" columns
        self.log_view.setPlainText(job.log if job else "")
        self.show_details(job)
        self.open_btn.setEnabled(bool(job and job.sm))
        self.edit_btn.setEnabled(bool(job and job.sm and job.sm.is_file()))
        stats = side(job.sm, ".stats.md") if job and job.sm else None
        if stats and stats.is_file():
            self.stats_view.setMarkdown(used_settings(job.sm) + stats.read_text(encoding="utf-8", errors="replace"))
        else:
            self.stats_view.setPlainText("Stats appear here once a song is done." if job else "")

    def edit_selected(self):
        jobs = self.selected_jobs()
        if jobs and jobs[0].sm and self.editor.confirm_discard():
            self.editor.open(jobs[0].sm)
            self.tabs.setCurrentWidget(self.editor)

    def open_selected(self):
        jobs = self.selected_jobs()
        if jobs and jobs[0].sm:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(outer_of(jobs[0].sm))))

    # ------------------------------------------------------------------ run
    def out_dir(self) -> Path | None:
        text = self.out_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "stepgen", "Pick an output folder first.")
            return None
        return Path(text)

    def start(self):
        out = self.out_dir()
        if out is None:
            return
        todo = [j for j in self.jobs if j.status not in MADE and j not in self.running]
        if not todo:
            self.statusBar().showMessage("Nothing to do: add songs, or they're all done.")
            return
        out.mkdir(parents=True, exist_ok=True)
        self.out = out
        for j in todo:
            j.status = "Queued"
            j.meters = {}
            self._set_status(j, "Queued", "#888888")
        self.stopping = False
        self.go_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._progress_max()
        self._update_progress()
        self._pump()

    def _pump(self):
        """Start queued songs until the parallel limit is reached."""
        while not self.stopping and len(self.running) < self.parallel.value():
            job = next((j for j in self.jobs if j.status == "Queued"), None)
            if job is None:
                break
            title = out_title(job)
            folder = self.out / title
            if folder.exists() and foreign_charts(folder):
                job.log = f"{folder} has charts stepgen didn't make, so it was left alone."
                self._set_status(job, FAILED, "#c0392b")
                continue
            if self.skip_done.isChecked() and not job.force and (folder / f"{title}.stepgen.json").is_file():
                job.sm = find_sm(folder, title)
                job.meters = read_meters(job.sm)
                app_json = folder / f"{title}.app.json"
                if app_json.is_file():               # the settings it was made with
                    try:
                        job.settings = json.loads(app_json.read_text())
                        self._show_settings(job)
                    except ValueError:
                        pass
                self._set_status(job, SKIPPED, "#888888")
                self._update_progress()
                continue
            self._launch(job, title)
        if not self.running:
            self.go_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            done = sum(j.status == DONE for j in self.jobs)
            failed = sum(j.status == FAILED for j in self.jobs)
            self.statusBar().showMessage(f"Finished: {done} done, {failed} failed. Charts are in {self.out}")

    def _launch(self, job: Job, title: str):
        args = [str(job.path), "--out", str(self.out), "--title", show_title(job)] + self.args_for(job.settings)
        if job.artist:
            args += ["--artist", job.artist]
        if job.bpm > 0:
            args += ["--bpm", f"{job.bpm:g}"]
        if self.art.isChecked():
            if job.art_state == "found" and job.art_image and job.art_image.is_file():
                args += ["--art-image", str(job.art_image), "--art-from", self._art_from(job)]
            elif job.art_state == "cleared":
                args.append("--no-art")
        if getattr(sys, "frozen", False):
            prog, pre = sys.executable, ["--run-stepgen"]
        else:
            prog, pre = sys.executable, [str(Path(__file__).resolve()), "--run-stepgen"]
        p = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        ff = HERE / "ffmpeg"                         # bundled ffmpeg in the installed app
        if ff.is_dir():
            env.insert("PATH", str(ff) + os.pathsep + env.value("PATH"))
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("STEPGEN_DEVICE", self.device.currentData() or "auto")     # accel.py
        p.setProcessEnvironment(env)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(lambda j=job: self._output(j))
        p.finished.connect(lambda code, _s, j=job: self._finished(j, code))
        job.proc, job.log, job.partial = p, "", ""
        self.running.append(job)
        self._set_status(job, "Running", "#2471a3")
        p.start(prog, pre + args)

    def _output(self, job: Job):
        text = job.partial + bytes(job.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        lines = text.split("\n")
        job.partial = lines.pop()                    # not a whole line yet
        kept = []
        for line in lines:
            if DECODER_NOISE.match(line.strip()):
                internal_log(job.path.name, line.strip())
            else:
                kept.append(line)
        job.log += "".join(l + "\n" for l in kept)
        for line in kept:
            m = re.match(r"progress: (analyzing|charting|separating|finding) (.*)", line)
            if m:
                self._set_status(job, {"analyzing": "Analyzing…", "separating": "Separating vocals…",
                                       "finding": "Finding artwork…"}.get(
                    m.group(1), f"Charting {m.group(2)}…"), "#2471a3")
            m = re.match(r"\s+(\w+)\s+meter\s+(\d+)", line)
            if m:
                job.meters[m.group(1)] = m.group(2)
            m = re.match(r"\s+-> (.*\.sm)\s*$", line)
            if m:
                job.sm = Path(m.group(1))
        if self.selected_jobs()[:1] == [job]:
            self.log_view.setPlainText(job.log)

    def _finished(self, job: Job, code: int):
        if job in self.running:
            self.running.remove(job)
        if job.partial:
            job.log += job.partial
            job.partial = ""
        if job.status == CANCELLED:
            pass
        elif code == 0 and job.sm:
            job.force = False
            self._set_status(job, DONE, "#1e8449")
            try:                                     # so the app can show them again later
                side(job.sm, ".app.json").write_text(json.dumps(job.settings, indent=2))
            except OSError:
                pass
        else:
            last = [l for l in job.log.splitlines() if l.strip()][-1:] or ["no output"]
            job.log += f"\n[stepgen stopped with code {code}]"
            self._set_status(job, f"{FAILED}: {last[0][:60]}", "#c0392b")
            job.status = FAILED
        self._update_progress()
        if self.selected_jobs()[:1] == [job]:
            self.show_selected()
        self._pump()

    def _progress_max(self):
        n = sum(j.status != EARLIER for j in self.jobs)     # songs already made don't count
        self.progress.setMaximum(max(n, 1))                 # 0 would make the bar spin
        self.progress.setFormat("%v of %m songs" if n else "")

    def _update_progress(self):
        self.progress.setValue(sum(j.status in (DONE, FAILED, SKIPPED) for j in self.jobs))

    def cancel(self):
        self.stopping = True
        for j in self.jobs:
            if j.status == "Queued":
                self._set_status(j, CANCELLED, "#888888")
        for j in list(self.running):
            j.status = CANCELLED
            self._set_status(j, CANCELLED, "#888888")
            if j.proc:
                j.proc.kill()


def groove_easy(v: int) -> float:
    """The Groove slider (0 off .. 100) as stepgen's --easy groove value,
    where 0.5 changes nothing and 1 is the most."""
    return 0.5 + v / 200


def old_groove(d: dict) -> int:
    """A song's Groove setting, 0..100. Songs saved before 0 meant off kept
    it with the Feel sliders, where 50 was off."""
    if "groove" in d:
        return int(d["groove"])
    return max(0, 2 * (int(d.get("sliders", {}).get("groove", 50)) - 50))


class ExportDialog(QDialog):
    """Pick made songs and copy them into StepMania's Songs/<group> folder,
    or into a zip: just the chart, the song and its pictures (export.py)."""

    def __init__(self, folder: Path, settings: QSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export songs")
        self.resize(760, 560)
        self.settings = settings
        self.songs = export.made_songs(folder)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"Songs made in {folder}:"))

        self.all = QCheckBox("All")
        self.all.setTristate(True)
        self.all.clicked.connect(self._all_clicked)
        v.addWidget(self.all)
        self.table = QTableWidget(len(self.songs), 5)
        self.table.setHorizontalHeaderLabels(["Title", "Artist", "Meters E/M/H", "Made in", "Exported as"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, (song, name) in enumerate(zip(self.songs, export.names(self.songs))):
            meters = read_meters(song.sm)
            it = QTableWidgetItem(song.title)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            it.setToolTip(str(song.sm.parent))
            self.table.setItem(r, 0, it)
            self.table.setItem(r, 1, QTableWidgetItem(song.artist))
            self.table.setItem(r, 2, QTableWidgetItem(" / ".join(meters.get(d, "-") for d in DIFFS)))
            # the song's folder in the output folder, to tell apart songs made twice
            self.table.setItem(r, 3, QTableWidgetItem(outer_of(song.sm).name))
            self.table.setItem(r, 4, QTableWidgetItem(name))
        self.table.itemChanged.connect(self._sync_all)
        # a click anywhere else on the row ticks it too
        self.table.cellClicked.connect(lambda r, c: c and self._toggle(r))
        v.addWidget(self.table, 1)
        if not self.songs:
            v.addWidget(QLabel("No songs made there yet."))

        box = QGroupBox("Where to")
        g = QGridLayout(box)
        self.to_folder = QRadioButton("Copy into a folder")
        self.to_folder.setToolTip("Each song gets its own folder in here: pick a group folder in "
                                  "StepMania's Songs folder, e.g. Songs\\AATesting.")
        self.to_zip = QRadioButton("Save as a zip")
        self.to_zip.setToolTip("One zip with a folder per song inside: unzip it into a group "
                               "folder in StepMania's Songs folder.")
        self.dest = QLineEdit(settings.value("export_dir", ""))
        self.dest.setPlaceholderText("e.g. C:\\Games\\StepMania 5\\Songs\\AATesting")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        g.addWidget(self.to_folder, 0, 0)
        g.addWidget(self.dest, 0, 1)
        g.addWidget(browse, 0, 2)
        g.addWidget(self.to_zip, 1, 0)
        g.addWidget(QLabel("You pick where the zip goes when you press Export."), 1, 1, 1, 2)
        (self.to_zip if settings.value("export_zip", "false") == "true" else self.to_folder).setChecked(True)
        v.addWidget(box)

        bb = QDialogButtonBox()
        self.go = bb.addButton("Export", QDialogButtonBox.AcceptRole)
        bb.addButton(QDialogButtonBox.Close)
        bb.accepted.connect(self.run)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._sync_all()

    def _toggle(self, r: int):
        it = self.table.item(r, 0)
        it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)

    def _all_clicked(self):
        # clicking a partly ticked box ticks everything rather than cycling
        on = self.all.checkState() != Qt.Unchecked
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._sync_all()

    def chosen(self) -> list:
        return [s for r, s in enumerate(self.songs) if self.table.item(r, 0).checkState() == Qt.Checked]

    def _sync_all(self, *_):
        n = len(self.chosen())
        self.all.setCheckState(Qt.Unchecked if n == 0 else Qt.Checked if n == len(self.songs)
                               else Qt.PartiallyChecked)
        self.go.setEnabled(n > 0)
        self.go.setText(f"Export {n} song{'s' * (n != 1)}" if n else "Export")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Export into", self.dest.text())
        if d:
            self.dest.setText(d)
            self.to_folder.setChecked(True)

    def run(self):
        songs = self.chosen()
        if self.to_zip.isChecked():
            last = self.settings.value("export_zip_path", "") or str(Path.home() / "stepgen songs.zip")
            f, _ = QFileDialog.getSaveFileName(self, "Save zip", last, "Zip files (*.zip)")
            if not f:
                return
            dest = Path(f) if f.lower().endswith(".zip") else Path(f + ".zip")
            self.settings.setValue("export_zip_path", str(dest))
        else:
            text = self.dest.text().strip()
            if not text:
                QMessageBox.warning(self, "Export songs", "Pick the folder to copy the songs into.")
                return
            dest = Path(text)
            self.settings.setValue("export_dir", text)
        self.settings.setValue("export_zip", "true" if self.to_zip.isChecked() else "false")

        prog = QProgressDialog("Exporting…", "Stop", 0, len(songs), self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(300)

        def step(i, n):
            prog.setValue(i)
            prog.setLabelText(f"Exporting {songs[i].title}…")
            QApplication.processEvents()
            return not prog.wasCanceled()

        notes = []
        try:
            done = export.export(songs, dest, notes.append, step)
        except OSError as e:
            prog.close()
            QMessageBox.warning(self, "Export songs", f"The export stopped: {e}")
            return
        prog.setValue(len(songs))
        msg = QMessageBox(self)
        msg.setWindowTitle("Export songs")
        msg.setIcon(QMessageBox.Warning if notes else QMessageBox.Information)
        msg.setText(f"Exported {len(done)} song{'s' * (len(done) != 1)} to {dest}.")
        if notes:
            msg.setInformativeText(f"{len(notes)} note{'s' * (len(notes) != 1)}: see Show Details.")
            msg.setDetailedText("\n".join(notes))
        show = msg.addButton("Open folder", QMessageBox.AcceptRole)
        msg.addButton(QMessageBox.Close)
        msg.exec()
        if msg.clickedButton() is show:
            if sys.platform == "win32" and dest.suffix.lower() == ".zip":
                QProcess.startDetached("explorer", [f"/select,{dest}"])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest if dest.suffix.lower() != ".zip"
                                                                 else dest.parent)))


SHORTEN = [("Full song", 0), ("Try to shorten to about 1:30", 90), ("Try to shorten to about 2:00", 120)]


def show_title(job) -> str:
    """The title StepMania shows: a shortened song is a separate one,
    '<title> (short)'."""
    title = job.title.strip()
    if job.settings.get("shorten") and not title.endswith(" (short)"):
        title += " (short)"
    return title


def out_title(job) -> str:
    """The folder and chart name a song is made under: its title in plain
    ASCII (layout.file_name), which StepMania can always load."""
    return file_name(show_title(job), job.artist)


def usable(w) -> bool:
    """The control itself is switched on (its add-on or model is there),
    whatever its page is: isEnabled() is also False while a made song's
    locked settings are shown, which used to wipe them on the way in."""
    return not w.testAttribute(Qt.WA_ForceDisabled)


def ai_ready() -> bool:
    """The AI assist model and onnxruntime are there."""
    try:
        import ai_assist
    except ImportError:
        return False
    return ai_assist.available()


def used_settings(sm: Path) -> str:
    """Markdown summary of the settings a chart was made with, from the
    .stepgen.json stepgen writes beside it."""
    meta = side(sm, ".stepgen.json")
    try:
        d = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    targets, follow, ai, other = {}, None, None, []
    for s in d.get("set", []):
        k, _, v = s.partition("=")
        if k.endswith(".target_meter"):
            targets[k.split(".")[0]] = v
        elif k.endswith(".melody_follow"):
            follow = v
        elif k.endswith(".ai_assist"):
            ai = v
        else:
            other.append(s)
    lines = ["## Settings used", "",
             f"- Profile **{d.get('profile', '?')}**, seed {d.get('seed', 1)}"
             + (f", BPM forced to {d['bpm']:g}" if d.get("bpm") else "")]
    if targets:
        lines.append("- Aimed at: " + ", ".join(f"{k} {v}" for k, v in targets.items()))
    if d.get("easy"):
        lines.append("- Feel sliders: " + ", ".join(f"{k} {round(float(v) * 100)}%" for k, v in d["easy"].items()))
    if follow or d.get("follow"):
        lines.append(f"- Follow the melody: {round(float(follow or 0) * 100)}%"
                     + "".join(f", {k} {round(float(v) * 100)}%" for k, v in d.get("follow", {}).items())
                     + (" (vocals separated)" if d.get("stems") else ""))
    if ai or d.get("ai_assist"):
        lines.append(f"- AI assist: {round(float(ai or 0) * 100)}%"
                     + (f" ({d['ai_model']})" if d.get("ai_model") else ""))
    if d.get("lyrics"):
        lines.append("- AI verse detection: sections named from the lyrics")
    if d.get("backoff"):
        lines.append("- Backoff: the easier charts were cut out of the hardest")
    if (d.get("shorten") or {}).get("summary"):
        lines.append(f"- Shortened toward {int(d['shorten']['target'])} s: {d['shorten']['summary']}")
    if other:
        lines.append("- Exact settings: " + ", ".join(other))
    for k, r in (d.get("made_with") or {}).items():
        if r.get("breathing"):
            lines.append(f"- **{k}: {r['breathing']}**")
        elif r.get("changed") and not r.get("cut_from"):
            lines.append(f"- {k}: the difficulty target changed {len(r['changed'])} settings "
                         "(Advanced tab, \"made\" columns)")
    return "\n".join(lines) + "\n\n"


def read_meters(sm: Path) -> dict[str, str]:
    try:
        import chartstats
        _, charts = chartstats.parse(sm)
        return {c.difficulty: str(c.meter) for c in charts}
    except Exception:
        return {}


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    for icon in (HERE / "stepgen.png", HERE / "packaging" / "stepgen.png"):
        if icon.is_file():
            app.setWindowIcon(QIcon(str(icon)))
            break
    w = Window()
    w.show()
    if len(sys.argv) > 1:
        w.add_paths([Path(a) for a in sys.argv[1:]])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
