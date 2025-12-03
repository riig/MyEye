#!/usr/bin/env python3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
from PyQt6.QtWidgets import QMessageBox


class CaptureActionsMixin:
    def _capture_from_cam(self, cam, label="capture"):
        if not cam:
            QMessageBox.information(self, "No Camera", "Select a camera first.")
            return
        cap = self.capture_mgr.get(cam["index"] if isinstance(cam.get("index"), int) and cam.get("index") >= 0 else cam.get("path"))
        if not cap or not cap.isOpened():
            QMessageBox.warning(self, "Unavailable", "Camera not available.")
            return
        try:
            ret, frame = cap.read()
        except Exception:
            ret = False
            frame = None
        if not ret or frame is None:
            QMessageBox.warning(self, "Unavailable", "Camera not available.")
            return
        Path("captures").mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path("captures") / f"{label}_{stamp}.jpg"
        try:
            cv2.imwrite(str(path), frame)
            QMessageBox.information(self, "Saved", f"Saved to:\n{path}")
        except Exception:
            QMessageBox.warning(self, "Error", "Could not save image.")

    def _capture_main(self):
        if not self.current_cam:
            QMessageBox.information(self, "No Camera", "Select a main camera first.")
            return
        self._capture_from_cam(self.current_cam, "main")

    def _capture_corner(self, idx: int):
        thumb = self.corner1 if idx == 1 else self.corner2
        if not thumb.cam:
            QMessageBox.information(self, "No Camera", f"Select corner camera {idx} first.")
            return
        self._capture_from_cam(thumb.cam, f"corner{idx}")

    def toggle_corner_recording(self, idx: int):
        if self.corner_recording.get(idx):
            self.stop_corner_recording(idx)
        else:
            self.start_corner_recording(idx)

    def start_recording(self):
        if not self.current_cam:
            QMessageBox.information(self, "No Camera", "Select a main camera first.")
            self.main_record_btn.setChecked(False)
            return
        self.recording = True
        self.record_writer = None
        self.prev_gray = None
        Path("captures").mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.record_file = Path("captures") / f"record_{stamp}.mp4"
        self.main_record_btn.setText("Stop Recording")

    def stop_recording(self):
        self.recording = False
        self.main_record_btn.setChecked(False)
        self.main_record_btn.setText("Start Recording")
        if self.record_writer:
            try:
                self.record_writer.release()
            except Exception:
                pass
        self.record_writer = None
        self.record_file = None

    def start_corner_recording(self, idx: int):
        thumb = self.corner1 if idx == 1 else self.corner2
        if not thumb.cam or not thumb.cap or not thumb.cap.isOpened():
            QMessageBox.information(self, "No Camera", f"Select corner camera {idx} first.")
            thumb.set_recording_active(False)
            return
        Path("captures").mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.corner_record_files[idx] = Path("captures") / f"record_corner{idx}_{stamp}.mp4"
        fps = thumb.cap.get(cv2.CAP_PROP_FPS) or 20.0
        self.corner_record_fps[idx] = fps if fps and fps >= 1 else 20.0
        self.corner_recording[idx] = True
        thumb.set_recording_active(True)

    def stop_corner_recording(self, idx: int):
        self.corner_recording[idx] = False
        thumb = self.corner1 if idx == 1 else self.corner2
        thumb.set_recording_active(False)
        writer = self.corner_record_writers.get(idx)
        if writer:
            try:
                writer.release()
            except Exception:
                pass
        self.corner_record_writers[idx] = None
        self.corner_record_files[idx] = None

    def _toggle_corner_from_thumb(self, idx: int, state: bool):
        if state:
            self.start_corner_recording(idx)
        else:
            self.stop_corner_recording(idx)

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
