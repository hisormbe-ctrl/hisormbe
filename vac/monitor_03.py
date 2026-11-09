import serial
import csv
from datetime import datetime
import time
import os
import matplotlib.ticker as ticker
import collections
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ====== 設定項目 ======
PORT = "COM3"
BAUD_RATE = 115200
MAX_POINTS = 60
# ======================

# 保存用のフォルダを正しい絶対パスに修正
save_dir = r"C:\Users\HiSOR_MBE\メインの真空計log"
os.makedirs(save_dir, exist_ok=True)

times = collections.deque(maxlen=MAX_POINTS)
pressures = collections.deque(maxlen=MAX_POINTS)

csv_filename = os.path.join(save_dir, f"vacuum_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
with open(csv_filename, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Timestamp", "Voltage_V", "Pressure_Pa"])

try:
    ser = serial.Serial(PORT, BAUD_RATE, timeout=0.1)
    ser.dtr = True
    ser.rts = True
    time.sleep(0.5)
    
    ser.write(b"\r\n")
    
    print(f"✅ {PORT} に接続しました。データ受信を開始します...")
except Exception as e:
    print(f"❌ 接続エラー: {e}")
    print("※Tera TermやThonnyが開いている場合は閉じてください。")
    exit()

fig, ax = plt.subplots(figsize=(10, 5))
line, = ax.plot([], [], marker='o', linestyle='-', color='b')
ax.set_yscale('log')

# 縦軸を有効数字3桁（例：2.88e-08）にする設定
ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{x:.2e}"))

ax.set_xlabel('Time')
ax.set_ylabel('Pressure (Pa)')
ax.set_title('Real-time Vacuum Monitor')
plt.xticks(rotation=45, ha='right')
fig.subplots_adjust(bottom=0.25)
ax.grid(True, which="both", ls="--", alpha=0.5)

def update(frame):
    while ser.in_waiting > 0:
        try:
            raw_line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not raw_line:
                continue
                
            if "時刻を入力" in raw_line or ">" in raw_line:
                ser.write(b"\r\n")
                continue

            if "VAC," in raw_line:
                vac_part = raw_line[raw_line.find("VAC,"):]
                parts = vac_part.split(",")
                
                if len(parts) >= 3:
                    v_out = float(parts[-2])
                    pressure = float(parts[-1])
                    
                    now_dt = datetime.now()
                    timestamp = now_dt.strftime("%Y-%m-%d %H:%M:%S")
                    time_only = now_dt.strftime("%H:%M:%S")
                    
                    times.append(time_only)
                    pressures.append(pressure)
                    
                    print(f"[{timestamp}] 電圧: {v_out:.3f} V | 真空度: {pressure:.2e} Pa")
                    
                    with open(csv_filename, mode="a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow([timestamp, f"{v_out:.3f}", f"{pressure:.2e}"])
            else:
                print(f"[Picoからのメッセージ] {raw_line}")
                
        except Exception as e:
            print(f"[読み取りスキップ] {e}")
            
    if times:
        line.set_data(range(len(times)), pressures)
        ax.set_xlim(0, max(10, len(times) - 1))
        
        step = max(1, len(times) // 10)
        ticks = list(range(0, len(times), step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([times[i] for i in ticks])
        
        min_p = min(pressures) * 0.2
        max_p = max(pressures) * 5.0
        if min_p < max_p:
            ax.set_ylim(min_p, max_p)
            
    return line,

ani = FuncAnimation(fig, update, interval=1000, cache_frame_data=False)
plt.show()

print("記録を終了しました。")
ser.close()