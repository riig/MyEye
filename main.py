#!/usr/bin/env python3
import sys

from PyQt6.QtWidgets import QApplication

from main_window import CameraApp


def main():
    qt_app = QApplication(sys.argv)
    window = CameraApp()
    window.showFullScreen()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
