import sqlite3
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta, timezone
from pathlib import Path

st.set_page_config(page_title='Solar Tracker Analytics', layout='wide')
st.title('☀️ Solar Tracker Analytics — Free-Motion PV Tracker')

# -----------------------------
# Sidebar Input
# -----------------------------
st.sidebar.header("Settings")

DB_OR_CSV = st.sidebar.text_input('SQLite DB path (or CSV / URL)', 'sample_data.csv')
site = st.sidebar.text_input('Site ID', 'KMUTT-PROTOTYPE')
site_from_data = st.sidebar.text_input('Site ID (จากข้อมูลที่มี)', 'KMUTT-PROTOTYPE')

# วันที่
today = datetime.utcnow().date()
start_date = st.sidebar.date_input('Start date (UTC)', today)
end_date = st.sidebar.date_input('End date (UTC)', today)

# resample (minutes)
resample_min = st.sidebar.selectbox('Resample (minutes)', [1, 5, 10, 15, 30, 60], index=1)

# PR baseline settings
panel_area = st.sidebar.number_input("Panel area (m²) for PR baseline", value=1.00, step=0.1)
module_eff = st.sidebar.number_input("Module eff. (nameplate)", value=0.20, step=0.01)

# -----------------------------
# Load Data
# -----------------------------
def load_data(path, site, start, end):
    if path.endswith(".csv"):
        df = pd.read_csv(path)
    else:
        conn = sqlite3.connect(path)
        df = pd.read_sql_query("SELECT * FROM telemetry", conn)
        conn.close()

    # Convert time
    df["ts_utc"] = pd.to_datetime(df["ts_utc"])
    df = df[(df["site_id"] == site)]
    df = df[(df["ts_utc"] >= pd.Timestamp(start)) & (df["ts_utc"] <= pd.Timestamp(end) + pd.Timedelta(days=1))]

    if df.empty:
        return pd.DataFrame()

    df = df.set_index("ts_utc").sort_index()

    # Apply resample (mean)
    df = df.resample(f"{resample_min}T").mean().dropna()

    return df


df = load_data(DB_OR_CSV, site_from_data, start_date, end_date)

# -----------------------------
# If no data
# -----------------------------
if df.empty:
    st.info('ไม่พบข้อมูลในไฟล์นี้ระบุ/ช่วงเวลานี้ — ใส่ชื่อไฟล์เป็น "sample_data.csv" หรืออัปโหลดไฟล์ให้ถูกตำแหน่ง แล้วกด Rerun')
    st.stop()

# -----------------------------
# Summary Cards
# -----------------------------
st.subheader("Summary")
col1, col2, col3, col4 = st.columns(4)

daily_energy = (df["dc_power"].sum() * (resample_min / 60))  # Wh
peak_power = df["dc_power"].max()
avg_panel_temp = df["temp_panel"].mean() if "temp_panel" in df.columns else 0
performance_ratio = daily_energy / (panel_area * 1000 * module_eff + 1e-9)

col1.metric("Daily Energy (Wh)", f"{daily_energy:.1f}")
col2.metric("Peak Power (W)", f"{peak_power:.1f}")
col3.metric("Avg Panel Temp (°C)", f"{avg_panel_temp:.1f}")
col4.metric("Performance Ratio", f"{performance_ratio:.2f}")

# -----------------------------
# DC POWER GRAPH (WITH MARKERS)
# -----------------------------
st.subheader("DC Power vs Time")

df_plot = df.reset_index().rename(columns={"ts_utc": "timestamp"})

fig_power = px.line(
    df_plot,
    x="timestamp",
    y="dc_power",
    labels={"timestamp": "Time (UTC)", "dc_power": "DC Power (W)"},
    markers=True,       # ★ จุด marker เพื่อดูค่าง่าย
)

fig_power.update_layout(xaxis_rangeslider_visible=False)
st.plotly_chart(fig_power, use_container_width=True)

# Show raw data preview
st.write("🔍 **ค่าที่ใช้ในการพล็อตกราฟ DC Power**")
st.dataframe(df_plot[["timestamp", "dc_power"]])

# -----------------------------
# IRRADIANCE GRAPH
# -----------------------------
if "irradiance" in df.columns:
    st.subheader("Irradiance (W/m²)")
    fig_irr = px.line(
        df_plot,
        x="timestamp",
        y="irradiance",
        labels={"timestamp": "Time (UTC)", "irradiance": "Irradiance"},
        markers=True,
    )
    st.plotly_chart(fig_irr, use_container_width=True)

# -----------------------------
# PANEL TEMPERATURE GRAPH
# -----------------------------
if "temp_panel" in df.columns:
    st.subheader("Panel Temperature (°C)")
    fig_temp = px.line(
        df_plot,
        x="timestamp",
        y="temp_panel",
        labels={"timestamp": "Time (UTC)", "temp_panel": "Panel Temp (°C)"},
        markers=True,
    )
    st.plotly_chart(fig_temp, use_container_width=True)

# -----------------------------
# RAW DATA
# -----------------------------
st.subheader("Raw data")
st.dataframe(df)
