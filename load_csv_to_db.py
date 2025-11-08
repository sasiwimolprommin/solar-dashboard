import sqlite3, pandas as pd

DB = 'telemetry.db'
CSV = 'sample_data.csv'

con = sqlite3.connect(DB)
with open('db_init.sql', 'r', encoding='utf-8') as f:
    con.executescript(f.read())

pdf = pd.read_csv(CSV)
pdf.to_sql('telemetry', con, if_exists='append', index=False)

con.close()
print('Loaded CSV -> telemetry.db')
