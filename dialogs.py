#!/usr/bin/env python3
from typing import Any

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


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
