import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    import beatsmith_app as ui
except ImportError:
    ui = None


@unittest.skipIf(ui is None, 'UI checks run after installing build dependencies')
class LeadUiTests(unittest.TestCase):
    def test_source_roundtrip_cli_and_section_values(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / 'settings.ini'), QSettings.IniFormat)
            with patch.object(ui, 'QSettings', return_value=settings), \
                    patch.object(ui, 'user_profiles_dir', return_value=Path(tmp)), \
                    patch('addons.installed', return_value=True):
                w = ui.Window()
                self.assertEqual(w.capture()['melody_source'], 'singing')
                w.stems_box.setChecked(True)
                w.melody_source.setCurrentIndex(1)
                w.follow.setValue(80)
                d = w.capture()
                self.assertEqual(d['melody_source'], 'lead')
                self.assertTrue(all(sl.value() == 80 for sl, *_ in w.sec_sliders.values()))
                args = w.args_for(d)
                self.assertEqual(args[args.index('--melody-source') + 1], 'lead')
                w.melody_source.setCurrentIndex(0)
                w.restore(d)
                self.assertEqual(w.melody_source.currentData(), 'lead')
                w.restore({k: v for k, v in d.items() if k != 'melody_source'})
                self.assertEqual(w.melody_source.currentData(), 'singing')
                w.stems_box.setChecked(False)
                self.assertFalse(w.melody_source.isEnabled())
                self.assertNotIn('--melody-source', w.args_for(w.capture()))
                w.close()
                app.processEvents()
