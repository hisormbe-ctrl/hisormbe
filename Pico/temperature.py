#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Jun 2026.11.04
#

import time
import pico_config as cfg

class TemperatureADC:

    def __init__(
        self,
        i2c,
        address,
        config,
        v_min,
        v_max,
        temp_min,
        temp_max,
        samples,
        delay_ms,
    ):
        self.i2c = i2c
        self.address = address
        self.config = config

        self.v_min = v_min
        self.v_max = v_max
        self.temp_min = temp_min
        self.temp_max = temp_max

        self.samples = samples
        self.delay_ms = delay_ms

        # config=0xC383ではPGAが±4.096 V
        # ADS1015は符号付き12 bit
        #
        # 4.096 V / 2048 count = 0.002 V/count
        self.full_scale_voltage = 4.096
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

        # 0xC383では1600 SPS。
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
        return raw * self.volts_per_count

    def voltage_to_temperature(self, voltage):
        temperature = self.temp_min + (
            (voltage - self.v_min)
            * (self.temp_max - self.temp_min)
            / (self.v_max - self.v_min)
        )

        return temperature

    def read_temperature(self):
        _, _, temperature = self.read_all()
        return temperature

    def read_all(self):
        raw = self.read_raw_average()
        voltage = self.raw_to_voltage(raw)
        temperature = self.voltage_to_temperature(
            voltage
        )

        return raw, voltage, temperature
