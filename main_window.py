#!/usr/bin/env python3
import os
import contextlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cv2
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QMessageBox, QSizePolicy
)

from capture_manager import CaptureManager, scan_cameras
from settings_store import load_settings, save_settings
from widgets import CameraThumbnail
from control_panel import styled_list_view
from dialogs import populate_combo
from actions_mixin import CaptureActionsMixin
from fullscreen_mixin import FullscreenMixin
from panel_mixin import PanelMixin
from dialogs_mixin import DialogsMixin


class CameraApp(QWidget, CaptureActionsMixin, FullscreenMixin, PanelMixin, DialogsMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoCam")
        self.setMinimumSize(1100, 650)
        self.setStyleSheet("background:#000;")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self._drag_pos = None
        self.settings = load_settings()
        self.capture_mgr = CaptureManager()
        self.cams: List[Dict[str, Any]] = []
        self.current_cam = None
        self.video_label = QLabel("Live Preview")
        self.video_label.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0f172a, stop:1 #111827); color:#e6eef8; font-size:16px; border:1px solid #1f2937; border-radius:8px;")
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.main_overlay = QLabel("Main Camera", self.video_label)
        self.main_overlay.setStyleSheet("background: rgba(0,0,0,0.6); color: #fff; padding: 4px 8px; border-radius:4px;")
        self.main_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.main_overlay.hide()
        self.motion_indicator = QLabel("Motion", self.video_label)
        self.motion_indicator.setStyleSheet("background:#6366f1; color:#fff; padding:3px 6px; border-radius:4px;")
        self.motion_indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.motion_indicator.hide()
        self.logo_label = QLabel(self.video_label)
        self.logo_label.setFixedSize(88, 88)
        self.logo_label.setStyleSheet("background:transparent; border:1px dashed #1f2937; border-radius:44px;")
        self.logo_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.logo_label.setAutoFillBackground(False)
        self.brand_label = QLabel(self)
        self.brand_label.setFixedHeight(44)
        self.brand_label.setMinimumWidth(140)
        self.brand_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.brand_label.setStyleSheet("color:#e6eef8; font-size:18px; font-weight:600; background:transparent; border:1px dashed #1f2937; border-radius:8px; padding:8px 12px;")
        self.brand_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.brand_label.setAutoFillBackground(False)
        self.main_detach_btn = QPushButton("Separate Window", self.video_label)
        self.main_detach_btn.setMinimumHeight(30)
        self.main_detach_btn.setMinimumWidth(200)
        self.main_detach_btn.setStyleSheet("QPushButton{background:#1e88e5;color:#fff;border:none;border-radius:3px;} QPushButton:pressed{background:#166bb0;}")
        self.main_detach_btn.clicked.connect(self.detach_main_fullscreen)
        self.main_detach_btn.hide()
        self.main_capture_btn = QPushButton("Take Picture", self.video_label)
        self.main_capture_btn.setMinimumHeight(30)
        self.main_capture_btn.setMinimumWidth(160)
        self.main_capture_btn.setStyleSheet("QPushButton{background:#0ea5e9;color:#fff;border:none;border-radius:3px;} QPushButton:pressed{background:#0284c7;}")
        self.main_capture_btn.clicked.connect(self._capture_main)
        self.main_capture_btn.hide()
        self.main_record_btn = QPushButton("Start Recording", self.video_label)
        self.main_record_btn.setCheckable(True)
        self.main_record_btn.setMinimumHeight(30)
        self.main_record_btn.setMinimumWidth(160)
        self.main_record_btn.setStyleSheet("QPushButton{background:#16a34a;color:#fff;border:none;border-radius:3px;} QPushButton:pressed{background:#15803d;} QPushButton:checked{background:#b91c1c;}")
        self.main_record_btn.clicked.connect(self.toggle_recording)
        self.main_record_btn.hide()

        self.corner1 = CameraThumbnail("Corner Cam 1")
        self.corner2 = CameraThumbnail("Corner Cam 2")
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh_cameras)
        self.motion_btn = QPushButton("Motion Detect")
        self.motion_btn.setCheckable(True)
        self.motion_btn.clicked.connect(self.toggle_motion)
        self.motion_enabled = False
        self._update_motion_button_style()
        self.fs_combo = QComboBox()
        self.fs_btn = QPushButton("Make Separate Window")
        self.fs_btn.clicked.connect(self.open_fullscreen_from_combo)
        self.main_sel = QComboBox()
        self.c1_sel = QComboBox()
        self.c2_sel = QComboBox()
        self.res_sel = QComboBox()
        for r in [(640, 480), (1280, 720), (1920, 1080)]:
            self.res_sel.addItem(f"{r[0]} x {r[1]}", r)
        self.res_apply = QPushButton("Apply Resolution")
        for combo in (self.main_sel, self.c1_sel, self.c2_sel, self.fs_combo, self.res_sel):
            combo.setMinimumWidth(140)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setView(styled_list_view())
        self.main_sel.currentIndexChanged.connect(lambda _: self._select_slot("main", self.main_sel))
        self.c1_sel.currentIndexChanged.connect(lambda _: self._select_slot("corner1", self.c1_sel))
        self.c2_sel.currentIndexChanged.connect(lambda _: self._select_slot("corner2", self.c2_sel))
        self._selectors_updating = False
        self.close_btn = QPushButton("✕")
        self.close_btn.setParent(self)
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setStyleSheet("QPushButton{background:#b91c1c;color:#fff;font-size:14px;border:none;border-radius:11px;} QPushButton:pressed{background:#dc2626;}")
        self.close_btn.clicked.connect(self.close)
        self._load_logo()
        self._load_brand()
        self.logo_label.mousePressEvent = self._logo_press
        self.controls_panel = None
        self._panel_was_visible = False
        self.pending_settings = dict(self.settings)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.corner1.clicked.connect(self.open_fullscreen)
        self.corner2.clicked.connect(self.open_fullscreen)
        self.corner1.detach_requested.connect(self.open_fullscreen)
        self.corner2.detach_requested.connect(self.open_fullscreen)
        self.corner1.capture_requested.connect(lambda idx, name: self._capture_corner(1))
        self.corner2.capture_requested.connect(lambda idx, name: self._capture_corner(2))
        self.corner1.record_toggled.connect(lambda idx, name, state: self._toggle_corner_from_thumb(1, state))
        self.corner2.record_toggled.connect(lambda idx, name, state: self._toggle_corner_from_thumb(2, state))
        self.recording = False
        self.record_writer = None
        self.record_file = None
        self.prev_gray = None
        self.corner_recording = {1: False, 2: False}
        self.corner_record_writers = {1: None, 2: None}
        self.corner_record_files = {1: None, 2: None}
        self.corner_record_fps = {1: 20.0, 2: 20.0}
        self.build_ui()
        self.refresh_cameras(open_all=True, apply_saved=True)

    @contextlib.contextmanager
    def _paused_streams(self):
        main_active = self.timer.isActive()
        t1_active = self.corner1.timer.isActive()
        t2_active = self.corner2.timer.isActive()
        try:
            self.timer.stop()
            self.corner1.timer.stop()
            self.corner2.timer.stop()
            yield
        finally:
            if self.current_cam and main_active and not self.timer.isActive():
                self.timer.start(30)
            if self.corner1.cam and t1_active and not self.corner1.timer.isActive():
                self.corner1.timer.start(100)
            if self.corner2.cam and t2_active and not self.corner2.timer.isActive():
                self.corner2.timer.start(100)

    def resizeEvent(self, ev):
        try:
            margin = 6
            logo_x = 3
            logo_y = 20
            self.main_detach_btn.adjustSize()
            self.main_overlay.adjustSize()
            self.motion_indicator.adjustSize()
            self.logo_label.move(logo_x, self.height() - self.logo_label.height() - logo_y)
            brand_y = self.height() - max(self.logo_label.height(), self.brand_label.height()) - logo_y + (self.logo_label.height() - self.brand_label.height()) // 2 + 14
            brand_x = self.logo_label.x() + self.logo_label.width() + 2
            self.brand_label.move(brand_x, brand_y)
            self.close_btn.move(self.width() - self.close_btn.width() - margin, margin)
            self.close_btn.raise_()
            self.corner1.detach_btn.move(8, self.corner1.overlay.height() + 12)
            self.corner2.detach_btn.move(8, self.corner2.overlay.height() + 12)
            self.main_overlay.move(margin, margin)
            self.main_detach_btn.move(margin, self.main_overlay.height() + margin + 6)
            self.main_capture_btn.move(margin, self.main_detach_btn.y() + self.main_detach_btn.height() + 6)
            self.main_record_btn.move(margin, self.main_capture_btn.y() + self.main_capture_btn.height() + 6)
            motion_y = self.main_record_btn.y() + self.main_record_btn.height() + 6
            self.motion_indicator.move(margin, motion_y)
            self.brand_label.raise_()
        except Exception:
            pass
        super().resizeEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None
        super().mouseReleaseEvent(ev)

    def build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        left = QVBoxLayout()
        left.addWidget(self.video_label, 1)
        layout.addLayout(left, 3)
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self.corner1, 1)
        right.addWidget(self.corner2, 1)
        right.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(right, 1)

    def _set_main_placeholder(self, text="No camera selected"):
        self.video_label.setPixmap(QPixmap())
        self.video_label.setText(text)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_overlay.hide()
        self.main_detach_btn.hide()
        self.main_capture_btn.hide()
        self.main_record_btn.hide()
        self.motion_indicator.hide()
        self.prev_gray = None
        self.stop_recording()

    def toggle_motion(self):
        self.motion_enabled = self.motion_btn.isChecked()
        self._update_motion_button_style()
        if not self.motion_enabled:
            self.prev_gray = None
            self.motion_indicator.hide()

    def toggle_recording(self):
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def _frame_to_rgb(self, frame):
        try:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
            return None

    def apply_settings(self):
        self.cams = scan_cameras()
        self.capture_mgr.release_all()
        self.capture_mgr.open_all(self.cams)

        def find(idx=None, path=None):
            if path:
                for c in self.cams:
                    if c["path"] == path:
                        return c
            if isinstance(idx, int):
                for c in self.cams:
                    if c.get("index") == idx:
                        return c
            return None

        main = find(self.settings.get("main"), self.settings.get("main_path"))
        t1 = find(self.settings.get("corner1"), self.settings.get("corner1_path"))
        t2 = find(self.settings.get("corner2"), self.settings.get("corner2_path"))

        if main:
            if t1 and t1.get("path") == main.get("path"):
                t1 = None
            if t2 and t2.get("path") == main.get("path"):
                t2 = None
        if t1 and t2 and t1.get("path") == t2.get("path"):
            t2 = None

        if main:
            self.current_cam = main
            self.prev_gray = None
            cap = self.capture_mgr.get(main["index"] if isinstance(main.get("index"), int) and main.get("index") >= 0 else main.get("path"))
            if cap and self.settings.get("resolution"):
                try:
                    w, h = tuple(self.settings["resolution"])
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                except Exception:
                    pass
            if cap:
                if not self.timer.isActive():
                    self.timer.start(30)
                self.main_overlay.show()
                self.main_detach_btn.show()
                self.main_capture_btn.show()
                self.main_record_btn.show()
            else:
                self._set_main_placeholder()
        else:
            self.current_cam = None
            self._set_main_placeholder()
            try:
                self.timer.stop()
            except Exception:
                pass

        cap_t1 = None
        cap_t2 = None
        if t1:
            cap_t1 = self.capture_mgr.get(t1["index"] if isinstance(t1.get("index"), int) and t1.get("index") >= 0 else t1.get("path"))
        if t2:
            cap_t2 = self.capture_mgr.get(t2["index"] if isinstance(t2.get("index"), int) and t2.get("index") >= 0 else t2.get("path"))

        self.corner1.set_title("Corner Cam 1")
        self.corner2.set_title("Corner Cam 2")

        self.corner1.set_camera(t1, cap_t1)
        self.corner2.set_camera(t2, cap_t2)
        self.corner1.set_frame_callback(lambda frame: self._record_corner_frame(1, frame))
        self.corner2.set_frame_callback(lambda frame: self._record_corner_frame(2, frame))
        self.corner1.set_recording_active(self.corner_recording.get(1, False))
        self.corner2.set_recording_active(self.corner_recording.get(2, False))
        if not t1:
            self.stop_corner_recording(1)
        if not t2:
            self.stop_corner_recording(2)
        self._populate_fs_combo()
        self._populate_selectors(main, t1, t2)
        self._ensure_controls_panel()

    def refresh_cameras(self, open_all=False, apply_saved=True):
        self.cams = scan_cameras()
        if not self.cams:
            QMessageBox.warning(self, "No Cameras", "No cameras detected.")
            self.corner1.set_camera(None, None)
            self.corner2.set_camera(None, None)
            self.capture_mgr.release_all()
            self._set_main_placeholder()
            self._populate_fs_combo()
            self._populate_selectors(None, None, None)
            self._ensure_controls_panel()
            return
        if open_all:
            self.capture_mgr.open_all(self.cams)
        if apply_saved and (self.settings.get("main_path") or self.settings.get("main") is not None):
            sp = self.settings.get("main_path")
            sm = self.settings.get("main")
            found = False
            if sp and any(c["path"] == sp for c in self.cams):
                found = True
            if sm is not None and any(c.get("index") == sm for c in self.cams):
                found = True
            if found:
                self.apply_settings()
                return
        self.current_cam = None
        self._set_main_placeholder()
        self.corner1.set_camera(None, None)
        self.corner2.set_camera(None, None)
        self._populate_fs_combo()
        self._populate_selectors(None, None, None)
        self._ensure_controls_panel()
        try:
            self.timer.stop()
        except Exception:
            pass

    def update_frame(self):
        if not self.current_cam:
            return
        idx = self.current_cam.get("index")
        cap = None
        try:
            if isinstance(idx, int) and idx >= 0:
                cap = self.capture_mgr.get(int(idx))
            else:
                cap = self.capture_mgr.get(self.current_cam.get("path"))
        except Exception:
            cap = None
        if not cap:
            if self.recording:
                self.stop_recording()
            return
        try:
            ret, frame = cap.read()
        except Exception:
            ret = False
            frame = None
        if not ret or frame is None:
            return
        motion = False
        if self.motion_enabled:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (5, 5), 0)
                if self.prev_gray is not None:
                    diff = cv2.absdiff(self.prev_gray, gray)
                    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                    motion = cv2.countNonZero(thresh) > 5000
                self.prev_gray = gray
            except Exception:
                self.prev_gray = None
                motion = False
            if motion:
                try:
                    cv2.rectangle(frame, (0, 0), (frame.shape[1] - 1, frame.shape[0] - 1), (0, 0, 255), 3)
                except Exception:
                    pass
        else:
            self.prev_gray = None

        if self.recording:
            if not self.record_writer and self.record_file:
                try:
                    h, w = frame.shape[:2]
                    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
                    if fps and fps < 1:
                        fps = 20.0
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    self.record_writer = cv2.VideoWriter(str(self.record_file), fourcc, fps or 20.0, (w, h))
                except Exception:
                    self.stop_recording()
            if self.record_writer and self.record_writer.isOpened():
                try:
                    self.record_writer.write(frame)
                except Exception:
                    self.stop_recording()
            else:
                self.stop_recording()

        rgb = self._frame_to_rgb(frame)
        if rgb is None:
            return
        h, w, _ = rgb.shape
        q = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        p = QPixmap.fromImage(q).scaled(self.video_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.video_label.setPixmap(p)
        self.video_label.setText("")
        if self.motion_enabled:
            self.motion_indicator.setStyleSheet("background:#d32f2f; color:#fff; padding:3px 6px; border-radius:4px;" if motion else "background:#444; color:#fff; padding:3px 6px; border-radius:4px;")
            self.motion_indicator.show()
        else:
            self.motion_indicator.hide()

    def closeEvent(self, e):
        try:
            self.timer.stop()
        except Exception:
            pass
        try:
            self.corner1.timer.stop()
            self.corner2.timer.stop()
        except Exception:
            pass
        self.stop_recording()
        self.stop_corner_recording(1)
        self.stop_corner_recording(2)
        self.capture_mgr.release_all()
        super().closeEvent(e)

    def _logo_press(self, ev):
        try:
            self.toggle_controls_panel()
        finally:
            ev.accept()

    def _load_logo(self, path: Optional[Union[str, Path]] = None):
        target = Path(path) if path else Path(__file__).with_name("logo.png")
        if target.exists():
            pix = QPixmap(str(target)).scaled(self.logo_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pix)
            self.logo_label.setStyleSheet("background:transparent; border:none;")
            self.logo_label.setAutoFillBackground(False)
            self.logo_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _load_brand(self, path: Optional[Union[str, Path]] = None):
        target = Path(path) if path else Path(__file__).with_name("brand.png")
        if target.exists():
            pix = QPixmap(str(target)).scaled(self.brand_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.brand_label.clear()
            self.brand_label.setPixmap(pix)
            self.brand_label.setStyleSheet("background:transparent; border:none;")
            self.brand_label.setAutoFillBackground(False)
            self.brand_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        else:
            self.brand_label.setText("MyEye")
