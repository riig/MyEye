#!/usr/bin/env python3
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QListView,
    QSizePolicy,
)


def styled_list_view() -> QListView:
    lv = QListView()
    lv.setStyleSheet(
        "QListView{background:#0b1220; color:#e6eef8; border:1px solid #1f2937; padding:0; margin:0;}"
        "QListView::item{padding:10px 12px; margin:0; background:#0b1220; border:0;}"
        "QListView::item:selected{background:#1e3a8a; color:#fff; border:0;}"
        "QListView::item:hover{background:#111827; color:#fff;}"
    )
    return lv


def build_control_panel(app: Any) -> QWidget:
    panel = QWidget(app, Qt.WindowType.Tool)
    panel.setWindowTitle("MyEye - Control Panel")
    panel.setWindowFlags(panel.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
    panel.setStyleSheet("""
        QWidget#controlPanel {background:#0b1220; color:#e6eef8; border:1px solid #1f2937; border-radius:12px;}
        QLabel {font-size:13px; color:#e6eef8; background:transparent;}
        QPushButton {background:#1e3a8a; color:#fff; padding:10px 14px; border:none; border-radius:8px; font-weight:600;}
        QPushButton:checked {background:#2563eb;}
        QComboBox {background:#0b1220; color:#e6eef8; padding:8px 10px; border:1px solid #1f2937; border-radius:8px;}
        QComboBox::drop-down {border: none;}
        QComboBox QAbstractItemView {background:#0b1220; color:#e6eef8; selection-background-color:#1e3a8a; selection-color:#fff; border:1px solid #1f2937; outline:0; padding:0; margin:0;}
        QComboBox QAbstractItemView::item {padding:10px 12px; margin:0; background:#0b1220; border:0;}
        QComboBox QAbstractItemView::item:selected {background:#1e3a8a; color:#fff; border:0;}
        QComboBox QAbstractItemView::item:hover {background:#111827; color:#fff;}
    """)
    panel.setObjectName("controlPanel")
    panel.setMinimumWidth(520)

    title_bar = QFrame(panel)
    title_bar.setStyleSheet("background:#0b1220; border-bottom:1px solid #1f2937;")
    title_bar_layout = QHBoxLayout(title_bar)
    title_bar_layout.setContentsMargins(0, 0, 0, 0)
    title_label = QLabel("MyEye - Control Panel", title_bar)
    title_label.setStyleSheet("font-size:20px; font-weight:700; padding:12px 6px;")
    title_bar_layout.addWidget(title_label)

    for b in (app.motion_btn, app.refresh_btn, app.fs_btn):
        b.setParent(panel)
        b.setMinimumHeight(44)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    for cb in (app.main_sel, app.c1_sel, app.c2_sel, app.fs_combo, app.res_sel):
        cb.setParent(panel)
        cb.setMinimumHeight(38)

    row_actions = QHBoxLayout()
    row_actions.setSpacing(10)
    row_actions.addWidget(app.refresh_btn)

    row_main = QHBoxLayout()
    row_main.setSpacing(10)
    row_main.addWidget(QLabel("Main View", panel))
    row_main.addWidget(app.main_sel)

    row_c1 = QHBoxLayout()
    row_c1.setSpacing(10)
    row_c1.addWidget(QLabel("Corner 1", panel))
    row_c1.addWidget(app.c1_sel)

    row_c2 = QHBoxLayout()
    row_c2.setSpacing(10)
    row_c2.addWidget(QLabel("Corner 2", panel))
    row_c2.addWidget(app.c2_sel)

    row_misc = QHBoxLayout()
    row_misc.setSpacing(10)
    row_misc.addWidget(app.motion_btn)
    row_misc.addWidget(QLabel("Resolution", panel))
    row_misc.addWidget(app.res_sel)
    row_misc.addWidget(app.res_apply)
    row_misc.addWidget(app.fs_combo)
    row_misc.addWidget(app.fs_btn)

    wrap = QVBoxLayout(panel)
    wrap.setContentsMargins(16, 10, 16, 16)
    wrap.setSpacing(10)
    wrap.addWidget(title_bar)
    wrap.addLayout(row_actions)
    wrap.addLayout(row_main)
    wrap.addLayout(row_c1)
    wrap.addLayout(row_c2)
    wrap.addLayout(row_misc)
    wrap.addStretch(1)
    btn_row = QHBoxLayout()
    save_close_btn = QPushButton("Save and Close", panel)
    save_close_btn.setMinimumHeight(40)
    save_close_btn.clicked.connect(lambda: (app._apply_all_pending(), panel.hide()))
    btn_row.addStretch(1)
    btn_row.addWidget(save_close_btn)
    btn_row.addStretch(1)
    wrap.addLayout(btn_row)
    panel.setLayout(wrap)
    panel.adjustSize()
    app.res_apply.clicked.connect(app._apply_resolution_from_panel)
    return panel
