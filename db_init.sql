CREATE TABLE IF NOT EXISTS telemetry (
    ts_utc TEXT NOT NULL,
    site_id TEXT NOT NULL,
    dc_voltage REAL,
    dc_current REAL,
    dc_power REAL,
    energy_wh REAL,
    panel_temp_c REAL,
    ambient_temp_c REAL,
    irradiance_wm2 REAL,
    wind_ms REAL,
    tracker_az_deg REAL,
    tracker_el_deg REAL,
    sun_az_deg REAL,
    sun_el_deg REAL,
    gps_lat REAL,
    gps_lon REAL,
    status TEXT,
    PRIMARY KEY (ts_utc, site_id)
);
CREATE INDEX IF NOT EXISTS idx_telemetry_site_ts ON telemetry(site_id, ts_utc);
