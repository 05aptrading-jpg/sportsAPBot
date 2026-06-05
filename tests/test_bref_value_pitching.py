import re
import requests

url = "https://www.baseball-reference.com/leagues/majors/2025-value-pitching.shtml"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

print(f"Fetching {url}...")
try:
    r = requests.get(url, headers=headers, timeout=15)
    print(f"Status Code: {r.status_code}")
    html = r.text
    print(f"HTML length: {len(html)}")

    # Encontrar todas las IDs de las tablas
    table_ids = re.findall(r'<table[^>]+id="([^"]+)"', html)
    print("IDs de tablas encontradas directamente en HTML:")
    print(table_ids)

    # Buscar "teams_value_pitching"
    target_table_id = "teams_value_pitching"
    if target_table_id in html:
        print(f"¡'{target_table_id}' encontrado en el HTML directo!")
        table_match = re.search(rf'<table[^>]+id="{target_table_id}"[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
        if table_match:
            headers = re.findall(r'<th[^>]+data-stat="([^"]+)"[^>]*>([^<]*)</th>', table_match.group(1), re.IGNORECASE)
            print("Columnas de teams_value_pitching:")
            print([h[0] for h in headers])
except Exception as e:
    print(f"Error: {e}")
