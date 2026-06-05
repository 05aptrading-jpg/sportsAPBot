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

print(f"Fetching {url}...")
try:
    r = requests.get(url, headers=headers, timeout=15)
    print(f"Status Code: {r.status_code}")
    html = r.text
    print(f"HTML length: {len(html)}")

    table_ids = re.findall(r'<table[^>]+id="([^"]+)"', html)
    print("IDs de tablas:")
    print(table_ids)

    # Buscar en comentarios
    comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
    commented_table_ids = []
    for c in comments:
        commented_ids = re.findall(r'<table[^>]+id="([^"]+)"', c)
        commented_table_ids.extend(commented_ids)
    print("IDs de tablas en comentarios:")
    print(commented_table_ids)

except Exception as e:
    print(f"Error: {e}")
