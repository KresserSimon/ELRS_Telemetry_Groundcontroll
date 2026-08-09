"""Actually forces paintEvent to run for every draggable-overlay chrome
widget (resize grip, close button) via QWidget.grab(), instead of just
checking wiring/state. This is the class of bug that offscreen
wiring-only tests miss: a paintEvent() that raises (e.g. a Qt method
called with the wrong argument type) doesn't fail a plain state assertion
- it only surfaces once Qt actually tries to paint the widget, which
unhandled crashes the whole process instead of raising a catchable
Python exception (PyQt exceptions raised inside a Qt callback are fatal).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtWidgets import QApplication

from ui.draggable_overlay import DraggableOverlay

_app = QApplication.instance() or QApplication([])


class OverlayPaintTest(unittest.TestCase):
    def test_resize_grip_and_close_button_paint_without_raising(self):
        overlay = DraggableOverlay()
        overlay.resize(200, 120)
        overlay.show()

        # .grab() forces a real paintEvent() call (unlike offscreen wiring
        # tests, which only check state/signals) - any exception raised
        # inside paintEvent would otherwise only crash a real GUI run.
        grip_pixmap = overlay._resize_grip.grab()
        close_pixmap = overlay._close_button.grab()

        self.assertFalse(grip_pixmap.isNull())
        self.assertFalse(close_pixmap.isNull())

        overlay.close()


if __name__ == "__main__":
    unittest.main()
