#!/usr/bin/env python3
import json
import platform
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2

DEFAULT_SETTINGS: Dict[str, Any] = {
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


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        payload = {k: settings.get(k) for k in DEFAULT_SETTINGS}
        if payload.get("resolution"):
            payload["resolution"] = list(payload["resolution"])
        SETTINGS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass
