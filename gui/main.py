#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ゲージリード・シーケンス制御GUI

機能
----
・Raspberry Pi PicoへUSBシリアル通信でコマンドを送信
・Picoから返されたメッセージを受信
・送受信内容をCommLogへ保存
・温度ADC値と画像認識値をTempLogへ保存
・QTimerを使ってゲージリード・シーケンスを実行

シーケンス
----------
SEQUENCE START
    1. STATUS確認
    2. サーボOPEN
    3. 5秒待機
    4. 温度ADC読取り
    5. カメラから画像認識値を取得
    6. TempLogへ記録
    7. サーボCLOSE
    8. 60秒待機
    9. 2へ戻る

SEQUENCE STOP / CLOSE
    ・待機タイマーを停止
    ・シーケンスを終了
    ・サーボへCLOSEを送信

Picoへ送信するコマンド
----------------------
OFF
OPEN
CLOSE
TEMP
STATUS
PING
PULSE 1500
"""

import re
import sys
from datetime import datetime

import serial
from serial.tools import list_ports

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dataIO import CommLog, TempLog
from gauge_reader import GaugeReader


class MainWindow(QMainWindow):

    SERIAL_BAUDRATE = 115200
    SERIAL_POLL_INTERVAL_MS = 20

    # シーケンス時間
    OPEN_WAIT_MS = 5_000
    NEXT_SEQUENCE_WAIT_MS = 60_000

    # Picoからの応答待ち時間
    RESPONSE_TIMEOUT_MS = 3_000

    # カメラ・画像認識
    CAMERA_ID = 0
    GAUGE_MODEL_PATH = "7seg_svm_model.joblib"

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Gauge Read Sequence Controller")
        self.resize(780, 640)

        # ====================================================
        # シリアル通信
        # ====================================================

        self.serial_port = None

        # Picoからの受信途中データを保存するバッファ
        self.receive_buffer = b""

        # ====================================================
        # ログ
        # ====================================================

        self.csv_writer = CommLog(
            "communication.csv"
        )

        self.temp_log = TempLog(
            "TempLog.csv"
        )

        self.csv_writer.csv_written.connect(
            self.on_csv_written
        )

        # ====================================================
        # シーケンス状態
        # ====================================================

        self.sequence_running = False
        self.sequence_state = "IDLE"
        self.sequence_count = 0

        # 現在、Picoからの返信を待っているコマンド
        self.awaiting_response = None

        # 1サイクル中に取得した温度値
        self.pending_temperature = None

        # 画像認識器
        # モデルとカメラはSET ROIまたは読取り時に遅延初期化する。
        self.gauge_reader = GaugeReader(
            cam_id=self.CAMERA_ID,
            model_path=self.GAUGE_MODEL_PATH,
        )

        # ====================================================
        # GUI
        # ====================================================

        self.create_ui()
        self.apply_style()

        # ====================================================
        # タイマー
        # ====================================================

        # シリアル受信用タイマー
        self.serial_timer = QTimer(self)
        self.serial_timer.setInterval(
            self.SERIAL_POLL_INTERVAL_MS
        )
        self.serial_timer.timeout.connect(
            self.read_serial
        )

        # 5秒待機・60秒待機に使うタイマー
        self.sequence_timer = QTimer(self)
        self.sequence_timer.setSingleShot(True)
        self.sequence_timer.timeout.connect(
            self.advance_sequence
        )

        # Pico応答タイムアウト監視
        self.response_timeout_timer = QTimer(self)
        self.response_timeout_timer.setSingleShot(True)
        self.response_timeout_timer.timeout.connect(
            self.on_response_timeout
        )

        # COMポート一覧を取得
        self.refresh_ports()

        # 初期状態では未接続
        self.update_control_states()

        self.record_log(
            "INFO",
            (
                "Program started. "
                f"CommLog: {self.get_log_path(self.csv_writer)}, "
                f"TempLog: {self.get_log_path(self.temp_log)}"
            ),
        )

    # ========================================================
    # GUI作成
    # ========================================================

    def create_ui(self):

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # ----------------------------------------------------
        # シリアル接続部分
        # ----------------------------------------------------

        connection_layout = QGridLayout()

        port_label = QLabel("COM port")

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(300)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(
            self.refresh_ports
        )

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(
            self.toggle_serial_connection
        )

        self.connection_status_label = QLabel(
            "Disconnected"
        )
        self.connection_status_label.setObjectName(
            "connectionStatus"
        )

        connection_layout.addWidget(
            port_label,
            0,
            0,
        )
        connection_layout.addWidget(
            self.port_combo,
            0,
            1,
        )
        connection_layout.addWidget(
            self.refresh_button,
            0,
            2,
        )
        connection_layout.addWidget(
            self.connect_button,
            0,
            3,
        )
        connection_layout.addWidget(
            self.connection_status_label,
            1,
            0,
            1,
            4,
        )

        main_layout.addLayout(connection_layout)

        # ----------------------------------------------------
        # ゲージリード・シーケンス
        # ----------------------------------------------------

        sequence_label = QLabel("Gauge read sequence")
        sequence_label.setObjectName("sectionLabel")
        main_layout.addWidget(sequence_label)

        sequence_layout = QHBoxLayout()

        self.sequence_start_button = QPushButton(
            "SEQUENCE START"
        )
        self.sequence_start_button.setObjectName(
            "onButton"
        )
        self.sequence_start_button.clicked.connect(
            self.start_sequence
        )

        self.sequence_stop_button = QPushButton(
            "SEQUENCE STOP / CLOSE"
        )
        self.sequence_stop_button.setObjectName(
            "offButton"
        )
        self.sequence_stop_button.clicked.connect(
            self.stop_sequence
        )

        sequence_layout.addWidget(
            self.sequence_start_button
        )
        sequence_layout.addWidget(
            self.sequence_stop_button
        )

        main_layout.addLayout(sequence_layout)

        self.sequence_status_label = QLabel(
            "Sequence: IDLE"
        )
        self.sequence_status_label.setObjectName(
            "sequenceStatus"
        )
        main_layout.addWidget(
            self.sequence_status_label
        )

        # ----------------------------------------------------
        # 単独操作ボタン
        # ----------------------------------------------------

        manual_label = QLabel("Manual operation")
        manual_label.setObjectName("sectionLabel")
        main_layout.addWidget(manual_label)

        manual_layout = QHBoxLayout()

        self.open_button = QPushButton("OPEN")

        self.open_button.clicked.connect(
            self.open_then_temp
        )

        self.close_button = QPushButton("CLOSE")
        self.close_button.clicked.connect(
            lambda: self.send_command("CLOSE")
        )

        self.status_button = QPushButton("STATUS")
        self.status_button.clicked.connect(
            lambda: self.send_command("STATUS")
        )

        self.ping_button = QPushButton("PING")
        self.ping_button.clicked.connect(
            lambda: self.send_command("PING")
        )

        manual_layout.addWidget(self.open_button)
        manual_layout.addWidget(self.close_button)
        manual_layout.addWidget(self.status_button)
        manual_layout.addWidget(self.ping_button)

        main_layout.addLayout(manual_layout)

        # ----------------------------------------------------
        # 任意パルス幅
        # ----------------------------------------------------

        pulse_layout = QHBoxLayout()

        pulse_label = QLabel("Pulse width [µs]")

        self.pulse_edit = QLineEdit("1500")
        self.pulse_edit.setPlaceholderText(
            "500 - 2500"
        )

        self.pulse_button = QPushButton(
            "Send pulse"
        )
        self.pulse_button.clicked.connect(
            self.send_custom_pulse
        )

        pulse_layout.addWidget(pulse_label)
        pulse_layout.addWidget(self.pulse_edit)
        pulse_layout.addWidget(self.pulse_button)

        main_layout.addLayout(pulse_layout)

        # ----------------------------------------------------
        # Camera / gauge recognition
        # ----------------------------------------------------

        camera_label = QLabel("Camera / gauge recognition")
        camera_label.setObjectName("sectionLabel")
        main_layout.addWidget(camera_label)

        camera_layout = QHBoxLayout()

        self.set_roi_button = QPushButton("SET ROI")
        self.set_roi_button.clicked.connect(
            self.select_gauge_roi
        )

        self.read_gauge_button = QPushButton("READ GAUGE")
        self.read_gauge_button.clicked.connect(
            self.test_read_gauge
        )

        self.gauge_value_label = QLabel(
            "Gauge: ROI not set"
        )
        self.gauge_value_label.setObjectName(
            "gaugeValue"
        )

        camera_layout.addWidget(self.set_roi_button)
        camera_layout.addWidget(self.read_gauge_button)
        camera_layout.addWidget(self.gauge_value_label)

        main_layout.addLayout(camera_layout)

        # ----------------------------------------------------
        # Temperature read
        # ----------------------------------------------------

        temp_label = QLabel("Read temperature")
        temp_label.setObjectName("sectionLabel")
        main_layout.addWidget(temp_label)

        temp_layout = QHBoxLayout()

        self.read_adc_button = QPushButton("READ ADC")
        self.read_adc_button.clicked.connect(
            lambda: self.send_command("TEMP")
        )

        temp_layout.addWidget(self.read_adc_button)

        main_layout.addLayout(temp_layout)

        # ----------------------------------------------------
        # ログ表示
        # ----------------------------------------------------

        log_label = QLabel("Communication log")
        log_label.setObjectName("sectionLabel")
        main_layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(
            QTextEdit.LineWrapMode.NoWrap
        )

        main_layout.addWidget(self.log_text)

        # ----------------------------------------------------
        # CSV保存先表示
        # ----------------------------------------------------

        self.csv_path_label = QLabel(
            (
                f"CommLog: {self.get_log_path(self.csv_writer)}\n"
                f"TempLog: {self.get_log_path(self.temp_log)}"
            )
        )
        self.csv_path_label.setObjectName("csvPath")

        main_layout.addWidget(self.csv_path_label)

        # 手動操作ボタン一覧
        self.manual_buttons = [
            self.open_button,
            self.close_button,
            self.status_button,
            self.ping_button,
            self.pulse_button,
            self.read_adc_button,
        ]

    def open_then_temp(self):
        self.open_button.setEnabled(False)

        self.send_command("OPEN")

        QTimer.singleShot(
            5000,
            self.measure_and_capture,
        )


    # ========================================================
    # デザイン
    # ========================================================

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

    # ========================================================
    # COMポート一覧
    # ========================================================

    def refresh_ports(self):

        previous_device = self.port_combo.currentData()

        self.port_combo.clear()

        ports = list(list_ports.comports())

        for port in ports:
            label = f"{port.device}  {port.description}"

            self.port_combo.addItem(
                label,
                port.device,
            )

        if not ports:
            self.port_combo.addItem(
                "No serial port found",
                None,
            )

            self.record_log(
                "INFO",
                "No serial port found.",
            )
            return

        # 前に選択していたCOMポートを再選択
        if previous_device is not None:
            for index in range(
                self.port_combo.count()
            ):
                if (
                    self.port_combo.itemData(index)
                    == previous_device
                ):
                    self.port_combo.setCurrentIndex(
                        index
                    )
                    break

    # ========================================================
    # シリアル接続
    # ========================================================

    def toggle_serial_connection(self):

        if self.is_serial_connected():
            self.disconnect_serial(send_off=True)
        else:
            self.connect_serial()

    def connect_serial(self):

        port_name = self.port_combo.currentData()

        if port_name is None:
            self.record_log(
                "ERROR",
                "COM port is not selected.",
            )
            return

        try:
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=self.SERIAL_BAUDRATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,
                write_timeout=1,
            )

            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            self.receive_buffer = b""

            self.serial_timer.start()

            self.connect_button.setText("Disconnect")

            self.connection_status_label.setText(
                f"Connected: {port_name} "
                f"@ {self.SERIAL_BAUDRATE} baud"
            )

            self.record_log(
                "INFO",
                f"Serial connected: {port_name}",
            )

            self.update_control_states()

            # Picoの起動後に現在状態を表示する
            QTimer.singleShot(
                1000,
                self.request_status,
            )

        except serial.SerialException as error:
            self.serial_port = None

            self.record_log(
                "ERROR",
                f"Serial connection failed: {error}",
            )

            self.update_control_states()

    def disconnect_serial(self, send_off=True):

        if self.serial_port is None:
            return

        # 切断前にシーケンスを停止する
        self.clear_sequence_runtime(
            state="IDLE"
        )

        try:
            if (
                send_off
                and self.serial_port.is_open
            ):
                # 切断時は安全のためOFFを送信
                command_data = b"OFF\n"

                self.serial_port.write(command_data)
                self.serial_port.flush()

                self.record_log(
                    "TX",
                    "OFF (before disconnect)",
                )

        except serial.SerialException as error:
            self.record_log(
                "ERROR",
                f"OFF command failed: {error}",
            )

        self.serial_timer.stop()

        try:
            if self.serial_port.is_open:
                self.serial_port.close()

        except serial.SerialException as error:
            self.record_log(
                "ERROR",
                f"Serial close failed: {error}",
            )

        self.serial_port = None
        self.receive_buffer = b""

        self.connect_button.setText("Connect")
        self.connection_status_label.setText(
            "Disconnected"
        )

        self.sequence_status_label.setText(
            "Sequence: IDLE"
        )

        self.update_control_states()

        self.record_log(
            "INFO",
            "Serial disconnected.",
        )

    def is_serial_connected(self):

        return (
            self.serial_port is not None
            and self.serial_port.is_open
        )

    def request_status(self):

        if self.is_serial_connected():
            self.send_command("STATUS")

    # ========================================================
    # コマンド送信
    # ========================================================

    def send_command(self, command):
        """
        Picoへ1行のコマンドを送信する。

        成功時はTrue、失敗時はFalseを返す。
        """

        if not self.is_serial_connected():
            self.record_log(
                "ERROR",
                "Serial port is not connected.",
            )
            return False

        command = str(command).strip()

        if not command:
            return False

        try:
            send_data = (
                command + "\n"
            ).encode("utf-8")

            self.serial_port.write(send_data)
            self.serial_port.flush()

            self.record_log(
                "TX",
                command,
            )

            return True

        except (
            serial.SerialException,
            serial.SerialTimeoutException,
        ) as error:

            self.record_log(
                "ERROR",
                f"Serial write failed: {error}",
            )

            self.disconnect_serial(
                send_off=False
            )

            return False

    def send_custom_pulse(self):

        pulse_text = self.pulse_edit.text().strip()

        try:
            pulse_us = int(pulse_text)

        except ValueError:
            self.record_log(
                "ERROR",
                f"Invalid pulse value: {pulse_text}",
            )
            return

        if not 500 <= pulse_us <= 2500:
            self.record_log(
                "ERROR",
                "Pulse width must be between "
                "500 and 2500 µs.",
            )
            return

        self.send_command(
            f"PULSE {pulse_us}"
        )

    # ========================================================
    # シーケンス開始・停止
    # ========================================================

    def start_sequence(self):
        """
        SEQUENCE STARTボタンから呼ばれる。

        STATUS応答を確認してから最初のサイクルを始める。
        """

        if self.sequence_running:
            self.record_log(
                "INFO",
                "Sequence is already running.",
            )
            return

        if not self.is_serial_connected():
            self.record_log(
                "ERROR",
                "Sequence cannot start: Pico is not connected.",
            )
            return

        if not self.gauge_reader.has_roi:
            self.record_log(
                "ERROR",
                "Sequence cannot start: gauge ROI is not set.",
            )
            self.gauge_value_label.setText(
                "Gauge: set ROI before starting"
            )
            return

        # 古い受信データがSTATUS判定へ混ざるのを防ぐ
        try:
            self.serial_port.reset_input_buffer()
        except serial.SerialException as error:
            self.record_log(
                "ERROR",
                f"Input buffer reset failed: {error}",
            )
            return

        self.receive_buffer = b""

        self.sequence_running = True
        self.sequence_state = "WAIT_STATUS"
        self.sequence_count = 0
        self.pending_temperature = None

        self.sequence_status_label.setText(
            "Sequence: checking Pico STATUS..."
        )

        self.record_log(
            "INFO",
            "SEQUENCE START requested.",
        )

        self.update_control_states()

        self.send_sequence_command(
            "STATUS"
        )

    def stop_sequence(self):
        """
        SEQUENCE STOP / CLOSEボタンから呼ばれる。

        現在の工程に関係なく待機を中止し、
        サーボへCLOSEを送信する。
        """

        was_running = self.sequence_running

        self.clear_sequence_runtime(
            state="STOPPED"
        )

        self.sequence_status_label.setText(
            "Sequence: STOPPED / SERVO CLOSE"
        )

        if self.is_serial_connected():
            self.send_command("CLOSE")

        if was_running:
            self.record_log(
                "INFO",
                "SEQUENCE STOPPED. Servo CLOSE was requested.",
            )
        else:
            self.record_log(
                "INFO",
                "Servo CLOSE was requested.",
            )

        self.update_control_states()

    def clear_sequence_runtime(self, state="IDLE"):
        """
        シーケンス関連タイマーと待機状態を解除する。
        """

        self.sequence_timer.stop()
        self.response_timeout_timer.stop()

        self.sequence_running = False
        self.sequence_state = state
        self.awaiting_response = None
        self.pending_temperature = None

    # ========================================================
    # シーケンス進行
    # ========================================================

    def send_sequence_command(self, command):
        """
        シーケンス用コマンドを送信し、
        Picoからの返信タイムアウト監視を開始する。
        """

        if not self.sequence_running:
            return

        self.awaiting_response = command

        if not self.send_command(command):
            self.handle_sequence_error(
                f"{command} command could not be sent."
            )
            return

        self.response_timeout_timer.start(
            self.RESPONSE_TIMEOUT_MS
        )

    def advance_sequence(self):
        """
        5秒待機または60秒待機が完了したときに呼ばれる。
        """

        if not self.sequence_running:
            return

        if self.sequence_state == "WAIT_OPEN_DELAY":
            self.request_temperature_for_sequence()
            return

        if self.sequence_state == "WAIT_NEXT_SEQUENCE":
            self.start_one_sequence_cycle()
            return

        self.handle_sequence_error(
            (
                "Unexpected sequence timer event: "
                f"{self.sequence_state}"
            )
        )

    def start_one_sequence_cycle(self):
        """
        1サイクル目または次のサイクルを開始する。
        """

        if not self.sequence_running:
            return

        cycle_number = self.sequence_count + 1

        self.sequence_state = "WAIT_OPEN_ACK"

        self.sequence_status_label.setText(
            f"Sequence {cycle_number}: opening servo..."
        )

        self.record_log(
            "INFO",
            f"Sequence {cycle_number}: servo OPEN.",
        )

        self.send_sequence_command(
            "OPEN"
        )

    def on_status_confirmed(self, line):
        """
        STATUS確認成功後、最初のサイクルを開始する。
        """

        self.finish_response_wait()

        self.record_log(
            "INFO",
            f"Pico STATUS check passed: {line}",
        )

        self.start_one_sequence_cycle()

    def on_open_confirmed(self):
        """
        OPEN応答確認後、5秒待機する。
        """

        self.finish_response_wait()

        cycle_number = self.sequence_count + 1

        self.sequence_state = "WAIT_OPEN_DELAY"

        self.sequence_status_label.setText(
            (
                f"Sequence {cycle_number}: "
                f"waiting {self.OPEN_WAIT_MS / 1000:.1f} s"
            )
        )

        self.sequence_timer.start(
            self.OPEN_WAIT_MS
        )

    def request_temperature_for_sequence(self):
        """
        5秒待機後、PicoへTEMPコマンドを送る。
        """

        cycle_number = self.sequence_count + 1

        self.sequence_state = "WAIT_TEMP"

        self.sequence_status_label.setText(
            f"Sequence {cycle_number}: reading temperature..."
        )

        self.record_log(
            "INFO",
            f"Sequence {cycle_number}: TEMP read requested.",
        )

        self.send_sequence_command(
            "TEMP"
        )

    def on_temperature_received(self, temperature):
        """
        温度値受信後、画像認識値を取得しTempLogへ書き込む。
        """

        self.finish_response_wait()

        self.pending_temperature = temperature

        try:
            # その時点のカメラ画像を複数フレーム認識し、
            # 多数決した値を取得する。
            gauge_value = self.gauge_reader.read_value()
            self.gauge_value_label.setText(
                f"Gauge: {gauge_value}"
            )

        except (RuntimeError, ValueError, OSError) as error:
            self.handle_sequence_error(
                f"Gauge read failed: {error}"
            )
            return

        try:
            # TempLogの列順：
            # timestamp, current, temperature
            #
            # currentへ画像認識値、
            # temperatureへADC温度値を記録する。
            self.temp_log.write_row(
                gauge_value,
                temperature,
            )

        except Exception as error:
            self.handle_sequence_error(
                f"TempLog write failed: {error}"
            )
            return

        cycle_number = self.sequence_count + 1

        self.record_log(
            "DATA",
            (
                f"Sequence {cycle_number}: "
                f"gauge={gauge_value}, "
                f"temperature={temperature}"
            ),
        )

        self.sequence_state = "WAIT_CLOSE_ACK"

        self.sequence_status_label.setText(
            f"Sequence {cycle_number}: closing servo..."
        )

        self.record_log(
            "INFO",
            f"Sequence {cycle_number}: servo CLOSE.",
        )

        self.send_sequence_command(
            "CLOSE"
        )

    def on_close_confirmed(self):
        """
        CLOSE応答確認後、1サイクル完了として60秒待機する。
        """

        self.finish_response_wait()

        self.sequence_count += 1
        self.pending_temperature = None

        self.record_log(
            "INFO",
            f"Sequence {self.sequence_count} completed.",
        )

        self.sequence_state = "WAIT_NEXT_SEQUENCE"

        self.sequence_status_label.setText(
            (
                f"Sequence {self.sequence_count}: completed. "
                f"Next start in "
                f"{self.NEXT_SEQUENCE_WAIT_MS / 1000:.0f} s"
            )
        )

        self.sequence_timer.start(
            self.NEXT_SEQUENCE_WAIT_MS
        )

    def finish_response_wait(self):
        """
        Pico応答待ちを終了する。
        """

        self.response_timeout_timer.stop()
        self.awaiting_response = None

    def on_response_timeout(self):
        """
        STATUS、OPEN、TEMP、CLOSEの返信が来ない場合の処理。
        """

        command = self.awaiting_response
        self.awaiting_response = None

        self.handle_sequence_error(
            (
                f"No response from Pico for {command} "
                f"within {self.RESPONSE_TIMEOUT_MS} ms."
            )
        )

    def handle_sequence_error(self, message):
        """
        シーケンスエラー時の安全停止。
        """

        self.clear_sequence_runtime(
            state="ERROR"
        )

        self.sequence_status_label.setText(
            f"Sequence: ERROR - {message}"
        )

        self.record_log(
            "ERROR",
            f"SEQUENCE ERROR: {message}",
        )

        if self.is_serial_connected():
            # 応答は待たず、安全側へCLOSEする。
            self.send_command("CLOSE")

            self.record_log(
                "INFO",
                "Safety action: servo CLOSE requested.",
            )

        self.update_control_states()

    # ========================================================
    # カメラ・画像認識
    # ========================================================

    # 2026.10.1 追加
    def measure_and_capture(self):
        measurement_id = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        # PicoにADC測定を要求
        self.send_command("TEMP")

        # TEMP送信直後のフレームを保存
        filename = (
            f"captures/"
            f"temperature_{measurement_id}.png"
        )

        saved_path = self.gauge_reader.save_snapshot(
            filename,
            roi_only=True,
        )

        print("画像保存:", saved_path)

        self.open_button.setEnabled(True)

    def select_gauge_roi(self):
        """SET ROIボタンから表示器ROIを設定する。"""

        if self.sequence_running:
            self.record_log(
                "ERROR",
                "ROI cannot be changed while the sequence is running.",
            )
            return

        try:
            roi = self.gauge_reader.select_roi()

        except (RuntimeError, ValueError, OSError) as error:
            self.record_log(
                "ERROR",
                f"ROI setup failed: {error}",
            )
            self.gauge_value_label.setText(
                "Gauge: ROI setup failed"
            )
            self.update_control_states()
            return

        x, y, width, height = roi

        self.gauge_value_label.setText(
            f"Gauge: ROI=({x}, {y}, {width}, {height})"
        )

        self.record_log(
            "INFO",
            (
                "Gauge ROI set: "
                f"x={x}, y={y}, w={width}, h={height}"
            ),
        )

        self.update_control_states()

    def test_read_gauge(self):
        """READ GAUGEボタンから画像認識だけを試す。"""

        if not self.gauge_reader.has_roi:
            self.record_log(
                "ERROR",
                "Gauge ROI is not set.",
            )
            return

        try:
            value = self.gauge_reader.read_value()

        except (RuntimeError, ValueError, OSError) as error:
            self.record_log(
                "ERROR",
                f"Gauge read failed: {error}",
            )
            self.gauge_value_label.setText(
                "Gauge: read failed"
            )
            return

        self.gauge_value_label.setText(
            f"Gauge: {value}"
        )

        self.record_log(
            "DATA",
            f"Gauge test read: {value}",
        )

    # ========================================================
    # シリアル受信
    # ========================================================

    def read_serial(self):
        """
        Picoから届いたデータを読み取る。

        データが途中で分割されて届いても、
        改行が届くまでreceive_bufferへ保存する。
        """

        if not self.is_serial_connected():
            return

        try:
            waiting_bytes = self.serial_port.in_waiting

            if waiting_bytes <= 0:
                return

            received_data = self.serial_port.read(
                waiting_bytes
            )

            self.receive_buffer += received_data

            while b"\n" in self.receive_buffer:

                line_bytes, self.receive_buffer = (
                    self.receive_buffer.split(
                        b"\n",
                        1,
                    )
                )

                line = line_bytes.decode(
                    "utf-8",
                    errors="replace",
                )

                line = line.rstrip("\r").strip()

                if line:
                    self.record_log(
                        "RX",
                        line,
                    )

                    self.handle_serial_line(
                        line
                    )

        except serial.SerialException as error:
            self.record_log(
                "ERROR",
                f"Serial read failed: {error}",
            )

            self.disconnect_serial(
                send_off=False
            )

    def handle_serial_line(self, line):
        """
        シーケンス実行中のPico返信を処理する。

        Pico側の
            received: COMMAND
        はエコーなので、応答判定には使わない。
        """

        if not self.sequence_running:
            return

        if self.is_echo_line(line):
            return

        if self.is_error_line(line):
            self.handle_sequence_error(
                f"Pico returned an error: {line}"
            )
            return

        command = self.awaiting_response

        if command == "STATUS":
            if self.is_status_response(line):
                self.on_status_confirmed(line)
            return

        if command == "OPEN":
            if self.is_command_ack(line, "OPEN"):
                self.on_open_confirmed()
            return

        if command == "TEMP":
            temperature = self.parse_temperature(line)

            if temperature is not None:
                self.on_temperature_received(
                    temperature
                )
            return

        if command == "CLOSE":
            if self.is_command_ack(line, "CLOSE"):
                self.on_close_confirmed()
            return

    @staticmethod
    def is_echo_line(line):

        upper_line = line.strip().upper()

        return (
            upper_line.startswith("RECEIVED:")
            or upper_line.startswith("RECEIVED ")
        )

    @staticmethod
    def is_error_line(line):

        upper_line = line.upper()

        error_words = (
            "ERROR",
            "FAILED",
            "FAIL",
            "INVALID",
            "UNKNOWN COMMAND",
            "EXCEPTION",
        )

        return any(
            word in upper_line
            for word in error_words
        )

    @staticmethod
    def is_status_response(line):
        """
        Pico側のSTATUS形式にある程度幅を持たせる。

        例：
            OK STATUS
            STATUS OFF
            SERVO: CLOSED
            STATE=OFF
        """

        upper_line = line.strip().upper()

        if upper_line in {
            "ON",
            "OFF",
            "OPEN",
            "CLOSE",
            "CLOSED",
        }:
            return True

        return any(
            token in upper_line
            for token in (
                "STATUS",
                "STATE",
                "SERVO",
                "OK",
            )
        )

    @staticmethod
    def is_command_ack(line, command):

        upper_line = line.strip().upper()
        command = command.upper()

        if upper_line == command:
            return True

        if command not in upper_line:
            return False

        return any(
            token in upper_line
            for token in (
                "OK",
                "DONE",
                "COMPLETE",
                "OPENED",
                "CLOSED",
            )
        )

    @staticmethod
    def parse_temperature(line):
        """
        TEMP返信行から数値を抽出する。

        例：
            TEMP 523.4
            TEMP: 523.4
            ADC=523.4
            OK TEMP 523.4

        複数の数値がある場合は最後の値を使用する。
        Pico側の返信形式が決まったら、
        この関数をその形式へ絞るとより安全。
        """

        number_pattern = (
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?"
        )

        matches = re.findall(
            number_pattern,
            line,
        )

        if not matches:
            return None

        try:
            return float(matches[-1])

        except ValueError:
            return None

    # ========================================================
    # ログ
    # ========================================================

    @staticmethod
    def get_log_path(log_object):
        """
        CommLog / TempLogの保存先属性名の違いを吸収する。
        """

        return getattr(
            log_object,
            "file_path",
            getattr(
                log_object,
                "csv_path",
                "unknown",
            ),
        )

    def record_log(self, source, message):
        """
        CommLogへログを書き込む。

        csv_writtenシグナルを通して、
        GUIにも同じ内容が表示される。
        """

        try:
            self.csv_writer.write_row(
                source,
                message,
            )

        except Exception as error:
            timestamp = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )[:-3]

            self.log_text.append(
                f"{timestamp}  [ERROR] "
                f"CSV write failed: {error}"
            )

    def on_csv_written(self, row):
        """
        CommLogが書き込んだ行をGUIへ表示する。

        例：
        2026-07-15 10:00:00.000  [TX] OPEN
        """

        timestamp, source, message = row

        self.log_text.append(
            f"{timestamp}  [{source}] {message}"
        )

        scroll_bar = self.log_text.verticalScrollBar()
        scroll_bar.setValue(
            scroll_bar.maximum()
        )

    # ========================================================
    # ボタン有効・無効
    # ========================================================

    def update_control_states(self):
        """
        未接続時およびシーケンス中の誤操作を防ぐ。

        シーケンス中はSTOP / CLOSEだけ操作可能。
        """

        connected = self.is_serial_connected()
        running = self.sequence_running

        self.sequence_start_button.setEnabled(
            connected and not running
        )

        self.sequence_stop_button.setEnabled(
            connected
        )

        manual_enabled = (
            connected and not running
        )

        for button in self.manual_buttons:
            button.setEnabled(
                manual_enabled
            )

        self.pulse_edit.setEnabled(
            manual_enabled
        )

        # ROI変更と単独認識はシーケンス停止中だけ許可する。
        self.set_roi_button.setEnabled(
            not running
        )
        self.read_gauge_button.setEnabled(
            (not running) and self.gauge_reader.has_roi
        )

        # シーケンス中の切断は可能。
        self.connect_button.setEnabled(True)

    # ========================================================
    # ウィンドウ終了
    # ========================================================

    def closeEvent(self, event: QCloseEvent):
        """
        ウィンドウを閉じるときの処理。

        1. シーケンス停止
        2. PicoへOFFを送信
        3. シリアルポートを閉じる
        4. CSVファイルを閉じる
        """

        self.clear_sequence_runtime(
            state="IDLE"
        )

        if self.is_serial_connected():
            self.disconnect_serial(
                send_off=True
            )

        self.gauge_reader.close()

        self.record_log(
            "INFO",
            "Program closed.",
        )

        self.close_log_object(
            self.temp_log
        )

        self.close_log_object(
            self.csv_writer
        )

        event.accept()

    @staticmethod
    def close_log_object(log_object):
        """
        close()を持つログクラスだけ閉じる。
        """

        close_method = getattr(
            log_object,
            "close",
            None,
        )

        if callable(close_method):
            close_method()


# ============================================================
# メイン処理
# ============================================================

def main():

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":

    main()
