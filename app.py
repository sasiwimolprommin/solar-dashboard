import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

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
    # ตัดช่องว่าง
    source = source.strip()

    if source.lower().endswith((".db", ".sqlite", ".sqlite3")):
        # โหลดจาก SQLite
        conn = sqlite3.connect(source)
        try:
            # สมมติว่าตารางชื่อ telemetry และมีคอลัมน์ ts_utc เป็น TEXT/ISO8601
            df = pd.read_sql_query("SELECT * FROM telemetry", conn)
        finally:
            conn.close()
    else:
        # โหลดจาก CSV หรือ URL (รองรับทั้งไฟล์ใน repo และ Google Sheet URL)
        df = pd.read_csv(source)

    # แปลงเวลาเป็น datetime UTC
    if "ts_utc" not in df.columns:
        raise ValueError("ไม่พบคอลัมน์ 'ts_utc' ในไฟล์/ฐานข้อมูล")

    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc"]).copy()

    # ถ้ามี site_id ก็แปลงเป็น str เผื่อมีตัวเลข
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
    # ฟิลเตอร์ site
    if "site_id" in df.columns and site_id:
        df = df[df["site_id"] == site_id]

    # ฟิลเตอร์ช่วงเวลา (ts_utc อยู่ในรูป datetime UTC)
    mask = (df["ts_utc"] >= start_dt) & (df["ts_utc"] <= end_dt)
    df = df.loc[mask].copy()

    if df.empty:
        return df

    df = df.sort_values("ts_utc").set_index("ts_utc")

    # resample เป็นค่าเฉลี่ยต่อช่วงเวลา (เช่น 5 นาที)
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


# ----------------- ส่วน Sidebar: การตั้งค่า -----------------
st.sidebar.header("⚙️ Settings")

DB_OR_CSV = st.sidebar.text_input(
    "SQLite DB path (or CSV / URL)",
    "sample_data.csv",
)

site = st.sidebar.text_input("Site ID", "KMUTT-PROTOTYPE")

# โหลดข้อมูลดิบก่อน เพื่อดูช่วงวันที่ทั้งหมด
df_raw = pd.DataFrame()
error = None
try:
    df_raw = load_all_data(DB_OR_CSV)
except Exception as e:
    error = str(e)

if error:
    st.error(f"โหลดข้อมูลไม่สำเร็จ: {error}")
    st.stop()

if df_raw.empty:
    st.warning("ไม่พบข้อมูลในไฟล์/ฐานข้อมูลที่ระบุ")
    st.stop()

# ถ้ามีหลาย site ให้ผู้ใช้เลือกได้จากรายการ
if "site_id" in df_raw.columns:
    unique_sites = sorted(df_raw["site_id"].astype(str).unique())
    if site not in unique_sites:
        # ถ้า site ที่พิมพ์ไม่อยู่ในรายการ ให้เลือกตัวแรก
        site = st.sidebar.selectbox("Site ID (จากข้อมูลที่มี)", unique_sites, index=0)
    else:
        site = st.sidebar.selectbox("Site ID (จากข้อมูลที่มี)", unique_sites, index=unique_sites.index(site))

# หาช่วงวันที่จากข้อมูล
min_date = df_raw["ts_utc"].min().date()
max_date = df_raw["ts_utc"].max().date()

start_date = st.sidebar.date_input("Start date (UTC)", min_date, min_value=min_date, max_value=max_date)
end_date = st.sidebar.date_input("End date (UTC)", max_date, min_value=min_date, max_value=max_date)

if start_date > end_date:
    st.sidebar.error("Start date ต้องไม่มากกว่า End date")
    st.stop()

resample_min = st.sidebar.selectbox("Resample (minutes)", [1, 5, 10, 15, 30, 60], index=1)

panel_area = st.sidebar.number_input(
    "Panel area (m²) for PR baseline",
    min_value=0.1,
    value=1.0,
    step=0.1,
)

module_eff = st.sidebar.number_input(
    "Module eff. (nameplate)",
    min_value=0.01,
    max_value=1.0,
    value=0.20,
    step=0.01,
)

fixed_pr_baseline = st.sidebar.number_input(
    "Fixed-tilt PR baseline (โซลาร์ปกติ)",
    min_value=0.1,
    max_value=1.0,
    value=0.80,
    step=0.05,
)


# ----------------- เตรียมช่วงเวลา และฟิลเตอร์ข้อมูล -----------------
start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

df = filter_and_resample(df_raw, site, start_dt, end_dt, resample_min)

st.title("☀️ Solar Tracker Analytics — Free-Motion PV Tracker")

if df.empty:
    st.warning("ไม่พบข้อมูลในไฟล์ที่ระบุ/ช่วงเวลานี้ – ลองเปลี่ยนช่วงวันที่ หรือไฟล์ข้อมูล")
    st.stop()


# ----------------- คำนวณสถิติหลัก -----------------
dt_hours = resample_min / 60.0

dc_power = df.get("dc_power", pd.Series(dtype=float)).fillna(0.0)
panel_temp_c = df.get("panel_temp_c", pd.Series(dtype=float))
irradiance = df.get("irradiance_wm2", pd.Series(dtype=float)).fillna(0.0)

# พลังงานจริงที่ผลิตได้ (Wh)
daily_energy_wh = float((dc_power * dt_hours).sum())

# กำลังสูงสุด (W)
peak_power = float(dc_power.max()) if not dc_power.empty else 0.0

# อุณหภูมิแผงเฉลี่ย (°C)
avg_panel_temp = float(panel_temp_c.mean()) if not panel_temp_c.empty else np.nan

# พลังงานอ้างอิงจาก irradiance (Wh) สำหรับคำนวณ PR
ref_energy_wh = float((irradiance * panel_area * module_eff * dt_hours).sum())

if ref_energy_wh > 0:
    pr = daily_energy_wh / ref_energy_wh
else:
    pr = np.nan

# เปรียบเทียบกับโซลาร์คงที่
tracker_gain_pct = None
if np.isfinite(pr) and fixed_pr_baseline > 0:
    tracker_gain_pct = (pr - fixed_pr_baseline) / fixed_pr_baseline * 100.0


# ----------------- แสดงผลเป็น metrics -----------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Daily Energy (Wh)", f"{daily_energy_wh:.1f}")
col2.metric("Peak Power (W)", f"{peak_power:.1f}")
if np.isfinite(avg_panel_temp):
    col3.metric("Avg Panel Temp (°C)", f"{avg_panel_temp:.1f}")
else:
    col3.metric("Avg Panel Temp (°C)", "N/A")
if np.isfinite(pr):
    col4.metric("Performance Ratio (Tracker)", f"{pr:.2f}")
else:
    col4.metric("Performance Ratio (Tracker)", "N/A")

if tracker_gain_pct is not None:
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Tracker Gain vs Fixed (%)", f"{tracker_gain_pct:.1f}%")
    col6.metric("Fixed-tilt PR baseline", f"{fixed_pr_baseline:.2f}")
    col7.metric("Reference Energy (Wh)", f"{ref_energy_wh:.1f}")
    col8.metric("Resample", f"{resample_min} min")


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

# ----------------- กราฟเพิ่มเติม (Optional) -----------------
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
    "ระบบนี้รองรับทั้งไฟล์ตัวอย่าง sample_data.csv และข้อมูลจริงจาก ESP32 "
    "ผ่าน Google Sheet / SQLite; ปรับค่า PR baseline ในแถบซ้ายเพื่อเทียบกับโซลาร์แบบปกติได้"
)

