#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Jun 2026.10.26
#

import csv
import pyqtgraph as pg
from datetime import datetime

def create_graph(ylabel, unit):
    graph = pg.PlotWidget()

    graph.setLabel("bottom", "Time", units="s")
    graph.setLabel("left", ylabel, units=unit)
    graph.showGrid(x=True, y=True)

    return graph

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
                    "%Y-%m-%d %H:%M:%S.%f",
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