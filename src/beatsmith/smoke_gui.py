"""Internal frozen-GUI check with isolated preferences and no user library."""
import os
from pathlib import Path
import tempfile


def main():
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication
    from beatsmith import beatsmith_app, addons, accel

    with tempfile.TemporaryDirectory(prefix='beatsmith-gui-check-') as tmp:
        work = Path(tmp)
        os.environ['BEATSMITH_DATA'] = str(work / 'data')
        settings = QSettings(str(work / 'settings.ini'), QSettings.IniFormat)
        beatsmith_app.QSettings = lambda *args: settings
        from beatsmith import chart_editor
        chart_editor.QSettings = lambda *args: settings
        beatsmith_app.user_profiles_dir = lambda: work / 'profiles'
        addons.installed = lambda *args: False
        accel.nvidia_gpu = lambda: None
        app = QApplication([])
        window = beatsmith_app.Window()
        window.show()
        QTimer.singleShot(200, app.quit)
        code = app.exec()
        window.close()
        if code:
            raise RuntimeError(f'GUI event loop failed: {code}')
    print('Frozen GUI and editor construction passed with isolated settings')
    return 0
