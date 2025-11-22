import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ----------------- หน้า & การรีเฟรชอัตโนมัติ -----------------
st.set_page_config(page_title="Solar Tracker Analytics", layout="wide")
# รีเฟรชทุก 30 วินาที (เผื่อใช้กับข้อมูลสดจาก ESP32/Google Sheet)
st_autorefresh(interval=30000, key="data_refresh")


# ----------------- ฟังก์ชันโหลดข้อมูล -----------------
@st.cache_data(show_spinner=False, ttl=30)
def load_all_data(source: str) -> pd.DataFrame:
    """
    โหลดข้อมูลทั้งหมดจาก SQLite หรือ CSV/URL
    คืนค่า DataFrame ที่มีคอลัมน์ ts_utc (datetime UTC)
    """
    source = source.strip()

    # ถ้าลงท้าย .db / .sqlite ให้ถือว่าเป็นฐานข้อมูล
    if source.lower().endswith((".db", ".sqlite", ".sqlite3")):
        conn = sqlite3.connect(source)
        try:
            # สมมติว่าตารางชื่อ telemetry
            df = pd.read_sql_query("SELECT * FROM telemetry", conn)
        finally:
            conn.close()
    else:
        # ถ้าไม่ใช่ .db ให้ลองอ่านเป็น CSV หรือ URL
        df = pd.read_csv(source)

    if "ts_utc" not in df.columns:
        raise ValueError("ไม่พบคอลัมน์ 'ts_utc' ในไฟล์/ฐานข้อมูล")

    # แปลงเวลาเป็น datetime แบบ UTC
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc"]).copy()

    # แปลง site_id เป็น string เผื่อเป็นตัวเลข
    if "site_id" in df.columns:
        df["site_id"] = df["site_id"].astype(str)

    return df


def filter_and_resample(
    df: pd.DataFrame,
    site_id: str,
    start_dt: datetime,
    end_dt: datetime,
    resample_min: int,
) -> pd.DataFrame:
    """
    ฟิลเตอร์ข้อมูลตาม site_id และช่วงเวลา แล้ว resample ตามนาทีที่กำหนด
    """
    # ฟิลเตอร์ตาม site_id
    if "site_id" in df.columns and site_id:
        df = df[df["site_id"] == site_id]

    # ฟิลเตอร์ช่วงเวลา
    mask = (df["ts_utc"] >= start_dt) & (df["ts_utc"] <= end_dt)
    df = df.loc[mask].copy()

    if df.empty:
        return df

    df = df.sort_values("ts_utc").set_index("ts_utc")

    rule = f"{resample_min}min"
    agg_cols = {}

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            agg_cols[col] = "mean"
        else:
            agg_cols[col] = "first"

    df_resampled = df.resample(rule).agg(agg_cols)
    df_resampled = df_resampled.dropna(how="all")

    return df_resampled


# ----------------- Sidebar: การตั้งค่า -----------------
st.sidebar.header("⚙️ Settings")

DB_OR_CSV = st.sidebar.text_input(
    "SQLite DB path (or CSV / URL)",
    "sample_data.csv",
)

site_input = st.sidebar.text_input("Site ID", "KMUTT-PROTOTYPE")

# โหลดข้อมูลดิบ
try:
    df_raw = load_all_data(DB_OR_CSV)
except Exception as e:
    st.error(f"โหลดข้อมูลไม่สำเร็จ: {e}")
    st.stop()

if df_raw.empty:
    st.warning("ไม่พบข้อมูลในไฟล์/ฐานข้อมูลที่ระบุ")
    st.stop()

# ถ้ามีหลาย site ให้เลือกจากรายการ
if "site_id" in df_raw.columns:
    unique_sites = sorted(df_raw["site_id"].astype(str).unique())
    if site_input in unique_sites:
        default_idx = unique_sites.index(site_input)
    else:
        default_idx = 0
    site = st.sidebar.selectbox("Site ID (จากข้อมูลที่มี)", unique_sites, index=default_idx)
else:
    site = site_input

min_date = df_raw["ts_utc"].min().date()
max_date = df_raw["ts_utc"].max().date()

start_date = st.sidebar.date_input("Start date (UTC)", min_date, min_value=min_date, max_value=max_date)
end_date = st.sidebar.date_input("End date (UTC)", max_date, min_value=min_date, max_value=max_date)

if start_date > end_date:
    st.sidebar.error("Start date ต้องไม่มากกว่า End date")
    st.stop()

resample_min = st.sidebar.selectbox("Resample (minutes)", [1, 5, 10, 15, 30, 60], index=0)

panel_area = st.sidebar.number_input(
    "Panel area (m²) baseline",
    min_value=0.05,
    value=1.00,
    step=0.05,
)

module_eff = st.sidebar.number_input(
    "Module eff. (0–1)",
    min_value=0.01,
    max_value=1.00,
    value=0.20,
    step=0.01,
)

fixed_pr_baseline = st.sidebar.number_input(
    "Fixed-tilt PR baseline (โซลาร์ 5V ธรรมดา)",
    min_value=0.10,
    max_value=1.00,
    value=0.80,
    step=0.05,
)


# ----------------- ฟิลเตอร์ข้อมูลตามช่วงเวลา -----------------
start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

df = filter_and_resample(df_raw, site, start_dt, end_dt, resample_min)

st.title("☀️ Solar Tracker Analytics — Free-Motion PV Tracker")

if df.empty:
    st.warning("ไม่พบข้อมูลในไฟล์/ช่วงเวลาที่เลือก")
    st.stop()


# ----------------- คำนวณสถิติหลัก -----------------
dt_hours = resample_min / 60.0

dc_power = df.get("dc_power", pd.Series(dtype=float)).fillna(0.0)
panel_temp_c = df.get("panel_temp_c", pd.Series(dtype=float))
irradiance = df.get("irradiance_wm2", pd.Series(dtype=float)).fillna(0.0)

# พลังงานจริงของ Tracker (Wh)
daily_energy_wh = float((dc_power * dt_hours).sum())

# กำลังสูงสุด
peak_power = float(dc_power.max()) if not dc_power.empty else 0.0

# อุณหภูมิแผงเฉลี่ย
avg_panel_temp = float(panel_temp_c.mean()) if not panel_temp_c.empty else np.nan

# พลังงานอ้างอิงตาม irradiance (สำหรับใช้ทั้ง Tracker และ Fixed)
ref_energy_wh = float((irradiance * panel_area * module_eff * dt_hours).sum())

if ref_energy_wh > 0:
    pr_tracker = daily_energy_wh / ref_energy_wh
else:
    pr_tracker = np.nan

# สมมติแผง Fixed 5V มี PR = fixed_pr_baseline
if ref_energy_wh > 0:
    fixed_energy_wh = ref_energy_wh * fixed_pr_baseline
else:
    fixed_energy_wh = np.nan

# Tracker Gain เทียบกับ Fixed 5V
if fixed_energy_wh and fixed_energy_wh > 0:
    tracker_gain_pct = (daily_energy_wh - fixed_energy_wh) / fixed_energy_wh * 100.0
else:
    tracker_gain_pct = np.nan


# ----------------- แสดงผล Metrics -----------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Tracker Energy (Wh)", f"{daily_energy_wh:.2f}")
if np.isfinite(fixed_energy_wh):
    col2.metric("Fixed 5V Energy (Wh, est.)", f"{fixed_energy_wh:.2f}")
else:
    col2.metric("Fixed 5V Energy (Wh, est.)", "N/A")

if np.isfinite(tracker_gain_pct):
    col3.metric("Tracker Gain vs Fixed (%)", f"{tracker_gain_pct:.1f}%")
else:
    col3.metric("Tracker Gain vs Fixed (%)", "N/A")

col4.metric("Peak Power (W)", f"{peak_power:.2f}")

col5, col6, col7, col8 = st.columns(4)
if np.isfinite(pr_tracker):
    col5.metric("Performance Ratio (Tracker)", f"{pr_tracker:.2f}")
else:
    col5.metric("Performance Ratio (Tracker)", "N/A")

col6.metric("Fixed-tilt PR baseline", f"{fixed_pr_baseline:.2f}")
col7.metric("Reference Energy (Wh)", f"{ref_energy_wh:.2f}")
if np.isfinite(avg_panel_temp):
    col8.metric("Avg Panel Temp (°C)", f"{avg_panel_temp:.1f}")
else:
    col8.metric("Avg Panel Temp (°C)", "N/A")

st.markdown("---")

# ----------------- กราฟ DC Power -----------------
st.subheader("DC Power vs Time")

df_plot = df.reset_index().rename(columns={"ts_utc": "timestamp"})

fig_power = px.line(
    df_plot,
    x="timestamp",
    y="dc_power",
    labels={"timestamp": "Time (UTC)", "dc_power": "DC Power (W)"},
)
fig_power.update_layout(xaxis_rangeslider_visible=False)
st.plotly_chart(fig_power, use_container_width=True)

# ----------------- กราฟ Irradiance & Temp -----------------
cols_plot = st.columns(2)

with cols_plot[0]:
    if "irradiance_wm2" in df.columns:
        st.subheader("Irradiance (W/m²)")
        fig_irr = px.line(
            df_plot,
            x="timestamp",
            y="irradiance_wm2",
            labels={"timestamp": "Time (UTC)", "irradiance_wm2": "Irradiance (W/m²)"},
        )
        fig_irr.update_layout(xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_irr, use_container_width=True)

with cols_plot[1]:
    if "panel_temp_c" in df.columns:
        st.subheader("Panel Temperature (°C)")
        fig_tmp = px.line(
            df_plot,
            x="timestamp",
            y="panel_temp_c",
            labels={"timestamp": "Time (UTC)", "panel_temp_c": "Panel Temp (°C)"},
        )
        fig_tmp.update_layout(xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_tmp, use_container_width=True)

st.markdown("___")
st.caption(
    "Tracker Energy คือพลังงานจริงจากระบบหันตามดวงอาทิตย์\n"
    "Fixed 5V Energy คือพลังงานที่คาดว่าได้จากโซลาร์ 5V ธรรมดา (ติดตายตัว) โดยอ้างอิง PR baseline ที่ตั้งใน Sidebar\n"
    "Tracker Gain vs Fixed คือเปอร์เซ็นต์ที่ระบบ Free-Motion Tracker ดีกว่า/แย่กว่าแผงคงที่"
)
