import streamlit as st
import pandas as pd
import time
import os
import glob
import altair as alt

st.title("🔬 リアルタイム真空度モニタリング")
st.write("実験室の真空状態をブラウザでリアルタイム表示しています。")

chart_placeholder = st.empty()
metric_placeholder = st.empty()

def get_latest_csv():
    # ▼ 実際の保存先フォルダ（絶対パス）を指定するように変更 ▼
    files = glob.glob(r"C:\Users\HiSOR_MBE\メインの真空計log\vacuum_log_*.csv")
    if not files:
        return None
    return max(files, key=os.path.getctime)

while True:
    csv_file = get_latest_csv()
    
    if csv_file and os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            
            if not df.empty:
                latest_time = df["Timestamp"].iloc[-1]
                latest_volt = df["Voltage_V"].iloc[-1]
                latest_press = float(df["Pressure_Pa"].iloc[-1])
                
                metric_placeholder.metric(
                    label=f"最新の真空度 ({latest_time})", 
                    value=f"{latest_press:.2e} Pa", 
                    delta=f"電圧: {latest_volt} V"
                )
                
                df["Timestamp"] = pd.to_datetime(df["Timestamp"])
                
                chart = alt.Chart(df).mark_line(color='blue').encode(
                    x=alt.X('Timestamp:T', title='時間'),
                    y=alt.Y('Pressure_Pa:Q', 
                            scale=alt.Scale(type='log'), 
                            axis=alt.Axis(format='.2e', title='Pressure (Pa)'))
                )
                
                chart_placeholder.altair_chart(chart, use_container_width=True)
        except Exception as e:
            pass
            
    time.sleep(3)
    st.rerun()