import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Solar Tracker Analytics", layout="wide")

st.title("🌞 Solar Tracker Analytics — Free-Motion PV Tracker")

# ======= READ CSV SAFELY =======
def load_csv(path):
    try:
        df = pd.read_csv(path)
    except:
        st.error("❌ โหลดไฟล์ CSV ไม่ได้ — ตรวจสอบว่าไฟล์อยู่ใน repo จริงหรือชื่อถูกต้อง")
        return None

    # แปลง timestamp → datetime
    if "ts_utc" in df.columns:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], errors="coerce")

    return df


# ======= FILTER DATA SAFELY =======
def filter_date(df, start_date, end_date):
    if df is None:
        return None
    if "ts_utc" not in df.columns:
        st.error("❌ ไม่มีคอลัมน์ ts_utc ในไฟล์ CSV")
        return None

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    df = df[(df["ts_utc"] >= start_dt) & (df["ts_utc"] <= end_dt)]
    return df


# ======= SIDEBAR =======
st.sidebar.header("Settings")

csv_path = st.sidebar.text_input("CSV file (or URL)", "sample_data.csv")
site_id = st.sidebar.text_input("Site ID", "KMUTT-PROTOTYPE")

start_date = st.sidebar.date_input("Start date (UTC)", datetime.utcnow().date())
end_date = st.sidebar.date_input("End date (UTC)", datetime.utcnow().date())

resample_min = st.sidebar.selectbox("Resample (minutes)", [1, 5, 10, 30, 60], index=1)

panel_area = st.sidebar.number_input("Panel area (m²) baseline", 0.05, 10.0, 1.0, 0.01)
module_eff = st.sidebar.number_input("Module eff. (0–1)", 0.01, 1.0, 0.20, 0.01)

# ======= LOAD DATA =======
df_raw = load_csv(csv_path)
df = filter_date(df_raw, start_date, end_date)

if df is None or df.empty:
    st.info("ไม่พบข้อมูลในไฟล์ช่วงเวลานี้ — ตรวจสอบวันที่หรือข้อมูลใน CSV")
    st.stop()

# ======= RESAMPLE =======
df = df.set_index("ts_utc").resample(f"{resample_min}min").mean().reset_index()

# ======= KPIs =======
daily_energy_Wh = (df["dc_power"].sum() * (resample_min / 60))
peak_power = df["dc_power"].max()
avg_panel_temp = df["panel_temp_c"].mean()

pr = (df["dc_power"].mean() / (df["irradiance_wm2"].mean() * panel_area * module_eff + 1e-6))

st.subheader("📊 Performance Summary")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Daily Energy (Wh)", f"{daily_energy_Wh:.1f}")
col2.metric("Peak Power (W)", f"{peak_power:.1f}")
col3.metric("Avg Panel Temp (°C)", f"{avg_panel_temp:.1f}")
col4.metric("Performance Ratio", f"{pr:.2f}")

# ======= GRAPHS =======
st.subheader("DC Power vs Time")
fig1 = px.line(df, x="ts_utc", y="dc_power", title="DC Power", markers=True)
st.plotly_chart(fig1, use_container_width=True)

st.subheader("Irradiance (W/m²)")
fig2 = px.line(df, x="ts_utc", y="irradiance_wm2", title="Irradiance", markers=True)
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Panel Temperature (°C)")
fig3 = px.line(df, x="ts_utc", y="panel_temp_c", title="Panel Temperature", markers=True)
st.plotly_chart(fig3, use_container_width=True)

st.subheader("Wind Speed (m/s)")
fig4 = px.line(df, x="ts_utc", y="wind_ms", title="Wind Speed", markers=True)
st.plotly_chart(fig4, use_container_width=True)

st.subheader("Tracker Angles (Azimuth / Elevation)")
fig5 = px.line(df, x="ts_utc", y=["tracker_az_deg", "tracker_el_deg"], title="Tracker Angles")
st.plotly_chart(fig5, use_container_width=True)
