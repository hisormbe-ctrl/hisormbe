#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
dataIO
I will utilize this function so many...

Functions
----
- 

"""

import sys
import csv
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer


class CommLog(QObject):
    """
    This class write log into csv.
    lines are:
        timestamp, source, message

    source:
        INFO
        TX
        RX
        ERROR
    """

    csv_written = Signal(list)

    def __init__(
        self, 
        file_name,
        output_directory="logs", 
        parent=None
    ):
        super().__init__(parent) # parent is for Qt inheritance

        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)

        self.file_path = output_path / file_name

        self.csv_file = open(
            self.file_path,
            mode="a",
            newline="",
            encoding="utf-8-sig",
        )

        self.writer = csv.writer(self.csv_file)

        self.writer.writerow(
            [
                "timestamp",
                "source",
                "message",
            ]
        )

        self.csv_file.flush()

    def write_row(self, source, message):
        """
        CSVへログを1行書き込む。
        """

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

        source = str(source)
        message = str(message).replace("\r", "").replace("\n", " ")

        row = [
            timestamp,
            source,
            message,
        ]

        with self.file_path.open(
            mode = "a",
            newline = "",
            encoding = "utf-8-sig",
        ) as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(row)

        # 異常終了時にもログが残りやすいように毎回flushする
        self.csv_file.flush()

        # GUIログへ通知
        self.csv_written.emit(row)

    def close(self):
        """
        CSVファイルを閉じる。
        """

        if self.csv_file is not None:
            if not self.csv_file.closed:
                self.csv_file.flush()
                self.csv_file.close()


class TempLog(QObject):
    """
    This class write temperature log into csv.
    lines are:
        timestamp, current, temperature

    """

    csv_written = Signal(list)

    def __init__(
        self, 
        file_name="TempLog.csv",
        output_directory="logs", 
        parent=None
    ):
        super().__init__(parent) # parent is for Qt inheritance

        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)

        self.file_path = output_path / file_name

        self.csv_file = open(
            self.file_path,
            mode="a",
            newline="",
            encoding="utf-8-sig",
        )

        self.writer = csv.writer(self.csv_file)

        self.writer.writerow(
            [
                "timestamp",
                "current",
                "temperature",
            ]
        )

        self.csv_file.flush()

    def write_row(self, current, temperature):
        """
        CSVへログを1行書き込む。
        """

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

        current = str(current)
        temperature = str(temperature).replace("\r", "").replace("\n", " ")

        row = [
            timestamp,
            current,
            temperature,
        ]

        with self.file_path.open(
            mode = "a",
            newline = "",
            encoding = "utf-8-sig",
        ) as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(row)

        # 異常終了時にもログが残りやすいように毎回flushする
        self.csv_file.flush()

        # GUIログへ通知
        self.csv_written.emit(row)

    def close(self):
        """
        CSVファイルを閉じる。
        """

        if self.csv_file is not None:
            if not self.csv_file.closed:
                self.csv_file.flush()
                self.csv_file.close()


if __name__=="__main__":

    comm = CommLog("communication_log.csv")
    temp = TempLog("temperature_log.csv")    
    comm.write_row("INFO","test line 1")
    comm.write_row("TX","test line 2")
    comm.close
    temp.write_row("10.0","273.15")

