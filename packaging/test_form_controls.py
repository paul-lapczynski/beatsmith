"""Use real Qt wheel delivery to check values and scroll-area propagation."""
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget
    from form_controls import protect_form_wheels
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "Qt checks run after installing app build dependencies")
class FormWheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        protect_form_wheels(cls.app)

    def setUp(self):
        self.scroll = QScrollArea()
        self.scroll.resize(400, 200)
        self.scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.layout = QVBoxLayout(self.body)
        self.widgets = [QSpinBox(), QDoubleSpinBox(), QComboBox(), QSlider(Qt.Horizontal)]
        self.widgets[0].setValue(50)
        self.widgets[1].setValue(50)
        self.widgets[2].addItems(["First", "Second", "Third"])
        self.widgets[2].setCurrentIndex(1)
        self.widgets[3].setValue(50)
        for widget in self.widgets:
            self.layout.addWidget(widget)
        self.layout.addStretch()
        self.body.setMinimumHeight(1000)
        self.scroll.setWidget(self.body)
        self.scroll.show()
        self.app.processEvents()
        self.addCleanup(self.scroll.close)

    def wheel(self, widget, delta=-120):
        position = QPointF(widget.rect().center())
        event = QWheelEvent(position, QPointF(widget.mapToGlobal(position.toPoint())), QPoint(), QPoint(0, delta),
                            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(widget, event)
        self.app.processEvents()

    def test_values_do_not_change_with_or_without_focus(self):
        for widget in self.widgets:
            for focus in (False, True):
                with self.subTest(widget=type(widget).__name__, focus=focus):
                    widget.setFocus() if focus else widget.clearFocus()
                    before = widget.currentIndex() if isinstance(widget, QComboBox) else widget.value()
                    self.wheel(widget)
                    self.wheel(widget, 120)
                    after = widget.currentIndex() if isinstance(widget, QComboBox) else widget.value()
                    self.assertEqual(before, after)

    def test_wheel_over_controls_scrolls_the_form(self):
        for widget in self.widgets:
            with self.subTest(widget=type(widget).__name__):
                self.scroll.verticalScrollBar().setValue(0)
                self.wheel(widget)
                self.assertGreater(self.scroll.verticalScrollBar().value(), 0)

    def test_controls_still_accept_explicit_changes(self):
        QTest.keyClick(self.widgets[0], Qt.Key_Up)
        QTest.keyClick(self.widgets[1], Qt.Key_Up)
        QTest.keyClick(self.widgets[2], Qt.Key_Down)
        QTest.keyClick(self.widgets[3], Qt.Key_Right)
        self.assertEqual([self.widgets[0].value(), self.widgets[1].value(), self.widgets[2].currentIndex(), self.widgets[3].value()],
                         [51, 51, 2, 51])

    def test_wheel_over_spinbox_text_does_not_change_value(self):
        for widget in self.widgets[:2]:
            with self.subTest(widget=type(widget).__name__):
                self.scroll.verticalScrollBar().setValue(0)
                self.wheel(widget.lineEdit())
                self.assertEqual(widget.value(), 50)
                self.assertGreater(self.scroll.verticalScrollBar().value(), 0)

    def test_trackpad_pixel_scroll_is_forwarded(self):
        widget = self.widgets[0]
        event = QWheelEvent(QPointF(5, 5), QPointF(widget.mapToGlobal(QPoint(5, 5))), QPoint(0, -40), QPoint(),
                            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
        QApplication.sendEvent(widget, event)
        self.app.processEvents()
        self.assertEqual(widget.value(), 50)
        self.assertGreater(self.scroll.verticalScrollBar().value(), 0)


if __name__ == "__main__":
    unittest.main()
