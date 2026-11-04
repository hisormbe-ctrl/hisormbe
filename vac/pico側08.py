import math
import time
import machine

CHANNEL = 3
DIVIDER_RATIO = 3.875  # 2.89e-06 Pa (4.289V) に合わせた係数
I2C_SDA_PIN = 2
I2C_SCL_PIN = 3

ADS_ADDR = 0x48
i2c = machine.I2C(
    1,
    sda=machine.Pin(I2C_SDA_PIN, machine.Pin.IN, machine.Pin.PULL_UP),
    scl=machine.Pin(I2C_SCL_PIN, machine.Pin.IN, machine.Pin.PULL_UP),
    freq=50000,
)


def read_ads1015_averaging(channel, samples=20):
  total_v = 0.0
  for _ in range(samples):
    # 0xC3にすることで、測定レンジを±4.096V（1目盛り0.002V）に高精細化
    config_msb = 0xC3 | (channel << 4)
    config_lsb = 0x83
    i2c.writeto(ADS_ADDR, bytearray([1, config_msb, config_lsb]))
    time.sleep_ms(10)
    i2c.writeto(ADS_ADDR, bytearray([0]))
    data = i2c.readfrom(ADS_ADDR, 2)
    val = (data[0] << 8) | data[1]
    if val > 32767:
      val -= 65536
    total_v += (val >> 4) * 0.002
  return total_v / samples


# ==========================================
# 🚀 起動時の時刻あわせ
# ==========================================
print("----------------------------------------")
print("【時刻合わせ】今の時間を入力してください")
print("2026,10,22,16,30,00 と入力してエンターを押す")
print("----------------------------------------")

user_input = input("時刻を入力 > ").strip()

if user_input:
  try:
    parts = [int(p) for p in user_input.split(",")]
    if len(parts) == 6:
      machine.RTC().datetime(
          (parts[0], parts[1], parts[2], 0, parts[3], parts[4], parts[5], 0)
      )
      print("✅ 時刻をセットしました！計測を開始します...\n")
  except Exception:
    pass
else:
  print("➡️ そのまま計測を開始します...\n")

time.sleep(1)

# ==========================================
# 📊 メイン計測ループ
# ==========================================
while True:
  try:
    # 20回平均で滑らかに読み取る
    v_measured = read_ads1015_averaging(CHANNEL, samples=20)
    v_out = v_measured * DIVIDER_RATIO

    exponent = math.floor(v_out)
    mantissa = (v_out - exponent) * 10.0
    pressure_pa = mantissa * (10 ** (exponent - 10))

    t = time.localtime()
    time_str = (
        f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
    )

    print(f"VAC,{time_str},{v_out:.3f},{pressure_pa:.2e}")
  except Exception:
    pass

  time.sleep(0.8)
