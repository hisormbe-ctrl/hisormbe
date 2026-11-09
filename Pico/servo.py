from machine import I2C
import time
import math

class PCA9685:
    def __init__(self, i2c, address, osc_hz=25_000_000):
        self.i2c = i2c
        self.address = address
        self.osc_hz = osc_hz
        self.prescale = None
        self.reset()

    def _write(self, reg, value):
        self.i2c.writeto_mem(self.address, reg, bytes([value]))

    def _read(self, reg):
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]

    def reset(self):
        self._write(0x00, 0x00)

    def freq(self, freq=None):
        if freq is None:
            return None

        prescaleval = float(self.osc_hz)
        prescaleval /= 4096.0
        prescaleval /= float(freq)
        prescaleval -= 1.0
        prescale = int(math.floor(prescaleval + 0.5))
        self.prescale = prescale

        oldmode = self._read(0x00)
        newmode = (oldmode & 0x7F) | 0x10
        self._write(0x00, newmode)
        self._write(0xFE, prescale)
        self._write(0x00, oldmode)
        time.sleep_us(500)   # 発振器安定待ち (データシート上 500 us)
        self._write(0x00, oldmode | 0xA1)

    def pulse_us_to_count(self, pulse_us):
        """実際のprescaleと発振器周波数から正確にカウントへ変換する。"""
        count = int(
            pulse_us * self.osc_hz
            / ((self.prescale + 1) * 1_000_000)
            + 0.5
        )
        return max(0, min(4095, count))

    def pwm(self, index, on=None, off=None):
        if on is None or off is None:
            data = self.i2c.readfrom_mem(self.address, 0x06 + 4 * index, 4)
            return data[0] | (data[1] << 8), data[2] | (data[3] << 8)

        data = bytes([
            on & 0xFF,
            on >> 8,
            off & 0xFF,
            off >> 8
        ])
        self.i2c.writeto_mem(self.address, 0x06 + 4 * index, data)

    def duty(self, index, value):
        if value <= 0:
            self.pwm(index, 0, 4096)
        elif value >= 4095:
            self.pwm(index, 4096, 0)
        else:
            self.pwm(index, 0, value)
