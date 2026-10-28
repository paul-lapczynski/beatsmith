"""Keep scrolling a form from silently changing its inputs."""
from PySide6.QtCore import QEvent, QObject, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QAbstractSpinBox, QComboBox, QSlider, QWidget


class _FormWheelGuard(QObject):
    def eventFilter(self, watched, event):
        if event.type() != QEvent.Wheel or not isinstance(watched, QWidget):
            return False
        control = watched
        while control is not None and not isinstance(control, (QAbstractSpinBox, QComboBox, QSlider)):
            # Let dropdown option lists and ordinary scroll areas handle their
            # own wheels; include a spinbox's internal text field in its guard.
            if isinstance(control, QAbstractScrollArea):
                return False
            control = control.parentWidget()
        if control is not None:
            # Event filters consume input before Qt's usual parent propagation.
            # Send a copy to the form's viewport so the page still scrolls.
            parent = control.parentWidget()
            while parent is not None and not isinstance(parent, QAbstractScrollArea):
                parent = parent.parentWidget()
            if parent is not None:
                pixels = event.pixelDelta()
                if event.angleDelta().isNull() and not pixels.isNull():
                    # Some Qt scrollbars ignore pixel-only touchpad events.
                    for bar, delta in ((parent.verticalScrollBar(), pixels.y()),
                                       (parent.horizontalScrollBar(), pixels.x())):
                        bar.setValue(bar.value() - delta)
                else:
                    viewport = parent.viewport()
                    forwarded = QWheelEvent(QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                                            event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                                            event.buttons(), event.modifiers(), event.phase(), event.inverted())
                    QApplication.sendEvent(viewport, forwarded)
            event.accept()
            return True
        return False


def protect_form_wheels(app):
    """Install once, including for inputs created later (such as table editors)."""
    if not hasattr(app, "_form_wheel_guard"):
        app._form_wheel_guard = _FormWheelGuard(app)
        app.installEventFilter(app._form_wheel_guard)
