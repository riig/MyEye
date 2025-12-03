#!/usr/bin/env python3
import os
from typing import Optional, Union

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QCheckBox,
    QLineEdit,
    QScrollArea,
    QWidget,
)

import cv2
from capture_manager import scan_cameras
from dialogs import CameraConfigDialog
from settings_store import save_settings


class DialogsMixin:
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
        dlg.setStyleSheet(
            "QDialog{background:#0b1220; color:#e6eef8;}"
            "QLabel{color:#e6eef8;}"
            "QCheckBox{color:#e6eef8;}"
            "QLineEdit{background:#0f172a; color:#e6eef8; border:1px solid #1f2937; border-radius:6px; padding:6px;}"
            "QPushButton{background:#1e3a8a; color:#fff; padding:10px 14px; border:none; border-radius:8px; font-weight:600;}"
            "QPushButton:pressed{background:#2563eb;}"
            "QScrollArea{background:#0b1220; border:1px solid #1f2937; border-radius:8px;}"
            "QScrollArea QWidget{background:#0b1220;}"
            "QDialogButtonBox QPushButton{min-height:36px;}"
        )
        v = QVBoxLayout(dlg)
        scroll = QScrollArea()
        w = QWidget()
        w.setStyleSheet("background:#0b1220; color:#e6eef8;")
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
