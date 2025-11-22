import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta

# -------------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------------
st.set_page_config(
    page_title='Solar Tracker Analytics',
    layout='wide'
)

st.title("🌞 Solar Tracker Analytics — Free-Motion PV Tracker")

# -------------------------------------------------------
# SIDEBAR — INPUTS
# -------------------------------------------------------
st.sidebar.header("Settings")

csv_path = st.sidebar.text_input("CSV file (or URL)", "sample_data.csv")

site_id = st.sidebar.text_input("Site ID", "KMUTT-PROTOTYPE")

today = datetime.utcnow().date()
start_date = st.sidebar.date_input("Start date (UTC)", today)
end_date = st.sidebar.date_input("End date (UTC)", today)

resample_min = st.sidebar.selectbox("Resample (minutes)", [1, 5, 10, 15, 30, 60], index=1)

panel_area = st.sidebar.number_input("Panel area (m²) baseline", 0.1, 10.0, 1.00, 0.1)
eff = st.sidebar.number_input("Module eff. (0–1)", 0.01, 1.0, 0.20, 0.01)


# -------------------------------------------------------
# LOAD DATA
# -------------------------------------------------------
def load_csv(path):
    try:
        df = pd.read_csv(path)

        # ⭐ สำคัญสุด – แปลง timestamp ให้เป็น datetime
        df['ts_utc'] = pd.to_datetime(df['ts_utc'], errors='coerce')

        # ลบทุกรายการที่ไม่สามารถแปลงได้
        df = df.dropna(subset=['ts_utc'])

        return df

    except Exception as e:
        st.error(f"โหลดไฟล์ไม่สำเร็จ: {e}")
        return None


# -------------------------------------------------------
# FILTER DATA BY DATE
# -------------------------------------------------------
def filter_data(df, start, end):
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)

    df = df[(df['ts_utc'] >= start_ts) & (df['ts_utc'] < end_ts)]
    return df


# -------------------------------------------------------
# RESAMPLE DATA
# -------------------------------------------------------
def resample_df(df, minutes):
    df = df.set_index('ts_utc')
    df = df.resample(f"{minutes}T").mean().interpolate()
    df = df.reset_index()
    return df


# -------------------------------------------------------
# PROCESSING
# -------------------------------------------------------
df = load_csv(csv_path)

if df is None or df.empty:
    st.warning("ไม่พบข้อมูลในไฟล์หรือโหลดไม่ได้ – ตรวจสอบชื่อไฟล์ CSV แล้วกด Rerun")
    st.stop()

df = df[df["site_id"] == site_id]

df = filter_data(df, start_date, end_date)

if df.empty:
    st.warning("ไม่พบข้อมูลในช่วงวันที่นี้")
    st.stop()

df = resample_df(df, resample_min)

# -------------------------------------------------------
# SUMMARY METRICS
# -------------------------------------------------------
daily_wh = np.trapz(df['dc_power'], dx=resample_min * 60) / 3600
peak_power = df['dc_power'].max()
avg_temp = df['panel_temp_c'].mean()
pr_value = (daily_wh / (panel_area * eff * 1000)) if eff > 0 else 0


# -------------------------------------------------------
# SHOW SUMMARY
# -------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Daily Energy (Wh)", f"{daily_wh:.1f}")
col2.metric("Peak Power (W)", f"{peak_power:.1f}")
col3.metric("Avg Panel Temp (°C)", f"{avg_temp:.1f}")
col4.metric("Performance Ratio", f"{pr_value:.2f}")


# -------------------------------------------------------
# PLOTS
# -------------------------------------------------------

# 1) DC POWER
fig1 = px.line(df, x="ts_utc", y="dc_power", title="DC Power vs Time")
st.plotly_chart(fig1, use_container_width=True)

# 2) IRRADIANCE
fig2 = px.line(df, x="ts_utc", y="irradiance_wm2", title="Irradiance (W/m²)")
st.plotly_chart(fig2, use_container_width=True)

# 3) PANEL TEMP
fig3 = px.line(df, x="ts_utc", y="panel_temp_c", title="Panel Temperature (°C)")
st.plotly_chart(fig3, use_container_width=True)

# 4) WIND SPEED
fig4 = px.line(df, x="ts_utc", y="wind_ms", title="Wind Speed (m/s)")
st.plotly_chart(fig4, use_container_width=True)

# 5) TRACKER ANGLE (Az & Elevation)
fig5 = px.line(df, x="ts_utc", y=["tracker_az_deg", "tracker_el_deg"],
               title="Tracker Angle (Azimuth / Elevation)")
st.plotly_chart(fig5, use_container_width=True)
