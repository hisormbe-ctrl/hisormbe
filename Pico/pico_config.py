#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Jun 2026.11.04

# standard sampling rate for Pico
I2C_FREQUENCY = 400_000

# for TempADC, I2C0
ADS_I2C_ID = 0
ADS_I2C_SDA_PIN = 0
ADS_I2C_SCL_PIN = 1
ADS1015_ADDRESS = 0x48

# for TempADC: A0, PGA ±4.096 V, single-shot, 1600 SPS
# (main.py が参照しているが未定義だったため追加)
TEMPERATURE_CONFIG = 0xC383

# from themometer setting
TEMP_V_MIN = 0.0
TEMP_V_MAX = 1.0

# ex. 0.0 V = 0 ℃, 1.0 V = 100 ℃
TEMP_MIN_C = -140.0
TEMP_MAX_C = 1400.0

# take average
TEMP_ADC_SAMPLES = 32
TEMP_ADC_DELAY_MS = 2

# for VacADC, I2C0
# A3, PGA ±6.144 V (0.003 V/count), single-shot, 1600 SPS
VACUUM_CONFIG = 0xF183 #A3
VAC_V_MIN = 0.0
VAC_V_MAX = 10.9
# 真空計出力がこの電圧以上ならフィラメントOFF
VACUUM_FILAMENT_OFF_V = 11.0

# take average
VACUUM_ADC_SAMPLES = 32
VACUUM_ADC_DELAY_MS = 2

# for PCA9685, I2C1
PCA_I2C_ID = 1
PCA_I2C_SDA_PIN = 18
PCA_I2C_SCL_PIN = 19
PCA9685_ADDRESS = 0x40

# for servo
PWM_FREQUENCY = 50
SERVO_CHANNEL = 0

# PCA9685内蔵発振器の実周波数。公称25 MHzだが個体差が大きい(実測で
# 25.5~27 MHz程度の例が多い)。オシロでパルス幅を測り、
#   実周波数 = 25_000_000 * (実測パルス幅 / 指令パルス幅)
# で補正する。
PCA9685_OSC_HZ = 25_000_000

# 機械的な端(エンドストップ)に当てないこと。
# 端に当たるとサーボが押し続けてジッタ・発熱・大電流・電圧降下が起きる。
# PULSE コマンドで少しずつ動かし、端から 50~100 us 手前を採用する。
CLOSE_PULSE_US = 600
OPEN_PULSE_US = 2400

# for safety
MIN_PULSE_US = 500
MAX_PULSE_US = 2500

# 移動を細かいステップに分けて加減速する(突入電流と衝撃の低減)
SERVO_STEP_US = 25          # 1ステップのパルス変化量
SERVO_STEP_MS = 10          # ステップ間隔  -> 1800 us の移動で約0.72 s
SERVO_SETTLE_MS = 250       # 到達後の静定待ち

# True: 移動完了後にPWMを止める(保持トルクなし。シャッターが自重等で
#       動かない構造ならジッタ/発熱が完全に消える)
SERVO_RELEASE_AFTER_MOVE = False

# メインループの待ち時間。500 ms だとコマンド応答が最大0.5 s遅れる
MAIN_LOOP_SLEEP_MS = 5

# ADS1015 registers (temperature.py / vacuum.py が参照)
CONVERSION_REGISTER = 0x00
CONFIG_REGISTER = 0x01



