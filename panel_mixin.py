#!/usr/bin/env python3
from typing import Any, Dict

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QMessageBox, QComboBox

from control_panel import build_control_panel
from dialogs import populate_combo


class PanelMixin:
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
                self._show_in_use_warning()
                self._selectors_updating = True
                try:
                    key = self._cam_key({"index": self.pending_settings.get(slot), "path": self.pending_settings.get(f"{slot}_path")})
                    for i in range(cb.count()):
                        data = cb.itemData(i)
                        if self._cam_key(data) == key:
                            cb.setCurrentIndex(i)
                            break
                    else:
                        cb.setCurrentIndex(0)
                finally:
                    self._selectors_updating = False
                return

        if cam is None:
            self.pending_settings[slot] = None
            self.pending_settings[f"{slot}_path"] = None
        else:
            self.pending_settings[slot] = cam.get("index") if isinstance(cam.get("index"), int) and cam.get("index") >= 0 else None
            self.pending_settings[f"{slot}_path"] = cam.get("path")

        self.settings[slot] = self.pending_settings.get(slot)
        self.settings[f"{slot}_path"] = self.pending_settings.get(f"{slot}_path")
        self.save_and_apply()

    def save_and_apply(self):
        from settings_store import save_settings
        save_settings(self.settings)
        self.apply_settings()

    def _apply_resolution_from_panel(self):
        res = self.res_sel.currentData()
        if res:
            self.settings["resolution"] = res
            self.save_and_apply()

    def _apply_all_pending(self):
        for slot in ("main", "corner1", "corner2"):
            self.settings[slot] = self.pending_settings.get(slot)
            self.settings[f"{slot}_path"] = self.pending_settings.get(f"{slot}_path")
        res = self.res_sel.currentData()
        if res:
            self.settings["resolution"] = res
        self.save_and_apply()

    def _reset_pending_to_live(self):
        self.pending_settings = dict(self.settings)

    def _update_motion_button_style(self):
        if self.motion_enabled:
            self.motion_btn.setStyleSheet("background:#16a34a; color:#fff; padding:10px 14px; border:none; border-radius:8px; font-weight:600;")
        else:
            self.motion_btn.setStyleSheet("background:#b91c1c; color:#fff; padding:10px 14px; border:none; border-radius:8px; font-weight:600;")

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
        self.controls_panel = build_control_panel(self)

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
        self.controls_panel.showFullScreen()

    def _show_in_use_warning(self):
        parent = self.controls_panel if self.controls_panel else self
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("In Use")
        msg.setText("This camera is chosen for another window already.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setWindowModality(Qt.WindowModality.NonModal)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        msg.show()
        QTimer.singleShot(2000, msg.close)
