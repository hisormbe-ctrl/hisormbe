#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Jun 2026.10.2
#

import sys,re

def apply_style(self):

    self.setStyleSheet(
        """
        QMainWindow {
            background-color: #20242b;
        }

        QWidget {
            color: #e8e8e8;
            font-size: 14px;
        }

        /* タブの下にあるページ領域 */
        QTabWidget::pane {
            border: 1px solid #606060;
            background-color: #20242b;
        }

        /* 通常のタブ */
        QTabBar::tab {
            background-color: #3a414b;
            color: #b5b5b5;
            padding: 8px 20px;
            border: 1px solid #606060;
            border-top-left-radius: 5px;
            border-top-right-radius: 5px;
            margin-right: 2px;
        }

        /* 選択中のタブ */
        QTabBar::tab:selected {
            background-color: #237a3b;
            color: #ffffff;
            font-weight: bold;
        }

        /* 選択されていないタブにマウスを乗せたとき */
        QTabBar::tab:!selected:hover {
            background-color: #4a535f;
            color: #ffffff;
        }

        QLabel#sectionLabel {
            font-size: 15px;
            font-weight: bold;
            margin-top: 10px;
        }

        QLabel#connectionStatus {
            padding: 5px;
            font-weight: bold;
        }

        QLabel#sequenceStatus,
        QLabel#gaugeValue {
            padding: 7px;
            border: 1px solid #606060;
            border-radius: 4px;
            background-color: #15181d;
            font-weight: bold;
        }

        QLabel#csvPath {
            color: #b5b5b5;
            font-size: 12px;
        }

        QPushButton {
            min-height: 38px;
            padding: 4px 12px;
            border: 1px solid #707070;
            border-radius: 5px;
            background-color: #3a414b;
        }

        QPushButton:hover {
            background-color: #4a535f;
        }

        QPushButton:pressed {
            background-color: #252a31;
        }

        QPushButton:disabled {
            color: #777777;
            background-color: #303030;
        }

        QPushButton#onButton {
            background-color: #237a3b;
            font-weight: bold;
        }

        QPushButton#onButton:hover {
            background-color: #2d964a;
        }

        QPushButton#offButton {
            background-color: #9a3535;
            font-weight: bold;
        }

        QPushButton#offButton:hover {
            background-color: #b84444;
        }

        QComboBox,
        QLineEdit,
        QTextEdit {
            background-color: #15181d;
            border: 1px solid #606060;
            border-radius: 4px;
            padding: 5px;
        }

        QTextEdit {
            font-family: Consolas;
            font-size: 13px;
        }

        """
    )

