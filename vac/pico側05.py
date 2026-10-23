import machine
import time

CHANNEL = 3
DIVIDER_RATIO = 4.0  
I2C_SDA_PIN = 2
I2C_SCL_PIN = 3

ADS_ADDR = 0x48
i2c = machine.I2C(1, sda=machine.Pin(I2C_SDA_PIN, machine.Pin.IN, machine.Pin.PULL_UP),
                     scl=machine.Pin(I2C_SCL_PIN, machine.Pin.IN, machine.Pin.PULL_UP), freq=50000)

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
# 🚀 起動時の時刻あわせ（Tera Term用）
# ==========================================
print("----------------------------------------")
print("【時刻合わせ】今の時間を入力してください")
print("例: 2026年10月22日 16時30分00秒 なら:")
print("2026,10,22,16,30,00 と入力してエンターを押す")
print("(※そのままエンターを押すと 2026-01-01 から始まります)")
print("----------------------------------------")

user_input = input("時刻を入力 > ").strip()

if user_input:
    try:
        parts = [int(p) for p in user_input.split(",")]
        if len(parts) == 6:
            # 入力された時間でPicoの時計をセット
            # (年, 月, 日, 曜日(0), 時, 分, 秒, 0)
            machine.RTC().datetime((parts[0], parts[1], parts[2], 0, parts[3], parts[4], parts[5], 0))
            print("✅ 時刻をセットしました！計測を開始します...\n")
        else:
            print("⚠️ 形式が違うため、デフォルト時刻で開始します。\n")
    except Exception:
        print("⚠️ エラーのため、デフォルト時刻で開始します。\n")
else:
    print("➡️ そのまま計測を開始します...\n")

time.sleep(1)

# ==========================================
# 📊 メイン計測ループ
# ==========================================
while True:
    try:
        v_measured = read_ads1015(CHANNEL)
        v_out = v_measured * DIVIDER_RATIO
        pressure_pa = 10 ** (v_out - 10.0)
        
        # Picoの内蔵時計から現在時刻を取得
        t = time.localtime()
        time_str = f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
        
        print(f"VAC,{time_str},{v_out:.3f},{pressure_pa:.2e}")
    except Exception:
        pass
        
    time.sleep(1)