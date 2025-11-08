import sqlite3
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title='Solar Tracker Analytics', layout='wide')
st.title('🔆 Solar Tracker Analytics — Free‑Motion PV Tracker')

DB_PATH = st.sidebar.text_input('SQLite DB path', 'telemetry.db')
site = st.sidebar.text_input('Site ID', 'KMUTT-PROTOTYPE')

today = datetime.utcnow().date()
start_date = st.sidebar.date_input('Start date (UTC)', today)
end_date = st.sidebar.date_input('End date (UTC)', today)

resample_min = st.sidebar.selectbox('Resample (minutes)', [1, 5, 10, 15, 30, 60], index=1)

@st.cache_data(show_spinner=False)
def read_range(db_path: str, site_id: str, start: datetime, end: datetime) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    q = (
        "SELECT * FROM telemetry WHERE site_id = ? "
        "AND ts_utc >= ? AND ts_utc < ? ORDER BY ts_utc ASC"
    )
    df = pd.read_sql_query(q, con, params=[site_id, start.isoformat()+'Z', end.isoformat()+'Z'])
    con.close()
    if df.empty:
        return df
    df['ts_utc'] = pd.to_datetime(df['ts_utc'], utc=True)
    if 'dc_power' in df.columns:
        if df['dc_power'].isna().all() or (df['dc_power']<=0).all():
            if {'dc_voltage','dc_current'}.issubset(df.columns):
                df['dc_power'] = df['dc_voltage']*df['dc_current']
    else:
        if {'dc_voltage','dc_current'}.issubset(df.columns):
            df['dc_power'] = df['dc_voltage']*df['dc_current']
    return df

start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

raw = read_range(DB_PATH, site, start_dt, end_dt)
if raw.empty:
    st.info('ไม่พบข้อมูลในช่วงเวลานี้ ลองเปลี่ยนวันหรือเช็คไฟล์ DB path/site_id')
    st.stop()

raw = raw.set_index('ts_utc').sort_index()
rule = f'{resample_min}min'
agg = raw.resample(rule).agg({
    'dc_power':'mean',
    'dc_voltage':'mean',
    'dc_current':'mean',
    'irradiance_wm2':'mean',
    'panel_temp_c':'mean',
    'ambient_temp_c':'mean',
    'tracker_az_deg':'mean',
    'tracker_el_deg':'mean',
    'sun_az_deg':'mean',
    'sun_el_deg':'mean',
    'wind_ms':'mean'
}).dropna(how='all')

interval_h = resample_min/60.0
agg['energy_Wh_step'] = (agg['dc_power'].fillna(0) * interval_h)

daily_energy_wh = agg['energy_Wh_step'].sum()
peak_power_w = agg['dc_power'].max()
pr = None
if 'irradiance_wm2' in agg.columns and agg['irradiance_wm2'].notna().any():
    area_m2 = st.sidebar.number_input('Panel area (m²) for PR baseline', value=1.0, min_value=0.1, step=0.1)
    eta_nameplate = st.sidebar.number_input('Module eff. (nameplate)', value=0.20, min_value=0.05, max_value=0.30, step=0.01)
    expected_power_w = (agg['irradiance_wm2'].clip(lower=0) * area_m2 * eta_nameplate)
    pr = (agg['dc_power'].clip(lower=0).sum()) / (expected_power_w.sum() + 1e-9)

col1, col2, col3, col4 = st.columns(4)
col1.metric('Daily Energy (Wh)', f"{daily_energy_wh:,.1f}")
col2.metric('Peak Power (W)', f"{peak_power_w:,.1f}")
col3.metric('Avg Panel Temp (°C)', f"{agg['panel_temp_c'].mean():.1f}" if 'panel_temp_c' in agg else '-')
col4.metric('Performance Ratio', f"{pr:.2f}" if pr is not None else '-')

fig_p = px.line(agg.reset_index(), x='ts_utc', y='dc_power', title='DC Power (W)')
st.plotly_chart(fig_p, use_container_width=True)

cols = st.columns(2)
fig_g = px.line(agg.reset_index(), x='ts_utc', y='irradiance_wm2', title='Irradiance (W/m²)')
cols[0].plotly_chart(fig_g, use_container_width=True)

fig_t = px.line(agg.reset_index(), x='ts_utc', y=['panel_temp_c','ambient_temp_c'], title='Temperatures (°C)')
cols[1].plotly_chart(fig_t, use_container_width=True)

if {'tracker_az_deg','sun_az_deg','tracker_el_deg','sun_el_deg'}.issubset(agg.columns):
    err_az = (agg['tracker_az_deg'] - agg['sun_az_deg']).abs()
    err_el = (agg['tracker_el_deg'] - agg['sun_el_deg']).abs()
    err = pd.DataFrame({'ts_utc': agg.index, 'err_az': err_az, 'err_el': err_el})
    fig_err = px.line(err, x='ts_utc', y=['err_az','err_el'], title='Tracking Error (°)')
    st.plotly_chart(fig_err, use_container_width=True)

with st.expander('Event Flags (Simple Rules)'):
    flags = []
    if 'wind_ms' in agg.columns:
        high_wind = agg[agg['wind_ms'] >= 12]
        if not high_wind.empty:
            flags.append(f"High wind samples: {len(high_wind)} (>=12 m/s)")
    if pr is not None and pr < 0.7:
        flags.append(f"Low Performance Ratio: {pr:.2f} (< 0.70 baseline)")
    if 'dc_power' in agg.columns and agg['dc_power'].max() < 50:
        flags.append('Very low peak power (<50 W)')
    if flags:
        for f in flags:
            st.warning(f)
    else:
        st.success('No obvious issues detected by simple rules.')

st.subheader('Resampled Table')
st.dataframe(agg.reset_index().tail(200))

csv = agg.reset_index().to_csv(index=False).encode('utf-8')
st.download_button('Download aggregated CSV', data=csv, file_name='aggregated.csv', mime='text/csv')
