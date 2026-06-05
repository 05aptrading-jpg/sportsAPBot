import requests

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

print("Fetching raw Savant leaderboard CSV...")
try:
    r = requests.get(url, params=params, headers=headers, timeout=15)
    print(f"Status Code: {r.status_code}")
    text = r.text
    print(f"Text length: {len(text)}")
    
    # Quitar el BOM
    if text.startswith('\ufeff'):
        text = text[1:]
        
    print("\n--- FIRST 3 LINES (encoded safe) ---")
    lines = text.splitlines()
    for i, line in enumerate(lines[:3]):
        # Codificar de forma segura para la consola de Windows
        print(f"Line {i}: {line.encode('ascii', errors='replace').decode('ascii')}")
except Exception as e:
    print(f"Error: {e}")
