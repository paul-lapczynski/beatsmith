"""Render the real app with synthetic demo content and isolated settings.

Run from the repository with the app dependencies installed:
    python docs/capture_screenshots.py

Only PNG screenshots are written to the repository. Temporary audio, charts,
settings and profiles are discarded. No downloads, artwork or playback run.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import soundfile as sf
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QGroupBox, QScrollArea, QTabWidget

import beatsmith_app as ui
import chart_editor
import stepgen


def demo_audio(path):
    sr, seconds = 22050, 32
    y = np.zeros(sr * seconds, dtype=np.float32)
    rng = np.random.default_rng(128)

    def add(t, data):
        i = round(t * sr)
        length = min(len(data), len(y) - i)
        if i >= 0 and length > 0:
            y[i:i + length] += data[:length]

    for beat in range(64):
        t = beat / 2
        ts = np.arange(int(sr * 0.18)) / sr
        add(t, 0.45 * np.sin(2 * np.pi * (65 * ts - 55 * ts ** 2)) * np.exp(-ts * 24))
        if beat % 2:
            ts = np.arange(int(sr * 0.1)) / sr
            add(t, 0.14 * rng.normal(size=len(ts)) * np.exp(-ts * 40))
        for off in (0.0, 0.25):
            ts = np.arange(int(sr * 0.035)) / sr
            add(t + off, 0.04 * rng.normal(size=len(ts)) * np.exp(-ts * 100))
        if beat % 8 < 6:
            ts = np.arange(int(sr * 0.4)) / sr
            hz = (261.63, 329.63, 392, 440)[(beat // 2) % 4]
            add(t + (0.25 if beat % 4 == 3 else 0),
                0.13 * np.sin(2 * np.pi * hz * ts) * np.minimum(1, ts / 0.008) * np.exp(-ts * 5))
    sf.write(path, y / max(1, np.max(np.abs(y))), sr)


def main():
    output = ROOT / "docs" / "img" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    # Offscreen Qt on Windows may not enumerate system fonts automatically.
    for font in ("segoeui.ttf", "segoeuib.ttf", "seguisym.ttf", "seguiemj.ttf", "consola.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    if "Segoe UI" in QFontDatabase.families():
        app.setFont(QFont("Segoe UI", 10))

    with tempfile.TemporaryDirectory(prefix="beatsmith-docs-") as tmp:
        work = Path(tmp)
        source = work / "BeatSmith Demo.wav"
        demo_audio(source)
        with patch.dict(os.environ, BEATSMITH_DATA=str(work / "data")):
            stepgen.PROFILE_NAME = "konami"
            stepgen.RUN_SETS = ["Easy.target_meter=3", "Medium.target_meter=6", "Hard.target_meter=8"]
            specs = stepgen.load_patterns(stepgen.resolve_profile("konami"), stepgen.RUN_SETS)
            sm = stepgen.generate(source, work / "Songs", title="BeatSmith Demo",
                                  artist="Synthetic demo", specs=specs,
                                  keep_format=True, art=False)
            settings = QSettings(str(work / "settings.ini"), QSettings.IniFormat)
            # These are demo availability states, not calls to an installer.
            with patch.object(ui, "QSettings", return_value=settings), \
                    patch.object(chart_editor, "QSettings", return_value=settings), \
                    patch.object(ui, "user_profiles_dir", return_value=work / "profiles"), \
                    patch("addons.installed", return_value=False), \
                    patch("accel.nvidia_gpu", return_value=None):
                w = ui.Window()
                w.resize(1540, 1030)
                w.art.setChecked(False)
                w.art_online.setChecked(False)
                w.show_made.setChecked(False)
                w.out_edit.setText("C:/Games/OutFox/Songs/BeatSmith")
                w.defaults = w.capture()
                for name in ("BeatSmith Demo", "Evening Groove"):
                    queued_source = source.with_name(name + ".wav")
                    if queued_source != source:
                        shutil.copy2(source, queued_source)
                    job = ui.Job(queued_source, title=name, artist="Synthetic demo")
                    job.settings = w.capture()
                    w.jobs.append(job)
                    w._add_row(job)
                # Keep the selected queue's lower panel free of local file paths.
                detail_tabs = w.stats_view.parentWidget().parentWidget()
                if isinstance(detail_tabs, QTabWidget):
                    detail_tabs.setCurrentWidget(w.stats_view)
                setting_tabs = w.easy_page.parentWidget().parentWidget()
                settings_scroll = next(s for s in w.findChildren(QScrollArea) if s.widget() and s.widget().isAncestorOf(w.easy_page))

                def settle():
                    for _ in range(4):
                        app.processEvents()
                        time.sleep(0.04)

                def save(name, widget=None):
                    settle()
                    target = output / name
                    if not (widget or w).grab().save(str(target)):
                        raise RuntimeError(f"Could not save {target}")
                    print(target.name, flush=True)

                w.show()
                w._progress_max()
                w.statusBar().showMessage("Added 2 songs. 2 in the queue.")
                w.table.selectRow(1)
                settings_scroll.verticalScrollBar().setValue(0)
                save("generate.png")

                if isinstance(setting_tabs, QTabWidget):
                    setting_tabs.setCurrentWidget(w.adv_page)
                save("advanced.png")
                if isinstance(setting_tabs, QTabWidget):
                    setting_tabs.setCurrentIndex(2)
                save("options.png")
                if isinstance(setting_tabs, QTabWidget):
                    setting_tabs.setCurrentWidget(w.easy_page)
                settings_scroll.ensureWidgetVisible(w.stems_box)
                save("optional-ai.png", w.stems_box.parentWidget())
                save("ai-assist.png", w.ai.parentWidget())
                feel = next((g for g in w.findChildren(QGroupBox) if g.title().startswith("Feel")), None)
                if feel:
                    settings_scroll.ensureWidgetVisible(feel)
                    save("feel.png", feel)

                job = w.jobs[0]
                job.status, job.sm = ui.DONE, sm
                job.meters = ui.read_meters(sm)
                w.table.item(0, ui.C_STATUS).setText(ui.DONE)
                w.table.item(0, ui.C_METERS).setText("/".join(job.meters.get(d, "-") for d in ui.DIFFS))
                w.table.selectRow(0)
                settings_scroll.verticalScrollBar().setValue(0)
                w.statusBar().showMessage("BeatSmith Demo is done. Select Edit chart to review it.")
                save("results.png")
                w.edit_selected()
                w.editor.field.cursor = 8 * chart_editor.TPB
                w.editor.field.update()
                w.editor._status()
                save("editor.png")
                w.editor.compare_box.setCurrentIndex(2 if w.editor.compare_box.count() > 2 else 1)
                save("compare.png")
                w.close()
                settle()


if __name__ == "__main__":
    main()
