import sys
import os
import csv
import io

sys.path.append(os.path.abspath('.'))
from api_client import savant

print("Running original get_pitcher_leaderboard...")
# Vamos a ver qué obtiene DictReader en la función original
import requests
import config

url = "https://baseballsavant.mlb.com/leaderboard/custom"
params = {
    "year":       2025,
    "type":       "pitcher",
    "filter":     "",
    "sort":       4,
    "sortDir":    "asc",
    "min":        10,
    "selections": savant._PITCHER_COLS,
    "csv":        "true",
}
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

r = requests.get(url, params=params, headers=headers, timeout=15)
csv_text = r.text

print(f"Original csv_text length: {len(csv_text)}")
# Ver si empieza con BOM
print(f"Starts with BOM: {csv_text.startswith(chr(65279))}")

# Parsear usando la función original de api_client:
rows = savant._parse_csv(csv_text)
print(f"Total rows parsed: {len(rows)}")
print("First row keys:")
print(list(rows[0].keys()))
print("First row values:")
for k, v in rows[0].items():
    print(f"  {k}: {repr(v)}")
