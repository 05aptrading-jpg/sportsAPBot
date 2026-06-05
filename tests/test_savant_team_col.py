import csv
import io
import requests

url = "https://baseballsavant.mlb.com/leaderboard/custom"
cols = ",".join([
    "player_id", "player_name", "player_team", "xwoba"
])

params = {
    "year":       2025,
    "type":       "batter",
    "filter":     "",
    "sort":       4,
    "sortDir":    "desc",
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
    print("Keys parsed:")
    print(reader.fieldnames)
    print("\nFirst row parsed:")
    print(rows[0])
except Exception as e:
    print(f"Error: {e}")
