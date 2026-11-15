#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VideoScreen 本地桌面原生 GUI 客户端 (PyQt5)

独立运行的本地桌面客户端，无需依赖浏览器或 Web 服务端口。
具备：素材扫描、SenseVoice 批量转写、AI 爆款大模型分析、一键精准剪辑成片、
发布管理、对标账号雷达与同款二创翻剪，以及实时多任务控制台。
"""

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 环境自适应：若当前 Python 环境（如 Conda base/video-screen）未安装 PyQt5，
# 自动寻找系统自带已装有 PyQt5 的 Python 解释器重新调起自身，保证开箱即用
try:
    import PyQt5
except ImportError:
    for cand in ["/usr/bin/python3", "/usr/bin/python"]:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            check_res = subprocess.run([cand, "-c", "import PyQt5"], capture_output=True)
            if check_res.returncode == 0:
                os.execv(cand, [cand] + sys.argv)
    raise

from PyQt5.QtCore import (
    QProcess,
    QProcessEnvironment,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QCursor, QFont, QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 导入底层业务服务模块
import ai_service
import benchmark_radar
import dashboard_server
import remix_service
import live_recorder_service

APP_DIR = Path(__file__).resolve().parent

# 确保 miniconda 路径在 PATH 中
CONDA_PATHS = "/home/ubuntu/miniconda3/bin:/home/ubuntu/miniconda3/condabin"
if CONDA_PATHS not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{CONDA_PATHS}:{os.environ.get('PATH', '')}"


def get_python():
    """获取专用的 Python 解释器路径"""
    dedicated = Path("/home/ubuntu/miniconda3/envs/video-screen/bin/python")
    if dedicated.is_file() and os.access(dedicated, os.X_OK):
        return str(dedicated)
    return sys.executable


# ==============================================================================
# macOS Sonoma/Ventura 专业风格 (Apple HIG 设计语言)
# ==============================================================================
LIGHT_STYLE = """
QMainWindow, QWidget {
    background-color: #f2f2f7;
    color: #1c1c1e;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    font-size: 13px;
}

QDialog {
    background-color: #f2f2f7;
    color: #1c1c1e;
}

QLabel {
    background-color: transparent;
}

/* ── Tab Widget (macOS Segmented Control) ─────────────────────────── */
QTabWidget::pane {
    border: none;
    background-color: transparent;
    padding-top: 8px;
}

QTabWidget::tab-bar {
    alignment: left;
    left: 2px;
}

QTabBar {
    background-color: rgba(118, 118, 128, 0.12);
    border-radius: 8px;
    padding: 3px;
}

QTabBar::tab {
    background-color: transparent;
    color: #636366;
    padding: 6px 16px;
    margin: 0 1px;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    font-size: 13px;
    min-width: 50px;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #1c1c1e;
    font-weight: 600;
    border: 0.5px solid rgba(0, 0, 0, 0.04);
}

QTabBar::tab:hover:!selected {
    color: #1c1c1e;
    background-color: rgba(255, 255, 255, 0.45);
}

/* ── Push Buttons (macOS HIG System Controls) ────────────────────── */
QPushButton {
    background-color: #ffffff;
    color: #1c1c1e;
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 7px;
    padding: 6px 14px;
    font-weight: 500;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #f5f5f7;
    border-color: rgba(0, 0, 0, 0.2);
}

QPushButton:pressed {
    background-color: #e5e5ea;
}

QPushButton:disabled {
    background-color: rgba(120, 120, 128, 0.08);
    color: #aeaeb2;
    border-color: rgba(0, 0, 0, 0.06);
}

QPushButton[class="hero"], QPushButton.hero,
QPushButton[class="primary"], QPushButton.primary {
    background-color: #007aff;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 7px 18px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton[class="hero"]:hover, QPushButton.hero:hover,
QPushButton[class="primary"]:hover, QPushButton.primary:hover {
    background-color: #0071ee;
}
QPushButton[class="hero"]:pressed, QPushButton.hero:pressed,
QPushButton[class="primary"]:pressed, QPushButton.primary:pressed {
    background-color: #0062cc;
}

QPushButton[class="success"], QPushButton.success {
    background-color: #34c759;
    color: #ffffff;
    border-radius: 7px;
    border: none;
    font-weight: 600;
}
QPushButton[class="success"]:hover, QPushButton.success:hover {
    background-color: #2eb350;
}

QPushButton[class="danger"], QPushButton.danger {
    background-color: rgba(255, 59, 48, 0.08);
    color: #ff3b30;
    border: 1px solid rgba(255, 59, 48, 0.22);
    border-radius: 7px;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton[class="danger"]:hover, QPushButton.danger:hover {
    background-color: rgba(255, 59, 48, 0.16);
    border-color: rgba(255, 59, 48, 0.35);
}
QPushButton[class="danger"]:pressed, QPushButton.danger:pressed {
    background-color: #ff3b30;
    color: #ffffff;
}

QPushButton[class="secondary"], QPushButton.secondary {
    background-color: #ffffff;
    color: #1c1c1e;
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 7px;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton[class="secondary"]:hover, QPushButton.secondary:hover {
    background-color: #f5f5f7;
    border-color: rgba(0, 0, 0, 0.2);
}

/* ── Menu ───────────────────────────────────────────────────────────── */
QMenu {
    background-color: rgba(255, 255, 255, 0.98);
    color: #1c1c1e;
    border: 1px solid rgba(60, 60, 67, 0.15);
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px 6px 12px;
    border-radius: 5px;
    font-size: 13px;
}
QMenu::item:selected {
    background-color: #007aff;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #aeaeb2;
}
QMenu::separator {
    height: 1px;
    background-color: rgba(60, 60, 67, 0.1);
    margin: 4px 6px;
}

/* ── Tooltip ────────────────────────────────────────────────────────── */
QToolTip {
    background-color: rgba(40, 40, 45, 0.95);
    color: #f2f2f7;
    border: none;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 12px;
}

/* ── Input controls ─────────────────────────────────────────────────── */
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid rgba(60, 60, 67, 0.18);
    border-radius: 6px;
    padding: 5px 10px;
    color: #1c1c1e;
    selection-background-color: #007aff;
    selection-color: #ffffff;
    font-size: 13px;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1.5px solid #007aff;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #1c1c1e;
    selection-background-color: #007aff;
    selection-color: #ffffff;
    border: 1px solid rgba(60, 60, 67, 0.15);
    border-radius: 6px;
    padding: 4px;
    outline: none;
}

/* ── Table (macOS Clean Grid) ───────────────────────────────────────── */
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #fafafc;
    border: 1px solid rgba(60, 60, 67, 0.1);
    border-radius: 8px;
    gridline-color: rgba(60, 60, 67, 0.06);
    color: #1c1c1e;
    selection-background-color: rgba(0, 122, 255, 0.08);
    selection-color: #1c1c1e;
    outline: none;
    font-size: 13px;
}

QHeaderView::section {
    background-color: #f6f6f8;
    color: #6e6e73;
    padding: 7px 10px;
    border: none;
    border-right: 1px solid rgba(60, 60, 67, 0.06);
    border-bottom: 1px solid rgba(60, 60, 67, 0.1);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
}

/* ── Scrollbars (macOS overlay style) ──────────────────────────────── */
QScrollBar:vertical {
    border: none;
    background-color: transparent;
    width: 7px;
    margin: 2px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background-color: rgba(60, 60, 67, 0.25);
    min-height: 20px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background-color: rgba(60, 60, 67, 0.4);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    border: none;
    background-color: transparent;
    height: 7px;
    margin: 2px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background-color: rgba(60, 60, 67, 0.25);
    min-width: 20px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover {
    background-color: rgba(60, 60, 67, 0.4);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── GroupBox (macOS Card Style) ────────────────────────────────────── */
QGroupBox {
    border: 1px solid rgba(60, 60, 67, 0.1);
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: 600;
    color: #1c1c1e;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #8e8e93;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    background-color: #ffffff;
}

/* ── Splitter ───────────────────────────────────────────────────────── */
QSplitter::handle {
    background-color: rgba(60, 60, 67, 0.08);
    width: 1px;
    height: 1px;
}
QSplitter::handle:hover {
    background-color: #007aff;
}

/* ── Progress Bar ───────────────────────────────────────────────────── */
QProgressBar {
    background-color: rgba(120, 120, 128, 0.12);
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #007aff;
    border-radius: 4px;
}

/* ── Status Bar ─────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #f2f2f7;
    color: #6e6e73;
    border-top: 1px solid rgba(60, 60, 67, 0.1);
    font-size: 11px;
}

/* ── CheckBox ───────────────────────────────────────────────────────── */
QCheckBox {
    spacing: 7px;
    color: #1c1c1e;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1.5px solid rgba(60, 60, 67, 0.3);
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background-color: #007aff;
    border-color: #007aff;
}
QCheckBox::indicator:hover {
    border-color: #007aff;
}
"""

DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1c1c1e;
    color: #f2f2f7;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    font-size: 13px;
}

QDialog {
    background-color: #1c1c1e;
    color: #f2f2f7;
}

QLabel {
    background-color: transparent;
}

QTabWidget::pane {
    border: none;
    background-color: transparent;
    padding-top: 8px;
}

QTabWidget::tab-bar {
    alignment: left;
    left: 2px;
}

QTabBar {
    background-color: rgba(120, 120, 128, 0.24);
    border-radius: 8px;
    padding: 3px;
}

QTabBar::tab {
    background-color: transparent;
    color: #8e8e93;
    padding: 6px 16px;
    margin: 0 1px;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    font-size: 13px;
    min-width: 50px;
}

QTabBar::tab:selected {
    background-color: rgba(255, 255, 255, 0.15);
    color: #f2f2f7;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background-color: rgba(255, 255, 255, 0.08);
    color: #d1d1d6;
}

QPushButton {
    background-color: rgba(255, 255, 255, 0.08);
    color: #f2f2f7;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 7px;
    padding: 6px 14px;
    font-weight: 500;
    font-size: 13px;
}

QPushButton:hover {
    background-color: rgba(255, 255, 255, 0.15);
    border-color: rgba(255, 255, 255, 0.22);
}

QPushButton:pressed {
    background-color: rgba(255, 255, 255, 0.25);
}

QPushButton:disabled {
    background-color: rgba(120, 120, 128, 0.12);
    color: #48484a;
    border-color: rgba(255, 255, 255, 0.04);
}

QPushButton[class="hero"], QPushButton.hero {
    background-color: #0a84ff;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 9px 22px;
    font-weight: 700;
    font-size: 14px;
}
QPushButton[class="hero"]:hover, QPushButton.hero:hover {
    background-color: #0071ee;
}

QPushButton[class="success"], QPushButton.success {
    background-color: #30d158;
    color: #ffffff;
    border-radius: 8px;
    border: none;
}
QPushButton[class="success"]:hover, QPushButton.success:hover {
    background-color: #28b34a;
}

QPushButton[class="danger"], QPushButton.danger {
    background-color: rgba(255, 69, 58, 0.15);
    color: #ff453a;
    border: 1px solid rgba(255, 69, 58, 0.3);
    border-radius: 8px;
    font-weight: 600;
}
QPushButton[class="danger"]:hover, QPushButton.danger:hover {
    background-color: rgba(255, 69, 58, 0.25);
    border-color: rgba(255, 69, 58, 0.5);
}
QPushButton[class="danger"]:pressed, QPushButton.danger:pressed {
    background-color: #ff453a;
    color: #ffffff;
}

QPushButton[class="secondary"], QPushButton.secondary {
    background-color: rgba(120, 120, 128, 0.18);
    color: #d1d1d6;
    border: none;
    border-radius: 8px;
    font-weight: 500;
}
QPushButton[class="secondary"]:hover, QPushButton.secondary:hover {
    background-color: rgba(120, 120, 128, 0.28);
}

QMenu {
    background-color: rgba(44, 44, 46, 0.98);
    color: #f2f2f7;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 5px;
}
QMenu::item {
    padding: 7px 24px 7px 14px;
    border-radius: 6px;
    font-size: 13px;
}
QMenu::item:selected {
    background-color: #0a84ff;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #48484a;
}
QMenu::separator {
    height: 1px;
    background-color: rgba(255, 255, 255, 0.08);
    margin: 4px 6px;
}

QToolTip {
    background-color: rgba(44, 44, 46, 0.95);
    color: #f2f2f7;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
}

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: rgba(60, 60, 67, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 7px 10px;
    color: #f2f2f7;
    selection-background-color: #0a84ff;
    selection-color: #ffffff;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1.5px solid #0a84ff;
}

QComboBox QAbstractItemView {
    background-color: rgba(44, 44, 46, 0.98);
    color: #f2f2f7;
    selection-background-color: #0a84ff;
    selection-color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 4px;
}

QTableWidget {
    background-color: rgba(44, 44, 46, 0.5);
    alternate-background-color: rgba(60, 60, 67, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    gridline-color: rgba(255, 255, 255, 0.05);
    color: #f2f2f7;
    selection-background-color: rgba(10, 132, 255, 0.2);
    selection-color: #f2f2f7;
    outline: none;
}

QHeaderView::section {
    background-color: rgba(28, 28, 30, 0.8);
    color: #8e8e93;
    padding: 8px 10px;
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 0.05);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 11px;
    font-weight: 700;
}

QScrollBar:vertical {
    border: none;
    background-color: transparent;
    width: 7px;
    margin: 2px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background-color: rgba(255, 255, 255, 0.2);
    min-height: 20px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background-color: rgba(255, 255, 255, 0.35);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    border: none;
    background-color: transparent;
    height: 7px;
    margin: 2px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background-color: rgba(255, 255, 255, 0.2);
    min-width: 20px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover {
    background-color: rgba(255, 255, 255, 0.35);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QGroupBox {
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    margin-top: 16px;
    padding-top: 16px;
    font-weight: 600;
    color: #d1d1d6;
    background-color: rgba(44, 44, 46, 0.5);
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #8e8e93;
    font-size: 11px;
    font-weight: 700;
}

QProgressBar {
    background-color: rgba(255, 255, 255, 0.1);
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #0a84ff;
    border-radius: 4px;
}

QStatusBar {
    background-color: #1c1c1e;
    color: #8e8e93;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 11px;
}

QSplitter::handle {
    background-color: rgba(255, 255, 255, 0.08);
    width: 1px;
    height: 1px;
}
QSplitter::handle:hover {
    background-color: #0a84ff;
}

QCheckBox {
    spacing: 7px;
    color: #f2f2f7;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1.5px solid rgba(255, 255, 255, 0.25);
    background: rgba(60, 60, 67, 0.4);
}
QCheckBox::indicator:checked {
    background-color: #0a84ff;
    border-color: #0a84ff;
}

QLabel#StatCardTitle {
    font-size: 11px;
    font-weight: 600;
    color: #8e8e93;
}
QLabel#StatCardValue {
    font-size: 26px;
    font-weight: 700;
    color: #f2f2f7;
    letter-spacing: -0.03em;
}
QLabel#StatCardSub {
    font-size: 11px;
    color: #636366;
}
"""


# ==============================================================================
# 自定义指标统计卡片组件 (macOS 现代极简微质感风格)
# ==============================================================================
class StatCard(QFrame):
    def __init__(self, title, value="0", subtitle="", color="#007aff", bg_tint="#eff6ff", icon="●", parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.color = color
        self.bg_tint = bg_tint
        self.icon = icon
        self.is_dark = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)

        # 顶部：精致状态圆点 + 浅灰色类别标题
        header = QHBoxLayout()
        header.setSpacing(6)
        header.setContentsMargins(0, 0, 0, 0)

        self.lbl_dot = QLabel("●")
        self.lbl_dot.setObjectName("StatCardDot")
        self.lbl_dot.setStyleSheet(f"color: {self.color}; font-size: 8px; background: transparent;")
        header.addWidget(self.lbl_dot)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("StatCardTitle")
        header.addWidget(self.lbl_title)
        header.addStretch()

        self.lbl_value = QLabel(str(value))
        self.lbl_value.setObjectName("StatCardValue")

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("StatCardSub")
        self.lbl_sub.setWordWrap(True)

        layout.addLayout(header)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_sub)
        layout.addStretch()

        self.apply_theme(False)

    def apply_theme(self, is_dark=False):
        self.is_dark = is_dark
        if is_dark:
            card_bg = "#252528"
            card_border = "rgba(255, 255, 255, 0.08)"
            card_hover = "rgba(255, 255, 255, 0.18)"
            title_color = "#98989d"
            val_color = "#f5f5f7"
            sub_color = "#76767a"
        else:
            card_bg = "#ffffff"
            card_border = "rgba(0, 0, 0, 0.08)"
            card_hover = "rgba(0, 0, 0, 0.18)"
            title_color = "#8e8e93"
            val_color = "#1c1c1e"
            sub_color = "#8e8e93"

        self.setStyleSheet(f"""
            QFrame#StatCard {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 10px;
            }}
            QFrame#StatCard:hover {{
                border-color: {card_hover};
            }}
            QFrame#StatCard QLabel {{
                border: none;
                background: transparent;
                padding: 0;
            }}
            QFrame#StatCard QLabel#StatCardDot {{
                color: {self.color};
                font-size: 8px;
            }}
            QFrame#StatCard QLabel#StatCardTitle {{
                color: {title_color};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.02em;
            }}
            QFrame#StatCard QLabel#StatCardValue {{
                color: {val_color};
                font-size: 26px;
                font-weight: 700;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Segoe UI", sans-serif;
                letter-spacing: -0.02em;
                margin-top: 2px;
                margin-bottom: 2px;
            }}
            QFrame#StatCard QLabel#StatCardSub {{
                color: {sub_color};
                font-size: 11px;
            }}
        """)

    def set_value(self, value, subtitle=None):
        self.lbl_value.setText(str(value))
        if subtitle is not None:
            self.lbl_sub.setText(subtitle)


# ==============================================================================
# 查看转写文本弹窗
# ==============================================================================
class TranscriptDialog(QDialog):
    def __init__(self, video_name, transcript_path, parent=None, is_dark=False):
        super().__init__(parent)
        self.setWindowTitle(f"语音转写文本查看 - {video_name}")
        self.resize(780, 560)
        self.setStyleSheet(DARK_STYLE if is_dark else LIGHT_STYLE)

        layout = QVBoxLayout(self)
        info_lbl = QLabel(f"📄 文件: {transcript_path}")
        info_lbl.setStyleSheet(f"color: {'#94a3b8' if is_dark else '#64748b'}; font-size: 12px;")
        layout.addWidget(info_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["开始时间", "结束时间", "识别字幕内容"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.close)
        layout.addWidget(btn_box)

        self.load_transcript(transcript_path)

    def load_transcript(self, path_str):
        p = Path(path_str)
        if not p.is_file():
            return
        try:
            records = json.loads(p.read_text(encoding="utf-8"))
            self.table.setRowCount(len(records))
            for i, seg in enumerate(records):
                s_str = f"{seg.get('start', 0.0):.1f}s"
                e_str = f"{seg.get('end', 0.0):.1f}s"
                t_str = str(seg.get("text", "")).strip()

                item_s = QTableWidgetItem(s_str)
                item_s.setTextAlignment(Qt.AlignCenter)
                item_e = QTableWidgetItem(e_str)
                item_e.setTextAlignment(Qt.AlignCenter)
                item_t = QTableWidgetItem(t_str)

                self.table.setItem(i, 0, item_s)
                self.table.setItem(i, 1, item_e)
                self.table.setItem(i, 2, item_t)
        except Exception as e:
            QMessageBox.warning(self, "读取错误", f"无法解析转写文件：{e}")


# ==============================================================================
# 通用后台异步工作线程 (彻底告别网络/AI大模型/大文件操作阻塞 GUI 主线程)
# ==============================================================================
_ACTIVE_WORKERS = set()


class AsyncTaskThread(QThread):
    finished_ok = pyqtSignal(object)
    finished_err = pyqtSignal(str)
    progress_changed = pyqtSignal(int, str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__(None)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def emit_progress(self, pct, msg=""):
        try:
            self.progress_changed.emit(max(0, min(100, int(pct))), str(msg or ""))
        except Exception:
            pass

    def run(self):
        try:
            import inspect
            call_kwargs = dict(self.kwargs)
            try:
                sig = inspect.signature(self.fn)
                if "progress_cb" in sig.parameters and "progress_cb" not in call_kwargs:
                    call_kwargs["progress_cb"] = self.emit_progress
            except (TypeError, ValueError):
                pass
            res = self.fn(*self.args, **call_kwargs)
            self.finished_ok.emit(res)
        except Exception as e:
            self.finished_err.emit(str(e))


def run_async_task(fn, on_ok=None, on_err=None, *args, on_progress=None, **kwargs):
    """在独立 QThread 中异步执行耗时任务，并自动管理线程对象生命周期与实时进度回传"""
    worker = AsyncTaskThread(fn, *args, **kwargs)
    _ACTIVE_WORKERS.add(worker)

    def _cleanup():
        _ACTIVE_WORKERS.discard(worker)
        worker.deleteLater()

    if on_ok is not None:
        worker.finished_ok.connect(on_ok)
    if on_err is not None:
        worker.finished_err.connect(on_err)
    if on_progress is not None:
        worker.progress_changed.connect(on_progress)
    worker.finished.connect(_cleanup)
    worker.start()
    return worker


# ==============================================================================
# 发布文案生成与编辑弹窗
# ==============================================================================
class PublishEditDialog(QDialog):
    def __init__(self, clip_row, parent=None, is_dark=False):
        super().__init__(parent)
        self.clip_row = clip_row
        self.output_path = clip_row.get("output", "")
        self.is_dark = is_dark
        self.has_changes = False
        self._is_closed = False
        self._is_generating = False

        self.setWindowTitle(f"编辑发布文案 - {Path(self.output_path).name}")
        self.resize(700, 560)
        self.setStyleSheet(DARK_STYLE if is_dark else LIGHT_STYLE)

        layout = QVBoxLayout(self)

        info_lbl = QLabel(f"成片文件: {self.output_path}")
        info_lbl.setStyleSheet(f"color: {'#94a3b8' if is_dark else '#64748b'}; font-size: 12px;")
        layout.addWidget(info_lbl)

        # 标题输入
        layout.addWidget(QLabel("发布标题 (建议 12-28 字，提炼争议或观点):"))
        self.txt_title = QLineEdit()
        self.txt_title.setText(clip_row.get("title", ""))
        layout.addWidget(self.txt_title)

        # 正文内容
        layout.addWidget(QLabel("正文文案与话题标签 (#话题):"))
        self.txt_content = QTextEdit()
        layout.addWidget(self.txt_content)

        # AI 快捷生成栏
        ai_box = QHBoxLayout()
        ai_box.addWidget(QLabel("AI 文案生成风格:"))
        self.cmb_style = QComboBox()
        self.cmb_style.addItems([
            "tactical_youth (⚽ 战术复盘与青训深度干货 - 默认推荐)",
            "tactical (🎯 专业硬核技战术打法复盘)",
            "youth (🌱 中国青训实战与球员成长深度观察)",
            "benchmark_viral (🔥 头部高赞爆款张力范式)",
            "opinionated (⚡ 犀利评析直击痛点不和稀泥)",
            "humorous_meme (🎙️ 董路特色幽默相声金句)"
        ])
        ai_box.addWidget(self.cmb_style)

        self.btn_ai_gen = QPushButton("🧠 AI 自动生成文案")
        self.btn_ai_gen.setStyleSheet("background-color: #7c3aed; color: #fff;")
        self.btn_ai_gen.clicked.connect(self.on_ai_generate)
        ai_box.addWidget(self.btn_ai_gen)
        layout.addLayout(ai_box)

        # 异步状态提示与实时进度条
        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 100)
        self.ai_progress.setValue(0)
        self.ai_progress.setFixedHeight(16)
        self.ai_progress.setTextVisible(True)
        self.ai_progress.setVisible(False)
        layout.addWidget(self.ai_progress)

        self.lbl_ai_status = QLabel("")
        self.lbl_ai_status.setWordWrap(True)
        self.lbl_ai_status.setStyleSheet(f"color: {'#94a3b8' if is_dark else '#64748b'}; font-size: 12px;")
        self.lbl_ai_status.setVisible(False)
        layout.addWidget(self.lbl_ai_status)

        self._ai_start_ts = 0.0
        self._ai_heavy_busy = False
        self.ai_elapsed_timer = QTimer(self)
        self.ai_elapsed_timer.setInterval(200)
        self.ai_elapsed_timer.timeout.connect(self._on_ai_tick)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_save = QPushButton("💾 保存发布文案")
        self.btn_save.setProperty("class", "success")
        self.btn_save.clicked.connect(self.on_save)
        self.btn_cancel = QPushButton("关闭")
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.close)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

        # 加载已有内容
        self.load_existing_text()

    def closeEvent(self, event):
        self._is_closed = True
        self.ai_elapsed_timer.stop()
        super().closeEvent(event)

    def reject(self):
        self._is_closed = True
        self.ai_elapsed_timer.stop()
        super().reject()

    def load_existing_text(self):
        if self.clip_row.get("publish_title"):
            self.txt_title.setText(self.clip_row["publish_title"])
        if self.clip_row.get("publish_content"):
            self.txt_content.setText(self.clip_row["publish_content"])
            return

        queue = dashboard_server.read_json(dashboard_server.QUEUE_JSON, [])
        target = os.path.abspath(self.output_path) if self.output_path else ""
        item = next(
            (r for r in queue if r.get("output") and os.path.abspath(r["output"]) == target),
            None,
        )
        if item:
            if item.get("publish_title"):
                self.txt_title.setText(item["publish_title"])
            if item.get("publish_content"):
                self.txt_content.setText(item["publish_content"])

    def _on_ai_tick(self):
        if not self._is_generating or self._is_closed:
            self.ai_elapsed_timer.stop()
            return
        elapsed = max(0.0, time.time() - self._ai_start_ts)
        # 渐近式预估进度（8s 内平滑升至 90%，绝不卡死在 0%）
        sim_pct = min(92, int(15 + 77 * (1.0 - pow(0.75, elapsed))))
        self.ai_progress.setValue(sim_pct)
        self.ai_progress.setFormat(f"AI 文案生成中... {sim_pct}% ({elapsed:.1f}s)")
        prefix = "⚠️ 后台高算力并发中，" if self._ai_heavy_busy else "⏳ 后台大模型推理中"
        self.lbl_ai_status.setText(f"{prefix} · 正在撰写文案与标签 · 已用时 {elapsed:.1f} 秒（界面保持流畅）")

    def on_ai_generate(self):
        if self._is_generating:
            return
        style_key = self.cmb_style.currentText().split()[0]
        self._is_generating = True
        self._ai_start_ts = time.time()
        self.btn_ai_gen.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.cmb_style.setEnabled(False)
        self.btn_ai_gen.setText("⏳ AI 异步撰写中...")
        self.ai_progress.setRange(0, 100)
        self.ai_progress.setValue(12)
        self.ai_progress.setFormat("准备上下文中... 12%")
        self.ai_progress.setVisible(True)

        parent_win = self.parent()
        self._ai_heavy_busy = bool(
            parent_win is not None
            and getattr(parent_win, "current_process", None) is not None
            and parent_win.current_process.state() == QProcess.Running
        )
        hint_color = "#f59e0b" if self._ai_heavy_busy else ("#38bdf8" if self.is_dark else "#2563eb")
        self.lbl_ai_status.setStyleSheet(f"color: {hint_color}; font-size: 12px; font-weight: 600;")
        self.lbl_ai_status.setVisible(True)
        self._on_ai_tick()
        self.ai_elapsed_timer.start()

        self._worker = run_async_task(
            dashboard_server.generate_publish_text,
            self._on_ai_success,
            self._on_ai_error,
            self.output_path,
            style=style_key,
        )

    def _on_ai_success(self, res):
        self.ai_elapsed_timer.stop()
        if self._is_closed:
            return
        self._is_generating = False
        cost = time.time() - self._ai_start_ts
        self.ai_progress.setValue(100)
        self.ai_progress.setFormat(f"完成 100% ({cost:.1f}s)")
        self.btn_ai_gen.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.cmb_style.setEnabled(True)
        self.btn_ai_gen.setText("🧠 AI 自动生成文案")

        self.txt_title.setText(res.get("publish_title", ""))
        self.txt_content.setText(res.get("publish_content", ""))
        self.has_changes = True

        ok_color = "#10b981" if self.is_dark else "#059669"
        self.lbl_ai_status.setStyleSheet(f"color: {ok_color}; font-size: 12px; font-weight: 600;")
        self.lbl_ai_status.setText(f"✅ AI 生成并自动保存成功！耗时 {cost:.1f}s（模型: {res.get('model')}），可直接微调或关闭。")

    def _on_ai_error(self, err_msg):
        self.ai_elapsed_timer.stop()
        if self._is_closed:
            return
        self._is_generating = False
        self.ai_progress.setVisible(False)
        self.btn_ai_gen.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.cmb_style.setEnabled(True)
        self.btn_ai_gen.setText("🧠 AI 自动生成文案")

        err_color = "#f87171" if self.is_dark else "#dc2626"
        self.lbl_ai_status.setStyleSheet(f"color: {err_color}; font-size: 12px; font-weight: 600;")
        self.lbl_ai_status.setText(f"❌ AI 生成失败：{err_msg}")
        QMessageBox.critical(self, "生成失败", f"AI 生成文案出错：{err_msg}")

    def on_save(self):
        title = self.txt_title.text().strip()
        content = self.txt_content.toPlainText().strip()
        if not title:
            QMessageBox.warning(self, "提示", "发布标题不能为空")
            return
        try:
            dashboard_server.update_publish_text(self.output_path, title, content)
            self.has_changes = True
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))


# ==============================================================================
# 手动录入标杆爆款弹窗
# ==============================================================================
class AddRadarItemDialog(QDialog):
    def __init__(self, tracked_accounts=None, parent=None, is_dark=False):
        super().__init__(parent)
        self.setWindowTitle("录入同行标杆爆款")
        self.resize(520, 260)
        self.setStyleSheet(DARK_STYLE if is_dark else LIGHT_STYLE)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("输入同行爆款标题或金句（如：不敢对抗就别谈留洋）")
        form.addRow("爆款标题:", self.txt_title)

        self.cmb_author = QComboBox()
        self.cmb_author.setEditable(True)
        names = [a.get("name", "") for a in (tracked_accounts or []) if a.get("name")]
        if names:
            self.cmb_author.addItems(names)
        else:
            self.cmb_author.addItems(["董路侃球", "董路足球精选", "同行标杆"])
        form.addRow("对标账号:", self.cmb_author)

        self.txt_likes = QLineEdit("5000")
        form.addRow("当前点赞:", self.txt_likes)

        self.txt_velocity = QLineEdit("500")
        form.addRow("点赞增速 (/h):", self.txt_velocity)

        layout.addLayout(form)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setProperty("class", "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("💾 保存并匹配本地素材")
        btn_ok.setProperty("class", "success")
        btn_ok.clicked.connect(self.accept)
        btn_bar.addWidget(btn_cancel)
        btn_bar.addWidget(btn_ok)
        layout.addLayout(btn_bar)

    def get_values(self):
        try:
            likes = int(self.txt_likes.text().strip() or "5000")
        except ValueError:
            likes = 5000
        try:
            vel = float(self.txt_velocity.text().strip() or "500")
        except ValueError:
            vel = 500.0
        return {
            "title": self.txt_title.text().strip(),
            "author": self.cmb_author.currentText().strip() or "同行标杆",
            "likes": likes,
            "velocity": vel,
        }


# ==============================================================================
# 主窗口：VideoScreen 本地原生执行客户端
# ==============================================================================
class VideoScreenMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoScreen 直播切片系统 (本地执行桌面端)")
        self.resize(1300, 850)

        # 读取用户界面主题设置，默认现代清爽浅色风 (Light)
        config_json = dashboard_server.read_json(APP_DIR / "config.json", {})
        ui_theme = config_json.get("ui_theme", "light")
        self.current_is_dark = (ui_theme == "dark")
        self.setStyleSheet(DARK_STYLE if self.current_is_dark else LIGHT_STYLE)

        # 进程管理器与全自动流水线控制队列
        self.current_process = None
        self.current_action_name = ""
        self.start_time = 0
        self.pipeline_steps = []
        self.pipeline_current_step = 0
        self.is_running_auto_pipeline = False
        self.checked_clip_outputs = set()

        # 主部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        root_layout = QVBoxLayout(main_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # 1. 顶部全局工具条与指标看板
        self.setup_header_stats(root_layout)

        # 2. 中部核心选项卡
        splitter = QSplitter(Qt.Vertical)
        root_layout.addWidget(splitter, 1)

        self.tab_widget = QTabWidget()
        splitter.addWidget(self.tab_widget)

        self.tab_overview = QWidget()
        self.tab_recorder = QWidget()
        self.tab_sources = QWidget()
        self.tab_candidates = QWidget()
        self.tab_clips = QWidget()
        self.tab_radar = QWidget()
        self.tab_settings = QWidget()

        self.tab_widget.addTab(self.tab_overview, "概览")
        self.tab_widget.addTab(self.tab_recorder, "直播录制")
        self.tab_widget.addTab(self.tab_sources, "素材管理")
        self.tab_widget.addTab(self.tab_candidates, "AI 候选")
        self.tab_widget.addTab(self.tab_clips, "成片发布")
        self.tab_widget.addTab(self.tab_radar, "账号雷达")
        self.tab_widget.addTab(self.tab_settings, "设置")
        self.tab_widget.setDocumentMode(False)
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.tabBar().setElideMode(Qt.ElideNone)

        # 构建各个选项卡视图
        self.build_tab_overview()
        self.build_tab_recorder()
        self.build_tab_sources()
        self.build_tab_candidates()
        self.build_tab_clips()
        self.build_tab_radar()
        self.build_tab_settings()

        # 3. 底部实时运行日志控制台
        self.setup_log_console(splitter)
        splitter.setStretchFactor(0, 1)  # 上部核心工作区拥有主要拉伸权重
        splitter.setStretchFactor(1, 0)  # 底部日志区保持紧凑状态
        splitter.setSizes([650, 180])

        # 高性能流式日志缓冲与节流合并刷新定时器 (合并高频控制台写入，杜绝阻塞 Qt GUI 主事件循环)
        self.log_buffer = []
        self.log_flush_timer = QTimer(self)
        self.log_flush_timer.setInterval(60)  # 60ms 批量渲染 (最高 16fps，极大降低 GUI 负担)
        self.log_flush_timer.timeout.connect(self.flush_log_buffer)
        self.log_flush_timer.start()

        # 搜索输入防抖定时器 (200ms 防抖，杜绝按键输入连环刷新造成卡顿)
        self.source_search_timer = QTimer(self)
        self.source_search_timer.setSingleShot(True)
        self.source_search_timer.timeout.connect(self.filter_sources_table)

        self.cand_search_timer = QTimer(self)
        self.cand_search_timer.setSingleShot(True)
        self.cand_search_timer.timeout.connect(self.filter_candidates_table)

        self.clip_search_timer = QTimer(self)
        self.clip_search_timer.setSingleShot(True)
        self.clip_search_timer.timeout.connect(self.filter_clips_table)

        # 初始加载数据
        self._is_closing = False
        self._is_refreshing_overview = False
        self.refresh_all_data()

        # 定时器：每 30 秒在后台异步轻量刷新概览，彻底避免阻塞主线程
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.on_auto_refresh_overview)
        self.auto_timer.start(30000)

    # --------------------------------------------------------------------------
    # 顶部全局导航与指标看板
    # --------------------------------------------------------------------------
    def setup_header_stats(self, parent_layout):
        # 顶部全局常驻导航与快捷操作栏 (macOS 顶部工具栏风格)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 6)

        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(10)
        lbl_app_logo = QLabel("<b>VideoScreen</b> <span style='color:#8e8e93;font-weight:500;font-size:12px;'>直播切片系统</span>")
        lbl_app_logo.setStyleSheet("font-size: 14px; color: #1d1d1f;" if not self.current_is_dark else "font-size: 14px; color: #f8fafc;")

        self.lbl_global_badge = QLabel("● 系统就绪")
        self.lbl_global_badge.setStyleSheet(
            "background-color: rgba(52, 199, 89, 0.12); color: #15803d; border: 1px solid rgba(52, 199, 89, 0.25); border-radius: 999px; padding: 2px 10px; font-size: 11px; font-weight: 600;"
            if not self.current_is_dark else
            "background-color: rgba(52, 199, 89, 0.15); color: #30d158; border: 1px solid rgba(52, 199, 89, 0.3); border-radius: 999px; padding: 2px 10px; font-size: 11px; font-weight: 600;"
        )
        brand_layout.addWidget(lbl_app_logo)
        brand_layout.addWidget(self.lbl_global_badge)
        top_bar.addLayout(brand_layout)

        top_bar.addStretch()

        # 全局快捷常驻按钮 (macOS 质感圆角按钮)
        self.btn_top_auto = QPushButton("一键全自动出片")
        self.btn_top_auto.setProperty("class", "hero")
        self.btn_top_auto.setToolTip("录像录完后一键挂机：自动依次执行 扫描 ➔ 转写 ➔ AI分析 ➔ 批量成片")
        self.btn_top_auto.clicked.connect(self.on_action_auto_pipeline)
        top_bar.addWidget(self.btn_top_auto)

        btn_top_refresh = QPushButton("刷新")
        btn_top_refresh.setProperty("class", "secondary")
        btn_top_refresh.clicked.connect(self.refresh_all_data)
        top_bar.addWidget(btn_top_refresh)

        btn_top_clips = QPushButton("成片目录")
        btn_top_clips.setProperty("class", "secondary")
        btn_top_clips.clicked.connect(lambda: subprocess.Popen(["xdg-open", str(APP_DIR / "clips")]))
        top_bar.addWidget(btn_top_clips)

        parent_layout.addLayout(top_bar)

        # 6 项数据看板指标卡片 (macOS 极简微质感圆角卡片，等比例 1:1:1:1:1:1 响应式铺满)
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)

        self.card_sources = StatCard("总录像素材", "0", "已录制场次", color="#007aff", bg_tint="#eff6ff")
        self.card_waiting = StatCard("待转写素材", "0", "等待语音识别", color="#ff9500", bg_tint="#fff7ed")
        self.card_analyzed = StatCard("AI 已分析", "0", "高光挖掘完成", color="#34c759", bg_tint="#f0fdf4")
        self.card_clips = StatCard("最终成片库", "0", "高清切割成品", color="#af52de", bg_tint="#f5f3ff")
        self.card_publish = StatCard("待发布队列", "0", "等待推送抖音", color="#ff3b30", bg_tint="#fff1f0")
        self.card_storage = StatCard("磁盘剩余空间", "0 GB", "可清理原片 0 GB", color="#8e8e93", bg_tint="#f2f2f7")

        stats_layout.addWidget(self.card_sources, 1)
        stats_layout.addWidget(self.card_waiting, 1)
        stats_layout.addWidget(self.card_analyzed, 1)
        stats_layout.addWidget(self.card_clips, 1)
        stats_layout.addWidget(self.card_publish, 1)
        stats_layout.addWidget(self.card_storage, 1)

        parent_layout.addLayout(stats_layout)

        if self.current_is_dark:
            for c in [self.card_sources, self.card_waiting, self.card_analyzed,
                      self.card_clips, self.card_publish, self.card_storage]:
                c.apply_theme(True)

    # --------------------------------------------------------------------------
    # Tab 1: 概览与一键流水线控制台
    # --------------------------------------------------------------------------
    def build_tab_overview(self):
        layout = QVBoxLayout(self.tab_overview)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 1. 核心 C 位：全自动流水线 Hero Card (macOS 极简 Banner 布局)
        hero_box = QGroupBox("全自动出片流水线")
        hero_layout = QHBoxLayout(hero_box)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(16)

        desc_layout = QVBoxLayout()
        desc_layout.setSpacing(4)
        lbl_hero_title = QLabel("全自动无人值守出片流水线")
        lbl_hero_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #1c1c1e;" if not self.current_is_dark else "font-size: 14px; font-weight: 700; color: #f5f5f7;")
        self.lbl_hero_desc = QLabel(
            "自动按序执行：<b>扫描新录像 → SenseVoice 语音转写 → AI 高光挖掘 → 精准批量剪辑 → 同步抖音待发队列</b>。支持挂机无人值守自动完成。"
        )
        self.lbl_hero_desc.setTextFormat(Qt.RichText)
        self.lbl_hero_desc.setStyleSheet(
            "color: #8e8e93; font-size: 12px; line-height: 140%;" if not self.current_is_dark else "color: #98989d; font-size: 12px; line-height: 140%;"
        )
        desc_layout.addWidget(lbl_hero_title)
        desc_layout.addWidget(self.lbl_hero_desc)
        hero_layout.addLayout(desc_layout, 1)

        self.btn_hero_auto = QPushButton("启动全自动流水线")
        self.btn_hero_auto.setFixedSize(160, 36)
        self.btn_hero_auto.setProperty("class", "hero")
        self.btn_hero_auto.clicked.connect(self.on_action_auto_pipeline)
        hero_layout.addWidget(self.btn_hero_auto)

        layout.addWidget(hero_box)

        # 2. 分步单项调试操作（向导式步骤流）
        steps_box = QGroupBox("单工序独立调试")
        steps_layout = QVBoxLayout(steps_box)
        steps_layout.setContentsMargins(16, 12, 16, 12)
        steps_layout.setSpacing(8)

        steps_row = QHBoxLayout()
        steps_row.setSpacing(8)

        btn_rec = QPushButton("01 直播录制\n网络推流")
        btn_rec.setFixedHeight(44)
        btn_rec.setProperty("class", "secondary")
        btn_rec.clicked.connect(lambda: self.tab_widget.setCurrentIndex(1))
        steps_row.addWidget(btn_rec, 1)

        lbl_arr0 = QLabel("›")
        lbl_arr0.setStyleSheet("color: #8e8e93; font-weight: bold; font-size: 18px;")
        lbl_arr0.setAlignment(Qt.AlignCenter)
        steps_row.addWidget(lbl_arr0)

        btn_scan = QPushButton("02 素材扫描\n检测新录像")
        btn_scan.setFixedHeight(44)
        btn_scan.setProperty("class", "secondary")
        btn_scan.clicked.connect(self.on_action_scan)
        steps_row.addWidget(btn_scan, 1)

        lbl_arr1 = QLabel("›")
        lbl_arr1.setStyleSheet("color: #8e8e93; font-weight: bold; font-size: 18px;")
        lbl_arr1.setAlignment(Qt.AlignCenter)
        steps_row.addWidget(lbl_arr1)

        btn_transcribe = QPushButton("03 语音转写\nSenseVoice")
        btn_transcribe.setFixedHeight(44)
        btn_transcribe.setProperty("class", "secondary")
        btn_transcribe.clicked.connect(self.on_action_transcribe)
        steps_row.addWidget(btn_transcribe, 1)

        lbl_arr2 = QLabel("›")
        lbl_arr2.setStyleSheet("color: #8e8e93; font-weight: bold; font-size: 18px;")
        lbl_arr2.setAlignment(Qt.AlignCenter)
        steps_row.addWidget(lbl_arr2)

        btn_analyze = QPushButton("04 AI 分析\n高光挖掘 70+")
        btn_analyze.setFixedHeight(44)
        btn_analyze.setProperty("class", "secondary")
        btn_analyze.clicked.connect(self.on_action_analyze)
        steps_row.addWidget(btn_analyze, 1)

        lbl_arr3 = QLabel("›")
        lbl_arr3.setStyleSheet("color: #8e8e93; font-weight: bold; font-size: 18px;")
        lbl_arr3.setAlignment(Qt.AlignCenter)
        steps_row.addWidget(lbl_arr3)

        btn_cut = QPushButton("05 批量剪辑\n无损精准")
        btn_cut.setFixedHeight(44)
        btn_cut.setProperty("class", "secondary")
        btn_cut.clicked.connect(self.on_action_cut)
        steps_row.addWidget(btn_cut, 1)

        lbl_arr4 = QLabel("›")
        lbl_arr4.setStyleSheet("color: #8e8e93; font-weight: bold; font-size: 18px;")
        lbl_arr4.setAlignment(Qt.AlignCenter)
        steps_row.addWidget(lbl_arr4)

        btn_sync = QPushButton("06 队列同步\n发布待审")
        btn_sync.setFixedHeight(44)
        btn_sync.setProperty("class", "secondary")
        btn_sync.clicked.connect(self.on_action_sync_queue)
        steps_row.addWidget(btn_sync, 1)

        steps_layout.addLayout(steps_row)
        layout.addWidget(steps_box)

        # 3. 独立磁盘存储管理区
        storage_box = QGroupBox("磁盘空间与存储维护")
        storage_layout = QHBoxLayout(storage_box)
        storage_layout.setContentsMargins(18, 12, 18, 12)
        storage_layout.setSpacing(12)

        self.lbl_cleanable_desc = QLabel("正在扫描可清理的已剪辑原素材...")
        self.lbl_cleanable_desc.setTextFormat(Qt.RichText)
        self.lbl_cleanable_desc.setStyleSheet(
            "color: #8e8e93; font-size: 12px;" if not self.current_is_dark else "color: #98989d; font-size: 12px;"
        )
        storage_layout.addWidget(self.lbl_cleanable_desc, 1)

        btn_cleanup = QPushButton("清理已剪原片")
        btn_cleanup.setFixedSize(110, 32)
        btn_cleanup.setProperty("class", "danger")
        btn_cleanup.clicked.connect(self.on_action_cleanup)
        storage_layout.addWidget(btn_cleanup)

        layout.addWidget(storage_box)

        # 4. 指南与运行模式说明
        guide_box = QGroupBox("使用说明与快捷操作")
        guide_layout = QVBoxLayout(guide_box)
        guide_layout.setContentsMargins(18, 12, 18, 12)
        self.lbl_guide = QLabel(
            "• <b>原生桌面运行</b>：直接调度本地 Python 解释器与 FFmpeg 核心，脱离浏览器与端口独立运行。<br>"
            "• <b>手势与快捷操作</b>：所有表格均支持 <b>鼠标双击</b>（查看字幕 / 播放视频 / 候选详情）与 <b>鼠标右键</b> 快捷操作菜单。"
        )
        self.lbl_guide.setTextFormat(Qt.RichText)
        self.lbl_guide.setStyleSheet(
            "color: #8e8e93; line-height: 150%; font-size: 12px;" if not self.current_is_dark
            else "color: #98989d; line-height: 150%; font-size: 12px;"
        )
        guide_layout.addWidget(self.lbl_guide)
        layout.addWidget(guide_box)

        layout.addStretch()

    # --------------------------------------------------------------------------
    # Tab 2: 直播自动录制 (DouyinLiveRecorder)
    # --------------------------------------------------------------------------
    def build_tab_recorder(self):
        layout = QVBoxLayout(self.tab_recorder)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. 顶部状态栏与控制操作群
        top_box = QGroupBox("直播录制服务状态")
        top_layout = QHBoxLayout(top_box)
        top_layout.setContentsMargins(14, 10, 14, 10)
        top_layout.setSpacing(12)

        self.lbl_rec_status = QLabel("● 检测中...")
        self.lbl_rec_status.setStyleSheet("font-weight: 600; font-size: 13px; color: #8e8e93;")
        top_layout.addWidget(self.lbl_rec_status)

        self.lbl_rec_stream = QLabel("● 活跃录制流: 0")
        self.lbl_rec_stream.setStyleSheet("color: #007aff; font-size: 12px; font-weight: 500;")
        top_layout.addWidget(self.lbl_rec_stream)

        self.lbl_rec_storage = QLabel("● 录像库已占用: 0 GB")
        self.lbl_rec_storage.setStyleSheet("color: #8e8e93; font-size: 12px; font-weight: 500;")
        top_layout.addWidget(self.lbl_rec_storage)

        top_layout.addStretch()

        self.btn_start_rec = QPushButton("启动服务")
        self.btn_start_rec.setProperty("class", "hero")
        self.btn_start_rec.clicked.connect(self.on_start_recorder)
        top_layout.addWidget(self.btn_start_rec)

        self.btn_stop_rec = QPushButton("停止服务")
        self.btn_stop_rec.setProperty("class", "danger")
        self.btn_stop_rec.clicked.connect(self.on_stop_recorder)
        top_layout.addWidget(self.btn_stop_rec)

        self.btn_restart_rec = QPushButton("重启")
        self.btn_restart_rec.setProperty("class", "secondary")
        self.btn_restart_rec.clicked.connect(self.on_restart_recorder)
        top_layout.addWidget(self.btn_restart_rec)

        btn_open_rec_dir = QPushButton("录像目录")
        btn_open_rec_dir.setProperty("class", "secondary")
        btn_open_rec_dir.clicked.connect(lambda: subprocess.Popen(["xdg-open", str(live_recorder_service.RECORDER_DIR / "downloads")]))
        top_layout.addWidget(btn_open_rec_dir)

        btn_refresh_rec = QPushButton("刷新")
        btn_refresh_rec.setProperty("class", "secondary")
        btn_refresh_rec.clicked.connect(self.refresh_recorder_tab)
        top_layout.addWidget(btn_refresh_rec)

        layout.addWidget(top_box)

        # 2. 中部主体 Splitter (左：直播间监控配置 / 右：活跃流与控制台日志)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        # 左侧：直播间监控清单
        left_box = QGroupBox("监控直播间清单")
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        self.table_rooms = QTableWidget()
        self.table_rooms.setColumnCount(4)
        self.table_rooms.setHorizontalHeaderLabels(["状态", "主播名称", "直播平台", "直播间地址"])
        self.table_rooms.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table_rooms.setColumnWidth(0, 65)
        self.table_rooms.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table_rooms.setColumnWidth(1, 105)
        self.table_rooms.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table_rooms.setColumnWidth(2, 90)
        self.table_rooms.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_rooms.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_rooms.setEditTriggers(QAbstractItemView.NoEditTriggers)
        left_layout.addWidget(self.table_rooms)

        # 添加直播间表单
        form_row = QHBoxLayout()
        self.txt_add_room_url = QLineEdit()
        self.txt_add_room_url.setPlaceholderText("粘贴直播间地址 (抖音/快手/TikTok等)...")
        form_row.addWidget(self.txt_add_room_url, 1)

        self.txt_add_room_name = QLineEdit()
        self.txt_add_room_name.setPlaceholderText("主播备注 (如：董路)")
        self.txt_add_room_name.setFixedWidth(160)
        form_row.addWidget(self.txt_add_room_name)

        btn_add_room = QPushButton("添加")
        btn_add_room.setProperty("class", "primary")
        btn_add_room.clicked.connect(self.on_add_recorder_room)
        form_row.addWidget(btn_add_room)
        left_layout.addLayout(form_row)

        action_row = QHBoxLayout()
        btn_toggle_room = QPushButton("切换启用/禁用")
        btn_toggle_room.setProperty("class", "secondary")
        btn_toggle_room.clicked.connect(self.on_toggle_recorder_room)
        action_row.addWidget(btn_toggle_room)

        btn_del_room = QPushButton("移除直播间")
        btn_del_room.setProperty("class", "danger")
        btn_del_room.clicked.connect(self.on_delete_recorder_room)
        action_row.addWidget(btn_del_room)
        action_row.addStretch()
        left_layout.addLayout(action_row)

        splitter.addWidget(left_box)

        # 右侧：活跃录制任务 & 实时日志
        right_box = QGroupBox("录制实时日志")
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        self.txt_recorder_logs = QPlainTextEdit()
        self.txt_recorder_logs.setReadOnly(True)
        self.txt_recorder_logs.setMaximumBlockCount(2000)
        right_layout.addWidget(self.txt_recorder_logs, 1)

        log_btn_bar = QHBoxLayout()
        self.lbl_log_hint = QLabel("提示：主播开播后将自动调起后台 FFmpeg 进行高码率录制并分段保存。")
        self.lbl_log_hint.setStyleSheet("color: #8e8e93; font-size: 11px;")
        log_btn_bar.addWidget(self.lbl_log_hint)
        log_btn_bar.addStretch()

        btn_copy_rec_log = QPushButton("复制日志")
        btn_copy_rec_log.setProperty("class", "secondary")
        btn_copy_rec_log.clicked.connect(lambda: QApplication.clipboard().setText(self.txt_recorder_logs.toPlainText()))
        log_btn_bar.addWidget(btn_copy_rec_log)

        btn_reload_log = QPushButton("刷新日志")
        btn_reload_log.setProperty("class", "secondary")
        btn_reload_log.clicked.connect(self.refresh_recorder_logs)
        log_btn_bar.addWidget(btn_reload_log)

        right_layout.addLayout(log_btn_bar)
        splitter.addWidget(right_box)
        splitter.setSizes([540, 600])

        # 定时器定期自动同步录制状态与日志
        self.recorder_timer = QTimer(self)
        self.recorder_timer.setInterval(4000)  # 4秒同步
        self.recorder_timer.timeout.connect(self.refresh_recorder_tab)
        self.recorder_timer.start()

        # 初始刷新
        self.refresh_recorder_tab()

    def refresh_recorder_tab(self):
        try:
            status = live_recorder_service.get_status()
        except Exception as e:
            return

        is_running = status.get("is_running", False)
        pid = status.get("pid")
        if is_running:
            self.lbl_rec_status.setText(f"● 录制服务运行中 (PID: {pid})")
            self.lbl_rec_status.setStyleSheet("font-weight: 600; font-size: 13px; color: #34c759;")
            self.btn_start_rec.setEnabled(False)
            self.btn_stop_rec.setEnabled(True)
        else:
            self.lbl_rec_status.setText("● 录制服务未运行")
            self.lbl_rec_status.setStyleSheet("font-weight: 600; font-size: 13px; color: #8e8e93;")
            self.btn_start_rec.setEnabled(True)
            self.btn_stop_rec.setEnabled(False)

        stream_count = status.get("active_stream_count", 0)
        streams = status.get("ffmpeg_streams", [])
        if stream_count > 0:
            names = " | ".join(s["anchor"] for s in streams)
            self.lbl_rec_stream.setText(f"● 正在捕获直播流 ({stream_count}): {names}")
            self.lbl_rec_stream.setStyleSheet("color: #ff3b30; font-weight: 600; font-size: 12px;")
        else:
            self.lbl_rec_stream.setText("● 活跃录制流: 0 (监控中，主播开播自动抓取)")
            self.lbl_rec_stream.setStyleSheet("color: #007aff; font-size: 12px; font-weight: 500;")

        size_gb = status.get("total_recordings_size_gb", 0)
        self.lbl_rec_storage.setText(f"● 录像库已占用: {size_gb} GB")

        # 刷新直播间列表
        rooms = status.get("rooms", [])
        self.table_rooms.setRowCount(len(rooms))
        for r_idx, r in enumerate(rooms):
            enabled = r.get("enabled", True)
            item_status = QTableWidgetItem("● 启用" if enabled else "○ 禁用")
            item_status.setTextAlignment(Qt.AlignCenter)
            item_status.setForeground(QColor("#34c759" if enabled else "#8e8e93"))
            self.table_rooms.setItem(r_idx, 0, item_status)

            item_name = QTableWidgetItem(r.get("name", ""))
            item_name.setTextAlignment(Qt.AlignCenter)
            self.table_rooms.setItem(r_idx, 1, item_name)

            item_plat = QTableWidgetItem(r.get("platform", ""))
            item_plat.setTextAlignment(Qt.AlignCenter)
            item_plat.setForeground(QColor("#0284c7"))
            self.table_rooms.setItem(r_idx, 2, item_plat)

            item_url = QTableWidgetItem(r.get("url", ""))
            item_url.setData(Qt.UserRole, r)
            self.table_rooms.setItem(r_idx, 3, item_url)

        self.refresh_recorder_logs()

    def refresh_recorder_logs(self):
        try:
            logs = live_recorder_service.get_recent_logs(100)
            self.txt_recorder_logs.setPlainText(logs)
            cursor = self.txt_recorder_logs.textCursor()
            cursor.movePosition(cursor.End)
            self.txt_recorder_logs.setTextCursor(cursor)
        except Exception:
            pass

    def on_start_recorder(self):
        res = live_recorder_service.start_recorder()
        if res.get("success"):
            self.append_log(f"🟢 [LiveRecorder] {res.get('message')}\n")
        else:
            QMessageBox.warning(self, "启动失败", res.get("message", "未知错误"))
        self.refresh_recorder_tab()

    def on_stop_recorder(self):
        reply = QMessageBox.question(
            self, "确认停止",
            "确定要停止 DouyinLiveRecorder 录制服务吗？\n当前若有直播正在录制，将安全收尾分段并关闭。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            res = live_recorder_service.stop_recorder()
            self.append_log(f"⚪ [LiveRecorder] {res.get('message')}\n")
            self.refresh_recorder_tab()

    def on_restart_recorder(self):
        res = live_recorder_service.restart_recorder()
        self.append_log(f"🔄 [LiveRecorder] 重启结果: {res.get('message')}\n")
        self.refresh_recorder_tab()

    def on_add_recorder_room(self):
        url = self.txt_add_room_url.text().strip()
        name = self.txt_add_room_name.text().strip()
        if not url:
            QMessageBox.information(self, "提示", "请先输入直播间地址。")
            return
        if not url.startswith("http"):
            QMessageBox.warning(self, "格式错误", "直播间地址必须以 http:// 或 https:// 开头。")
            return
        live_recorder_service.add_room(url, name)
        self.txt_add_room_url.clear()
        self.txt_add_room_name.clear()
        self.refresh_recorder_tab()
        QMessageBox.information(self, "成功", f"已成功添加监控直播间：{name or url}")

    def on_delete_recorder_room(self):
        row = self.table_rooms.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在列表中选中要移除的直播间。")
            return
        r = self.table_rooms.item(row, 3).data(Qt.UserRole)
        url = r.get("url")
        name = r.get("name")
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要从监控清单中移除直播间【{name or url}】吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            live_recorder_service.remove_room(url)
            self.refresh_recorder_tab()

    def on_toggle_recorder_room(self):
        row = self.table_rooms.currentRow()
        if row < 0:
            return
        r = self.table_rooms.item(row, 3).data(Qt.UserRole)
        rooms = live_recorder_service.list_monitored_rooms()
        for item in rooms:
            if item["url"] == r.get("url"):
                item["enabled"] = not item.get("enabled", True)
                break
        live_recorder_service.save_monitored_rooms(rooms)
        self.refresh_recorder_tab()

    # --------------------------------------------------------------------------
    # Tab 2: 录像素材库
    # --------------------------------------------------------------------------
    def build_tab_sources(self):
        layout = QVBoxLayout(self.tab_sources)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 顶部过滤器
        toolbar = QHBoxLayout()
        self.txt_source_search = QLineEdit()
        self.txt_source_search.setPlaceholderText("搜索素材文件名或日期...")
        self.txt_source_search.setMaximumWidth(280)
        self.txt_source_search.textChanged.connect(lambda: self.source_search_timer.start(200))
        toolbar.addWidget(self.txt_source_search)

        self.cmb_source_filter = QComboBox()
        self.cmb_source_filter.addItems(["全部状态", "待转写", "已转写", "已分析", "已剪辑", "原片已清理", "无音轨", "失败"])
        self.cmb_source_filter.setMinimumWidth(120)
        self.cmb_source_filter.currentTextChanged.connect(self.filter_sources_table)
        toolbar.addWidget(self.cmb_source_filter)

        toolbar.addStretch()

        btn_refresh = QPushButton("刷新")
        btn_refresh.setProperty("class", "secondary")
        btn_refresh.clicked.connect(self.refresh_sources_table)
        toolbar.addWidget(btn_refresh)

        layout.addLayout(toolbar)

        # 素材表格 (支持双击查看字幕 + 右键上下文菜单)
        self.table_sources = QTableWidget()
        self.table_sources.setColumnCount(7)
        self.table_sources.setHorizontalHeaderLabels([
            "文件名", "大小 (MB)", "状态", "AI候选数", "成片数", "原视频状态", "路径"
        ])
        self.table_sources.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col_idx, col_w in [(1, 85), (2, 100), (3, 80), (4, 70), (5, 90), (6, 280)]:
            self.table_sources.horizontalHeader().setSectionResizeMode(col_idx, QHeaderView.Interactive)
            self.table_sources.setColumnWidth(col_idx, col_w)
        self.table_sources.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_sources.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_sources.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_sources.customContextMenuRequested.connect(self.on_sources_context_menu)
        self.table_sources.cellDoubleClicked.connect(lambda r, c: self.on_view_selected_transcript())
        layout.addWidget(self.table_sources)

        # 底部选中操作条
        action_bar = QHBoxLayout()
        self.btn_retry_source = QPushButton("单独转写")
        self.btn_retry_source.setProperty("class", "secondary")
        self.btn_retry_source.setToolTip("对选中的录像单独触发 SenseVoice 批量语音识别")
        self.btn_retry_source.clicked.connect(self.on_retry_selected_source)
        action_bar.addWidget(self.btn_retry_source)

        self.btn_view_transcript = QPushButton("查看字幕")
        self.btn_view_transcript.setProperty("class", "secondary")
        self.btn_view_transcript.setToolTip("查看语音识别生成的带时间戳字幕 (亦可双击表格行)")
        self.btn_view_transcript.clicked.connect(self.on_view_selected_transcript)
        action_bar.addWidget(self.btn_view_transcript)

        self.btn_open_source_dir = QPushButton("打开目录")
        self.btn_open_source_dir.setProperty("class", "secondary")
        self.btn_open_source_dir.clicked.connect(self.on_open_selected_source_dir)
        action_bar.addWidget(self.btn_open_source_dir)

        self.btn_clean_source = QPushButton("清理原片")
        self.btn_clean_source.setProperty("class", "danger")
        self.btn_clean_source.setToolTip("删除已成功剪辑出片的原素材大文件以释放磁盘空间")
        self.btn_clean_source.clicked.connect(self.on_clean_selected_source)
        action_bar.addWidget(self.btn_clean_source)

        action_bar.addStretch()
        layout.addLayout(action_bar)

    # --------------------------------------------------------------------------
    # Tab 3: AI 爆款高光候选
    # --------------------------------------------------------------------------
    def build_tab_candidates(self):
        layout = QVBoxLayout(self.tab_candidates)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.txt_cand_search = QLineEdit()
        self.txt_cand_search.setPlaceholderText("搜索切片标题、人名或话题...")
        self.txt_cand_search.setMaximumWidth(280)
        self.txt_cand_search.textChanged.connect(lambda: self.cand_search_timer.start(200))
        toolbar.addWidget(self.txt_cand_search)

        self.cmb_cand_score = QComboBox()
        self.cmb_cand_score.addItems(["全部评分", ">= 80 分 (精选)", ">= 75 分", ">= 70 分"])
        self.cmb_cand_score.setMinimumWidth(140)
        self.cmb_cand_score.currentTextChanged.connect(self.filter_candidates_table)
        toolbar.addWidget(self.cmb_cand_score)

        self.cmb_cand_sort = QComboBox()
        self.cmb_cand_sort.addItems(["评分最高优先", "最新录像优先", "随机探索"])
        self.cmb_cand_sort.setMinimumWidth(120)
        self.cmb_cand_sort.currentTextChanged.connect(self.filter_candidates_table)
        toolbar.addWidget(self.cmb_cand_sort)

        toolbar.addStretch()

        btn_refresh = QPushButton("刷新候选")
        btn_refresh.setProperty("class", "secondary")
        btn_refresh.clicked.connect(self.refresh_candidates_table)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        # 候选表格 (支持双击查看详情 + 右键上下文菜单)
        self.table_candidates = QTableWidget()
        self.table_candidates.setColumnCount(7)
        self.table_candidates.setHorizontalHeaderLabels([
            "评分", "候选切片标题", "区间 (秒)", "时长", "话题类别", "命中重点人名/词汇", "推荐理由"
        ])
        self.table_candidates.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col_idx, col_w in [(0, 60), (2, 110), (3, 70), (4, 130), (5, 180), (6, 280)]:
            self.table_candidates.horizontalHeader().setSectionResizeMode(col_idx, QHeaderView.Interactive)
            self.table_candidates.setColumnWidth(col_idx, col_w)
        self.table_candidates.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_candidates.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_candidates.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_candidates.customContextMenuRequested.connect(self.on_candidates_context_menu)
        self.table_candidates.cellDoubleClicked.connect(lambda r, c: self.on_view_candidate_detail())
        layout.addWidget(self.table_candidates)

        cand_actions = QHBoxLayout()
        btn_detail = QPushButton("查看详情")
        btn_detail.setProperty("class", "secondary")
        btn_detail.setToolTip("查看该候选切片的 AI 推荐理由与原视频摘要 (可双击表格行)")
        btn_detail.clicked.connect(self.on_view_candidate_detail)
        cand_actions.addWidget(btn_detail)

        btn_cut_selected = QPushButton("剪辑所选切片")
        btn_cut_selected.setProperty("class", "primary")
        btn_cut_selected.setToolTip("调用 FFmpeg 精确裁剪所选区间并生成成片")
        btn_cut_selected.clicked.connect(self.on_cut_single_candidate)
        cand_actions.addWidget(btn_cut_selected)

        cand_actions.addStretch()
        layout.addLayout(cand_actions)

    # --------------------------------------------------------------------------
    # Tab 4: 最终成片库与发布
    # --------------------------------------------------------------------------
    def build_tab_clips(self):
        layout = QVBoxLayout(self.tab_clips)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 顶部：成片状态分栏 (待发布 / 已发布 / 全部) 与检索工具栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.clip_stage_bar = QTabBar()
        self.clip_stage_bar.setShape(QTabBar.RoundedNorth)
        self.clip_stage_bar.setDocumentMode(False)
        self.clip_stage_bar.setExpanding(False)
        self.clip_stage_bar.setElideMode(Qt.ElideNone)
        self.clip_stage_bar.addTab("待发布 (0)")
        self.clip_stage_bar.addTab("已发布 (0)")
        self.clip_stage_bar.addTab("全部成片 (0)")
        self.clip_stage_bar.currentChanged.connect(self.on_clip_stage_tab_changed)
        top_bar.addWidget(self.clip_stage_bar)

        top_bar.addStretch()

        self.txt_clip_search = QLineEdit()
        self.txt_clip_search.setPlaceholderText("搜索成片标题...")
        self.txt_clip_search.setFixedWidth(220)
        self.txt_clip_search.textChanged.connect(lambda: self.clip_search_timer.start(200))
        top_bar.addWidget(self.txt_clip_search)

        btn_open_clips_dir = QPushButton("成片目录")
        btn_open_clips_dir.setProperty("class", "secondary")
        btn_open_clips_dir.clicked.connect(lambda: subprocess.Popen(["xdg-open", str(APP_DIR / "clips")]))
        top_bar.addWidget(btn_open_clips_dir)

        btn_refresh = QPushButton("刷新")
        btn_refresh.setProperty("class", "secondary")
        btn_refresh.clicked.connect(self.refresh_clips_table)
        top_bar.addWidget(btn_refresh)
        layout.addLayout(top_bar)

        # 成片表格 (支持双击直接播放 + 右键完整上下文菜单)
        self.table_clips = QTableWidget()
        self.table_clips.setColumnCount(6)
        self.table_clips.setHorizontalHeaderLabels([
            "序号", "成片标题", "时长 (秒)", "大小 (MB)", "抖音发布状态", "文件路径"
        ])
        self.table_clips.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col_idx, col_w in [(0, 76), (2, 85), (3, 100), (4, 150), (5, 300)]:
            self.table_clips.horizontalHeader().setSectionResizeMode(col_idx, QHeaderView.Interactive)
            self.table_clips.setColumnWidth(col_idx, col_w)
        self.table_clips.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_clips.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_clips.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_clips.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_clips.customContextMenuRequested.connect(self.on_clips_context_menu)
        self.table_clips.cellDoubleClicked.connect(lambda r, c: self.on_play_clip())
        self.table_clips.itemChanged.connect(self.on_clip_item_changed)
        layout.addWidget(self.table_clips)

        # ----------------------------------------------------------------------
        # 底部操作栏 1：待发布专属操作面板 (发布、AI配置、废弃成片)
        # ----------------------------------------------------------------------
        self.box_pending_ops = QWidget()
        layout_pending = QVBoxLayout(self.box_pending_ops)
        layout_pending.setContentsMargins(0, 0, 0, 0)
        layout_pending.setSpacing(6)

        publish_bar = QHBoxLayout()
        publish_bar.setSpacing(8)
        btn_check_top5 = QPushButton("勾选前 5 条")
        btn_check_top5.setProperty("class", "secondary")
        btn_check_top5.setToolTip("自动勾选当前列表中前 5 条未发布成片（推荐分批，防抖音频控）")
        btn_check_top5.clicked.connect(lambda: self.on_check_top_pending_clips(5))
        publish_bar.addWidget(btn_check_top5)

        btn_check_clear = QPushButton("清空勾选")
        btn_check_clear.setProperty("class", "secondary")
        btn_check_clear.clicked.connect(self.on_clear_checked_clips)
        publish_bar.addWidget(btn_check_clear)

        self.lbl_checked_clips = QLabel("已勾选 0 条")
        self.lbl_checked_clips.setStyleSheet("color: #64748b; font-weight: 600;")
        publish_bar.addWidget(self.lbl_checked_clips)

        publish_bar.addStretch()

        self.chk_pub_ai_cover = QCheckBox("AI 封面")
        self.chk_pub_ai_cover.setChecked(True)
        self.chk_pub_ai_cover.setToolTip("自动选择抖音后台生成的 AI 推荐封面（超时则保留默认封面）")
        publish_bar.addWidget(self.chk_pub_ai_cover)

        self.chk_pub_declaration = QCheckBox("虚构演绎声明")
        self.chk_pub_declaration.setChecked(True)
        self.chk_pub_declaration.setToolTip("自动勾选自主声明：虚构演绎，仅供娱乐")
        publish_bar.addWidget(self.chk_pub_declaration)

        self.chk_pub_auto_click = QCheckBox("自动点击发布")
        self.chk_pub_auto_click.setChecked(True)
        self.chk_pub_auto_click.setToolTip("勾选：上传并自动点击最终“发布”按钮；不勾选：自动填好后停在页面等你检查后手动发布")
        publish_bar.addWidget(self.chk_pub_auto_click)

        self.btn_publish_selected = QPushButton("自动发布到抖音")
        self.btn_publish_selected.setProperty("class", "primary")
        self.btn_publish_selected.setToolTip("使用 Playwright 自动打开 Chrome 上传并填写文案（支持多选勾选，未勾选则发布当前选中行）")
        self.btn_publish_selected.clicked.connect(lambda: self.on_auto_publish_douyin())
        publish_bar.addWidget(self.btn_publish_selected)
        layout_pending.addLayout(publish_bar)

        pending_action_bar = QHBoxLayout()
        pending_action_bar.setSpacing(8)
        btn_play = QPushButton("播放成片")
        btn_play.setProperty("class", "secondary")
        btn_play.clicked.connect(self.on_play_clip)
        pending_action_bar.addWidget(btn_play)

        btn_edit_text = QPushButton("编辑发布文案")
        btn_edit_text.setProperty("class", "secondary")
        btn_edit_text.clicked.connect(self.on_edit_clip_text)
        pending_action_bar.addWidget(btn_edit_text)

        btn_mark_pub = QPushButton("标记为已发布")
        btn_mark_pub.setProperty("class", "secondary")
        btn_mark_pub.clicked.connect(lambda: self.on_change_publish_status("published"))
        pending_action_bar.addWidget(btn_mark_pub)

        btn_manual_pub = QPushButton("打开发布页")
        btn_manual_pub.setProperty("class", "secondary")
        btn_manual_pub.clicked.connect(self.on_manual_open_douyin_publish)
        pending_action_bar.addWidget(btn_manual_pub)

        btn_del_clip = QPushButton("废弃成片")
        btn_del_clip.setProperty("class", "danger")
        btn_del_clip.setToolTip("彻底删除勾选或选中的未发布成片并物理删除文件释放磁盘空间")
        btn_del_clip.clicked.connect(self.on_delete_clip)
        pending_action_bar.addWidget(btn_del_clip)

        pending_action_bar.addStretch()
        layout_pending.addLayout(pending_action_bar)
        layout.addWidget(self.box_pending_ops)

        # ----------------------------------------------------------------------
        # 底部操作栏 2：已发布专属操作面板 (空间清理释放、彻底删除记录、改回待发布)
        # ----------------------------------------------------------------------
        self.box_published_ops = QWidget()
        layout_published = QVBoxLayout(self.box_published_ops)
        layout_published.setContentsMargins(0, 0, 0, 0)
        layout_published.setSpacing(6)

        pub_bar_1 = QHBoxLayout()
        pub_bar_1.setSpacing(8)

        btn_check_top20_pub = QPushButton("☑ 勾选前20条已发布")
        btn_check_top20_pub.setProperty("class", "secondary")
        btn_check_top20_pub.clicked.connect(lambda: self.on_check_top_published_clips(20))
        pub_bar_1.addWidget(btn_check_top20_pub)

        btn_check_all_pub = QPushButton("☑ 勾选全部已发布")
        btn_check_all_pub.setProperty("class", "secondary")
        btn_check_all_pub.clicked.connect(lambda: self.on_check_top_published_clips(0))
        pub_bar_1.addWidget(btn_check_all_pub)

        btn_clear_pub_check = QPushButton("☐ 清空勾选")
        btn_clear_pub_check.setProperty("class", "secondary")
        btn_clear_pub_check.clicked.connect(self.on_clear_checked_clips)
        pub_bar_1.addWidget(btn_clear_pub_check)

        self.lbl_checked_pub_clips = QLabel("已勾选 0 条")
        self.lbl_checked_pub_clips.setStyleSheet("color: #64748b; font-weight: 600;")
        pub_bar_1.addWidget(self.lbl_checked_pub_clips)

        pub_bar_1.addStretch()

        btn_clean_pub_files = QPushButton("🧹 清理本地视频 (释放空间 · 保留抖音发布记录)")
        btn_clean_pub_files.setProperty("class", "primary")
        btn_clean_pub_files.setToolTip("物理删除本地庞大的 .mp4 视频文件以释放磁盘空间，同时完整保留抖音已发布状态、文案及流量归因记录")
        btn_clean_pub_files.clicked.connect(self.on_clean_published_files)
        pub_bar_1.addWidget(btn_clean_pub_files)

        btn_del_pub_records = QPushButton("🗑️ 彻底删除发布记录")
        btn_del_pub_records.setProperty("class", "danger")
        btn_del_pub_records.setToolTip("彻底删除所选已发布成片的本地文件（若存在）及所有发布记录")
        btn_del_pub_records.clicked.connect(self.on_delete_published_records)
        pub_bar_1.addWidget(btn_del_pub_records)
        layout_published.addLayout(pub_bar_1)

        pub_bar_2 = QHBoxLayout()
        pub_bar_2.setSpacing(8)

        btn_pub_play = QPushButton("▶ 播放本地视频 (若保留)")
        btn_pub_play.setProperty("class", "success")
        btn_pub_play.clicked.connect(self.on_play_clip)
        pub_bar_2.addWidget(btn_pub_play)

        btn_pub_edit = QPushButton("📝 查看文案与流量")
        btn_pub_edit.setProperty("class", "secondary")
        btn_pub_edit.clicked.connect(self.on_edit_clip_text)
        pub_bar_2.addWidget(btn_pub_edit)

        btn_pub_unpub = QPushButton("⏳ 改回待发布")
        btn_pub_unpub.setProperty("class", "secondary")
        btn_pub_unpub.setToolTip("将成片状态改回待发布，以便重新编辑文案或再次上传")
        btn_pub_unpub.clicked.connect(lambda: self.on_change_publish_status("pending"))
        pub_bar_2.addWidget(btn_pub_unpub)

        btn_pub_open_dir = QPushButton("📂 在文件管理器中定位")
        btn_pub_open_dir.setProperty("class", "secondary")
        btn_pub_open_dir.clicked.connect(self.on_open_selected_clip_dir)
        pub_bar_2.addWidget(btn_pub_open_dir)

        pub_bar_2.addStretch()
        layout_published.addLayout(pub_bar_2)
        layout.addWidget(self.box_published_ops)
        self.box_published_ops.setVisible(False)

    # --------------------------------------------------------------------------
    # Tab 5: 对标账号雷达与一键二创
    # --------------------------------------------------------------------------
    def build_tab_radar(self):
        layout = QHBoxLayout(self.tab_radar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 左侧：监控账号管理
        left_box = QGroupBox("对标账号关注清单")
        left_box.setFixedWidth(360)
        left_layout = QVBoxLayout(left_box)

        self.table_accounts = QTableWidget()
        self.table_accounts.setColumnCount(3)
        self.table_accounts.setHorizontalHeaderLabels(["账号名称", "平台", "主页 / 备注"])
        self.table_accounts.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_accounts.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table_accounts.setColumnWidth(1, 60)
        self.table_accounts.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table_accounts.setColumnWidth(2, 110)
        self.table_accounts.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_accounts.setEditTriggers(QAbstractItemView.NoEditTriggers)
        left_layout.addWidget(self.table_accounts)

        lbl_acc_note = QLabel(
            "说明：抖音网页存在反爬验证风控，无法静默抓取。此处管理重点对标账号清单，配合右侧同款搜索与跟剪使用。"
        )
        lbl_acc_note.setWordWrap(True)
        lbl_acc_note.setStyleSheet("color: #8e8e93; font-size: 11px;")
        left_layout.addWidget(lbl_acc_note)

        add_form = QFormLayout()
        self.txt_acc_name = QLineEdit()
        self.txt_acc_name.setPlaceholderText("如: 董路侃球")
        self.cmb_acc_platform = QComboBox()
        self.cmb_acc_platform.addItems(["douyin (抖音)", "kuaishou (快手)", "channels (视频号)", "xiaohongshu (小红书)"])
        self.txt_acc_id = QLineEdit()
        self.txt_acc_id.setPlaceholderText("主页链接或抖音号 (选填)")
        add_form.addRow("名称:", self.txt_acc_name)
        add_form.addRow("平台:", self.cmb_acc_platform)
        add_form.addRow("主页:", self.txt_acc_id)
        left_layout.addLayout(add_form)

        btn_add_acc = QPushButton("添加关注账号")
        btn_add_acc.setProperty("class", "secondary")
        btn_add_acc.clicked.connect(self.on_add_radar_account)
        left_layout.addWidget(btn_add_acc)

        btn_del_acc = QPushButton("删除选中账号")
        btn_del_acc.setProperty("class", "danger")
        btn_del_acc.clicked.connect(self.on_delete_radar_account)
        left_layout.addWidget(btn_del_acc)

        layout.addWidget(left_box)

        # 右侧：全素材库同款检索 + 爆款雷达 + 链接二创
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)

        # 1. 全素材库同款检索
        search_box = QGroupBox("素材库同款检索")
        search_v = QVBoxLayout(search_box)
        search_bar = QHBoxLayout()
        self.txt_radar_search = QLineEdit()
        self.txt_radar_search.setPlaceholderText("粘贴同行爆款标题或金句（如：不敢对抗就别谈留洋 / 45度防守）...")
        self.txt_radar_search.returnPressed.connect(self.on_search_radar_match)
        search_bar.addWidget(self.txt_radar_search, 1)

        self.btn_radar_search = QPushButton("搜索同款原片")
        self.btn_radar_search.setProperty("class", "primary")
        self.btn_radar_search.clicked.connect(self.on_search_radar_match)
        search_bar.addWidget(self.btn_radar_search)

        self.btn_cut_match = QPushButton("跟剪选中片段")
        self.btn_cut_match.setProperty("class", "primary")
        self.btn_cut_match.setEnabled(False)
        self.btn_cut_match.clicked.connect(self.on_cut_selected_match)
        search_bar.addWidget(self.btn_cut_match)
        search_v.addLayout(search_bar)

        self.table_radar_matches = QTableWidget()
        self.table_radar_matches.setColumnCount(5)
        self.table_radar_matches.setHorizontalHeaderLabels(["匹配度", "直播原片", "区间 / 时长", "原声片段摘要", "原片状态"])
        self.table_radar_matches.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for idx_c, w_c in [(0, 75), (1, 200), (2, 130), (4, 95)]:
            self.table_radar_matches.horizontalHeader().setSectionResizeMode(idx_c, QHeaderView.Interactive)
            self.table_radar_matches.setColumnWidth(idx_c, w_c)
        self.table_radar_matches.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_radar_matches.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_radar_matches.setMaximumHeight(150)
        self.table_radar_matches.cellDoubleClicked.connect(lambda r, c: self.on_cut_selected_match())
        search_v.addWidget(self.table_radar_matches)
        right_layout.addWidget(search_box)

        # 2. 标杆爆款列表与一键跟剪
        radar_box = QGroupBox("标杆爆款选题雷达")
        radar_v = QVBoxLayout(radar_box)

        top_info = QHBoxLayout()
        self.lbl_radar_status = QLabel("加载中...")
        self.lbl_radar_status.setStyleSheet("color: #8e8e93; font-size: 12px; font-weight: 500;")
        top_info.addWidget(self.lbl_radar_status)
        top_info.addStretch()

        btn_add_item = QPushButton("录入爆款")
        btn_add_item.setProperty("class", "secondary")
        btn_add_item.clicked.connect(self.on_add_radar_item)
        top_info.addWidget(btn_add_item)

        btn_shuffle = QPushButton("换一批热点")
        btn_shuffle.setProperty("class", "secondary")
        btn_shuffle.setToolTip("从标杆题库中随机轮换全新高赞选题，告别重复！")
        btn_shuffle.clicked.connect(self.on_shuffle_radar_items)
        top_info.addWidget(btn_shuffle)

        btn_discover = QPushButton("AI 挖掘新爆款")
        btn_discover.setProperty("class", "secondary")
        btn_discover.setToolTip("从本地高光转写片段中自动提炼全新高赞议题")
        btn_discover.clicked.connect(self.on_discover_radar_items)
        top_info.addWidget(btn_discover)

        btn_seed = QPushButton("载入标杆全库")
        btn_seed.setProperty("class", "secondary")
        btn_seed.clicked.connect(self.on_seed_radar_items)
        top_info.addWidget(btn_seed)

        btn_refresh_radar = QPushButton("刷新匹配")
        btn_refresh_radar.setProperty("class", "secondary")
        btn_refresh_radar.clicked.connect(self.refresh_radar_data)
        top_info.addWidget(btn_refresh_radar)
        radar_v.addLayout(top_info)

        self.table_radar_items = QTableWidget()
        self.table_radar_items.setColumnCount(5)
        self.table_radar_items.setHorizontalHeaderLabels([
            "对标账号", "点赞", "增速", "爆款标题", "素材库同款命中"
        ])
        self.table_radar_items.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for idx_c, w_c in [(0, 120), (1, 75), (2, 75), (4, 190)]:
            self.table_radar_items.horizontalHeader().setSectionResizeMode(idx_c, QHeaderView.Interactive)
            self.table_radar_items.setColumnWidth(idx_c, w_c)
        self.table_radar_items.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_radar_items.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_radar_items.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_radar_items.customContextMenuRequested.connect(self.on_radar_context_menu)
        self.table_radar_items.cellDoubleClicked.connect(lambda r, c: self.on_remix_radar_item())
        radar_v.addWidget(self.table_radar_items)

        radar_action_bar = QHBoxLayout()
        self.btn_remix = QPushButton("跟剪同款成片")
        self.btn_remix.setProperty("class", "primary")
        self.btn_remix.clicked.connect(self.on_remix_radar_item)
        radar_action_bar.addWidget(self.btn_remix)

        btn_search_sel = QPushButton("检索同款")
        btn_search_sel.setProperty("class", "secondary")
        btn_search_sel.clicked.connect(self.on_search_selected_radar_item)
        radar_action_bar.addWidget(btn_search_sel)

        btn_del_item = QPushButton("删除条目")
        btn_del_item.setProperty("class", "danger")
        btn_del_item.clicked.connect(self.on_delete_radar_item)
        radar_action_bar.addWidget(btn_del_item)

        radar_action_bar.addStretch()
        radar_v.addLayout(radar_action_bar)
        right_layout.addWidget(radar_box, 1)

        # 3. 外部视频/本地原片 Remix 二次创作
        remix_box = QGroupBox("外部视频同款二次创作")
        remix_bar = QHBoxLayout(remix_box)
        self.txt_remix_url = QLineEdit()
        self.txt_remix_url.setPlaceholderText("粘贴分享链接（如 https://v.douyin.com/...）或本地 .mp4 路径...")
        remix_bar.addWidget(self.txt_remix_url, 1)

        btn_pick_file = QPushButton("选择本地文件")
        btn_pick_file.setProperty("class", "secondary")
        btn_pick_file.clicked.connect(self.on_pick_remix_local_file)
        remix_bar.addWidget(btn_pick_file)

        self.btn_remix_url = QPushButton("一键二创入库")
        self.btn_remix_url.setProperty("class", "primary")
        self.btn_remix_url.clicked.connect(self.on_remix_url)
        remix_bar.addWidget(self.btn_remix_url)
        right_layout.addWidget(remix_box)

        layout.addLayout(right_layout, 1)

    # --------------------------------------------------------------------------
    # Tab 6: 系统设置
    # --------------------------------------------------------------------------
    def build_tab_settings(self):
        root_layout = QVBoxLayout(self.tab_settings)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 16, 0, 16)
        container_layout.addStretch()

        content_w = QWidget()
        content_w.setFixedWidth(840)
        layout = QVBoxLayout(content_w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # 界面主题设置
        ui_box = QGroupBox("界面外观与视觉风格")
        ui_form = QFormLayout(ui_box)
        ui_form.setSpacing(12)

        self.cmb_ui_theme = QComboBox()
        self.cmb_ui_theme.addItems([
            "浅色模式 (macOS 现代清爽 - 默认推荐)",
            "深色模式 (暗色沉浸)"
        ])
        self.cmb_ui_theme.setCurrentIndex(1 if self.current_is_dark else 0)
        self.cmb_ui_theme.currentIndexChanged.connect(self.on_ui_theme_changed)
        ui_form.addRow("界面主题:", self.cmb_ui_theme)
        layout.addWidget(ui_box)

        # AI 模型配置
        ai_box = QGroupBox("AI 语义分析与文案大模型配置")
        ai_form = QFormLayout(ai_box)
        ai_form.setSpacing(12)

        self.cmb_ai_provider = QComboBox()
        self.cmb_ai_provider.addItems(["本地 Ollama 模型", "云端 API (DeepSeek / 通义千问 / 硅基流动)"])
        self.cmb_ai_provider.currentIndexChanged.connect(self.on_ai_provider_changed)
        ai_form.addRow("AI 提供商:", self.cmb_ai_provider)

        self.txt_ai_model = QLineEdit()
        ai_form.addRow("模型名称:", self.txt_ai_model)

        self.txt_ai_base_url = QLineEdit()
        ai_form.addRow("API Base URL:", self.txt_ai_base_url)

        self.txt_ai_api_key = QLineEdit()
        self.txt_ai_api_key.setEchoMode(QLineEdit.Password)
        ai_form.addRow("API Key:", self.txt_ai_api_key)

        ai_btn_bar = QHBoxLayout()
        self.btn_test_ai = QPushButton("测试连接")
        self.btn_test_ai.setProperty("class", "secondary")
        self.btn_test_ai.setFixedSize(110, 32)
        self.btn_test_ai.clicked.connect(self.on_test_ai)
        ai_btn_bar.addWidget(self.btn_test_ai)

        btn_save_ai = QPushButton("保存配置")
        btn_save_ai.setProperty("class", "primary")
        btn_save_ai.setFixedSize(110, 32)
        btn_save_ai.clicked.connect(self.on_save_ai_config)
        ai_btn_bar.addWidget(btn_save_ai)
        ai_btn_bar.addStretch()
        ai_form.addRow("", ai_btn_bar)

        layout.addWidget(ai_box)

        # 重点词汇配置
        kw_box = QGroupBox("重点人名、行业热词与监控词列表")
        kw_layout = QVBoxLayout(kw_box)
        kw_layout.setContentsMargins(14, 14, 14, 14)
        kw_layout.setSpacing(10)

        self.txt_keywords = QTextEdit()
        self.txt_keywords.setPlaceholderText("每行一个重点词，例如：\n高光\n金句\n名场面\n干货\n互动\n争议")
        self.txt_keywords.setFixedHeight(120)
        kw_layout.addWidget(self.txt_keywords)

        btn_save_kw = QPushButton("保存重点监控词")
        btn_save_kw.setProperty("class", "secondary")
        btn_save_kw.setFixedSize(140, 32)
        btn_save_kw.clicked.connect(self.on_save_keywords)
        kw_layout.addWidget(btn_save_kw)

        layout.addWidget(kw_box)
        layout.addStretch()

        container_layout.addWidget(content_w)
        container_layout.addStretch()

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

        # 加载初始配置
        self.load_settings()

    # --------------------------------------------------------------------------
    # 底部控制台与实时任务日志
    # --------------------------------------------------------------------------
    def setup_log_console(self, splitter):
        console_widget = QWidget()
        layout = QVBoxLayout(console_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 控制台标题栏
        header = QHBoxLayout()
        self.lbl_task_status = QLabel("● 就绪")
        idle_color = "#94a3b8" if self.current_is_dark else "#475569"
        self.lbl_task_status.setStyleSheet(f"color: {idle_color}; font-weight: 600; font-size: 12px;")
        header.addWidget(self.lbl_task_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setMinimumWidth(240)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setVisible(False)
        self.update_progress_bar_style(self.current_is_dark)
        header.addWidget(self.progress_bar, 1)

        # 任务实时进度与耗时刷新状态
        self._active_task_mode = None  # None | "proc" | "async"
        self._current_task_pct = -1
        self._current_task_detail = ""
        self._outer_idx = 0
        self._outer_total = 0
        self._proc_line_buf = ""
        self.task_elapsed_timer = QTimer(self)
        self.task_elapsed_timer.setInterval(500)
        self.task_elapsed_timer.timeout.connect(self._update_task_progress_ui)

        header.addStretch(1)

        self.btn_stop_task = QPushButton("停止任务")
        self.btn_stop_task.setProperty("class", "danger")
        self.btn_stop_task.setFixedSize(85, 28)
        self.btn_stop_task.setEnabled(False)
        self.btn_stop_task.clicked.connect(self.on_stop_task)
        header.addWidget(self.btn_stop_task)

        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.setProperty("class", "secondary")
        btn_clear_log.setFixedSize(85, 28)
        btn_clear_log.clicked.connect(lambda: self.log_view.clear())
        header.addWidget(btn_clear_log)

        btn_copy_log = QPushButton("复制日志")
        btn_copy_log.setProperty("class", "secondary")
        btn_copy_log.setFixedSize(85, 28)
        btn_copy_log.clicked.connect(self.on_copy_log)
        header.addWidget(btn_copy_log)

        layout.addLayout(header)

        # 实时日志输出框 (升级为极速 QPlainTextEdit，并限制最大 3000 行，释放 DOM 开销)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.update_log_view_style(self.current_is_dark)
        layout.addWidget(self.log_view)

        splitter.addWidget(console_widget)

    def update_log_view_style(self, is_dark=False):
        self.log_view.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1c1c1e;
                color: #e5e5ea;
                border: 1px solid rgba(0, 0, 0, 0.15);
                border-radius: 8px;
                font-family: -apple-system-monospaced, Menlo, "SF Mono", "DejaVu Sans Mono", "Courier New", monospace;
                font-size: 12px;
                line-height: 145%;
                padding: 8px;
                selection-background-color: #0a84ff;
                selection-color: #ffffff;
            }
        """)

    def update_progress_bar_style(self, is_dark=False):
        if is_dark:
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #1e293b;
                    color: #f8fafc;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #0284c7;
                    border-radius: 5px;
                }
            """)
        else:
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #e2e8f0;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #7dd3fc;
                    border-radius: 5px;
                }
            """)

    def on_ui_theme_changed(self, idx):
        is_dark = (idx == 1)
        self.current_is_dark = is_dark
        self.setStyleSheet(DARK_STYLE if is_dark else LIGHT_STYLE)

        # 更新卡片主题
        for c in [self.card_sources, self.card_waiting, self.card_analyzed,
                  self.card_clips, self.card_publish, self.card_storage]:
            c.apply_theme(is_dark)

        # 更新控制台样式
        self.update_log_view_style(is_dark)
        self.update_progress_bar_style(is_dark)

        # 更新状态标签颜色（空闲时）
        if self.current_process is None or self.current_process.state() != QProcess.Running:
            idle_color = "#94a3b8" if is_dark else "#475569"
            self.lbl_task_status.setStyleSheet(f"color: {idle_color}; font-weight: bold; font-size: 13px;")

        # 更新指引文本与横幅说明
        if hasattr(self, "lbl_guide"):
            self.lbl_guide.setStyleSheet(
                "color: #cbd5e1; line-height: 160%; font-size: 13px;" if is_dark
                else "color: #475569; line-height: 160%; font-size: 13px;"
            )
        if hasattr(self, "lbl_hero_desc"):
            self.lbl_hero_desc.setStyleSheet(
                "color: #94a3b8; font-size: 13px; line-height: 150%;" if is_dark
                else "color: #475569; font-size: 13px; line-height: 150%;"
            )
        if hasattr(self, "lbl_cleanable_desc"):
            self.lbl_cleanable_desc.setStyleSheet(
                "color: #94a3b8; font-size: 13px;" if is_dark
                else "color: #475569; font-size: 13px;"
            )
        if hasattr(self, "lbl_global_badge"):
            self.lbl_global_badge.setStyleSheet(
                "background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
                if is_dark else
                "background-color: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )

        # 保存偏好到 config.json
        try:
            cfg_path = APP_DIR / "config.json"
            cfg = dashboard_server.read_json(cfg_path, {})
            cfg["ui_theme"] = "dark" if is_dark else "light"
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("保存主题偏好失败:", e)

        # 刷新表格徽章配色
        self.filter_sources_table()
        self.filter_candidates_table()
        self.filter_clips_table()
        self.refresh_radar_data()

    # --------------------------------------------------------------------------
    # 异步多任务执行机制 (QProcess) 与实时进度解析调度
    # --------------------------------------------------------------------------
    def _format_elapsed(self, seconds):
        s = max(0, int(seconds))
        m, sec = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{sec:02d}" if h > 0 else f"{m:02d}:{sec:02d}"

    def _update_task_progress_ui(self):
        if self._active_task_mode is None:
            self.task_elapsed_timer.stop()
            return
        elapsed_str = self._format_elapsed(time.time() - self.start_time)
        pct = self._current_task_pct
        detail = self._current_task_detail

        if pct >= 0:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{pct}% · 已用时 {elapsed_str}")
            badge_txt = f"⚡ {pct}% 处理中"
        else:
            if self.progress_bar.maximum() != 0:
                self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat(f"处理中 · {elapsed_str}")
            badge_txt = "⚡ 处理中"

        short_detail = f" · {detail}" if detail else ""
        pct_prefix = f"[{pct}%] " if pct >= 0 else ""
        self.lbl_task_status.setText(f"🟢 {pct_prefix}{self.current_action_name}{short_detail} (已用时 {elapsed_str})")
        if hasattr(self, "lbl_global_badge"):
            self.lbl_global_badge.setText(badge_txt)

    def _parse_progress_line(self, line):
        line = line.strip()
        if not line:
            return

        # 1. 优先识别显式进度标记: [PROGRESS] 42% | 说明...
        m_prog = re.match(r"^\[PROGRESS\]\s*(\d+)%\s*\|\s*(.+)$", line)
        if m_prog:
            pct = max(0, min(100, int(m_prog.group(1))))
            detail = m_prog.group(2).strip()
            # 若为 batch 转写或批量发布子进程，按外层序号与当前项内部进度平滑加权计算总进度
            if self._outer_total > 1 and detail.startswith((
                "转写音频", "语音识别", "打开抖音", "上传视频",
                "填写标题", "选择AI", "设置作品", "等待预审", "发布完成", "自动填写完成",
            )) and self._outer_idx >= 1:
                overall = int(((self._outer_idx - 1) + pct / 100.0) * 100.0 / self._outer_total)
                self._current_task_pct = max(0, min(99, overall))
                self._current_task_detail = f"[{self._outer_idx}/{self._outer_total}] {detail}"
            else:
                self._current_task_pct = pct
                self._current_task_detail = detail
            self._update_task_progress_ui()
            return

        # 2. 记录外层批量任务计数 [i/N] 处理：xxx / [i/N] 自动准备发布：xxx
        m_outer = re.match(r"^\[(\d+)/(\d+)\]\s*(.*)$", line)
        if m_outer:
            idx = int(m_outer.group(1))
            total = max(1, int(m_outer.group(2)))
            desc = m_outer.group(3).strip()
            if "处理：" in desc or "自动准备发布：" in desc or desc == "":
                self._outer_idx = idx
                self._outer_total = total
            if total > 0:
                if self._outer_total <= 1:
                    self._current_task_pct = min(99, int((idx - 1) * 100 / total))
                if desc:
                    self._current_task_detail = f"[{idx}/{total}] {desc[:28]}"
                self._update_task_progress_ui()
            return

        # 3. 识别阶段性关键行
        if line.startswith(("加载 VAD", "加载 SenseVoiceSmall", "FFmpeg 提取音频", "扫描完成", "待处理视频总数：", "待检查视频：")):
            self._current_task_detail = line[:42]
            self._update_task_progress_ui()

    def _parse_progress_from_chunk(self, chunk_text):
        clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", chunk_text)
        buf = self._proc_line_buf + clean
        parts = re.split(r"[\r\n]+", buf)
        if clean.endswith(("\n", "\r")):
            self._proc_line_buf = ""
            lines = parts
        else:
            self._proc_line_buf = parts[-1]
            lines = parts[:-1]
        for line in lines:
            self._parse_progress_line(line)

    def start_async_progress(self, title):
        """供 QThread 异步任务（二创/同款跟剪/清理/队列同步）绑定底部实时进度条"""
        if self._active_task_mode == "proc":
            return
        self._active_task_mode = "async"
        self.current_action_name = title
        self.start_time = time.time()
        self._current_task_pct = 5
        self._current_task_detail = "初始化任务..."
        self.lbl_task_status.setStyleSheet("color: #059669; font-weight: bold; font-size: 13px;")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(5)
        self.progress_bar.setVisible(True)
        if hasattr(self, "lbl_global_badge"):
            self.lbl_global_badge.setStyleSheet(
                "background-color: #3b2814; color: #fbbf24; border: 1px solid #78350f; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
                if self.current_is_dark else
                "background-color: #fefce8; color: #a16207; border: 1px solid #fef08a; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )
        self._update_task_progress_ui()
        self.task_elapsed_timer.start()

    def update_async_progress(self, pct, msg=""):
        if self._active_task_mode != "async":
            return
        self._current_task_pct = max(0, min(100, int(pct)))
        if msg:
            self._current_task_detail = msg
        self._update_task_progress_ui()

    def finish_async_progress(self, ok=True, summary_msg=""):
        if self._active_task_mode == "proc":
            return
        self.task_elapsed_timer.stop()
        self._active_task_mode = None
        if ok:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("100% 完成")
            self.lbl_task_status.setText(summary_msg or f"⚪ 已就绪 (任务完成于 {time.strftime('%H:%M:%S')})")
            idle_color = "#94a3b8" if self.current_is_dark else "#475569"
            self.lbl_task_status.setStyleSheet(f"color: {idle_color}; font-weight: bold; font-size: 13px;")
            if hasattr(self, "lbl_global_badge"):
                self.lbl_global_badge.setText("🟢 系统就绪")
                self.lbl_global_badge.setStyleSheet(
                    "background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
                    if self.current_is_dark else
                    "background-color: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
                )
        else:
            self.lbl_task_status.setText(summary_msg or "🔴 异步任务失败")
            self.lbl_task_status.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 13px;")
            if hasattr(self, "lbl_global_badge"):
                self.lbl_global_badge.setText("🔴 任务异常")
        QTimer.singleShot(1500, lambda: self.progress_bar.setVisible(False) if self._active_task_mode is None else None)

    def run_subcommand(self, action_name, cmd_list, display_title, is_auto_pipeline=False):
        if self.current_process and self.current_process.state() == QProcess.Running:
            QMessageBox.warning(self, "任务冲突", f"当前正有任务正在运行中：{self.current_action_name}\n请等待完成或点击停止。")
            return

        self.is_running_auto_pipeline = is_auto_pipeline
        self.current_action_name = display_title
        self.start_time = time.time()
        self._active_task_mode = "proc"
        self._current_task_pct = -1
        self._current_task_detail = "正在启动子进程..."
        self._outer_idx = 0
        self._outer_total = 0
        self._proc_line_buf = ""

        self.lbl_task_status.setStyleSheet("color: #059669; font-weight: bold; font-size: 13px;")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.btn_stop_task.setEnabled(True)

        if hasattr(self, "lbl_global_badge"):
            self.lbl_global_badge.setStyleSheet(
                "background-color: #3b2814; color: #fbbf24; border: 1px solid #78350f; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
                if self.current_is_dark else
                "background-color: #fefce8; color: #a16207; border: 1px solid #fef08a; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )

        self._update_task_progress_ui()
        self.task_elapsed_timer.start()

        self.append_log(f"\n==================================================")
        self.append_log(f"🚀 开始执行任务：{display_title} [{time.strftime('%H:%M:%S')}]")
        self.append_log(f"执行命令: {' '.join(cmd_list)}")
        self.append_log(f"==================================================\n")

        self.current_process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PATH", f"{CONDA_PATHS}:{env.value('PATH')}")
        self.current_process.setProcessEnvironment(env)
        self.current_process.setWorkingDirectory(str(APP_DIR))

        self.current_process.readyReadStandardOutput.connect(self.on_proc_stdout)
        self.current_process.readyReadStandardError.connect(self.on_proc_stderr)
        self.current_process.finished.connect(self.on_proc_finished)

        # 优先使用 nice -n 10 降低计算子任务优先级，保证系统 UI 界面和音频绝对流畅，杜绝多任务卡顿
        exec_cmd = cmd_list[0]
        exec_args = cmd_list[1:]
        if shutil.which("nice"):
            exec_args = ["-n", "10", exec_cmd] + exec_args
            exec_cmd = "nice"

        self.current_process.start(exec_cmd, exec_args)

    def on_proc_stdout(self):
        if not self.current_process:
            return
        data = self.current_process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._parse_progress_from_chunk(data)
        self.append_log(data)

    def on_proc_stderr(self):
        if not self.current_process:
            return
        data = self.current_process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._parse_progress_from_chunk(data)
        self.append_log(data)

    def on_proc_finished(self, exit_code, exit_status):
        self.flush_log_buffer()
        self.task_elapsed_timer.stop()
        self._active_task_mode = None
        cost = time.time() - self.start_time
        if exit_code == 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat(f"100% 完成 ({cost:.1f}s)")
            self.append_log(f"\n✅ 任务完成：{self.current_action_name} (耗时: {cost:.1f} 秒)")
            # 检查全自动流水线
            if getattr(self, "is_running_auto_pipeline", False) and self.pipeline_steps:
                self.pipeline_current_step += 1
                if self.pipeline_current_step < len(self.pipeline_steps):
                    QTimer.singleShot(1000, self.run_next_pipeline_step)
                    return
                else:
                    self.is_running_auto_pipeline = False
                    self.run_next_pipeline_step()
                    return

            self.lbl_task_status.setText(f"⚪ 已就绪 (上一次任务完成于 {time.strftime('%H:%M:%S')} · 耗时 {cost:.1f}s)")
            idle_color = "#94a3b8" if self.current_is_dark else "#475569"
            self.lbl_task_status.setStyleSheet(f"color: {idle_color}; font-weight: bold; font-size: 13px;")
            if hasattr(self, "lbl_global_badge"):
                self.lbl_global_badge.setText("🟢 系统就绪")
                self.lbl_global_badge.setStyleSheet(
                    "background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
                    if self.current_is_dark else
                    "background-color: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
                )
        else:
            self.is_running_auto_pipeline = False
            self.pipeline_steps = []
            self.append_log(f"\n❌ 任务失败退出，返回码: {exit_code}")
            self.lbl_task_status.setText(f"🔴 任务异常退出 (返回码 {exit_code})")
            self.lbl_task_status.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 13px;")
            if hasattr(self, "lbl_global_badge"):
                self.lbl_global_badge.setText("🔴 任务异常")
                self.lbl_global_badge.setStyleSheet(
                    "background-color: #3b1818; color: #f87171; border: 1px solid #7f1d1d; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
                    if self.current_is_dark else
                    "background-color: #fef2f2; color: #dc2626; border: 1px solid #fecaca; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
                )

        QTimer.singleShot(1500, lambda: self.progress_bar.setVisible(False) if self._active_task_mode is None else None)
        self.btn_stop_task.setEnabled(False)
        self.current_process = None

        # 任务完成后自动刷新全局数据
        self.refresh_all_data()

    def on_stop_task(self):
        if self.current_process and self.current_process.state() == QProcess.Running:
            if QMessageBox.question(self, "确认停止", f"确定要终止正在运行的任务吗？\n{self.current_action_name}") == QMessageBox.Yes:
                self.is_running_auto_pipeline = False
                self.pipeline_steps = []
                self.current_process.terminate()
                QTimer.singleShot(2000, lambda: self.current_process.kill() if self.current_process else None)
                self.append_log("\n⚠️ 用户手动中断了任务。\n")

    # --------------------------------------------------------------------------
    # 一键全自动切片流水线调度
    # --------------------------------------------------------------------------
    def on_action_auto_pipeline(self):
        if self.current_process and self.current_process.state() == QProcess.Running:
            QMessageBox.warning(self, "任务进行中", f"当前已有任务正在执行：{self.current_action_name}\n请等待完成或点击下方停止。")
            return

        reply = QMessageBox.question(
            self,
            "启动一键全自动切片流水线",
            "【全自动切片出片模式】将依次自动执行：\n\n"
            "  1. 扫描录像新素材 (scan)\n"
            "  2. SenseVoice 批量语音转写 (GPU 加速识别)\n"
            "  3. AI 爆款高光智能分析 (挖掘 70+ 分精彩切片)\n"
            "  4. FFmpeg 批量精准剪辑高清成片\n"
            "  5. 同步至发布队列\n\n"
            "确认立即开始全自动流水线吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        python = get_python()
        self.pipeline_steps = [
            ("扫描录像新素材", [python, "-u", str(APP_DIR / "video_screen.py"), "scan"]),
            ("SenseVoice 批量语音转写", [python, "-u", str(APP_DIR / "video_screen.py"), "batch"]),
            ("AI 爆款大模型高光分析", [python, "-u", str(APP_DIR / "analyze_videos.py")]),
            ("FFmpeg 批量精准剪辑成片", [python, "-u", str(APP_DIR / "prepare_clips.py"), "--min-duration", "60", "--max-duration", "600", "--cut"]),
        ]
        self.pipeline_current_step = 0
        self.run_next_pipeline_step()

    def run_next_pipeline_step(self):
        if self.pipeline_current_step < len(self.pipeline_steps):
            name, cmd = self.pipeline_steps[self.pipeline_current_step]
            step_num = self.pipeline_current_step + 1
            total_steps = len(self.pipeline_steps)
            display_title = f"[流水线 {step_num}/{total_steps}] {name}"
            self.run_subcommand("auto_step", cmd, display_title, is_auto_pipeline=True)
        else:
            self.pipeline_steps = []
            self.pipeline_current_step = 0
            self.is_running_auto_pipeline = False
            try:
                import publish_assistant
                publish_assistant.sync_queue()
            except Exception as e:
                print("同步队列异常:", e)
            self.refresh_all_data()
            self.append_log("\n🎉🎉🎉 【全自动切片流水线】已圆满完成全流程！所有高清成片已就绪！\n")
            QMessageBox.information(self, "全自动流水线完成", "🎉 恭喜！全自动切片流水线已全部执行完成！\n成片与发布队列已更新完毕，可直接查看或发布。")

    def append_log(self, raw_text):
        if not raw_text:
            return
        clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_text)
        self.log_buffer.append(clean)

    def flush_log_buffer(self):
        if not self.log_buffer:
            return
        combined = "".join(self.log_buffer)
        self.log_buffer.clear()

        # 处理终端进度条的 \r 回车单行覆盖
        lines = combined.split("\n")
        processed_lines = []
        for line in lines:
            if "\r" in line:
                line = line.split("\r")[-1]
            processed_lines.append(line)
        final_text = "\n".join(processed_lines)

        self.log_view.appendPlainText(final_text.rstrip("\r\n"))

    def on_copy_log(self):
        text = self.log_view.toPlainText()
        if not text:
            QMessageBox.information(self, "提示", "当前控制台无日志内容。")
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "复制成功", "完整运行日志已复制到系统剪贴板！")

    # --------------------------------------------------------------------------
    # 各流水线操作触发函数
    # --------------------------------------------------------------------------
    def on_action_scan(self):
        python = get_python()
        self.run_subcommand("scan", [python, "-u", str(APP_DIR / "video_screen.py"), "scan"], "扫描录像新素材")

    def on_action_transcribe(self):
        python = get_python()
        self.run_subcommand("transcribe", [python, "-u", str(APP_DIR / "video_screen.py"), "batch"], "SenseVoice 批量语音转写")

    def on_action_analyze(self):
        python = get_python()
        self.run_subcommand("analyze", [python, "-u", str(APP_DIR / "analyze_videos.py")], "AI 大模型高光语义分析")

    def on_action_cut(self):
        python = get_python()
        self.run_subcommand("cut", [
            python, "-u", str(APP_DIR / "prepare_clips.py"),
            "--min-duration", "60", "--max-duration", "600", "--cut"
        ], "FFmpeg 批量精准剪辑成片")

    def on_action_sync_queue(self):
        self.start_async_progress("同步发布队列")
        self.append_log("\n🔄 正在异步同步发布队列...\n")

        def _do_sync(progress_cb=None):
            if progress_cb:
                progress_cb(30, "读取成片清单与发布队列...")
            import publish_assistant
            q = publish_assistant.sync_queue()
            if progress_cb:
                progress_cb(100, f"同步完成 ({len(q)} 条成片)")
            return q

        def _ok(queue):
            self.finish_async_progress(True, f"⚪ 已就绪 · 发布队列同步完成 ({len(queue)} 条)")
            if self._is_closing:
                return
            self.append_log(f"✅ 发布队列同步完成！当前成片数: {len(queue)}\n")
            QMessageBox.information(self, "成功", f"发布队列已完成同步！当前成片数: {len(queue)}")
            self.refresh_all_data()

        def _err(err):
            self.finish_async_progress(False, "🔴 发布队列同步失败")
            if self._is_closing:
                return
            self.append_log(f"❌ 同步发布队列失败: {err}\n")
            QMessageBox.critical(self, "同步失败", str(err))

        run_async_task(_do_sync, _ok, _err, on_progress=self.update_async_progress)

    def on_action_cleanup(self):
        try:
            overview = dashboard_server.build_overview()
            cleanable = [x["path"] for x in overview.get("sources", []) if x.get("stage") == "ready" and x.get("exists")]
            gb = overview.get("storage", {}).get("cleanable_gb", 0.0)
            if not cleanable:
                QMessageBox.information(self, "提示", "当前没有可清理的已剪辑原素材。")
                return

            msg = f"共发现 {len(cleanable)} 场已剪辑完成的直播原片，可安全清理释放约 {gb} GB 磁盘空间！\n\n注意：清理后原始录像将移入回收站，字幕与已剪切片将完好保留。\n确定要清理吗？"
            if QMessageBox.question(self, "确认清理原片", msg) == QMessageBox.Yes:
                self.start_async_progress(f"清理 {len(cleanable)} 个已剪原片")
                self.append_log(f"\n🧹 正在异步清理 {len(cleanable)} 个已剪辑原素材...\n")

                def _do_clean(paths, progress_cb=None):
                    deleted = []
                    failed = []
                    total = max(1, len(paths))
                    for i, src_p in enumerate(paths, 1):
                        if progress_cb:
                            progress_cb(int((i - 1) * 100 / total), f"清理 [{i}/{total}] {Path(src_p).name[:24]}")
                        try:
                            r = dashboard_server.cleanup_source(src_p)
                            deleted.append(r["source"])
                        except Exception as ex:
                            failed.append({"source": src_p, "error": str(ex)})
                    if progress_cb:
                        progress_cb(100, f"清理完成 ({len(deleted)} 个)")
                    return {"deleted": deleted, "failed": failed}

                def _ok(res):
                    self.finish_async_progress(True, f"⚪ 已就绪 · 已安全清理 {len(res['deleted'])} 个原素材")
                    if self._is_closing:
                        return
                    self.append_log(f"✅ 清理完成，已移除 {len(res['deleted'])} 个原素材！\n")
                    QMessageBox.information(self, "清理完成", f"已成功清理 {len(res['deleted'])} 个超大原素材！")
                    self.refresh_all_data()

                def _err(err):
                    self.finish_async_progress(False, "🔴 清理原素材失败")
                    if self._is_closing:
                        return
                    self.append_log(f"❌ 清理失败: {err}\n")
                    QMessageBox.critical(self, "清理失败", str(err))

                run_async_task(_do_clean, _ok, _err, cleanable, on_progress=self.update_async_progress)
        except Exception as e:
            QMessageBox.critical(self, "清理失败", str(e))

    def on_auto_refresh_overview(self):
        # 若正在关闭、已有异步刷新、或正在打开模态弹窗（如 AI 生成文案），跳过后台刷新以免抢占锁
        if self._is_closing or self._is_refreshing_overview or QApplication.activeModalWidget() is not None:
            return
        self._is_refreshing_overview = True

        def _ok(overview):
            self._is_refreshing_overview = False
            if not self._is_closing:
                self.refresh_overview_data(overview)

        def _err(_err):
            self._is_refreshing_overview = False

        run_async_task(dashboard_server.build_overview, _ok, _err)

    # --------------------------------------------------------------------------
    # 数据加载与表格刷新
    # --------------------------------------------------------------------------
    def refresh_all_data(self):
        try:
            overview = dashboard_server.build_overview()
            self.refresh_overview_data(overview)
            self.refresh_sources_table(overview)
            self.refresh_candidates_table()
            self.refresh_clips_table(overview)
            self.refresh_radar_data()
        except Exception as e:
            print("全局刷新异常:", e)

    def refresh_overview_data(self, data=None):
        try:
            if data is None:
                data = dashboard_server.build_overview()
            counts = data.get("counts", {})
            storage = data.get("storage", {})

            self.card_sources.set_value(counts.get("sources", 0), "已扫描录制场次")
            self.card_waiting.set_value(counts.get("waiting", 0), "待进行语音转写")
            self.card_analyzed.set_value(counts.get("analyzed", 0), "AI 高光已提取")
            self.card_clips.set_value(counts.get("clips", 0), "高清成片总数")
            self.card_publish.set_value(counts.get("douyin_pending", 0), "抖音待发布视频")

            free_gb = storage.get("disk_free_gb", 0)
            clean_gb = storage.get("cleanable_gb", 0)
            clips_gb = storage.get("clips_total_gb", 0)
            self.card_storage.set_value(f"{free_gb:.1f} GB", f"成片 {clips_gb:.1f}G · 可释放 {clean_gb:.1f}G")
            self.card_storage.setToolTip(f"磁盘剩余空间: {free_gb:.1f} GB\n成片目录占用: {clips_gb:.1f} GB\n已剪辑原素材可释放: {clean_gb:.1f} GB")

            clean_count = len([x for x in data.get("sources", []) if x.get("stage") == "ready" and x.get("exists")])
            if hasattr(self, "lbl_cleanable_desc"):
                if clean_count > 0:
                    self.lbl_cleanable_desc.setText(
                        f"检测到 <b>{clean_count}</b> 场已完成剪辑的直播原片，可安全清理释放约 <b>{clean_gb:.1f} GB</b> 磁盘空间（字幕与成片仍完好保留）。"
                    )
                else:
                    self.lbl_cleanable_desc.setText("当前暂无可清理的已剪辑原片，录像素材库存储状态良好。")
        except Exception as e:
            print("刷新概览数据异常:", e)

    def refresh_sources_table(self, overview=None):
        try:
            if overview is None:
                overview = dashboard_server.build_overview()
            sources = overview.get("sources", [])
            self.all_sources = sources
            self.filter_sources_table()
        except Exception as e:
            print("加载素材列表异常:", e)

    def filter_sources_table(self):
        if not hasattr(self, "all_sources"):
            return
        kw = self.txt_source_search.text().strip().lower()
        status_filter = self.cmb_source_filter.currentText()

        filtered = []
        for s in self.all_sources:
            name = s.get("name", "").lower()
            if kw and kw not in name:
                continue
            stage = s.get("stage", "")
            if status_filter == "待转写" and stage != "waiting":
                continue
            if status_filter == "已转写" and stage not in ("transcribed", "analyzed", "ready"):
                continue
            if status_filter == "已分析" and stage not in ("analyzed", "ready"):
                continue
            if status_filter == "已剪辑" and stage != "ready":
                continue
            if status_filter == "原片已清理" and stage != "source_deleted":
                continue
            if status_filter == "无音轨" and stage != "no_audio":
                continue
            if status_filter == "失败" and stage not in ("failed", "no_audio"):
                continue
            filtered.append(s)

        self.table_sources.setUpdatesEnabled(False)
        try:
            self.table_sources.setRowCount(len(filtered))
            is_dark = getattr(self, "current_is_dark", False)
            stage_map_light = {
                "waiting": ("● 待转写", "#d97706"),
                "transcribed": ("● 已转写", "#0284c7"),
                "analyzed": ("● 已分析", "#059669"),
                "ready": ("● 已剪辑", "#7c3aed"),
                "source_deleted": ("● 原片已清理", "#8e8e93"),
                "no_audio": ("● 无音轨", "#8e8e93"),
                "failed": ("● 失败", "#dc2626"),
                "published": ("● 全部发布", "#059669"),
            }
            stage_map_dark = {
                "waiting": ("● 待转写", "#f59e0b"),
                "transcribed": ("● 已转写", "#38bdf8"),
                "analyzed": ("● 已分析", "#10b981"),
                "ready": ("● 已剪辑", "#a78bfa"),
                "source_deleted": ("● 原片已清理", "#98989d"),
                "no_audio": ("● 无音轨", "#98989d"),
                "failed": ("● 失败", "#ef4444"),
                "published": ("● 全部发布", "#10b981"),
            }
            stage_map = stage_map_dark if is_dark else stage_map_light
            default_color = "#f8fafc" if is_dark else "#0f172a"

            for row_idx, s in enumerate(filtered):
                size_mb = s.get("size", 0) / (1024 * 1024)
                stage_text, stage_color = stage_map.get(s.get("stage"), (s.get("stage"), default_color))
                err_tip = str(s.get("error") or "").strip()

                item_name = QTableWidgetItem(s.get("name", ""))
                item_name.setData(Qt.UserRole, s)
                item_size = QTableWidgetItem(f"{size_mb:.1f}")
                item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item_stage = QTableWidgetItem(stage_text)
                item_stage.setForeground(QColor(stage_color))
                item_stage.setTextAlignment(Qt.AlignCenter)
                if err_tip:
                    item_stage.setToolTip(err_tip)
                    item_name.setToolTip(err_tip)
                item_cands = QTableWidgetItem(str(s.get("candidate_count", 0)))
                item_cands.setTextAlignment(Qt.AlignCenter)
                item_clips = QTableWidgetItem(str(s.get("clip_count", 0)))
                item_clips.setTextAlignment(Qt.AlignCenter)
                item_exists = QTableWidgetItem("存在" if s.get("exists") else "已删除")
                item_exists.setTextAlignment(Qt.AlignCenter)
                item_path = QTableWidgetItem(s.get("path", ""))

                self.table_sources.setItem(row_idx, 0, item_name)
                self.table_sources.setItem(row_idx, 1, item_size)
                self.table_sources.setItem(row_idx, 2, item_stage)
                self.table_sources.setItem(row_idx, 3, item_cands)
                self.table_sources.setItem(row_idx, 4, item_clips)
                self.table_sources.setItem(row_idx, 5, item_exists)
                self.table_sources.setItem(row_idx, 6, item_path)
        finally:
            self.table_sources.setUpdatesEnabled(True)

    def on_retry_selected_source(self):
        row = self.table_sources.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在表格中点击选择一个素材。")
            return
        s = self.table_sources.item(row, 0).data(Qt.UserRole)
        source_path = s["path"]
        python = get_python()
        self.run_subcommand("retry_source", [
            python, "-u", str(APP_DIR / "video_screen.py"),
            "batch", "--path", source_path, "--limit", "1"
        ], f"重试转写素材: {Path(source_path).name}")

    def on_view_selected_transcript(self):
        row = self.table_sources.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在表格中点击选择一个素材。")
            return
        s = self.table_sources.item(row, 0).data(Qt.UserRole)
        transcript_path = s.get("transcript_path", "")
        if not transcript_path or not Path(transcript_path).is_file():
            QMessageBox.warning(self, "提示", "该素材尚未生成有效的转写结果。")
            return
        dlg = TranscriptDialog(s.get("name", ""), transcript_path, self, is_dark=self.current_is_dark)
        dlg.exec_()

    def on_open_selected_source_dir(self):
        row = self.table_sources.currentRow()
        if row < 0:
            return
        s = self.table_sources.item(row, 0).data(Qt.UserRole)
        p = Path(s["path"])
        if p.parent.is_dir():
            subprocess.Popen(["xdg-open", str(p.parent)])

    def on_clean_selected_source(self):
        row = self.table_sources.currentRow()
        if row < 0:
            return
        s = self.table_sources.item(row, 0).data(Qt.UserRole)
        if s.get("stage") != "ready":
            QMessageBox.warning(self, "无法清理", "只有【已剪辑】出成片的原始素材才可以清理。")
            return
        if QMessageBox.question(self, "确认清理", f"确定清理原片吗？\n{s['name']}") == QMessageBox.Yes:
            try:
                dashboard_server.cleanup_source(s["path"])
                QMessageBox.information(self, "成功", "原素材已清理！")
                self.refresh_all_data()
            except Exception as e:
                QMessageBox.critical(self, "失败", str(e))

    def on_sources_context_menu(self, pos):
        item = self.table_sources.itemAt(pos)
        if not item:
            return
        row = item.row()
        self.table_sources.selectRow(row)
        s = self.table_sources.item(row, 0).data(Qt.UserRole)
        if not s:
            return

        menu = QMenu(self)
        act_view = menu.addAction("📄 查看转写字幕内容 (或双击行)")
        act_view.triggered.connect(self.on_view_selected_transcript)

        act_retry = menu.addAction("🎙️ 单独转写 / 重新转写")
        act_retry.triggered.connect(self.on_retry_selected_source)

        act_open_dir = menu.addAction("📂 在文件管理器中打开所在目录")
        act_open_dir.triggered.connect(self.on_open_selected_source_dir)

        menu.addSeparator()

        act_clean = menu.addAction("🧹 清理该原素材 (已剪辑)")
        act_clean.triggered.connect(self.on_clean_selected_source)
        if s.get("stage") != "ready":
            act_clean.setEnabled(False)

        menu.exec_(QCursor.pos())

    def refresh_candidates_table(self):
        csv_path = APP_DIR / "ai_analysis" / "candidates.csv"
        rows = dashboard_server.read_csv(csv_path)
        self.all_candidates = rows
        self.filter_candidates_table()

    def filter_candidates_table(self):
        if not hasattr(self, "all_candidates"):
            return
        kw = self.txt_cand_search.text().strip().lower()
        score_filter = self.cmb_cand_score.currentText()
        min_score = 0
        if ">= 80" in score_filter:
            min_score = 80
        elif ">= 75" in score_filter:
            min_score = 75
        elif ">= 70" in score_filter:
            min_score = 70

        filtered = []
        for c in self.all_candidates:
            title = c.get("title", "").lower()
            topic = c.get("topic", "").lower()
            terms = c.get("matched_terms", "").lower()
            if kw and (kw not in title and kw not in topic and kw not in terms):
                continue
            score = float(c.get("score", 0))
            if score < min_score:
                continue
            filtered.append(c)

        # 排序与随机换一批探索
        sort_opt = self.cmb_cand_sort.currentText() if hasattr(self, "cmb_cand_sort") else "评分最高优先"
        if "最新录像" in sort_opt:
            filtered.sort(key=lambda x: str(x.get("video", x.get("video_path", ""))), reverse=True)
        elif "随机探索" in sort_opt or "换一批" in sort_opt:
            import random
            random.shuffle(filtered)
        else:
            filtered.sort(key=lambda x: float(x.get("score", 0) or 0), reverse=True)

        self.table_candidates.setUpdatesEnabled(False)
        try:
            self.table_candidates.setRowCount(len(filtered))
            is_dark = getattr(self, "current_is_dark", False)
            for i, c in enumerate(filtered):
                score = int(float(c.get("score", 0)))
                if is_dark:
                    color = "#10b981" if score >= 85 else ("#38bdf8" if score >= 80 else "#f59e0b")
                else:
                    color = "#059669" if score >= 85 else ("#0284c7" if score >= 80 else "#d97706")
                start = float(c.get("start", 0))
                end = float(c.get("end", 0))
                dur = c.get("duration", round(end - start, 1))

                item_score = QTableWidgetItem(f"{score}分")
                item_score.setForeground(QColor(color))
                item_score.setTextAlignment(Qt.AlignCenter)
                item_title = QTableWidgetItem(c.get("title", ""))
                item_title.setData(Qt.UserRole, c)
                item_range = QTableWidgetItem(f"{start:.1f}s - {end:.1f}s")
                item_range.setTextAlignment(Qt.AlignCenter)
                item_dur = QTableWidgetItem(f"{dur}s")
                item_dur.setTextAlignment(Qt.AlignCenter)
                item_topic = QTableWidgetItem(c.get("topic", ""))
                item_terms = QTableWidgetItem(c.get("matched_terms", ""))
                item_reason = QTableWidgetItem(c.get("reason", ""))

                self.table_candidates.setItem(i, 0, item_score)
                self.table_candidates.setItem(i, 1, item_title)
                self.table_candidates.setItem(i, 2, item_range)
                self.table_candidates.setItem(i, 3, item_dur)
                self.table_candidates.setItem(i, 4, item_topic)
                self.table_candidates.setItem(i, 5, item_terms)
                self.table_candidates.setItem(i, 6, item_reason)
        finally:
            self.table_candidates.setUpdatesEnabled(True)

    def on_view_candidate_detail(self):
        row = self.table_candidates.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在表格中选择一个候选切片。")
            return
        c = self.table_candidates.item(row, 1).data(Qt.UserRole)
        msg = (
            f"【切片标题】: {c.get('title')}\n"
            f"【综合得分】: {c.get('score')} 分\n"
            f"【时间区间】: {c.get('start')}s - {c.get('end')}s ({c.get('duration')}秒)\n"
            f"【话题分类】: {c.get('topic')}\n"
            f"【命中词汇】: {c.get('matched_terms')}\n\n"
            f"【AI 提炼摘要】:\n{c.get('summary')}\n\n"
            f"【推荐理由】:\n{c.get('reason')}"
        )
        QMessageBox.information(self, "候选切片详情", msg)

    def on_candidates_context_menu(self, pos):
        item = self.table_candidates.itemAt(pos)
        if not item:
            return
        row = item.row()
        self.table_candidates.selectRow(row)
        c = self.table_candidates.item(row, 1).data(Qt.UserRole)
        if not c:
            return

        menu = QMenu(self)
        act_cut_single = menu.addAction("✂️ 立即极速剪辑此切片 (0.2s 极速成片)")
        act_cut_single.triggered.connect(self.on_cut_single_candidate)

        menu.addSeparator()

        act_detail = menu.addAction("👁️ 查看候选详情与AI摘要 (或双击行)")
        act_detail.triggered.connect(self.on_view_candidate_detail)

        menu.addSeparator()

        act_copy_title = menu.addAction("📋 复制切片标题")
        act_copy_title.triggered.connect(lambda: QApplication.clipboard().setText(c.get("title", "")))

        act_copy_summary = menu.addAction("📋 复制推荐理由与AI摘要")
        act_copy_summary.triggered.connect(lambda: QApplication.clipboard().setText(f"{c.get('summary', '')}\n\n推荐理由：{c.get('reason', '')}"))

        menu.exec_(QCursor.pos())

    def on_cut_single_candidate(self):
        row = self.table_candidates.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在候选列表中选择一个切片。")
            return
        c = self.table_candidates.item(row, 1).data(Qt.UserRole)
        if not c:
            return
        title = c.get("title", "")
        python = get_python()
        self.run_subcommand(
            "cut_single",
            [
                python, "-u", str(APP_DIR / "prepare_clips.py"),
                "--min-duration", "60", "--max-duration", "600",
                "--cut", "--single-title", title, "--overwrite"
            ],
            f"单片极速剪辑: {title[:20]}"
        )

    def refresh_clips_table(self, overview=None):
        try:
            if overview is None:
                overview = dashboard_server.build_overview()
            self.all_clips = overview.get("clips", [])
            pending_cnt = sum(1 for c in self.all_clips if c.get("douyin_status") != "published")
            published_cnt = sum(1 for c in self.all_clips if c.get("douyin_status") == "published")
            all_cnt = len(self.all_clips)
            if hasattr(self, "clip_stage_bar"):
                self.clip_stage_bar.setTabText(0, f"待发布 ({pending_cnt})")
                self.clip_stage_bar.setTabText(1, f"已发布 ({published_cnt})")
                self.clip_stage_bar.setTabText(2, f"全部成片 ({all_cnt})")
            self.filter_clips_table()
        except Exception as e:
            print("加载成片列表异常:", e)

    def on_clip_stage_tab_changed(self, index):
        is_published = (index == 1)
        if hasattr(self, "box_pending_ops") and hasattr(self, "box_published_ops"):
            self.box_pending_ops.setVisible(not is_published)
            self.box_published_ops.setVisible(is_published)
        self.checked_clip_outputs.clear()
        self._update_checked_clips_label()
        self.filter_clips_table()

    def filter_clips_table(self):
        if not hasattr(self, "all_clips"):
            return
        valid_outputs = {
            c.get("output", "")
            for c in self.all_clips
            if c.get("output")
        }
        self.checked_clip_outputs.intersection_update(valid_outputs)

        kw = self.txt_clip_search.text().strip().lower()
        stage_idx = self.clip_stage_bar.currentIndex() if hasattr(self, "clip_stage_bar") else 0

        filtered = []
        for c in self.all_clips:
            title = c.get("title", "").lower()
            name = c.get("name", "").lower()
            if kw and (kw not in title and kw not in name):
                continue
            status = c.get("douyin_status", "pending")
            if stage_idx == 0 and status == "published":
                continue
            if stage_idx == 1 and status != "published":
                continue
            filtered.append(c)

        self.table_clips.setUpdatesEnabled(False)
        self.table_clips.blockSignals(True)
        try:
            self.table_clips.setRowCount(len(filtered))
            is_dark = getattr(self, "current_is_dark", False)
            for i, c in enumerate(filtered):
                out_path = c.get("output", "")
                file_exists = bool(c.get("exists")) and Path(out_path).is_file()
                size_mb = c.get("size", 0) / (1024 * 1024)
                status = c.get("douyin_status", "pending")
                is_pub = (status == "published")
                is_failed = (status == "failed")

                if is_pub:
                    if file_exists:
                        status_text = "● 抖音已发布"
                        status_color = "#10b981" if is_dark else "#059669"
                        size_text = f"{size_mb:.1f}"
                    else:
                        status_text = "● 已发布 · 空间已释放"
                        status_color = "#38bdf8" if is_dark else "#0284c7"
                        size_text = "0.0 (已释放)"
                elif is_failed:
                    status_text = "● 发布失败"
                    status_color = "#ef4444" if is_dark else "#dc2626"
                    size_text = f"{size_mb:.1f}" if file_exists else "缺失"
                else:
                    status_text = "● 待发布"
                    status_color = "#f59e0b" if is_dark else "#d97706"
                    size_text = f"{size_mb:.1f}" if file_exists else "缺失"

                item_idx = QTableWidgetItem(str(c.get("index", i + 1)))
                item_idx.setTextAlignment(Qt.AlignCenter)
                item_idx.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                item_idx.setCheckState(Qt.Checked if out_path in self.checked_clip_outputs else Qt.Unchecked)

                item_title = QTableWidgetItem(c.get("title", c.get("name", "")))
                item_title.setData(Qt.UserRole, c)
                item_dur = QTableWidgetItem(f"{c.get('duration', 0)}s")
                item_dur.setTextAlignment(Qt.AlignCenter)
                item_size = QTableWidgetItem(size_text)
                item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item_stat = QTableWidgetItem(status_text)
                item_stat.setForeground(QColor(status_color))
                item_stat.setTextAlignment(Qt.AlignCenter)
                item_path = QTableWidgetItem(out_path)

                self.table_clips.setItem(i, 0, item_idx)
                self.table_clips.setItem(i, 1, item_title)
                self.table_clips.setItem(i, 2, item_dur)
                self.table_clips.setItem(i, 3, item_size)
                self.table_clips.setItem(i, 4, item_stat)
                self.table_clips.setItem(i, 5, item_path)
        finally:
            self.table_clips.blockSignals(False)
            self.table_clips.setUpdatesEnabled(True)
        self._update_checked_clips_label()

    def _update_checked_clips_label(self):
        n = len(getattr(self, "checked_clip_outputs", set()))
        if hasattr(self, "lbl_checked_clips"):
            self.lbl_checked_clips.setText(f"已勾选 {n} 条")
        if hasattr(self, "lbl_checked_pub_clips"):
            self.lbl_checked_pub_clips.setText(f"已勾选 {n} 条")

    def on_clip_item_changed(self, item):
        if not item or item.column() != 0:
            return
        title_item = self.table_clips.item(item.row(), 1)
        if not title_item:
            return
        c = title_item.data(Qt.UserRole) or {}
        out_path = c.get("output", "")
        if not out_path:
            return
        if item.checkState() == Qt.Checked:
            self.checked_clip_outputs.add(out_path)
        else:
            self.checked_clip_outputs.discard(out_path)
        self._update_checked_clips_label()

    def on_check_top_pending_clips(self, limit=5):
        self.table_clips.blockSignals(True)
        added = 0
        try:
            for r in range(self.table_clips.rowCount()):
                item_idx = self.table_clips.item(r, 0)
                item_title = self.table_clips.item(r, 1)
                if not item_idx or not item_title:
                    continue
                if not (item_idx.flags() & Qt.ItemIsUserCheckable):
                    continue
                c = item_title.data(Qt.UserRole) or {}
                out_path = c.get("output", "")
                if not out_path or not Path(out_path).is_file():
                    continue
                if c.get("douyin_status", "pending") == "published":
                    continue
                if out_path not in self.checked_clip_outputs:
                    self.checked_clip_outputs.add(out_path)
                    item_idx.setCheckState(Qt.Checked)
                    added += 1
                    if added >= limit:
                        break
        finally:
            self.table_clips.blockSignals(False)
        self._update_checked_clips_label()
        if added == 0:
            QMessageBox.information(self, "提示", "当前筛选列表中没有新增可勾选的待发布成片（或已勾选在列）。")

    def on_check_top_published_clips(self, limit=20):
        self.table_clips.blockSignals(True)
        added = 0
        try:
            for r in range(self.table_clips.rowCount()):
                item_idx = self.table_clips.item(r, 0)
                item_title = self.table_clips.item(r, 1)
                if not item_idx or not item_title:
                    continue
                c = item_title.data(Qt.UserRole) or {}
                out_path = c.get("output", "")
                if not out_path:
                    continue
                if c.get("douyin_status", "pending") == "published":
                    if out_path not in self.checked_clip_outputs:
                        self.checked_clip_outputs.add(out_path)
                        item_idx.setCheckState(Qt.Checked)
                        added += 1
                        if limit and added >= limit:
                            break
        finally:
            self.table_clips.blockSignals(False)
        self._update_checked_clips_label()
        if added == 0:
            QMessageBox.information(self, "提示", "当前筛选列表中没有可勾选的已发布成片。")

    def on_clear_checked_clips(self):
        self.checked_clip_outputs.clear()
        self.table_clips.blockSignals(True)
        try:
            for r in range(self.table_clips.rowCount()):
                item_idx = self.table_clips.item(r, 0)
                if item_idx and (item_idx.flags() & Qt.ItemIsUserCheckable):
                    item_idx.setCheckState(Qt.Unchecked)
        finally:
            self.table_clips.blockSignals(False)
        self._update_checked_clips_label()

    def on_auto_publish_douyin(self, single_clip=None):
        if self.current_process and self.current_process.state() == QProcess.Running:
            QMessageBox.warning(self, "任务冲突", f"当前正有任务正在运行中：{self.current_action_name}\n请等待完成或先点击停止。")
            return

        targets = []
        if single_clip is not None:
            targets = [single_clip]
        elif self.checked_clip_outputs:
            by_out = {c.get("output", ""): c for c in getattr(self, "all_clips", [])}
            for r in range(self.table_clips.rowCount()):
                item_title = self.table_clips.item(r, 1)
                if item_title:
                    c = item_title.data(Qt.UserRole) or {}
                    if c.get("output") in self.checked_clip_outputs:
                        targets.append(c)
                        by_out.pop(c.get("output"), None)
            for out_path in list(self.checked_clip_outputs):
                if out_path in by_out:
                    targets.append(by_out.pop(out_path))
        else:
            sel_model = self.table_clips.selectionModel()
            selected_rows = sorted({idx.row() for idx in sel_model.selectedRows()}) if sel_model else []
            if not selected_rows and self.table_clips.currentRow() >= 0:
                selected_rows = [self.table_clips.currentRow()]
            for r in selected_rows:
                item_title = self.table_clips.item(r, 1)
                if item_title:
                    c = item_title.data(Qt.UserRole)
                    if c:
                        targets.append(c)

        valid_targets = [
            c for c in targets
            if c.get("output") and Path(c["output"]).is_file()
        ]
        if not valid_targets:
            QMessageBox.information(
                self, "请先选择成片",
                "请先在成片列表第 1 列勾选待发布成片（可点“勾选前5条待发”），\n或单击选中至少一条存在本地文件的成片后再发布。"
            )
            return

        auto_click = self.chk_pub_auto_click.isChecked()
        ai_cover = self.chk_pub_ai_cover.isChecked()
        declaration = self.chk_pub_declaration.isChecked()

        preview = "\n".join(
            f"  {i + 1}. {c.get('title', c.get('name', ''))[:42]}"
            for i, c in enumerate(valid_targets[:5])
        )
        if len(valid_targets) > 5:
            preview += f"\n  ... 等共 {len(valid_targets)} 条"

        risk_tip = ""
        if len(valid_targets) > 10:
            risk_tip = "\n\n⚠️ 提示：本次超过 10 条，连续密集发布可能触发抖音审核或风控，建议每次 5~10 条。"

        mode_desc = "自动上传并直接点击“发布”" if auto_click else "仅自动上传填表（停在发布页等你检查后手动点发布）"
        confirm_msg = (
            f"准备自动发布 {len(valid_targets)} 条成片到抖音：\n\n"
            f"{preview}\n\n"
            f"发布模式：{mode_desc}\n"
            f"附加选项：AI封面={'开启' if ai_cover else '关闭'} · 虚构声明={'开启' if declaration else '关闭'}"
            f"{risk_tip}\n\n"
            f"确认启动浏览器自动发布吗？"
        )
        if QMessageBox.question(self, "确认自动发布到抖音", confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return

        python = get_python()
        cmd = [python, "-u", str(APP_DIR / "batch_publish.py")]
        for c in valid_targets:
            cmd.extend(["--output", c["output"]])
        if auto_click:
            cmd.append("--auto-publish")
        if ai_cover:
            cmd.append("--ai-cover")
        if declaration:
            cmd.append("--declaration")

        self.run_subcommand("publish_douyin", cmd, f"自动发布到抖音 ({len(valid_targets)} 条)")

    def on_manual_open_douyin_publish(self):
        import webbrowser
        webbrowser.open("https://creator.douyin.com/creator-micro/content/upload")
        row = self.table_clips.currentRow()
        folder = APP_DIR / "clips"
        if row >= 0:
            item_title = self.table_clips.item(row, 1)
            c = item_title.data(Qt.UserRole) if item_title else None
            if c and c.get("output"):
                p = Path(c["output"]).parent
                if p.is_dir():
                    folder = p
        subprocess.Popen(["xdg-open", str(folder)])

    def on_play_clip(self):
        row = self.table_clips.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在列表中选中一个成片。")
            return
        c = self.table_clips.item(row, 1).data(Qt.UserRole)
        p = Path(c.get("output", ""))
        if p.is_file():
            subprocess.Popen(["xdg-open", str(p)])
        else:
            QMessageBox.warning(self, "文件缺失", "该成片文件不存在或已被移除。")

    def on_edit_clip_text(self):
        row = self.table_clips.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在列表中选中一个成片。")
            return
        c = self.table_clips.item(row, 1).data(Qt.UserRole)
        dlg = PublishEditDialog(c, self, is_dark=self.current_is_dark)
        dlg.exec_()
        if dlg.has_changes:
            self.refresh_clips_table()

    def on_change_publish_status(self, new_status):
        row = self.table_clips.currentRow()
        if row < 0:
            return
        c = self.table_clips.item(row, 1).data(Qt.UserRole)
        try:
            dashboard_server.update_publish_status(c.get("index", 0), "douyin", new_status, c.get("output"))
            self.refresh_clips_table()
            self.refresh_overview_data()
        except Exception as e:
            QMessageBox.critical(self, "修改失败", str(e))

    def on_delete_clip(self):
        # 1. 优先获取多选勾选的成片
        targets = []
        if getattr(self, "checked_clip_outputs", None):
            by_out = {c.get("output", ""): c for c in getattr(self, "all_clips", [])}
            for out in list(self.checked_clip_outputs):
                if out in by_out:
                    targets.append(by_out[out])

        # 2. 若无勾选，获取当前行或多选高亮选中的成片
        if not targets:
            sel_model = self.table_clips.selectionModel()
            selected_rows = sorted({idx.row() for idx in sel_model.selectedRows()}) if sel_model else []
            if not selected_rows and self.table_clips.currentRow() >= 0:
                selected_rows = [self.table_clips.currentRow()]
            for r in selected_rows:
                item_title = self.table_clips.item(r, 1)
                if item_title:
                    c = item_title.data(Qt.UserRole)
                    if c and c not in targets:
                        targets.append(c)

        if not targets:
            QMessageBox.information(
                self, "请先选择成片",
                "请先在成片列表中单击选中至少一行成片，\n或在第 1 列勾选框勾选待删除成片后再点击【🗑️ 废弃删除成片】。"
            )
            return

        cnt = len(targets)
        preview_text = "\n".join(f"  • {c.get('title', c.get('name', ''))[:38]}" for c in targets[:5])
        if cnt > 5:
            preview_text += f"\n  ... 等共 {cnt} 条成片"

        reply = QMessageBox.question(
            self,
            "确认删除未发布成片",
            f"确定彻底删除以下 {cnt} 个未发布成片视频并立即释放磁盘空间吗？\n\n{preview_text}\n\n注意：本地视频文件将被物理删除以节省磁盘空间，原录制素材与分析记录将完整保留。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        deleted_cnt = 0
        failed_cnt = 0
        for c in targets:
            out = c.get("output")
            if not out:
                continue
            try:
                dashboard_server.delete_clip(out, cleanup_file_only=False)
                if hasattr(self, "checked_clip_outputs"):
                    self.checked_clip_outputs.discard(out)
                deleted_cnt += 1
            except Exception as e:
                failed_cnt += 1
                print(f"删除成片失败 {out}: {e}")

        if hasattr(self, "_update_checked_clips_label"):
            self._update_checked_clips_label()
        self.refresh_clips_table()
        self.refresh_overview_data()

        if failed_cnt == 0:
            self.append_log(f"🗑️ 已成功删除 {deleted_cnt} 个成片并释放磁盘空间！\n")
            QMessageBox.information(self, "删除成功", f"已成功删除 {deleted_cnt} 个成片视频并立即释放磁盘空间！")
        else:
            self.append_log(f"⚠️ 批量删除完成：成功 {deleted_cnt} 个，失败 {failed_cnt} 个。\n")
            QMessageBox.warning(self, "删除结果", f"成功删除 {deleted_cnt} 个成片，{failed_cnt} 个删除失败。")

    def on_clean_published_files(self):
        """清理已发布成片的本地视频文件以释放磁盘空间，完整保留发布与流量数据"""
        targets = []
        if getattr(self, "checked_clip_outputs", None):
            by_out = {c.get("output", ""): c for c in getattr(self, "all_clips", [])}
            for out in list(self.checked_clip_outputs):
                if out in by_out:
                    c = by_out[out]
                    if c.get("douyin_status") == "published":
                        targets.append(c)

        if not targets:
            sel_model = self.table_clips.selectionModel()
            selected_rows = sorted({idx.row() for idx in sel_model.selectedRows()}) if sel_model else []
            if not selected_rows and self.table_clips.currentRow() >= 0:
                selected_rows = [self.table_clips.currentRow()]
            for r in selected_rows:
                item_title = self.table_clips.item(r, 1)
                if item_title:
                    c = item_title.data(Qt.UserRole)
                    if c and c not in targets and c.get("douyin_status") == "published":
                        targets.append(c)

        valid_targets = [
            c for c in targets
            if c.get("output") and Path(c["output"]).is_file()
        ]
        if not valid_targets:
            QMessageBox.information(
                self, "提示",
                "请先在列表中勾选或选中本地视频仍存在的已发布成片。\n（若本地视频此前已被释放，则无需重复清理）"
            )
            return

        total_bytes = sum(c.get("size", 0) for c in valid_targets)
        total_mb = total_bytes / (1024 * 1024)
        total_gb = total_bytes / (1024 ** 3)
        size_str = f"{total_gb:.2f} GB" if total_gb >= 0.1 else f"{total_mb:.1f} MB"

        cnt = len(valid_targets)
        preview_text = "\n".join(f"  • {c.get('title', c.get('name', ''))[:38]}" for c in valid_targets[:5])
        if cnt > 5:
            preview_text += f"\n  ... 等共 {cnt} 条已发布成片"

        reply = QMessageBox.question(
            self,
            "确认清理本地大视频文件",
            f"确定清理以下 {cnt} 个已发布成片的本地视频文件以释放磁盘空间吗？\n\n"
            f"{preview_text}\n\n"
            f"💾 预计将立即释放磁盘空间：约 {size_str}！\n\n"
            f"✅ 重要保障：仅删除本地庞大的 .mp4 视频文件，抖音已发布状态、文案及流量归因记录将完整保留！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        cleaned_cnt = 0
        failed_cnt = 0
        for c in valid_targets:
            out = c.get("output")
            if not out:
                continue
            try:
                dashboard_server.delete_clip(out, cleanup_file_only=True)
                if hasattr(self, "checked_clip_outputs"):
                    self.checked_clip_outputs.discard(out)
                cleaned_cnt += 1
            except Exception as e:
                failed_cnt += 1
                print(f"清理已发布成片本地文件失败 {out}: {e}")

        if hasattr(self, "_update_checked_clips_label"):
            self._update_checked_clips_label()
        self.refresh_clips_table()
        self.refresh_overview_data()

        if failed_cnt == 0:
            self.append_log(f"🧹 已成功清理 {cleaned_cnt} 个已发布成片的本地视频，释放磁盘空间约 {size_str}！\n")
            QMessageBox.information(
                self, "空间释放成功",
                f"已成功清理 {cleaned_cnt} 个已发布成片的本地视频文件！\n"
                f"已释放磁盘空间约 {size_str}。\n\n"
                f"所有发布记录与流量归因数据均已完好保留。"
            )
        else:
            self.append_log(f"⚠️ 清理完成：成功 {cleaned_cnt} 个，失败 {failed_cnt} 个。\n")
            QMessageBox.warning(self, "清理结果", f"成功清理 {cleaned_cnt} 个成片文件，{failed_cnt} 个清理失败。")

    def on_delete_published_records(self):
        """彻底删除已发布成片的本地文件及所有记录"""
        targets = []
        if getattr(self, "checked_clip_outputs", None):
            by_out = {c.get("output", ""): c for c in getattr(self, "all_clips", [])}
            for out in list(self.checked_clip_outputs):
                if out in by_out:
                    c = by_out[out]
                    if c.get("douyin_status") == "published":
                        targets.append(c)

        if not targets:
            sel_model = self.table_clips.selectionModel()
            selected_rows = sorted({idx.row() for idx in sel_model.selectedRows()}) if sel_model else []
            if not selected_rows and self.table_clips.currentRow() >= 0:
                selected_rows = [self.table_clips.currentRow()]
            for r in selected_rows:
                item_title = self.table_clips.item(r, 1)
                if item_title:
                    c = item_title.data(Qt.UserRole)
                    if c and c not in targets and c.get("douyin_status") == "published":
                        targets.append(c)

        if not targets:
            QMessageBox.information(self, "请先选择成片", "请在列表中勾选或单选要彻底删除的已发布成片记录。")
            return

        cnt = len(targets)
        preview_text = "\n".join(f"  • {c.get('title', c.get('name', ''))[:38]}" for c in targets[:5])
        if cnt > 5:
            preview_text += f"\n  ... 等共 {cnt} 条已发布成片"

        reply = QMessageBox.question(
            self,
            "确认彻底删除发布记录",
            f"确定彻底删除以下 {cnt} 个已发布成片记录吗？\n\n{preview_text}\n\n⚠️ 警告：成片的本地视频文件（若存在）及抖音发布记录、流量归因数据将被彻底清除！\n（原录制素材仍完好保留）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        deleted_cnt = 0
        failed_cnt = 0
        for c in targets:
            out = c.get("output")
            if not out:
                continue
            try:
                dashboard_server.delete_clip(out, cleanup_file_only=False)
                if hasattr(self, "checked_clip_outputs"):
                    self.checked_clip_outputs.discard(out)
                deleted_cnt += 1
            except Exception as e:
                failed_cnt += 1
                print(f"彻底删除已发布成片记录失败 {out}: {e}")

        if hasattr(self, "_update_checked_clips_label"):
            self._update_checked_clips_label()
        self.refresh_clips_table()
        self.refresh_overview_data()

        if failed_cnt == 0:
            self.append_log(f"🗑️ 已成功彻底删除 {deleted_cnt} 条已发布成片及相关记录！\n")
            QMessageBox.information(self, "删除成功", f"已彻底删除 {deleted_cnt} 条已发布成片记录！")
        else:
            self.append_log(f"⚠️ 删除完成：成功 {deleted_cnt} 个，失败 {failed_cnt} 个。\n")
            QMessageBox.warning(self, "删除结果", f"成功删除 {deleted_cnt} 个，{failed_cnt} 个失败。")

    def on_open_selected_clip_dir(self):
        row = self.table_clips.currentRow()
        if row < 0:
            subprocess.Popen(["xdg-open", str(APP_DIR / "clips")])
            return
        item_title = self.table_clips.item(row, 1)
        c = item_title.data(Qt.UserRole) if item_title else {}
        out = c.get("output", "")
        p = Path(out) if out else (APP_DIR / "clips")
        target_dir = p.parent if p.is_file() else (APP_DIR / "clips")
        subprocess.Popen(["xdg-open", str(target_dir)])

    def on_clips_context_menu(self, pos):
        item = self.table_clips.itemAt(pos)
        if not item:
            return
        row = item.row()
        self.table_clips.selectRow(row)
        c = self.table_clips.item(row, 1).data(Qt.UserRole)
        if not c:
            return

        menu = QMenu(self)
        status = c.get("douyin_status", "pending")
        is_pub = (status == "published")
        out_path = c.get("output", "")
        file_exists = bool(c.get("exists")) and Path(out_path).is_file()

        if file_exists:
            act_play = menu.addAction("▶ 立即播放成片视频 (或双击行)")
            act_play.triggered.connect(self.on_play_clip)
        else:
            act_play = menu.addAction("▶ 视频文件已释放 (本地不可播)")
            act_play.setEnabled(False)

        act_edit = menu.addAction("📝 查看 / 编辑发布文案")
        act_edit.triggered.connect(self.on_edit_clip_text)

        if not is_pub:
            act_auto_pub = menu.addAction("🚀 自动发布此成片到抖音")
            act_auto_pub.triggered.connect(lambda: self.on_auto_publish_douyin(single_clip=c))

            act_manual_pub = menu.addAction("🌐 手动打开抖音发布页与目录")
            act_manual_pub.triggered.connect(self.on_manual_open_douyin_publish)

            menu.addSeparator()
            act_mark_pub = menu.addAction("✅ 标记为抖音已发布")
            act_mark_pub.triggered.connect(lambda: self.on_change_publish_status("published"))
        else:
            act_mark_unpub = menu.addAction("⏳ 改回待发布")
            act_mark_unpub.triggered.connect(lambda: self.on_change_publish_status("pending"))

        menu.addSeparator()

        p = Path(out_path)
        act_open_dir = menu.addAction("📂 在文件管理器中定位成片")
        act_open_dir.triggered.connect(lambda: subprocess.Popen(["xdg-open", str(p.parent if p.is_file() else APP_DIR / "clips")]))

        act_copy_title = menu.addAction("📋 复制成片标题")
        act_copy_title.triggered.connect(lambda: QApplication.clipboard().setText(c.get("title", c.get("name", ""))))

        menu.addSeparator()

        if is_pub:
            if file_exists:
                act_clean_file = menu.addAction("🧹 清理本地视频 (释放磁盘空间 · 保留发布记录)")
                act_clean_file.triggered.connect(self.on_clean_published_files)
            else:
                act_clean_file = menu.addAction("💾 本地视频已释放 (空间已节约)")
                act_clean_file.setEnabled(False)

            act_del_rec = menu.addAction("🗑️ 彻底删除发布记录")
            act_del_rec.triggered.connect(self.on_delete_published_records)
        else:
            act_del = menu.addAction("🗑️ 废弃删除此成片 (物理删除文件释放空间)")
            act_del.triggered.connect(self.on_delete_clip)

        menu.exec_(QCursor.pos())

    # --------------------------------------------------------------------------
    # Tab 5: 对标账号雷达与一键二创
    # --------------------------------------------------------------------------
    def refresh_radar_data(self):
        if getattr(self, "_is_refreshing_radar", False):
            return
        self._is_refreshing_radar = True
        if hasattr(self, "lbl_radar_status"):
            self.lbl_radar_status.setText("⏳ 正在比对全素材库转写内容...")

        def _ok(data):
            self._is_refreshing_radar = False
            if not self._is_closing:
                self._apply_radar_overview(data)

        def _err(err):
            self._is_refreshing_radar = False
            if not self._is_closing and hasattr(self, "lbl_radar_status"):
                self.lbl_radar_status.setText(f"❌ 雷达加载失败: {err}")

        run_async_task(benchmark_radar.get_radar_overview, _ok, _err)

    def _apply_radar_overview(self, data):
        try:
            accs = data.get("tracked_accounts", [])
            self._cached_tracked_accounts = accs
            platform_names = {
                "douyin": "抖音",
                "kuaishou": "快手",
                "channels": "视频号",
                "xiaohongshu": "小红书",
            }
            self.table_accounts.setUpdatesEnabled(False)
            try:
                self.table_accounts.setRowCount(len(accs))
                for i, a in enumerate(accs):
                    item_name = QTableWidgetItem(a.get("name", ""))
                    item_name.setData(Qt.UserRole, a)
                    plat_raw = str(a.get("platform", "douyin"))
                    item_plat = QTableWidgetItem(platform_names.get(plat_raw, plat_raw))
                    item_plat.setTextAlignment(Qt.AlignCenter)
                    homepage = a.get("homepage") or a.get("account_id") or "—"
                    item_home = QTableWidgetItem(str(homepage))
                    self.table_accounts.setItem(i, 0, item_name)
                    self.table_accounts.setItem(i, 1, item_plat)
                    self.table_accounts.setItem(i, 2, item_home)
            finally:
                self.table_accounts.setUpdatesEnabled(True)

            items = data.get("items", [])
            is_dark = getattr(self, "current_is_dark", False)
            self.table_radar_items.setUpdatesEnabled(False)
            try:
                self.table_radar_items.setRowCount(len(items))
                for i, it in enumerate(items):
                    is_breaking = it.get("is_breaking", False)
                    author = it.get("author") or it.get("account_name") or "同行标杆"
                    vel = float(it.get("velocity", it.get("speed", 0)) or 0)

                    item_acc = QTableWidgetItem(str(author))
                    item_likes = QTableWidgetItem(f"{int(it.get('likes', 0) or 0):,}")
                    item_likes.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    item_speed = QTableWidgetItem(f"+{int(vel)}/h")
                    item_speed.setTextAlignment(Qt.AlignCenter)
                    if is_breaking:
                        item_speed.setForeground(QColor("#ef4444" if is_dark else "#dc2626"))
                    item_title = QTableWidgetItem(it.get("title", ""))
                    item_title.setData(Qt.UserRole, it)

                    best = it.get("best_match")
                    if it.get("has_match") and best:
                        if best.get("source_exists"):
                            match_text = f"● 同款 {best.get('match_score', 0)}% ({best.get('start', 0):.0f}-{best.get('end', 0):.0f}s)"
                            match_color = "#10b981" if is_dark else "#059669"
                        else:
                            match_text = f"● 命中 {best.get('match_score', 0)}% (原片已清理)"
                            match_color = "#f59e0b" if is_dark else "#d97706"
                    else:
                        match_text = "未命中 (可手动搜索)"
                        match_color = "#94a3b8" if is_dark else "#8e8e93"

                    item_match = QTableWidgetItem(match_text)
                    item_match.setForeground(QColor(match_color))

                    self.table_radar_items.setItem(i, 0, item_acc)
                    self.table_radar_items.setItem(i, 1, item_likes)
                    self.table_radar_items.setItem(i, 2, item_speed)
                    self.table_radar_items.setItem(i, 3, item_title)
                    self.table_radar_items.setItem(i, 4, item_match)
            finally:
                self.table_radar_items.setUpdatesEnabled(True)

            if hasattr(self, "lbl_radar_status"):
                matched_cnt = data.get("matched_sources_count", 0)
                if not items:
                    self.lbl_radar_status.setText("爆款列表为空 — 可点击右侧【载入标杆全库】或【录入爆款】")
                else:
                    self.lbl_radar_status.setText(
                        f"监控 {len(items)} 条标杆爆款 · 爆发中 {data.get('breaking_count', 0)} 条 · 素材库命中同款 {matched_cnt} 条"
                    )
        except Exception as e:
            print("渲染雷达数据异常:", e)

    def on_add_radar_account(self):
        name = self.txt_acc_name.text().strip()
        platform = self.cmb_acc_platform.currentText().split()[0]
        homepage = self.txt_acc_id.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入关注的对标账号名称。")
            return
        try:
            benchmark_radar.add_tracked_account(name, platform=platform, homepage=homepage)
            self.txt_acc_name.clear()
            self.txt_acc_id.clear()
            self.refresh_radar_data()
            self.append_log(f"➕ 已添加关注账号: {name} ({platform})\n")
        except Exception as e:
            QMessageBox.critical(self, "添加失败", str(e))

    def on_delete_radar_account(self):
        row = self.table_accounts.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在左侧选择一条监控账号。")
            return
        a = self.table_accounts.item(row, 0).data(Qt.UserRole) or {}
        acc_id = a.get("id") or a.get("account_id")
        if not acc_id:
            QMessageBox.warning(self, "提示", "未识别到该账号的 ID。")
            return
        if QMessageBox.question(self, "确认删除", f"确定取消对账号【{a.get('name')}】的关注吗？") == QMessageBox.Yes:
            benchmark_radar.delete_tracked_account(acc_id)
            self.refresh_radar_data()
            self.append_log(f"➖ 已移除关注账号: {a.get('name')}\n")

    def on_add_radar_item(self):
        accs = getattr(self, "_cached_tracked_accounts", [])
        dlg = AddRadarItemDialog(accs, self, is_dark=self.current_is_dark)
        if dlg.exec_() == QDialog.Accepted:
            vals = dlg.get_values()
            if not vals["title"]:
                QMessageBox.warning(self, "提示", "爆款标题不能为空。")
                return
            try:
                benchmark_radar.add_radar_item(
                    title=vals["title"],
                    author=vals["author"],
                    velocity=vals["velocity"],
                    likes=vals["likes"],
                )
                self.append_log(f"➕ 已录入标杆爆款：《{vals['title']}》，正在匹配素材库同款...\n")
                self.refresh_radar_data()
            except Exception as e:
                QMessageBox.critical(self, "录入失败", str(e))

    def on_seed_radar_items(self):
        try:
            added = benchmark_radar.seed_radar_items()
            self.append_log(f"📥 已从标杆爆款题库中载入 {added} 条精选热点选题。\n")
            self.refresh_radar_data()
        except Exception as e:
            QMessageBox.critical(self, "载入失败", str(e))

    def on_shuffle_radar_items(self):
        try:
            cnt = benchmark_radar.shuffle_radar_topics(batch_size=6)
            self.append_log(f"🎲 已成功轮换 {cnt} 条全新标杆爆款选题！正在自动匹配全素材库...\n")
            self.refresh_radar_data()
        except Exception as e:
            QMessageBox.critical(self, "换一批失败", str(e))

    def on_discover_radar_items(self):
        try:
            cnt = benchmark_radar.discover_fresh_radar_topics(count=5)
            self.append_log(f"💡 AI 已从素材候选库深度挖掘并录入 {cnt} 条全新热点选题！正在匹配同款...\n")
            self.refresh_radar_data()
        except Exception as e:
            QMessageBox.critical(self, "挖掘失败", str(e))

    def on_delete_radar_item(self):
        row = self.table_radar_items.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一条爆款记录。")
            return
        it = self.table_radar_items.item(row, 3).data(Qt.UserRole) or {}
        item_id = it.get("id")
        if not item_id:
            return
        if QMessageBox.question(self, "确认删除", f"确定移除爆款记录：\n《{it.get('title')}》吗？") == QMessageBox.Yes:
            benchmark_radar.delete_radar_item(item_id)
            self.refresh_radar_data()

    def on_search_selected_radar_item(self):
        row = self.table_radar_items.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在下方列表选择一条爆款。")
            return
        it = self.table_radar_items.item(row, 3).data(Qt.UserRole) or {}
        title = it.get("title", "")
        if title:
            self.txt_radar_search.setText(title)
            self.on_search_radar_match()

    def on_search_radar_match(self):
        query = self.txt_radar_search.text().strip()
        if not query:
            QMessageBox.information(self, "提示", "请输入要检索的同行爆款标题或话题关键词。")
            return
        self.btn_radar_search.setEnabled(False)
        self.btn_radar_search.setText("⏳ 检索中...")
        self.btn_cut_match.setEnabled(False)

        def _ok(matches):
            self.btn_radar_search.setEnabled(True)
            self.btn_radar_search.setText("🔍 搜本地同款原片")
            if self._is_closing:
                return
            self._render_search_matches(query, matches)

        def _err(err):
            self.btn_radar_search.setEnabled(True)
            self.btn_radar_search.setText("🔍 搜本地同款原片")
            if not self._is_closing:
                QMessageBox.critical(self, "检索失败", str(err))

        run_async_task(benchmark_radar.find_matching_segments, _ok, _err, query)

    def _render_search_matches(self, query, matches):
        is_dark = getattr(self, "current_is_dark", False)
        self.table_radar_matches.setUpdatesEnabled(False)
        try:
            self.table_radar_matches.setRowCount(len(matches))
            for i, m in enumerate(matches):
                item_score = QTableWidgetItem(f"🎯 {m.get('match_score', 0)}%")
                item_score.setTextAlignment(Qt.AlignCenter)
                item_score.setForeground(QColor("#10b981" if is_dark else "#059669"))
                item_score.setData(Qt.UserRole, {**m, "query_title": query})

                item_src = QTableWidgetItem(m.get("source_name", ""))
                item_span = QTableWidgetItem(f"{m.get('start', 0):.0f}s - {m.get('end', 0):.0f}s ({m.get('duration', 0):.0f}s)")
                item_span.setTextAlignment(Qt.AlignCenter)
                item_snip = QTableWidgetItem(m.get("snippet", ""))
                exists = bool(m.get("source_exists"))
                item_stat = QTableWidgetItem("✅ 原片存在" if exists else "⚠️ 原片已清理")
                item_stat.setTextAlignment(Qt.AlignCenter)
                item_stat.setForeground(QColor(("#10b981" if is_dark else "#059669") if exists else "#dc2626"))

                self.table_radar_matches.setItem(i, 0, item_score)
                self.table_radar_matches.setItem(i, 1, item_src)
                self.table_radar_matches.setItem(i, 2, item_span)
                self.table_radar_matches.setItem(i, 3, item_snip)
                self.table_radar_matches.setItem(i, 4, item_stat)
        finally:
            self.table_radar_matches.setUpdatesEnabled(True)

        self.btn_cut_match.setEnabled(bool(matches))
        if matches:
            self.table_radar_matches.selectRow(0)
            self.append_log(f"🎯 检索“{query[:25]}”命中 {len(matches)} 处直播原片同款！\n")
        else:
            self.append_log(f"⚪ 未在最近 150 场转写库中检索到与“{query[:25]}”高度匹配的同款片段。\n")
            QMessageBox.information(self, "未找到同款", "未在当前转写库中匹配到明显同款片段，建议换几个核心关键词（如人名、战术词）再试。")

    def on_cut_selected_match(self):
        row = self.table_radar_matches.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在检索结果表格中选中一条命中片段。")
            return
        m = self.table_radar_matches.item(row, 0).data(Qt.UserRole) or {}
        if not m.get("source_exists"):
            QMessageBox.warning(self, "原片已清理", "该场直播原视频文件已被清理，仅留存字幕文本，无法剪切视频。")
            return
        title = self.txt_radar_search.text().strip() or m.get("query_title") or "雷达同款跟剪"
        self._run_cut_matched_clip(m["source_path"], m["start"], m["end"], title, "全素材库同款检索跟剪")

    def _run_cut_matched_clip(self, source_path, start, end, title, why_viral):
        self.btn_remix.setEnabled(False)
        self.btn_cut_match.setEnabled(False)
        self.start_async_progress(f"雷达同款跟剪: {title[:20]}")
        self.append_log(f"\n✂️ 启动异步同款跟剪：{title} ({start:.0f}s - {end:.0f}s)...\n")

        def _prog(pct, msg):
            self.update_async_progress(pct, msg)
            if hasattr(self, "lbl_radar_status"):
                self.lbl_radar_status.setText(f"⏳ [{pct}%] {msg}")

        def _ok(res):
            self.btn_remix.setEnabled(True)
            self.btn_cut_match.setEnabled(self.table_radar_matches.rowCount() > 0)
            self.finish_async_progress(True, f"⚪ 已就绪 · 同款跟剪完成 ({res.get('duration')}s)")
            if self._is_closing:
                return
            self.append_log(f"✅ 同款跟剪完成！成片路径: {res.get('output')}\n")
            QMessageBox.information(self, "跟剪成功", f"已从您的原片极速剪出同款成片并加入发布队列！\n时长: {res.get('duration')} 秒")
            self.refresh_all_data()

        def _err(err):
            self.btn_remix.setEnabled(True)
            self.btn_cut_match.setEnabled(self.table_radar_matches.rowCount() > 0)
            self.finish_async_progress(False, "🔴 同款跟剪失败")
            if self._is_closing:
                return
            self.append_log(f"❌ 跟剪失败: {err}\n")
            QMessageBox.critical(self, "跟剪失败", str(err))

        run_async_task(
            benchmark_radar.cut_matched_clip,
            _ok,
            _err,
            source_path,
            start,
            end,
            title,
            why_viral,
            on_progress=_prog,
        )

    def on_remix_radar_item(self):
        row = self.table_radar_items.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在标杆爆款列表中选择一条记录。")
            return
        it = self.table_radar_items.item(row, 3).data(Qt.UserRole) or {}
        best = it.get("best_match")

        # 优先：如果本地素材库已经匹配到同款直播录像且原片还在，直接调用毫秒跟剪
        if it.get("has_match") and best:
            if best.get("source_exists"):
                msg = (
                    f"将在您自己的直播原片中极速跟剪同款片段：\n\n"
                    f"• 标题：{it.get('title')}\n"
                    f"• 原片：{best.get('source_name')}\n"
                    f"• 时间区间：{best.get('start', 0):.0f}s - {best.get('end', 0):.0f}s (时长 {best.get('duration', 0):.0f}s)\n\n"
                    f"确认立即剪辑并加入发布队列吗？"
                )
                if QMessageBox.question(self, "确认同款跟剪", msg) == QMessageBox.Yes:
                    self._run_cut_matched_clip(
                        best["source_path"],
                        best["start"],
                        best["end"],
                        it.get("title", "雷达同款"),
                        f"对标账号【{it.get('author', '')}】爆款同款跟剪",
                    )
                return
            else:
                QMessageBox.warning(
                    self,
                    "原片已清理",
                    f"该话题曾命中《{best.get('source_name')}》，但该场原片已清理。您可以点击【🔍 检索此标题同款】寻找其他场次，或在下方粘贴同行视频进行 Remix 二创。",
                )
                return

        # 其次：如果条目本身附带了外部直链
        target_url = it.get("video_url") or it.get("url")
        if target_url:
            self.txt_remix_url.setText(target_url)
            self.on_remix_url(custom_title=it.get("title", ""))
            return

        # 未匹配到本地且无外链时，引导直接去全素材库搜同款
        title = it.get("title", "")
        if title:
            self.txt_radar_search.setText(title)
            self.on_search_radar_match()

    def on_pick_remix_local_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要二次创作的本地短视频 (.mp4/.mov/.ts)",
            str(APP_DIR),
            "视频文件 (*.mp4 *.mov *.mkv *.ts *.flv);;所有文件 (*)",
        )
        if file_path:
            self.txt_remix_url.setText(file_path)

    def on_remix_url(self, custom_title=""):
        url_or_path = self.txt_remix_url.text().strip()
        if not url_or_path:
            QMessageBox.warning(self, "提示", "请先粘贴同行抖音/快手分享链接，或点击【📂 选本地视频】。")
            return

        self.btn_remix_url.setEnabled(False)
        self.btn_remix_url.setText("⏳ 二创 5%...")
        self.start_async_progress("外部爆款视频二次创作 (Remix)")
        self.append_log(f"\n🎬 启动异步 Remix 二次创作：{url_or_path[:80]}...\n")

        def _prog(pct, msg):
            self.btn_remix_url.setText(f"⏳ 二创 {pct}%...")
            self.update_async_progress(pct, msg)
            if hasattr(self, "lbl_radar_status"):
                self.lbl_radar_status.setText(f"⏳ Remix [{pct}%] {msg}")

        def _ok(res):
            self.btn_remix_url.setEnabled(True)
            self.btn_remix_url.setText("⚡ 一键二创入库")
            self.finish_async_progress(True, f"⚪ 已就绪 · Remix 二创完成：{res.get('title')}")
            if self._is_closing:
                return
            self.txt_remix_url.clear()
            self.append_log(f"✅ 二创完成！标题: {res.get('title')} | 路径: {res.get('output')}\n")
            QMessageBox.information(self, "二创完成", f"已成功生成二创成片并加入发布队列！\n新标题：{res.get('title')}")
            self.refresh_all_data()

        def _err(err):
            self.btn_remix_url.setEnabled(True)
            self.btn_remix_url.setText("⚡ 一键二创入库")
            self.finish_async_progress(False, "🔴 Remix 二创失败")
            if self._is_closing:
                return
            self.append_log(f"❌ 二创失败: {err}\n")
            QMessageBox.critical(self, "二创失败", str(err))

        run_async_task(
            remix_service.process_benchmark_url_to_remix,
            _ok,
            _err,
            url_or_path,
            custom_title=custom_title,
            on_progress=_prog,
        )

    def on_radar_context_menu(self, pos):
        item = self.table_radar_items.itemAt(pos)
        if not item:
            return
        row = item.row()
        self.table_radar_items.selectRow(row)
        it = self.table_radar_items.item(row, 3).data(Qt.UserRole) or {}
        if not it:
            return

        menu = QMenu(self)
        act_remix = menu.addAction("✂️ 一键跟剪本地同款成片")
        act_remix.triggered.connect(self.on_remix_radar_item)

        act_search = menu.addAction("🔍 在全素材库检索此标题同款")
        act_search.triggered.connect(self.on_search_selected_radar_item)

        menu.addSeparator()

        act_copy = menu.addAction("📋 复制爆款标题")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(it.get("title", "")))

        act_del = menu.addAction("🗑️ 删除此条目")
        act_del.triggered.connect(self.on_delete_radar_item)

        menu.exec_(QCursor.pos())

    # --------------------------------------------------------------------------
    # Tab 6: 系统设置与配置
    # --------------------------------------------------------------------------
    def load_settings(self):
        try:
            cfg = ai_service.get_ai_config()
            provider = cfg.get("provider", "ollama")
            self.cmb_ai_provider.setCurrentIndex(0 if provider == "ollama" else 1)

            if provider == "ollama":
                self.txt_ai_model.setText(cfg.get("ollama", {}).get("model", "qwen2.5:7b"))
                self.txt_ai_base_url.setText(cfg.get("ollama", {}).get("base_url", "http://127.0.0.1:11434"))
                self.txt_ai_api_key.clear()
            else:
                api_cfg = cfg.get("api", {})
                self.txt_ai_model.setText(api_cfg.get("model", "deepseek-chat"))
                self.txt_ai_base_url.setText(api_cfg.get("base_url", "https://api.deepseek.com/v1"))
                self.txt_ai_api_key.setText(api_cfg.get("api_key", ""))

            # 加载重点词
            config_json = dashboard_server.read_json(APP_DIR / "config.json", {})
            kws = config_json.get("keywords", [])
            self.txt_keywords.setPlainText("\n".join(kws))
        except Exception as e:
            print("加载配置异常:", e)

    def on_ai_provider_changed(self, idx):
        if idx == 0:
            self.txt_ai_model.setText("qwen2.5:7b")
            self.txt_ai_base_url.setText("http://127.0.0.1:11434")
            self.txt_ai_api_key.setEnabled(False)
        else:
            self.txt_ai_model.setText("deepseek-chat")
            self.txt_ai_base_url.setText("https://api.deepseek.com/v1")
            self.txt_ai_api_key.setEnabled(True)

    def on_test_ai(self):
        provider = "ollama" if self.cmb_ai_provider.currentIndex() == 0 else "api"
        model = self.txt_ai_model.text().strip()
        base_url = self.txt_ai_base_url.text().strip()
        api_key = self.txt_ai_api_key.text().strip()
        cfg_override = {
            "provider": provider,
            "ollama": {"model": model or "qwen2.5:7b", "base_url": base_url or "http://127.0.0.1:11434"},
            "api": {"model": model or "deepseek-chat", "base_url": base_url or "https://api.deepseek.com/v1", "api_key": api_key},
        }
        self.btn_test_ai.setEnabled(False)
        self.btn_test_ai.setText("⏳ 正在异步测试连接...")
        self.append_log(f"\n🔍 正在异步测试 AI 模型连接 ({provider} - {model})...\n")

        def _do_test():
            messages = [{"role": "user", "content": "请回复'pong'五个字母。"}]
            return ai_service.chat_completion(
                messages=messages,
                provider=provider,
                config_override=cfg_override,
                timeout=30,
            )

        def _ok(res):
            self.btn_test_ai.setEnabled(True)
            self.btn_test_ai.setText("🔍 测试 AI 连接")
            if self._is_closing:
                return
            self.append_log(f"✅ AI 连接成功！响应内容: {res}\n")
            QMessageBox.information(self, "连接成功", f"AI 模型测试通过！响应：{res}")

        def _err(err):
            self.btn_test_ai.setEnabled(True)
            self.btn_test_ai.setText("🔍 测试 AI 连接")
            if self._is_closing:
                return
            self.append_log(f"❌ AI 连接失败: {err}\n")
            QMessageBox.critical(self, "连接失败", f"无法连接到 AI 服务：{err}")

        run_async_task(_do_test, _ok, _err)

    def closeEvent(self, event):
        self._is_closing = True
        for timer_attr in ("auto_timer", "log_flush_timer", "task_elapsed_timer", "recorder_timer"):
            if hasattr(self, timer_attr):
                getattr(self, timer_attr).stop()
        for worker in list(_ACTIVE_WORKERS):
            if worker.isRunning():
                worker.wait(500)
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            event.accept()
        elif event.key() == Qt.Key_F10:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            event.accept()
        else:
            super().keyPressEvent(event)

    def on_save_ai_config(self):
        provider = "ollama" if self.cmb_ai_provider.currentIndex() == 0 else "api"
        model = self.txt_ai_model.text().strip()
        base_url = self.txt_ai_base_url.text().strip()
        api_key = self.txt_ai_api_key.text().strip()

        new_cfg = {"provider": provider}
        if provider == "ollama":
            new_cfg["ollama"] = {"model": model, "base_url": base_url}
        else:
            new_cfg["api"] = {"model": model, "base_url": base_url, "api_key": api_key}

        try:
            ai_service.update_ai_config(new_cfg)
            QMessageBox.information(self, "成功", "AI 配置已成功保存！")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))

    def on_save_keywords(self):
        lines = [line.strip() for line in self.txt_keywords.toPlainText().splitlines() if line.strip()]
        if not lines:
            QMessageBox.warning(self, "提示", "重点词汇不能为空。")
            return
        try:
            cfg_path = APP_DIR / "config.json"
            cfg = dashboard_server.read_json(cfg_path, {})
            cfg["keywords"] = lines
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            QMessageBox.information(self, "成功", f"已成功保存 {len(lines)} 个重点监控词！")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))


# ==============================================================================
# 程序主入口
# ==============================================================================
def main():
    # 适配高分屏缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("VideoScreen")

    window = VideoScreenMainWindow()
    # 默认直接最大化铺满屏幕，享受完整宽屏视野
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

