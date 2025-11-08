# Solar Tracker Analytics (Streamlit)
เปิดได้บนมือถือ/เดสก์ท็อป เป็นเว็บแดชบอร์ดวิเคราะห์ข้อมูลโซลาร์แบบหันตามแสง

## รันเร็วในเครื่อง (เดโม)
```bash
pip install -r requirements.txt
# สร้างฐานและโหลดตัวอย่าง
sqlite3 telemetry.db < db_init.sql
python load_csv_to_db.py
# เปิดแดชบอร์ด
streamlit run app.py
```

## ดีพลอยขึ้นคลาวด์ (มือถือเปิดได้จากทุกที่)
1) อัปโหลดโฟลเดอร์นี้ขึ้น GitHub  
2) ไปที่ share.streamlit.io → New app → เลือก repo → main file = `app.py` → Deploy  
3) ได้ลิงก์เว็บ แล้วทำ Add to Home Screen บนมือถือ

## ฟีเจอร์
- KPI: Daily Energy, Peak Power, Temps, PR
- กราฟ: DC Power, Irradiance, Temperatures
- Tracking Error (az/el)
- Event flags (ลมแรง, PR ต่ำ, กำลังไฟตก)
- ดาวน์โหลด CSV หลังรีแซมเปิล

## โครงสร้างข้อมูล (ตาราง `telemetry`)
ดูไฟล์ `db_init.sql` (PRIMARY KEY = ts_utc + site_id)
