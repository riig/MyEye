#!/usr/bin/env python3
import contextlib
import glob
import os
import re
import sys
from typing import Any, Dict, List, Optional, Union

import cv2

from settings_store import CAP_BACKEND


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

    linux_cams = scan_linux() if sys.platform.startswith("linux") else []
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
