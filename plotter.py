#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Jun 2026.10.26
# 2026.11.10 deque による固定時間枠プロットを追加
#

import csv
import time
from collections import deque
from datetime import datetime

import pyqtgraph as pg

# ログのタイムスタンプ形式 (dataIO.CsvLog.make_timestamp と同じ)
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

# 表示する時間枠の既定値 [s]
DEFAULT_WINDOW_SEC = 60 * 60   # 1時間


def create_graph(ylabel, unit):
    graph = pg.PlotWidget()

    graph.setLabel("bottom", "Time", units="s")
    graph.setLabel("left", ylabel, units=unit)
    graph.showGrid(x=True, y=True)

    return graph


def parse_timestamp(value):
    """ログのタイムスタンプ文字列(または datetime / 数値)を epoch秒へ変換する。"""

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, datetime):
        return value.timestamp()

    return datetime.strptime(value, TIMESTAMP_FORMAT).timestamp()


class TimeWindowPlot(pg.PlotWidget):
    """
    直近 window_sec 秒分のデータだけを deque に保持して表示するグラフ。

    append() で1点ずつ追加し、時間枠より古い点は自動で捨てる。
    横軸は時刻(時:分:秒)、表示幅は常に window_sec 秒に固定する。
    """

    def __init__(
        self,
        ylabel,
        unit,
        window_sec=DEFAULT_WINDOW_SEC,
        log_y=False,
        parent=None,
    ):
        super().__init__(
            parent=parent,
            axisItems={"bottom": pg.DateAxisItem(orientation="bottom")},
        )

        self.window_sec = float(window_sec)
        self.log_y = log_y

        self.times = deque()    # epoch秒
        self.values = deque()

        self.setLabel("bottom", "Time")
        self.setLabel("left", ylabel, units=unit)
        self.showGrid(x=True, y=True)
        self.setLogMode(y=log_y)

        # 横軸は自前で固定するので自動調整は縦軸だけ
        self.enableAutoRange(axis="x", enable=False)
        self.enableAutoRange(axis="y", enable=True)

        self.curve = self.plot(
            [],
            [],
            pen=pg.mkPen("#00ccff", width=2),
            symbol="o",
            symbolSize=5,
        )

        self._update_x_range(time.time())

    def set_window(self, window_sec):
        """表示する時間枠 [s] を変更する。"""

        self.window_sec = float(window_sec)
        latest = self.times[-1] if self.times else time.time()
        self._trim(latest)
        self._redraw(latest)

    def clear_data(self):
        self.times.clear()
        self.values.clear()
        self._redraw(time.time())

    def append(self, timestamp, value):
        """
        1点追加する。

        timestamp: ログのタイムスタンプ文字列 / datetime / epoch秒
        value    : 数値 (数値に変換できない値、対数軸での0以下は無視)
        """

        try:
            t = parse_timestamp(timestamp)
            v = float(value)
        except (TypeError, ValueError):
            # "OFF" などは描画しない
            return

        if self.log_y and v <= 0:
            return

        self.times.append(t)
        self.values.append(v)

        self._trim(t)
        self._redraw(t)

    def _trim(self, latest):
        """時間枠より古い点を左端から捨てる。"""

        oldest_allowed = latest - self.window_sec

        while self.times and self.times[0] < oldest_allowed:
            self.times.popleft()
            self.values.popleft()

    def _update_x_range(self, latest):
        self.setXRange(latest - self.window_sec, latest, padding=0)

    def _redraw(self, latest):
        self.curve.setData(list(self.times), list(self.values))
        self._update_x_range(latest)


def load_csv(graph, filepath, value_column, time_column="timestamp"):
    time_values = []
    item_values = []
    start_time = None

    with open(filepath, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                timestamp = datetime.strptime(
                    row[time_column],
                    TIMESTAMP_FORMAT,
                )
                value = float(row[value_column])
            except (KeyError, TypeError, ValueError):
                # 壊れた行・列名不一致の行は飛ばす
                continue

            if start_time is None:
                start_time = timestamp

            time_values.append(
                (timestamp - start_time).total_seconds()
            )
            item_values.append(value)

    graph.plot(
        time_values,
        item_values,
        pen=pg.mkPen("#00ccff", width=2),
        symbol="o",
        symbolSize=5,
        clear=True,
    )
