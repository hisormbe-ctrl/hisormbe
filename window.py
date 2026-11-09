#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Jun 2026.9.25
#
# 2026.11.9 add vacuum tab contents.
#

import sys,re
from datetime import datetime

from PySide6.QtGui import (
    QIntValidator,
)

from PySide6.QtWidgets import (
    QApplication,    
    QMainWindow,
    QTabWidget,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,    
    QGridLayout,
    QComboBox,
    QLabel,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QFrame,
)
from PySide6.QtCore import QTimer

import cv2
from camera import Camera
# added VacLog.
from dataIO import CommLog, TempLog, LogManager, VacLog
from style import apply_style
import communication as comm
import pyqtgraph as pg
import plotter
from detachable_tabs import DetachableTabWidget


class MainWindow(QMainWindow):

    # Picoからの応答待ち時間
    RESPONSE_TIMEOUT_MS = 3_000

    # カメラ・画像認識
    # CAMERA_ID = 0
    GAUGE_MODEL_PATH = "7seg_svm_model.joblib"

    def __init__(self, camera_id):
        super().__init__()

        self.camera_id = camera_id
        self.setWindowTitle("autoMBE")
        self.resize(780,640)

        comm.initialize_serial(self)

        apply_style(self)

        # Logger generate
        self.logs = LogManager(self)

        # graph creation
        self.logs.temp_log.csv_written.connect(
            lambda row: plotter.load_csv(
                self.temp_graph,
                self.logs.temp_log.file_path,
                "temp_c",
                time_column="timestamp",
            )
        )        

        # servo tab, update status
        self.logs.comm_log.csv_written.connect(self.update_servo_status)

        # タブ管理
        self.tabs = DetachableTabWidget(self)

        self.main_tab = self.create_main_tab()
        self.temperature_tab = self.create_temperature_tab()        
# vacuum
        self.vacuum_tab = self.create_vacuum_tab()
        self.camera_tab = self.create_camera_tab()
        self.servo_tab = self.create_servo_tab()        
        self.comm_tab = self.create_communication_tab()

        # servo sequence initialize
        self.cycle_timer = QTimer(self)
        self.cycle_timer.setSingleShot(True)
        self.cycle_timer.timeout.connect(self.advance_cycle)

        # run refresh_ports automatically
        self.tabs.currentChanged.connect(
            lambda index: (
                comm.refresh_ports(self)
                if self.tabs.widget(index) is self.comm_tab
                else None
            )
        )

        # tab分離処理
        self.tabs.tabDetached.connect(
            lambda page: (
                comm.refresh_ports(self)
                if page is self.comm_tab
                else None
            )
        )

        # when initially comm_tab is selected
        if self.tabs.currentWidget() is self.comm_tab:
            comm.refresh_ports(self)

        self.tabs.addTab(self.main_tab, "メイン")
        self.tabs.addTab(self.temperature_tab, "温度")
        self.tabs.addTab(self.vacuum_tab, "真空")
        self.tabs.addTab(self.camera_tab, "カメラ")
        self.tabs.addTab(self.servo_tab, "サーボ") 
        self.tabs.addTab(self.comm_tab, "通信")

        self.setCentralWidget(self.tabs)

        # self.logs.comm_log.csv_written.connect(
        #     lambda row: self.on_csv_written(row, self.comm_log_text)
        # )

        # self.logs.temp_log.csv_written.connect(
        #     lambda row: self.on_csv_written(row, self.temp_log_text)
        # )

        self.logs.record_log("INFO", "Program started.")      


    def add_hline(self, layout):

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)


    def iteration(self, CYCLE_INTERVAL_TIME):
        interval_ms = int(float(CYCLE_INTERVAL_TIME) * 1000)

        if interval_ms <= 0:
            raise ValueError("時間間隔は0秒より大きくしてください。")

        self.cycle_timer.stop()

        self.cycle_interval_ms = interval_ms
        self.cycle_phase = "WAIT"

        # 最初は指定時間だけ待つ
        self.cycle_timer.start(self.cycle_interval_ms)


    def advance_cycle(self):
        if self.cycle_phase == "WAIT":
            comm.send_command(self, "OPEN")
            self.cycle_phase = "OPEN"
            self.cycle_timer.start(1500)
            comm.send_command(self, "TEMP")
            self.cycle_timer.start(500)            

        else:
            comm.send_command(self, "CLOSE")
            self.cycle_phase = "WAIT"

            # CLOSEの後、指定時間だけ待つ
            self.cycle_timer.start(self.cycle_interval_ms)


    def stop_iteration(self):
        self.cycle_timer.stop()
        comm.send_command(self, "CLOSE")
        self.cycle_phase = "WAIT"


    def create_main_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("autoMBE"))

#        self.add_hline(layout)

        layout.addWidget(QLabel("Thermmo Meter Shutter"))
        self.start_button = QPushButton("START")
        self.stop_button = QPushButton("STOP")
        self.intervaltime = QLineEdit()
        self.intervaltime.setText("1")
        self.time_notice = QLabel("秒（1~600）")
        validator = QIntValidator(1, 600, self.intervaltime)
        self.intervaltime.setValidator(validator)
        CYCLE_INTERVAL_TIME = int(self.intervaltime.text()) # integer.
        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.start_button,1)
        hbox1.addWidget(self.stop_button,1)
        hbox1.addWidget(self.intervaltime,1)
        hbox1.addWidget(self.time_notice,1)
        layout.addLayout(hbox1)

        self.start_button.clicked.connect(
            lambda checked: (
                self.iteration(self.intervaltime.text())
                if self.intervaltime.hasAcceptableInput()
                else None
            )
        )

        self.stop_button.clicked.connect(self.stop_iteration)

        layout.addSpacing(20)
#        self.add_hline(layout)

        self.comm_log_path_label = QLabel(
            f"CommLog: {self.logs.comm_log.file_path}\n"
        )
        
        log_label = QLabel("Communication log")
        log_label.setObjectName("sectionLabel")
        layout.addWidget(log_label)

        self.comm_log_text = QTextEdit()
        self.comm_log_text.setReadOnly(True)
        self.comm_log_text.setLineWrapMode(
            QTextEdit.LineWrapMode.NoWrap
        )
        visible_lines = 8
        line_height = self.comm_log_text.fontMetrics().lineSpacing()
        self.comm_log_text.setFixedHeight(line_height * visible_lines + 16)
        self.comm_log_path_label.setObjectName("CommcsvPath")
        layout.addWidget(self.comm_log_text)
        layout.addWidget(self.comm_log_path_label)

        # 通信ログ → 通信ログ欄
        self.logs.comm_log.csv_written.connect(
            lambda row: self.on_csv_written(row, self.comm_log_text)
        )

        layout.addStretch()

        return tab


    def on_csv_written(self, row, text_widget):
        if text_widget is self.comm_log_text:
            timestamp, source, message = row
            text = f"{timestamp}  [{source}] {message}"
        else:
            text = "  ".join(str(value) for value in row)

        text_widget.append(text)

        scroll_bar = text_widget.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())


    def create_temperature_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        label1 = QLabel("温度計則")
        layout.addWidget(label1)

# plot.
        self.temp_graph = plotter.create_graph("Temperature", "°C")
        layout.addWidget(self.temp_graph)
# graph update
        # self.plot_timer = QTimer(self)
        # self.plot_timer.timeout.connect(self.update_graph)

        self.temp_log_path_label = QLabel(
            f"TempLog: {self.logs.temp_log.file_path}\n"
        )
        
        log_label = QLabel("Temperature log")
        log_label.setObjectName("sectionLabel")
        layout.addWidget(log_label)

        self.temp_log_text = QTextEdit()
        self.temp_log_text.setReadOnly(True)
        self.temp_log_text.setLineWrapMode(
            QTextEdit.LineWrapMode.NoWrap
        )
        visible_lines = 8
        line_height = self.temp_log_text.fontMetrics().lineSpacing()
        self.temp_log_text.setFixedHeight(line_height * visible_lines + 16)
        self.temp_log_path_label.setObjectName("TempcsvPath")
        layout.addWidget(self.temp_log_text)
        layout.addWidget(self.temp_log_path_label)

        # 温度ログ → 温度ログ欄
        self.logs.temp_log.csv_written.connect(
            lambda row: self.on_csv_written(row, self.temp_log_text)
        )

        layout.addStretch()

        return tab


    def update_graph(self):
        # pressure=OFF の行は plotter.load_csv 側で読み飛ばされる
        plotter.load_csv(
            self.vac_graph,
            self.logs.vac_log.file_path,
            value_column="pressure",
            time_column="timestamp",
        )

# added for vac.
    def create_vacuum_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        label1 = QLabel("真空計則")
        layout.addWidget(label1)

# plot.
        self.vac_graph = plotter.create_graph("Vacuum", "Pa")
        layout.addWidget(self.vac_graph)
        # 圧力は桁が大きく変わるので対数軸
        self.vac_graph.setLogMode(y=True)
# graph update: VacLogに1行記録されるたびに再描画
        self.logs.vac_log.csv_written.connect(
            lambda row: self.update_graph()
        )

        self.vac_log_path_label = QLabel(
            f"VacLog: {self.logs.vac_log.file_path}\n"
        )
        
        log_label = QLabel("Vacuum log")
        log_label.setObjectName("sectionLabel")
        layout.addWidget(log_label)

        self.vac_log_text = QTextEdit()
        self.vac_log_text.setReadOnly(True)
        self.vac_log_text.setLineWrapMode(
            QTextEdit.LineWrapMode.NoWrap
        )
        visible_lines = 8
        line_height = self.vac_log_text.fontMetrics().lineSpacing()
        self.vac_log_text.setFixedHeight(line_height * visible_lines + 16)
        self.vac_log_path_label.setObjectName("VaccsvPath")
        layout.addWidget(self.vac_log_text)
        layout.addWidget(self.vac_log_path_label)

        self.logs.vac_log.csv_written.connect(
            lambda row: self.on_csv_written(row, self.vac_log_text)
        )

        layout.addStretch()

        return tab


    def create_camera_tab(self):

        self.camera = Camera(camera_id=self.camera_id)

        return self.camera


    def create_servo_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        label1 = QLabel("サーボ制御")
        layout.addWidget(label1)

        self.servo_status_button = QPushButton("STATUS")
        self.servo_status = QLabel("Unknow")
        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.servo_status_button,1)
        hbox1.addWidget(self.servo_status,1)

        self.servo_open_button = QPushButton("OPEN")
        self.servo_close_button = QPushButton("CLOSE")        
        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.servo_open_button,1)
        hbox2.addWidget(self.servo_close_button,1)

        self.servo_status_button.clicked.connect(
            lambda checked: comm.send_command(self,"STATUS")
        )
        self.servo_open_button.clicked.connect(
            lambda checked: comm.send_command(self,"OPEN")
        )
        self.servo_close_button.clicked.connect(
            lambda checked: comm.send_command(self,"CLOSE")
        )

        layout.addLayout(hbox1)
        layout.addLayout(hbox2)        
        layout.addStretch()

        return tab

    def update_servo_status(self, row):
        direction = row[1]
        message = row[2]

        if direction != "RX" or not message.startswith("STATUS"):
            return

        self.servo_status.setText(f"{message}")


    def create_communication_tab(self):

        tab = QWidget()
        layout = QGridLayout(tab)
        layout.addWidget(QLabel("通信"),0,0,1,4)

        port_label = QLabel("COM port")

        self.port_combo = QComboBox()
        # self.port_combo.setMinimumWidth(300)
  
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(
            lambda checked: comm.refresh_ports(self)
        )
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(
            lambda checked: comm.toggle_serial_connection(self)
        )

        self.connection_status_label = QLabel(
            "Disconnected"
        )
        self.connection_status_label.setObjectName(
            "connectionStatus"
        )

        layout.addWidget(port_label, 1, 0)
        layout.addWidget(self.port_combo, 1, 1)
        layout.addWidget(self.refresh_button, 1, 2)
        layout.addWidget(self.connect_button, 1, 3)

        layout.addWidget(
            self.connection_status_label,
            2, 0, 1, 4,
        )

        for column in range(4):
            layout.setColumnStretch(column, 1)
            # layout.setColumnStretch(1, 1)
            layout.setRowStretch(3, 1)

        return tab

def main():

    app = QApplication(sys.argv)
    

if __name__=='__main__':

    print("Window...")