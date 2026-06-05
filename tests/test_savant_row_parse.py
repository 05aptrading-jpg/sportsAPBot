import sys
import os
import csv
import io
import requests

sys.path.append(os.path.abspath('.'))
from api_client import savant

url = "https://baseballsavant.mlb.com/leaderboard/custom"
cols = ",".join([
    "player_id", "player_name",
    "p_formatted_ip",
    "k_percent",
    "bb_percent",
    "era",
    "xera",
    "p_strikeout",
    "p_walk",
    "p_home_run",
    "babip",
    "xwoba",
    "barrel_batted_rate",
    "hard_hit_percent",
    "whiff_percent",
])

params = {
    "year":       2025,
    "type":       "pitcher",
    "filter":     "",
    "sort":       4,
    "sortDir":    "asc",
    "min":        10,
    "selections": cols,
    "csv":        "true",
}
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

try:
    r = requests.get(url, params=params, headers=headers, timeout=15)
    text = r.text
    if text.startswith('\ufeff'):
        text = text[1:]
        
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    print("Keys parsed by DictReader:")
    print(reader.fieldnames)
    print("\nFirst row parsed by DictReader:")
    first_row = rows[0]
    for k, v in first_row.items():
        print(f"  {k}: {repr(v)}")
except Exception as e:
    print(f"Error: {e}")
