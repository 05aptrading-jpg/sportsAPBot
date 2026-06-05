import re
import requests

url = "https://www.baseball-reference.com/leagues/majors/2025-reliever-pitching.shtml"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

try:
    r = requests.get(url, headers=headers, timeout=15)
    html = r.text
    table_match = re.search(r'<table[^>]+id="teams_reliever_pitching"[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    if table_match:
        headers = re.findall(r'<th[^>]+data-stat="([^"]+)"[^>]*>([^<]*)</th>', table_match.group(1), re.IGNORECASE)
        print("Columnas de teams_reliever_pitching:")
        print([h[0] for h in headers])
        
        # Muestra la primera fila de datos reales
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_match.group(1), re.DOTALL)
        for r_html in rows[:10]:
            cells = re.findall(r'<(?:td|th)[^>]+data-stat="([^"]+)"[^>]*>(?:<[^>]+>)*([^<]*)(?:</[^>]+>)*</(?:td|th)>', r_html, re.IGNORECASE)
            row = {k: v.strip() for k, v in cells if k}
            if row and row.get("team_name") not in ("", "League Average", "Totals", "Tm"):
                print("Ejemplo de fila de equipo:")
                print(row)
                break
except Exception as e:
    print(f"Error: {e}")
