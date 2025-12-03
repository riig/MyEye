#!/usr/bin/env python3
from typing import Any, Dict, Optional

import cv2
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout


class CameraThumbnail(QFrame):
    clicked = pyqtSignal(int, str)
    detach_requested = pyqtSignal(int, str)
    capture_requested = pyqtSignal(int, str)
    record_toggled = pyqtSignal(int, str, bool)

    def __init__(self, title: str = "Corner Cam", min_w=320, min_h=240):
        super().__init__()
        self.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0f172a, stop:1 #111827);color:#e6eef8;border:1px solid #1f2937;border-radius:8px;")
        self.setMinimumSize(min_w, min_h)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("No camera selected")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color:#e6eef8; font-size:14px;")
        self.layout.addWidget(self.label)
        self.overlay = QLabel(title, self)
        self.overlay.setStyleSheet("background: rgba(0,0,0,0.6); color: #fff; padding: 3px 6px; border-radius:4px;")
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay.hide()
        self.detach_btn = QPushButton("Separate Window", self)
        self.detach_btn.setMinimumHeight(28)
        self.detach_btn.setMinimumWidth(190)
        self.detach_btn.setStyleSheet("QPushButton{background:#1e88e5;color:#fff;border:none;border-radius:3px;} QPushButton:pressed{background:#166bb0;}")
        self.detach_btn.clicked.connect(self._detach)
        self.detach_btn.hide()
        self.capture_btn = QPushButton("Take Picture", self)
        self.capture_btn.setMinimumHeight(28)
        self.capture_btn.setMinimumWidth(160)
        self.capture_btn.setStyleSheet("QPushButton{background:#0ea5e9;color:#fff;border:none;border-radius:3px;} QPushButton:pressed{background:#0284c7;}")
        self.capture_btn.clicked.connect(self._capture)
        self.capture_btn.hide()
        self.record_btn = QPushButton("Start Recording", self)
        self.record_btn.setCheckable(True)
        self.record_btn.setMinimumHeight(28)
        self.record_btn.setMinimumWidth(160)
        self.record_btn.setStyleSheet("QPushButton{background:#16a34a;color:#fff;border:none;border-radius:3px;} QPushButton:pressed{background:#15803d;} QPushButton:checked{background:#b91c1c;}")
        self.record_btn.clicked.connect(self._record_toggle)
        self.record_btn.hide()
        self.cam: Optional[Dict[str, Any]] = None
        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.frame_callback = None

    def resizeEvent(self, ev):
        try:
            self.overlay.move(8, 8)
            self.detach_btn.move(8, self.overlay.height() + 12)
            self.capture_btn.move(8, self.detach_btn.y() + self.detach_btn.height() + 6)
            self.record_btn.move(8, self.capture_btn.y() + self.capture_btn.height() + 6)
        except Exception:
            pass
        super().resizeEvent(ev)

    def set_title(self, text: str):
        self.overlay.setText(text)

    def set_camera(self, cam, cap):
        try:
            self.timer.stop()
        except Exception:
            pass
        self.cam, self.cap = cam, cap
        self.frame_callback = None
        if not cam or not cap:
            self.label.setPixmap(QPixmap())
            self.label.setText("No camera selected")
            self.label.show()
            self.overlay.hide()
            self.detach_btn.hide()
            self.capture_btn.hide()
            self.record_btn.hide()
            self.record_btn.setChecked(False)
            self.record_btn.setText("Start Recording")
            self.label.repaint()
            return
        try:
            if not cap.isOpened():
                self.label.setText("Camera unavailable.")
                self.label.show()
                self.overlay.hide()
                self.detach_btn.hide()
                self.capture_btn.hide()
                self.record_btn.hide()
                self.record_btn.setChecked(False)
                self.record_btn.setText("Start Recording")
                self.label.repaint()
                return
        except Exception:
            self.label.setText("Camera unavailable.")
            self.label.show()
            self.overlay.hide()
            self.detach_btn.hide()
            self.capture_btn.hide()
            self.record_btn.hide()
            self.record_btn.setChecked(False)
            self.record_btn.setText("Start Recording")
            self.label.repaint()
            return
        self.label.show()
        self.overlay.show()
        self.detach_btn.show()
        self.capture_btn.show()
        self.record_btn.show()
        self.timer.start(100)

    def set_frame_callback(self, cb):
        self.frame_callback = cb

    def mousePressEvent(self, e):
        if self.cam:
            try:
                idx = int(self.cam.get("index", -1))
            except Exception:
                idx = -1
            self.clicked.emit(idx, self.cam.get("name", "Camera"))

    def _detach(self):
        if not self.cam:
            return
        try:
            idx = int(self.cam.get("index", -1))
        except Exception:
            idx = -1
        self.detach_requested.emit(idx, self.cam.get("name", "Camera"))

    def _capture(self):
        if not self.cam:
            return
        try:
            idx = int(self.cam.get("index", -1))
        except Exception:
            idx = -1
        self.capture_requested.emit(idx, self.cam.get("name", "Camera"))

    def _record_toggle(self, state):
        if not self.cam:
            self.record_btn.setChecked(False)
            self.record_btn.setText("Start Recording")
            return
        try:
            idx = int(self.cam.get("index", -1))
        except Exception:
            idx = -1
        self.record_toggled.emit(idx, self.cam.get("name", "Camera"), state)

    def set_recording_active(self, active: bool):
        self.record_btn.setChecked(active)
        self.record_btn.setText("Stop Recording" if active else "Start Recording")

    def _tick(self):
        if not self.cap:
            return
        try:
            ret, frame = self.cap.read()
        except Exception:
            ret = False
            frame = None
        if not ret or frame is None:
            self.label.setPixmap(QPixmap())
            self.label.setText("No camera selected")
            self.label.show()
            return
        if self.frame_callback:
            try:
                self.frame_callback(frame.copy())
            except Exception:
                pass
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
            return
        h, w, _ = rgb.shape
        q = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        p = QPixmap.fromImage(q).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.label.setPixmap(p)
