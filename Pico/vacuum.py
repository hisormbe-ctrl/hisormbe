#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Jun 2026.11.09
#
# pico_13.py の真空計読み取りを temperature.py と同じ形式へ移植。
# ADS1015 の A3 (シングルエンド) に、抵抗分圧した真空計出力を入力する。

import time
import pico_config as cfg

# ADS1015 PGA設定 (config bit 11:9) -> フルスケール電圧 [V]
_PGA_FULL_SCALE = {
    0: 6.144,
    1: 4.096,
    2: 2.048,
    3: 1.024,
    4: 0.512,
    5: 0.256,
    6: 0.256,
    7: 0.256,
}


class VacuumADC:

    def __init__(
        self,
        i2c,
        address,
        config,
        calib_a,
        calib_b,
        filament_off_v,
        samples,
        delay_ms,
    ):
        self.i2c = i2c
        self.address = address
        self.config = config

        # 1次関数キャリブレーション: gauge_v = a * adc_v + b
        # a (傾き): 抵抗分圧の倍率 (理論値4.0付近)
        # b (切片): 真空計とPicoのGND電位差 (オフセット電圧)
        self.calib_a = calib_a
        self.calib_b = calib_b

        # この電圧以上ならフィラメントOFFとみなす
        self.filament_off_v = filament_off_v

        self.samples = samples
        self.delay_ms = delay_ms

        # PGAはconfigから決める。
        # config=0xF183 (A3) では PGA が ±6.144 V
        # ADS1015は符号付き12 bit
        #
        # 6.144 V / 2048 count = 0.003 V/count
        pga = (self.config >> 9) & 0x07
        self.full_scale_voltage = _PGA_FULL_SCALE[pga]
        self.volts_per_count = (
            self.full_scale_voltage / 2048
        )

    def start_conversion(self):
        """
        ADS1015へ変換開始コマンドを送る。
        """

        config_data = bytes([
            (self.config >> 8) & 0xFF,
            self.config & 0xFF,
        ])

        self.i2c.writeto_mem(
            self.address,
            cfg.CONFIG_REGISTER,
            config_data,
        )

    def read_raw_once(self):
        """
        ADS1015の変換結果を符号付き12 bit値として返す。
        """

        self.start_conversion()

        # 0xF183では1600 SPS。
        # 変換完了まで余裕をみて2 ms待つ。
        time.sleep_ms(2)

        data = self.i2c.readfrom_mem(
            self.address,
            cfg.CONVERSION_REGISTER,
            2,
        )

        raw16 = (
            (data[0] << 8)
            | data[1]
        )

        # ADS1015の12 bitデータは上位詰め
        raw12 = raw16 >> 4

        # 符号付き12 bitへ変換
        if raw12 & 0x0800:
            raw12 -= 0x1000

        return raw12

    def read_raw_average(self):
        total = 0

        for _ in range(self.samples):
            total += self.read_raw_once()

            if self.delay_ms > 0:
                time.sleep_ms(self.delay_ms)

        return total / self.samples

    def raw_to_voltage(self, raw):
        """
        ADC入力端子 (A3) の電圧 [V]
        """
        return raw * self.volts_per_count

    def voltage_to_gauge_voltage(self, voltage):
        """
        分圧前の真空計出力電圧 [V] (1次関数補正)
        """
        return (voltage * self.calib_a) + self.calib_b

    def is_filament_off(self, gauge_voltage):
        return gauge_voltage >= self.filament_off_v

    def gauge_voltage_to_pressure(self, gauge_voltage):
        """
        真空計出力電圧を圧力へ変換する。
        整数部 = 指数, 小数部 x 10 = 仮数
            pressure = mantissa * 10 ** (exponent - 11)

        フィラメントOFFのときは None を返す。
        """

        if self.is_filament_off(gauge_voltage):
            return None

        exponent = int(gauge_voltage)
        mantissa = (gauge_voltage - exponent) * 10.0
        pressure = mantissa * (10.0 ** (exponent - 11))

        return pressure

    def read_pressure(self):
        _, _, _, pressure = self.read_all()
        return pressure

    def read_all(self):
        raw = self.read_raw_average()
        voltage = self.raw_to_voltage(raw)
        gauge_voltage = self.voltage_to_gauge_voltage(
            voltage
        )
        pressure = self.gauge_voltage_to_pressure(
            gauge_voltage
        )

        return raw, voltage, gauge_voltage, pressure
