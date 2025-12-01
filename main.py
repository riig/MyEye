#!/usr/bin/env python3
import contextlib
import glob
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json
from datetime import datetime

import cv2
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QMessageBox, QFrame, QSizePolicy,
    QDialog, QListWidget, QListWidgetItem, QDialogButtonBox, QFileDialog,
    QCheckBox, QLineEdit, QScrollArea, QListView
)

DEFAULT_SETTINGS = {
    "main": None,
    "main_path": None,
    "corner1": None,
    "corner1_path": None,
    "corner2": None,
    "corner2_path": None,
    "resolution": (640, 480),
}
IS_LINUX = platform.system().lower() == "linux"
CAP_BACKEND = cv2.CAP_V4L2 if IS_LINUX else cv2.CAP_ANY
SETTINGS_FILE = Path(__file__).with_name("settings.json")

def load_settings() -> Dict[str, Any]:
    data = dict(DEFAULT_SETTINGS)
    try:
        if SETTINGS_FILE.exists():
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k in data:
                    if k in raw:
                        data[k] = raw[k]
    except Exception:
        pass
    if data.get("resolution"):
        data["resolution"] = tuple(data["resolution"])
    return data


def save_settings(settings: Dict[str, Any]):
    try:
        payload = {k: settings.get(k) for k in DEFAULT_SETTINGS}
        if payload.get("resolution"):
            payload["resolution"] = list(payload["resolution"])
        SETTINGS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass

@contextlib.contextmanager
def suppress_stderr():
    with open(os.devnull, "w") as devnull:
        old_fd = os.dup(2)
        os.dup2(devnull.fileno(), 2)
        try:
            yield
        finally:
            os.dup2(old_fd, 2)
            os.close(old_fd)

def scan_cameras() -> List[Dict[str, Any]]:
    def scan_linux() -> List[Dict[str, Any]]:
        devices = {}
        for node in sorted(glob.glob("/dev/video*")):
            m = re.search(r"video(\d+)$", node)
            if not m:
                continue
            try:
                idx = int(m.group(1))
            except Exception:
                continue

            sys_node = f"/sys/class/video4linux/video{idx}"
            parent = None
            try:
                device_link = os.path.join(sys_node, "device")
                if os.path.exists(device_link):
                    parent = os.path.realpath(device_link)
            except Exception:
                parent = None

            name = node
            name_file = os.path.join(sys_node, "name")
            if os.path.exists(name_file):
                with open(name_file, "r", encoding="utf-8", errors="ignore") as f:
                    name = f.read().strip() or name

            key = parent if parent else os.path.realpath(node)
            if key not in devices:
                devices[key] = {
                    "index": idx,
                    "path": node,
                    "name": name,
                    "display": f"{name} ({node})",
                    "all_nodes": [idx],
                }
            else:
                devices[key]["all_nodes"].append(idx)
                if idx < devices[key]["index"]:
                    devices[key]["index"] = idx
                    devices[key]["path"] = node
                    devices[key]["display"] = f"{devices[key]['name']} ({node})"
        return sorted(devices.values(), key=lambda c: c.get("index", 9999))

    def probe_indices(max_devices: int = 10) -> List[Dict[str, Any]]:
        found = []
        for idx in range(max_devices):
            with suppress_stderr():
                cap = None
                try:
                    cap = cv2.VideoCapture(idx)
                except Exception:
                    cap = None
            if cap and cap.isOpened():
                name = f"Camera {idx}"
                found.append({
                    "index": idx,
                    "path": str(idx),
                    "name": name,
                    "display": f"{name} (index {idx})",
                    "all_nodes": [idx]
                })
            try:
                if cap:
                    cap.release()
            except Exception:
                pass
        return found

    linux_cams = scan_linux() if platform.system().lower() == "linux" else []
    if linux_cams:
        return linux_cams
    return probe_indices()




class CaptureManager:
    def __init__(self):
        self.captures: Dict[str, cv2.VideoCapture] = {}

    def _key(self, src: Union[int, str, Dict[str, Any]]) -> str:
        if isinstance(src, dict):
            return str(src.get("path") or src.get("index"))
        if isinstance(src, int):
            return f"/dev/video{src}"
        return str(src)

    def _open(self, src: Union[int, str, None]) -> Optional[cv2.VideoCapture]:
        if src is None:
            return None
        with suppress_stderr():
            try:
                cap = cv2.VideoCapture(src, CAP_BACKEND)
            except Exception:
                cap = None
        if cap and cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            return cap
        if cap:
            try:
                cap.release()
            except Exception:
                pass
        return None

    def open_all(self, cams: List[Dict[str, Any]]):
        for cam in cams:
            idx = cam.get("index")
            target = idx if isinstance(idx, int) and idx >= 0 else cam.get("path")
            key = self._key(target)
            if key not in self.captures:
                cap = self._open(target)
                if cap:
                    self.captures[key] = cap

    def get(self, src: Union[int, str, Dict[str, Any]]) -> Optional[cv2.VideoCapture]:
        key = self._key(src)
        cap = self.captures.get(key)
        if cap and cap.isOpened():
            return cap
        if cap:
            try:
                cap.release()
            except Exception:
                pass
            self.captures.pop(key, None)

        if isinstance(src, dict):
            idx = src.get("index")
            target = idx if isinstance(idx, int) and idx >= 0 else src.get("path")
        else:
            target = src
        cap = self._open(target)
        if cap:
            self.captures[key] = cap
        return cap

    def release(self, src: Union[int, str]):
        cap = self.captures.pop(self._key(src), None)
        if cap:
            try:
                cap.release()
            except Exception:
                pass

    def release_all(self):
        for cap in self.captures.values():
            try:
                cap.release()
            except Exception:
                pass
        self.captures.clear()

class CameraThumbnail(QFrame):
    clicked = pyqtSignal(int, str)
    detach_requested = pyqtSignal(int, str)

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
        self.detach_btn = QPushButton("Make Separate Window", self)
        self.detach_btn.setMinimumHeight(28)
        self.detach_btn.setMinimumWidth(190)
        self.detach_btn.setStyleSheet("QPushButton{background:#1e88e5;color:#fff;border:none;border-radius:3px;} QPushButton:pressed{background:#166bb0;}")
        self.detach_btn.clicked.connect(self._detach)
        self.detach_btn.hide()
        self.cam = None
        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.frame_callback = None

    def resizeEvent(self, ev):
        try:
            self.overlay.move(8, 8)
            self.detach_btn.move(self.width() - self.detach_btn.width() - 8, 8)
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
            self.label.repaint()
            return
        try:
            if not cap.isOpened():
                self.label.setText("Camera unavailable.")
                self.label.show()
                self.overlay.hide()
                self.detach_btn.hide()
                self.label.repaint()
                return
        except Exception:
            self.label.setText("Camera unavailable.")
            self.label.show()
            self.overlay.hide()
            self.detach_btn.hide()
            self.label.repaint()
            return
        self.label.show()
        self.overlay.show()
        self.detach_btn.show()
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

def populate_combo(combo: QComboBox, cams, include_none=True):
    combo.clear()
    if include_none:
        combo.addItem("None", None)
    for c in cams:
        combo.addItem(c["display"], c)

class CameraConfigDialog(QDialog):
    def __init__(self, parent, cams, current):
        super().__init__(parent)
        self.setWindowTitle("Camera Configuration")
        self.resize(480, 340)
        v = QVBoxLayout(self)

        v.addWidget(QLabel("Main Camera"))
        self.main_cb = QComboBox()
        populate_combo(self.main_cb, cams, True)
        v.addWidget(self.main_cb)

        v.addWidget(QLabel("Corner Camera 1"))
        self.t1_cb = QComboBox()
        populate_combo(self.t1_cb, cams, True)
        v.addWidget(self.t1_cb)

        v.addWidget(QLabel("Corner Camera 2"))
        self.t2_cb = QComboBox()
        populate_combo(self.t2_cb, cams, True)
        v.addWidget(self.t2_cb)

        v.addWidget(QLabel("Resolution"))
        self.res_cb = QComboBox()
        for r in [(640, 480), (1280, 720), (1920, 1080)]:
            self.res_cb.addItem(f"{r[0]} x {r[1]}", r)
        v.addWidget(self.res_cb)

        first_run = (
            current.get("main") is None and
            current.get("main_path") is None and
            current.get("corner1") is None and
            current.get("corner1_path") is None and
            current.get("corner2") is None and
            current.get("corner2_path") is None
        )

        def find_index(cb: QComboBox, saved_index, saved_path):
            if saved_index is None and saved_path is None:
                return 0
            for i in range(cb.count()):
                data = cb.itemData(i)
                if not isinstance(data, dict):
                    continue
                if saved_path and data.get("path") == saved_path:
                    return i
                if saved_index is not None and data.get("index") == saved_index:
                    return i
            return 0

        if first_run:
            self.main_cb.setCurrentIndex(0)
            self.t1_cb.setCurrentIndex(0)
            self.t2_cb.setCurrentIndex(0)
        else:
            self.main_cb.setCurrentIndex(find_index(
                self.main_cb, current.get("main"), current.get("main_path")
            ))
            self.t1_cb.setCurrentIndex(find_index(
                self.t1_cb, current.get("corner1"), current.get("corner1_path")
            ))
            self.t2_cb.setCurrentIndex(find_index(
                self.t2_cb, current.get("corner2"), current.get("corner2_path")
            ))

        for i in range(self.res_cb.count()):
            if self.res_cb.itemData(i) == tuple(current.get("resolution", (640, 480))):
                self.res_cb.setCurrentIndex(i)
                break

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.ok)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)
        self.selected = None

    def ok(self):
        m = self.main_cb.currentData()
        t1 = self.t1_cb.currentData()
        t2 = self.t2_cb.currentData()
        r = self.res_cb.currentData()
        self.selected = {
            "main": (m["index"] if isinstance(m, dict) and isinstance(m.get("index"), int) and m["index"] >= 0 else None),
            "main_path": (m["path"] if isinstance(m, dict) else None),
            "corner1": (t1["index"] if isinstance(t1, dict) and isinstance(t1.get("index"), int) and t1["index"] >= 0 else None),
            "corner1_path": (t1["path"] if isinstance(t1, dict) else None),
            "corner2": (t2["index"] if isinstance(t2, dict) and isinstance(t2.get("index"), int) and t2["index"] >= 0 else None),
            "corner2_path": (t2["path"] if isinstance(t2, dict) else None),
            "resolution": r,
        }
        self.accept()


class CameraApp(QWidget):
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
        self.main_detach_btn = QPushButton("Make Separate Window", self.video_label)
        self.main_detach_btn.setMinimumHeight(30)
        self.main_detach_btn.setMinimumWidth(200)
        self.main_detach_btn.setStyleSheet("QPushButton{background:#1e88e5;color:#fff;border:none;border-radius:3px;} QPushButton:pressed{background:#166bb0;}")
        self.main_detach_btn.clicked.connect(self.detach_main_fullscreen)
        self.main_detach_btn.hide()

        self.corner1 = CameraThumbnail("Corner Cam 1")
        self.corner2 = CameraThumbnail("Corner Cam 2")
        self.capture_btn = QPushButton("📸 Capture")
        self.capture_btn.clicked.connect(self.capture_dialog)
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh_cameras)
        self.record_btn = QPushButton("Record Main")
        self.record_btn.setCheckable(True)
        self.record_btn.clicked.connect(self.toggle_recording)
        self.record_c1_btn = QPushButton("Record Corner 1")
        self.record_c1_btn.setCheckable(True)
        self.record_c1_btn.clicked.connect(lambda: self.toggle_corner_recording(1))
        self.record_c2_btn = QPushButton("Record Corner 2")
        self.record_c2_btn.setCheckable(True)
        self.record_c2_btn.clicked.connect(lambda: self.toggle_corner_recording(2))
        self.switch_main_btn = QPushButton("Switch Main")
        self.switch_c1_btn = QPushButton("Switch Corner 1")
        self.switch_c2_btn = QPushButton("Switch Corner 2")
        self.motion_btn = QPushButton("Motion Detect")
        self.motion_btn.setCheckable(True)
        self.motion_btn.clicked.connect(self.toggle_motion)
        self.motion_enabled = False
        self._update_motion_button_style()
        self.fs_combo = QComboBox()
        self.fs_btn = QPushButton("View Selected Camera")
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
            combo.setView(self._styled_list_view())
        self.main_sel.currentIndexChanged.connect(lambda _: self._select_slot("main", self.main_sel))
        self.c1_sel.currentIndexChanged.connect(lambda _: self._select_slot("corner1", self.c1_sel))
        self.c2_sel.currentIndexChanged.connect(lambda _: self._select_slot("corner2", self.c2_sel))
        self._selectors_updating = False
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setParent(self.video_label)
        self.settings_btn.setFixedSize(44, 44)
        self.settings_btn.setStyleSheet("QPushButton{background:#1e3a8a;color:#fff;font-size:20px;border:none;border-radius:22px;} QPushButton:pressed{background:#2563eb;}")
        self.settings_btn.clicked.connect(self.toggle_controls_panel)
        self.close_btn = QPushButton("✕")
        self.close_btn.setParent(self.video_label)
        self.close_btn.setFixedSize(44, 44)
        self.close_btn.setStyleSheet("QPushButton{background:#b91c1c;color:#fff;font-size:20px;border:none;border-radius:22px;} QPushButton:pressed{background:#dc2626;}")
        self.close_btn.clicked.connect(self.close)
        self.controls_panel = None
        self._panel_was_visible = False
        self.pending_settings = dict(self.settings)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.corner1.clicked.connect(self.open_fullscreen)
        self.corner2.clicked.connect(self.open_fullscreen)
        self.corner1.detach_requested.connect(self.open_fullscreen)
        self.corner2.detach_requested.connect(self.open_fullscreen)
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
            margin = 14
            self.main_detach_btn.adjustSize()
            self.main_overlay.adjustSize()
            self.motion_indicator.adjustSize()
            self.main_detach_btn.move(self.video_label.width() - self.main_detach_btn.width() - margin, margin)
            self.settings_btn.move(margin, margin)
            self.close_btn.move(margin, margin + self.settings_btn.height() + 8)
            overlay_y = max(margin, self.video_label.height() - self.main_overlay.height() - margin)
            self.main_overlay.move(margin, overlay_y)
            motion_y = max(margin, overlay_y - self.motion_indicator.height() - 8)
            self.motion_indicator.move(margin, motion_y)
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

    def toggle_corner_recording(self, idx: int):
        if self.corner_recording.get(idx):
            self.stop_corner_recording(idx)
        else:
            self.start_corner_recording(idx)

    def start_recording(self):
        if not self.current_cam:
            QMessageBox.information(self, "No Camera", "Select a main camera first.")
            self.record_btn.setChecked(False)
            return
        self.recording = True
        self.record_writer = None
        self.prev_gray = None
        Path("captures").mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.record_file = Path("captures") / f"record_{stamp}.mp4"
        self.record_btn.setText("Stop Main")

    def stop_recording(self):
        self.recording = False
        self.record_btn.setChecked(False)
        self.record_btn.setText("Record Main")
        if self.record_writer:
            try:
                self.record_writer.release()
            except Exception:
                pass
        self.record_writer = None
        self.record_file = None

    def start_corner_recording(self, idx: int):
        thumb = self.corner1 if idx == 1 else self.corner2
        btn = self.record_c1_btn if idx == 1 else self.record_c2_btn
        if not thumb.cam or not thumb.cap or not thumb.cap.isOpened():
            QMessageBox.information(self, "No Camera", f"Select corner camera {idx} first.")
            btn.setChecked(False)
            return
        Path("captures").mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.corner_record_files[idx] = Path("captures") / f"record_corner{idx}_{stamp}.mp4"
        fps = thumb.cap.get(cv2.CAP_PROP_FPS) or 20.0
        self.corner_record_fps[idx] = fps if fps and fps >= 1 else 20.0
        self.corner_recording[idx] = True
        btn.setText(f"Stop Corner {idx}")

    def stop_corner_recording(self, idx: int):
        self.corner_recording[idx] = False
        btn = self.record_c1_btn if idx == 1 else self.record_c2_btn
        btn.setChecked(False)
        btn.setText(f"Record Corner {idx}")
        writer = self.corner_record_writers.get(idx)
        if writer:
            try:
                writer.release()
            except Exception:
                pass
        self.corner_record_writers[idx] = None
        self.corner_record_files[idx] = None
    def open_camera_config(self):
        self._hide_controls_panel_for_dialog()
        with self._paused_streams():
            self.capture_mgr.release_all()
            self.cams = scan_cameras()
            cur = {"main": self.settings.get("main"), "main_path": self.settings.get("main_path"),
                   "corner1": self.settings.get("corner1"), "corner1_path": self.settings.get("corner1_path"),
                   "corner2": self.settings.get("corner2"), "corner2_path": self.settings.get("corner2_path"),
                   "resolution": tuple(self.settings.get("resolution", (640, 480)))}
            dlg = CameraConfigDialog(self, self.cams, cur)
            dlg.exec()
            sel = getattr(dlg, "selected", None)
            if sel:
                for k in ("main", "main_path", "corner1", "corner1_path", "corner2", "corner2_path", "resolution"):
                    self.settings[k] = sel.get(k, self.settings.get(k))
                self.apply_settings()
                save_settings(self.settings)
        self._restore_controls_panel_after_dialog()

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

    def open_resolution(self):
        self._hide_controls_panel_for_dialog()
        res = [(640, 480), (1280, 720), (1920, 1080)]
        dlg = QDialog(self)
        v = QVBoxLayout(dlg)
        lw = QListWidget()
        for r in res:
            it = QListWidgetItem(f"{r[0]} x {r[1]}")
            it.setData(Qt.ItemDataRole.UserRole, r)
            lw.addItem(it)
        v.addWidget(lw)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            it = lw.currentItem()
            if it:
                self.settings["resolution"] = it.data(Qt.ItemDataRole.UserRole)
                if self.current_cam:
                    cap = self.capture_mgr.get(self.current_cam["index"] if isinstance(self.current_cam.get("index"), int) and self.current_cam.get("index") >= 0 else self.current_cam.get("path"))
                    if cap:
                        try:
                            w, h = tuple(self.settings["resolution"])
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                        except Exception:
                            pass
                save_settings(self.settings)
        self._restore_controls_panel_after_dialog()

    def capture_dialog(self):
        cams = self.cams or scan_cameras()
        dlg = QDialog(self)
        dlg.setWindowTitle("Capture")
        v = QVBoxLayout(dlg)
        scroll = QScrollArea()
        w = QWidget()
        vv = QVBoxLayout(w)
        checks = []
        for c in cams:
            cb = QCheckBox(c["display"])
            cb.setProperty("cam", c)
            vv.addWidget(cb)
            checks.append(cb)
        vv.addStretch(1)
        w.setLayout(vv)
        scroll.setWidget(w)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(140)
        v.addWidget(scroll)
        row = QHBoxLayout()
        pe = QLineEdit("captures")
        br = QPushButton("Browse")
        br.clicked.connect(lambda: pe.setText(QFileDialog.getExistingDirectory(self, "Select", os.path.expanduser("~")) or pe.text()))
        row.addWidget(pe)
        row.addWidget(br)
        v.addLayout(row)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            folder = pe.text() or "captures"
            os.makedirs(folder, exist_ok=True)
            for cb in checks:
                if cb.isChecked():
                    cam = cb.property("cam")
                    cap = self.capture_mgr.get(cam["index"] if isinstance(cam.get("index"), int) and cam.get("index") >= 0 else cam.get("path"))
                    if not cap:
                        continue
                    try:
                        ret, frame = cap.read()
                    except Exception:
                        ret = False
                        frame = None
                    if not ret or frame is None:
                        continue
                    path = os.path.join(folder, f"capture_{cam['index'] if cam.get('index') is not None else 'unk'}_{cv2.getTickCount()}.jpg")
                    try:
                        cv2.imwrite(path, frame)
                    except Exception:
                        pass
            QMessageBox.information(self, "Saved", f"Saved captures to:\n{folder}")

    def detach_main_fullscreen(self):
        if not self.current_cam:
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
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
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

        fs.keyPressEvent = keyPressEvent
        fs.closeEvent = lambda ev: (cleanup(), QWidget.closeEvent(fs, ev))
        fs.destroyed.connect(lambda *_: cleanup())

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

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
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

    def _record_corner_frame(self, idx: int, frame):
        if not self.corner_recording.get(idx):
            return
        path = self.corner_record_files.get(idx)
        if not path:
            return
        writer = self.corner_record_writers.get(idx)
        if writer is None:
            try:
                h, w = frame.shape[:2]
                fps = self.corner_record_fps.get(idx, 20.0) or 20.0
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
                if not writer or not writer.isOpened():
                    self.stop_corner_recording(idx)
                    return
                self.corner_record_writers[idx] = writer
            except Exception:
                self.stop_corner_recording(idx)
                return
        try:
            writer.write(frame)
        except Exception:
            self.stop_corner_recording(idx)

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

    def _populate_fs_combo(self):
        self.fs_combo.clear()
        for c in self.cams:
            self.fs_combo.addItem(c["display"], c)

    def open_fullscreen_from_combo(self):
        cam = self.fs_combo.currentData()
        if not cam:
            return
        idx = cam.get("index")
        name = cam.get("name", cam.get("display", "Camera"))
        self.open_fullscreen(idx, name)

    def _cam_key(self, cam):
        if not cam:
            return None
        if cam.get("path") is not None:
            return f"path:{cam['path']}"
        return f"idx:{cam.get('index')}"

    def _populate_selectors(self, main, c1, c2):
        self._selectors_updating = True
        try:
            populate_combo(self.main_sel, self.cams, include_none=True)
            populate_combo(self.c1_sel, self.cams, include_none=True)
            populate_combo(self.c2_sel, self.cams, include_none=True)
            for i in range(self.res_sel.count()):
                if self.res_sel.itemData(i) == tuple(self.settings.get("resolution", (640, 480))):
                    self.res_sel.setCurrentIndex(i)
                    break

            def set_sel(cb: QComboBox, target):
                key = self._cam_key(target)
                for i in range(cb.count()):
                    data = cb.itemData(i)
                    if self._cam_key(data) == key:
                        cb.setCurrentIndex(i)
                        return
                cb.setCurrentIndex(0)

            set_sel(self.main_sel, main)
            set_sel(self.c1_sel, c1)
            set_sel(self.c2_sel, c2)
        finally:
            self._selectors_updating = False

    def _select_slot(self, slot: str, cb: QComboBox):
        if self._selectors_updating:
            return
        cam = cb.currentData()
        other_slots = {
            "main": ["corner1", "corner2"],
            "corner1": ["main", "corner2"],
            "corner2": ["main", "corner1"],
        }[slot]
        for other in other_slots:
            other_cam = self.pending_settings.get(other)
            other_path = self.pending_settings.get(f"{other}_path")
            if cam and ((cam.get("path") and cam.get("path") == other_path) or (cam.get("index") is not None and cam.get("index") == other_cam)):
                QMessageBox.warning(self, "In Use", "That camera is already assigned elsewhere.")
                self._populate_selectors(
                    {"index": self.pending_settings.get("main"), "path": self.pending_settings.get("main_path")},
                    {"index": self.pending_settings.get("corner1"), "path": self.pending_settings.get("corner1_path")},
                    {"index": self.pending_settings.get("corner2"), "path": self.pending_settings.get("corner2_path")},
                )
                return

        if cam is None:
            self.pending_settings[slot] = None
            self.pending_settings[f"{slot}_path"] = None
        else:
            self.pending_settings[slot] = cam.get("index") if isinstance(cam.get("index"), int) and cam.get("index") >= 0 else None
            self.pending_settings[f"{slot}_path"] = cam.get("path")

    def _apply_resolution_from_panel(self):
        res = self.res_sel.currentData()
        if res:
            self.settings["resolution"] = res
            save_settings(self.settings)
            self.apply_settings()

    def _apply_all_pending(self):
        for slot in ("main", "corner1", "corner2"):
            self.settings[slot] = self.pending_settings.get(slot)
            self.settings[f"{slot}_path"] = self.pending_settings.get(f"{slot}_path")
        res = self.res_sel.currentData()
        if res:
            self.settings["resolution"] = res
        save_settings(self.settings)
        self.apply_settings()

    def _apply_slot(self, slot: str):
        for key in (slot, f"{slot}_path"):
            self.settings[key] = self.pending_settings.get(key)
        save_settings(self.settings)
        self.apply_settings()

    def _reset_pending_to_live(self):
        self.pending_settings = dict(self.settings)

    def _update_motion_button_style(self):
        if self.motion_enabled:
            self.motion_btn.setStyleSheet("background:#16a34a; color:#fff; padding:10px 14px; border:none; border-radius:8px; font-weight:600;")
        else:
            self.motion_btn.setStyleSheet("background:#b91c1c; color:#fff; padding:10px 14px; border:none; border-radius:8px; font-weight:600;")

    def _styled_list_view(self):
        lv = QListView()
        lv.setStyleSheet(
            "QListView{background:#1e3a8a; color:#fff; border:none; padding:0; margin:0;}"
            "QListView::item{padding:8px 10px; margin:0; background:#1e3a8a;}"
            "QListView::item:selected{background:#000; color:#fff;}"
            "QListView::item:hover{background:#0b1220; color:#fff;}"
        )
        return lv

    def _hide_controls_panel_for_dialog(self):
        self._panel_was_visible = self.controls_panel and self.controls_panel.isVisible()
        if self.controls_panel:
            self.controls_panel.hide()

    def _restore_controls_panel_after_dialog(self):
        if self._panel_was_visible and self.controls_panel:
            self.controls_panel.show()

    def _ensure_controls_panel(self):
        if self.controls_panel:
            return
        panel = QWidget(self, Qt.WindowType.Tool)
        panel.setWindowTitle("Controls")
        panel.setWindowFlags(panel.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        panel.setStyleSheet("""
            QWidget#controlPanel {background:#0b1220; color:#e6eef8; border:1px solid #1f2937; border-radius:12px;}
            QLabel {font-size:13px; color:#e6eef8; background:transparent;}
            QPushButton {background:#1e3a8a; color:#fff; padding:10px 14px; border:none; border-radius:8px; font-weight:600;}
            QPushButton:checked {background:#2563eb;}
            QComboBox {background:#1e3a8a; color:#fff; padding:8px 10px; border:1px solid #1f2937; border-radius:8px;}
            QComboBox::drop-down {border: none;}
            QComboBox QAbstractItemView {background:#1e3a8a; color:#fff; selection-background-color:#000; selection-color:#fff; border:none; outline:0; padding:0; margin:0;}
            QComboBox QAbstractItemView::item {padding:8px 10px; margin:0; background:#1e3a8a;}
            QComboBox QAbstractItemView::item:selected {background:#000; color:#fff;}
            QComboBox QAbstractItemView::item:hover {background:#0b1220; color:#fff;}
        """)
        panel.setObjectName("controlPanel")
        panel.setMinimumWidth(520)

        title = QLabel("Control Center", panel)
        title.setStyleSheet("font-size:18px; font-weight:700;")
        subtitle = QLabel("Tap to switch cameras, record, or open fullscreen views.", panel)
        subtitle.setStyleSheet("color:#9ca3af;")


        for b in (self.capture_btn, self.record_btn, self.record_c1_btn, self.record_c2_btn, self.motion_btn, self.refresh_btn, self.fs_btn):
            b.setParent(panel)
            b.setMinimumHeight(44)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for b in (self.switch_main_btn, self.switch_c1_btn, self.switch_c2_btn, self.res_apply):
            b.setParent(panel)
            b.setMinimumHeight(44)
            b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        for cb in (self.main_sel, self.c1_sel, self.c2_sel, self.fs_combo, self.res_sel):
            cb.setParent(panel)
            cb.setMinimumHeight(38)

        row_actions = QHBoxLayout()
        row_actions.setSpacing(10)
        row_actions.addWidget(self.capture_btn)
        row_actions.addWidget(self.refresh_btn)

        row_main = QHBoxLayout()
        row_main.setSpacing(10)
        row_main.addWidget(QLabel("Main View", panel))
        row_main.addWidget(self.main_sel)
        row_main.addWidget(self.switch_main_btn)
        row_main.addWidget(self.record_btn)

        row_c1 = QHBoxLayout()
        row_c1.setSpacing(10)
        row_c1.addWidget(QLabel("Corner 1", panel))
        row_c1.addWidget(self.c1_sel)
        row_c1.addWidget(self.switch_c1_btn)
        row_c1.addWidget(self.record_c1_btn)

        row_c2 = QHBoxLayout()
        row_c2.setSpacing(10)
        row_c2.addWidget(QLabel("Corner 2", panel))
        row_c2.addWidget(self.c2_sel)
        row_c2.addWidget(self.switch_c2_btn)
        row_c2.addWidget(self.record_c2_btn)

        row_misc = QHBoxLayout()
        row_misc.setSpacing(10)
        row_misc.addWidget(self.motion_btn)
        row_misc.addWidget(QLabel("Resolution", panel))
        row_misc.addWidget(self.res_sel)
        row_misc.addWidget(self.res_apply)
        row_misc.addWidget(self.fs_combo)
        row_misc.addWidget(self.fs_btn)

        wrap = QVBoxLayout(panel)
        wrap.setContentsMargins(16, 16, 16, 16)
        wrap.setSpacing(12)
        wrap.addWidget(title)
        wrap.addWidget(subtitle)
        wrap.addWidget(QLabel("Cameras", panel))
        wrap.addLayout(row_actions)
        wrap.addSpacing(6)
        wrap.addLayout(row_main)
        wrap.addLayout(row_c1)
        wrap.addLayout(row_c2)
        wrap.addWidget(QLabel("Resolution & Fullscreen", panel))
        wrap.addLayout(row_misc)
        btn_row = QHBoxLayout()
        close_btn = QPushButton("Close", panel)
        save_close_btn = QPushButton("Save & Close", panel)
        close_btn.setMinimumHeight(40)
        save_close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(lambda: (self._reset_pending_to_live(), panel.hide()))
        save_close_btn.clicked.connect(lambda: (self._apply_all_pending(), panel.hide()))
        btn_row.addWidget(close_btn)
        btn_row.addWidget(save_close_btn)
        wrap.addLayout(btn_row)
        panel.setLayout(wrap)
        panel.adjustSize()
        self.controls_panel = panel
        self.res_apply.clicked.connect(self._apply_resolution_from_panel)
        self.switch_main_btn.clicked.connect(lambda: self._apply_slot("main"))
        self.switch_c1_btn.clicked.connect(lambda: self._apply_slot("corner1"))
        self.switch_c2_btn.clicked.connect(lambda: self._apply_slot("corner2"))

    def toggle_controls_panel(self):
        self._ensure_controls_panel()
        if self.controls_panel.isVisible():
            self.controls_panel.hide()
            return
        self.pending_settings = dict(self.settings)
        self._populate_selectors(
            {"index": self.settings.get("main"), "path": self.settings.get("main_path")},
            {"index": self.settings.get("corner1"), "path": self.settings.get("corner1_path")},
            {"index": self.settings.get("corner2"), "path": self.settings.get("corner2_path")},
        )
        pos = self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height() + 10))
        self.controls_panel.move(pos)
        self.controls_panel.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = CameraApp()
    w.showFullScreen()
    sys.exit(app.exec())
