#!/usr/bin/env python3
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout


class FullscreenMixin:
    def detach_main_fullscreen(self):
        if not self.current_cam:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Camera", "Select a main camera first.")
            return
        try:
            idx = int(self.current_cam.get("index", -1))
        except Exception:
            idx = -1
        name = self.current_cam.get("name", "Main Camera")
        self.open_fullscreen(idx, name)

    def open_fullscreen(self, index, name):
        cap = None
        if isinstance(index, int) and index >= 0:
            cap = self.capture_mgr.get(index)

        if not cap:
            for c in self.cams:
                if c.get("name") == name:
                    cap = self.capture_mgr.get(c["index"])
                    break

        if not cap:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Unavailable", "Camera not available.")
            return

        fs = QWidget()
        fs.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        fs.setWindowTitle(name)
        fs.resize(960, 720)
        lbl = QLabel(fs)
        lbl.setStyleSheet("background:#000;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(fs)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(lbl)
        fs.show()

        timer = QTimer(fs)

        def cleanup():
            try:
                if timer.isActive():
                    timer.stop()
            except Exception:
                pass

        def tick():
            if not cap or not cap.isOpened():
                cleanup()
                fs.close()
                return
            ret, frame = cap.read()
            if not ret or frame is None:
                return
            rgb = self._frame_to_rgb(frame)
            if rgb is None:
                return
            h, w, _ = rgb.shape
            q = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
            p = QPixmap.fromImage(q)
            lbl.setPixmap(p.scaled(lbl.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        timer.timeout.connect(tick)
        timer.start(30)

        def keyPressEvent(ev):
            if ev.key() == Qt.Key.Key_Escape:
                fs.close()
            else:
                QWidget.keyPressEvent(fs, ev)

        def closeEvent(ev):
            cleanup()
            QWidget.closeEvent(fs, ev)

        fs.keyPressEvent = keyPressEvent
        fs.closeEvent = closeEvent
        fs.destroyed.connect(lambda *_: cleanup())
