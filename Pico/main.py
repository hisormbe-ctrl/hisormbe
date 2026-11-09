#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# コマンド:
#   OPEN
#   CLOSE
#   PULSE 1500
#   STATUS
#   PING

import sys
import time
import select
from machine import Pin, I2C

import pico_config as cfg
from servo import PCA9685
from temperature import TemperatureADC
# for vacuum
# from vacuum import VacuumADC

# ============================================================
# 設定
# ============================================================

# ============================================================
# I2C初期化
# ============================================================

# ADS1015用 I2C0
# temp vac common
i2c_ads = I2C(
    cfg.ADS_I2C_ID,
    sda=Pin(cfg.ADS_I2C_SDA_PIN),
    scl=Pin(cfg.ADS_I2C_SCL_PIN),
    freq=cfg.I2C_FREQUENCY,
)

# PCA9685用 I2C1
i2c_pca = I2C(
    cfg.PCA_I2C_ID,
    sda=Pin(cfg.PCA_I2C_SDA_PIN),
    scl=Pin(cfg.PCA_I2C_SCL_PIN),
    freq=cfg.I2C_FREQUENCY,
)

ads_devices = i2c_ads.scan()
pca_devices = i2c_pca.scan()

print(
    "INFO I2C0 ADS1015 scan:",
    [hex(address) for address in ads_devices],
)

print(
    "INFO I2C1 Servo scan:",
    [hex(address) for address in pca_devices],
)

if cfg.ADS1015_ADDRESS not in ads_devices:
    raise RuntimeError(
        "ADS1015 not found on I2C0: {}".format(
            [hex(address) for address in ads_devices]
        )
    )

if cfg.PCA9685_ADDRESS not in pca_devices:
    raise RuntimeError(
        "PCA9685 not found on I2C1: {}".format(
            [hex(address) for address in pca_devices]
        )
    )

# PCA9685はI2C1へ接続
pca = PCA9685(
    i2c_pca,
    address=cfg.PCA9685_ADDRESS,
    osc_hz=cfg.PCA9685_OSC_HZ,
)

def set_pca_frequency(frequency):
    """
    PCA9685ライブラリごとのメソッド名の違いを吸収する。
    """

    if hasattr(pca, "freq"):
        pca.freq(frequency)
        return

    if hasattr(pca, "set_pwm_freq"):
        pca.set_pwm_freq(frequency)
        return

    raise RuntimeError(
        "PCA9685 frequency method not found: "
        "freq() or set_pwm_freq() is required"
    )

set_pca_frequency(cfg.PWM_FREQUENCY)

# ============================================================
# 温度ADC初期化
# ============================================================

temperature_sensor = TemperatureADC(
    i2c=i2c_ads,
    address=cfg.ADS1015_ADDRESS,
    config=cfg.TEMPERATURE_CONFIG,
    v_min=cfg.TEMP_V_MIN,
    v_max=cfg.TEMP_V_MAX,
    temp_min=cfg.TEMP_MIN_C,
    temp_max=cfg.TEMP_MAX_C,
    samples=cfg.TEMP_ADC_SAMPLES,
    delay_ms=cfg.TEMP_ADC_DELAY_MS,
)


# ============================================================
# サーボ制御
# ============================================================

def pulse_us_to_count(pulse_us):
    """
    マイクロ秒単位のパルス幅を、
    PCA9685の12 bitカウント値へ変換する。
    """

    return pca.pulse_us_to_count(pulse_us)


def set_servo_pulse(pulse_us):
    """
    指定したパルス幅でサーボを動かす。
    """

    pulse_us = int(pulse_us)

    if not cfg.MIN_PULSE_US <= pulse_us <= cfg.MAX_PULSE_US:
        raise ValueError(
            "Pulse must be between "
            "{} and {} us".format(
                cfg.MIN_PULSE_US,
                cfg.MAX_PULSE_US,
            )
        )

    pwm_count = pulse_us_to_count(pulse_us)

    # 一般的なMicroPython用PCA9685ライブラリ
    if hasattr(pca, "pwm"):
        pca.pwm(
            cfg.SERVO_CHANNEL,
            0,
            pwm_count,
        )

    # ライブラリに set_pwm() がある場合
    elif hasattr(pca, "set_pwm"):
        pca.set_pwm(
            cfg.SERVO_CHANNEL,
            0,
            pwm_count,
        )

    # duty()方式の場合
    elif hasattr(pca, "duty"):
        pca.duty(
            cfg.SERVO_CHANNEL,
            pwm_count,
        )

    else:
        raise RuntimeError(
            "PCA9685 PWM method not found: "
            "pwm(), set_pwm(), or duty() is required"
        )

    return pulse_us


def release_servo():
    """
    PCA9685からのPWM信号を停止する。

    サーボの保持力もなくなるため、
    通常のOFF動作では使用しない。
    """

    if hasattr(pca, "pwm"):
        pca.pwm(cfg.SERVO_CHANNEL, 0, 0)

    elif hasattr(pca, "set_pwm"):
        pca.set_pwm(cfg.SERVO_CHANNEL, 0, 0)

    elif hasattr(pca, "duty"):
        pca.duty(cfg.SERVO_CHANNEL, 0)


# ============================================================
# サーボ状態管理
# ============================================================

servo_position = "UNKNOWN"
current_pulse_us = None

def move_to(target_us):
    """
    現在位置から target_us までステップ状に移動し、静定まで待つ。
    現在位置が不明(起動直後/RELEASE後)の場合は直接移動する。
    """
    global current_pulse_us

    target_us = int(target_us)

    if not cfg.MIN_PULSE_US <= target_us <= cfg.MAX_PULSE_US:
        raise ValueError(
            "Pulse must be between {} and {} us".format(
                cfg.MIN_PULSE_US, cfg.MAX_PULSE_US
            )
        )

    start_us = current_pulse_us

    if start_us is not None and start_us != target_us:
        step = cfg.SERVO_STEP_US if target_us > start_us else -cfg.SERVO_STEP_US
        pulse = start_us + step

        while (step > 0 and pulse < target_us) or (step < 0 and pulse > target_us):
            set_servo_pulse(pulse)
            current_pulse_us = pulse
            time.sleep_ms(cfg.SERVO_STEP_MS)
            pulse += step

    current_pulse_us = set_servo_pulse(target_us)
    time.sleep_ms(cfg.SERVO_SETTLE_MS)

    if cfg.SERVO_RELEASE_AFTER_MOVE:
        release_servo()
        # 位置は保持していると見なす(次回のステップ移動の起点に使う)

    return current_pulse_us


def move_open():
    global servo_position

    move_to(cfg.OPEN_PULSE_US)
    servo_position = "OPEN"

    print("EVENT SERVO OPEN {}".format(current_pulse_us))


def move_close():
    global servo_position

    move_to(cfg.CLOSE_PULSE_US)
    servo_position = "CLOSE"

    print("EVENT SERVO CLOSE {}".format(current_pulse_us))


# ============================================================
# シリアルコマンド処理
# ============================================================

def show_status():
    print(
        "STATUS position={} pulse_us={}".format(
            servo_position,
            current_pulse_us,
        )
    )


def read_temperature_once():
    raw, voltage, temperature_c = temperature_sensor.read_all()

    print(
        "DATA TEMP raw={:.1f} voltage={:.4f} temp_c={:.2f}".format(
            raw,
            voltage,
            temperature_c,
        )
    )


def process_command(command):
    """
    PCから受け取った1行のコマンドを処理する。
    """

    global servo_position
    global current_pulse_us

    command = command.strip()

    if not command:
        return

    print("RECEIVED {}".format(command))

    parts = command.split()
    operation = parts[0].upper()

    try:
        if operation == "OPEN":
            move_open()
            print("OK OPEN")

        elif operation == "CLOSE" or operation == "OFF":
            move_close()
            print("OK CLOSE")

        elif operation == "PULSE":
            if len(parts) != 2:
                raise ValueError(
                    "Usage: PULSE pulse_us"
                )

            pulse_us = int(parts[1])
            move_to(pulse_us)
            servo_position = "CUSTOM"

            print(
                "OK PULSE {}".format(
                    current_pulse_us
                )
            )

        elif operation == "STATUS":
            show_status()

        elif operation == "PING":
            print("OK PONG")


        elif operation == "READ" or operation == "TEMP":
            read_temperature_once()


        elif operation == "RELEASE":
            release_servo()
            servo_position = "RELEASED"
            current_pulse_us = None

            print("OK RELEASE")

        else:
            print(
                "ERROR UNKNOWN_COMMAND {}".format(
                    command
                )
            )

    except Exception as error:
        print(
            "ERROR {}: {}".format(
                type(error).__name__,
                error,
            )
        )


# ============================================================
# USBシリアル入力
# ============================================================

serial_poll = select.poll()
serial_poll.register(sys.stdin, select.POLLIN)


def read_serial_command():
    """
    USBシリアルから1行をノンブロッキングで取得する。
    データがない場合はNoneを返す。
    """

    events = serial_poll.poll(0)

    if not events:
        return None

    line = sys.stdin.readline()

    if line is None:
        return None

    return line


# ============================================================
# メイン処理
# ============================================================

def main():
    print("READY PICO SERVO CONTROLLER")

    while True:
        command = read_serial_command()

        if command is not None:
            process_command(command)

        time.sleep_ms(cfg.MAIN_LOOP_SLEEP_MS)

try:
    main()

except KeyboardInterrupt:
    print("STOPPED KEYBOARD_INTERRUPT")

except Exception as error:
    # 異常終了時にも閉位置へ戻す
    try:
        move_close()
    except Exception:
        pass

    print(
        "FATAL {}: {}".format(
            type(error).__name__,
            error,
        )
    )

    raise
