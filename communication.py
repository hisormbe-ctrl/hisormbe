#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Jun 2026.10.22

import serial
from serial.tools import list_ports
from PySide6.QtCore import QTimer
import autombe_config as cfg

def initialize_serial(self):
    self.serial_port = None
    self.serial_timer = QTimer(self)
    self.serial_timer. setInterval(cfg.SERIAL_POLL_INTERVAL_MS)
    self.serial_timer.timeout.connect(
        lambda: read_serial(self)
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

        self.logs.record_log(
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

    if is_serial_connected(self):
        disconnect_serial(self, send_off=True)
    else:
        connect_serial(self)

def is_serial_connected(self):

    return (
        self.serial_port is not None
        and self.serial_port.is_open
    )

def connect_serial(self):

    port_name = self.port_combo.currentData()

    if port_name is None:
        self.logs.record_log(
            "ERROR",
            "COM port is not selected.",
        )
        return

    try:
        self.serial_port = serial.Serial(
            port=port_name,
            baudrate=cfg.SERIAL_BAUDRATE,
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
            f"@ {cfg.SERIAL_BAUDRATE} baud"
        )

        self.logs.record_log(
            "INFO",
            f"Serial connected: {port_name}",
        )

        # Picoの起動後に現在状態を表示する
        QTimer.singleShot(
            1000,
            lambda: request_status(self),
        )

    except serial.SerialException as error:
        self.serial_port = None

        self.logs.record_log(
            "ERROR",
            f"Serial connection failed: {error}",
        )


def disconnect_serial(self, send_off=True):

    if self.serial_port is None:
        return

    try:
        if (
            send_off
            and self.serial_port.is_open
        ):
            # 切断時は安全のためOFFを送信
            command_data = b"OFF\n"

            self.serial_port.write(command_data)
            self.serial_port.flush()

            self.logs.record_log(
                "TX",
                "OFF (before disconnect)",
            )

    except serial.SerialException as error:
        self.logs.record_log(
            "ERROR",
            f"OFF command failed: {error}",
        )

    self.serial_timer.stop()

    try:
        if self.serial_port.is_open:
            self.serial_port.close()

    except serial.SerialException as error:
        self.logs.record_log(
            "ERROR",
            f"Serial close failed: {error}",
        )

    self.serial_port = None
    self.receive_buffer = b""

    self.connect_button.setText("Connect")
    self.connection_status_label.setText(
        "Disconnected"
    )

    self.logs.record_log(
        "INFO",
        "Serial disconnected.",
    )

def request_status(self):

    if is_serial_connected(self):
        send_command(self, "STATUS")


# ========================================================
# シリアル受信
# ========================================================

def read_serial(self):
    """
    Picoから届いたデータを読み取る。

    データが途中で分割されて届いても、
    改行が届くまでreceive_bufferへ保存する。
    """

    if not is_serial_connected(self):
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
                self.logs.record_log(
                    "RX",
                    line,
                )

    except serial.SerialException as error:
        self.logs.record_log(
            "ERROR",
            f"Serial read failed: {error}",
        )

        self.disconnect_serial(
            send_off=False
        )

# ========================================================
# コマンド送信
# ========================================================

def send_command(self, command):
    """
    Picoへ1行のコマンドを送信する。

    成功時はTrue、失敗時はFalseを返す。
    """

    if not is_serial_connected(self):
        self.logs.record_log(
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

        self.logs.record_log(
            "TX",
            command,
        )

        return True

    except (
        serial.SerialException,
        serial.SerialTimeoutException,
    ) as error:

        self.logs.record_log(
            "ERROR",
            f"Serial write failed: {error}",
        )

        self.disconnect_serial(
            send_off=False
        )

        return False

