import time
import machine

# ==========================================
# 設定パラメータ（1次関数キャリブレーション）
# ==========================================
CHANNEL = 3

# 1次関数の係数: y = a * x + b
# a (傾き): 抵抗分圧の本来の倍率（理論値4.0に近い）
# b (切片): 真空計とPicoのGND電位差（オフセット電圧）
CALIB_A = 4.778
CALIB_B = 0.272

I2C_SDA_PIN = 0
I2C_SCL_PIN = 1
ADS_ADDR = 0x48

i2c = machine.I2C(
    0,
    sda=machine.Pin(I2C_SDA_PIN, machine.Pin.IN, machine.Pin.PULL_UP),
    scl=machine.Pin(I2C_SCL_PIN, machine.Pin.IN, machine.Pin.PULL_UP),
    freq=50000,
)

def read_ads1015(channel):
    config_msb = 0xC1 | (channel << 4)
    config_lsb = 0x83
    i2c.writeto(ADS_ADDR, bytearray([1, config_msb, config_lsb]))
    time.sleep_ms(15)
    i2c.writeto(ADS_ADDR, bytearray([0]))
    data = i2c.readfrom(ADS_ADDR, 2)
    val = (data[0] << 8) | data[1]
    if val > 32767:
        val -= 65536
    return (val >> 4) * 0.003

# ==========================================
# 🚀 起動時の時刻あわせ
# ==========================================
print("----------------------------------------")
print("【時刻合わせ】今の時間を入力してください")
user_input = input("例: 2026,11,07,15,30,00 > ").strip()

if user_input:
    try:
        parts = [int(p) for p in user_input.split(",")]
        if len(parts) == 6:
            machine.RTC().datetime(
                (parts[0], parts[1], parts[2], 0, parts[3], parts[4], parts[5], 0)
            )
            print("✅ 時刻をセットしました！\n")
    except Exception:
        print("⚠️ デフォルト時刻で開始します。\n")
else:
    print("➡️ デフォルト時刻で開始します。\n")

time.sleep(1)

# ==========================================
# 📊 メイン計測ループ
# ==========================================
while True:
    try:
        # 生のADC電圧を読み取る
        v_raw = read_ads1015(CHANNEL)
        
        # ★ 1次関数による全レンジ自動補正 (y = ax + b)
        originalVoltage = (v_raw * CALIB_A) + CALIB_B

        t = time.localtime()
        time_str = f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"

        if originalVoltage >= 10.5:
            # メンテナンス時の再調整用に、Raw電圧も出力に含めています
            print(f"VAC,{time_str},Raw:{v_raw:.3f}V,True:{originalVoltage:.3f}V,Filament_OFF")
        else:
            exponentIndex = int(originalVoltage)
            mantissa = (originalVoltage - exponentIndex) * 10.0
            pressure = mantissa * (10.0 ** (exponentIndex - 11))

            # ログ出力（Raw電圧も記録することで、今後のズレ検証が容易になります）
            print(f"VAC,{time_str},Raw:{v_raw:.3f}V,True:{originalVoltage:.3f}V,{pressure:.2e}")

    except Exception as ex:
        print("Error:", ex)

    time.sleep(1)
