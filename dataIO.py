#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""通信・温度・真空ログのCSV出力。"""

import csv
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class CsvLog(QObject):
    """CSVログ共通処理。"""

    csv_written = Signal(list)

    def __init__(
        self,
        file_name,
        columns,
        output_directory="logs",
        parent=None,
    ):
        super().__init__(parent)

        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)

        self.file_path = output_path / file_name

        # 既存ファイルのヘッダーが現在の列定義と異なる場合は、
        # 古いファイルを退避して新しいファイルを作る。
        self._backup_if_header_mismatch(columns)

        # 新規ファイル、または空ファイルの場合だけヘッダーを書く。
        needs_header = (
            not self.file_path.exists()
            or self.file_path.stat().st_size == 0
        )

        self.csv_file = self.file_path.open(
            mode="a",
            newline="",
            encoding="utf-8-sig",
        )
        self.writer = csv.writer(self.csv_file)

        if needs_header:
            self.writer.writerow(columns)
            self.csv_file.flush()

    def _backup_if_header_mismatch(self, columns):
        """列定義が変わった既存CSVを *_old_YYYYmmdd_HHMMSS.csv へ退避する。"""

        if (
            not self.file_path.exists()
            or self.file_path.stat().st_size == 0
        ):
            return

        with self.file_path.open(
            encoding="utf-8-sig", newline=""
        ) as f:
            header = next(csv.reader(f), [])

        if header == list(columns):
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.file_path.with_name(
            f"{self.file_path.stem}_old_{stamp}{self.file_path.suffix}"
        )
        self.file_path.rename(backup_path)

    @staticmethod
    def make_timestamp():
        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

    def write_row(self, *values, timestamp=None):
        """タイムスタンプを付けて1行記録する。

        timestamp を渡すと、その値をそのまま使う
        （別ログと同じ時刻で記録したい場合）。
        記録した行（list）を返す。
        """

        if self.csv_file.closed:
            raise RuntimeError(
                f"ログファイルは既に閉じています: {self.file_path}"
            )

        if timestamp is None:
            timestamp = self.make_timestamp()

        row = [timestamp] + [
            str(value).replace("\r", "").replace("\n", " ")
            for value in values
        ]

        self.writer.writerow(row)
        self.csv_file.flush()

        # GUIへ記録内容を通知。
        self.csv_written.emit(row)

        return row

    def close(self):
        """ログファイルを閉じる。"""

        if not self.csv_file.closed:
            self.csv_file.flush()
            self.csv_file.close()


class CommLog(CsvLog):
    def __init__(
        self,
        file_name="communication.csv",
        output_directory="logs",
        parent=None,
    ):
        super().__init__(
            file_name=file_name,
            columns=["timestamp", "source", "message"],
            output_directory=output_directory,
            parent=parent,
        )


class TempLog(CsvLog):
    def __init__(
        self,
        file_name="TempLog.csv",
        output_directory="logs",
        parent=None,
    ):
        super().__init__(
            file_name=file_name,
            columns=["timestamp", "raw", "voltage", "temp_c"],
            output_directory=output_directory,
            parent=parent,
        )


class VacLog(CsvLog):
    def __init__(
        self,
        file_name="VacLog.csv",
        output_directory="logs",
        parent=None,
    ):
        super().__init__(
            file_name=file_name,
            columns=["timestamp", "raw", "voltage", "gauge_v", "pressure"],
            output_directory=output_directory,
            parent=parent,
        )


# Picoの温度応答: "DATA TEMP raw=123.0 voltage=0.2460 temp_c=24.60"
TEMP_RX_PATTERN = re.compile(
    r"^DATA\s+TEMP\s+"
    r"raw=(?P<raw>\S+)\s+"
    r"voltage=(?P<voltage>\S+)\s+"
    r"temp_c=(?P<temp_c>\S+)"
)


def parse_temp_rx(message):
    """温度応答行を (raw, voltage, temp_c) のfloatで返す。該当しなければNone。"""

    match = TEMP_RX_PATTERN.match(str(message).strip())

    if match is None:
        return None

    try:
        return (
            float(match.group("raw")),
            float(match.group("voltage")),
            float(match.group("temp_c")),
        )
    except ValueError:
        return None


# Picoの真空応答:
#   "DATA VAC raw=500.0 voltage=1.5000 gauge_v=7.439 pressure=4.39e-04"
#   フィラメントOFF時は pressure=OFF
VAC_RX_PATTERN = re.compile(
    r"^DATA\s+VAC\s+"
    r"raw=(?P<raw>\S+)\s+"
    r"voltage=(?P<voltage>\S+)\s+"
    r"gauge_v=(?P<gauge_v>\S+)\s+"
    r"pressure=(?P<pressure>\S+)"
)


def parse_vac_rx(message):
    """真空応答行を (raw, voltage, gauge_v, pressure) で返す。該当しなければNone。

    raw, voltage, gauge_v は float。
    pressure は float、フィラメントOFF時は None。
    """

    match = VAC_RX_PATTERN.match(str(message).strip())

    if match is None:
        return None

    try:
        raw = float(match.group("raw"))
        voltage = float(match.group("voltage"))
        gauge_v = float(match.group("gauge_v"))

        pressure_text = match.group("pressure")
        if pressure_text.upper() == "OFF":
            pressure = None
        else:
            pressure = float(pressure_text)

    except ValueError:
        return None

    return raw, voltage, gauge_v, pressure


class LogManager(QObject):
    csv_written = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.comm_log = CommLog(parent=self)
        self.temp_log = TempLog(parent=self)
        self.vac_log = VacLog(parent=self)

        self.comm_log.csv_written.connect(self.csv_written.emit)
        self.temp_log.csv_written.connect(self.csv_written.emit)
        self.vac_log.csv_written.connect(self.csv_written.emit)

    def record_log(self, source, message):
        row = self.comm_log.write_row(source, message)

        # 温度データのRXは、同じタイムスタンプでTempLogにも記録する。
        if source == "RX":
            temp_values = parse_temp_rx(message)

            if temp_values is not None:
                raw, voltage, temp_c = temp_values
                self.temp_log.write_row(
                    f"{raw:.1f}",
                    f"{voltage:.4f}",
                    f"{temp_c:.2f}",
                    timestamp=row[0],
                )

            # 真空データのRXは、同じタイムスタンプでVacLogにも記録する。
            vac_values = parse_vac_rx(message)

            if vac_values is not None:
                raw, voltage, gauge_v, pressure = vac_values
                self.vac_log.write_row(
                    f"{raw:.1f}",
                    f"{voltage:.4f}",
                    f"{gauge_v:.3f}",
                    "OFF" if pressure is None else f"{pressure:.2e}",
                    timestamp=row[0],
                )

        return row

    def close(self):
        self.comm_log.close()
        self.temp_log.close()
        self.vac_log.close()


if __name__ == "__main__":
    logs = LogManager()

    try:
        logs.record_log("INFO", "test line 1")
        logs.record_log("TX", "test line 2")
        logs.record_log(
            "RX", "DATA TEMP raw=123.0 voltage=0.2460 temp_c=24.60"
        )
        logs.record_log(
            "RX",
            "DATA VAC raw=500.0 voltage=1.5000 gauge_v=7.439 pressure=4.39e-04",
        )
        logs.record_log(
            "RX",
            "DATA VAC raw=1500.0 voltage=4.5000 gauge_v=21.773 pressure=OFF",
        )
    finally:
        logs.close()