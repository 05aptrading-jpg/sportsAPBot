import re
import requests

url = "https://www.baseball-reference.com/leagues/majors/2025-standard-pitching.shtml"
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

    # Buscar en comentarios
    comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
    commented_table_ids = []
    for c in comments:
        commented_ids = re.findall(r'<table[^>]+id="([^"]+)"', c)
        commented_table_ids.extend(commented_ids)
    print("IDs de tablas encontradas en comentarios:")
    print(commented_table_ids)

    # Buscar "teams_standard_pitching" o "pitching_standard"
    target_table_id = "teams_standard_pitching"
    if target_table_id in html:
        print(f"¡'{target_table_id}' encontrado en el HTML directo!")
        # Buscar cabeceras de la tabla
        table_match = re.search(rf'<table[^>]+id="{target_table_id}"[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
        if table_match:
            headers = re.findall(r'<th[^>]+data-stat="([^"]+)"[^>]*>([^<]*)</th>', table_match.group(1), re.IGNORECASE)
            print("Columnas de teams_standard_pitching:")
            print([h[0] for h in headers])
    else:
        # Buscar en comentarios
        for c in comments:
            if target_table_id in c:
                print(f"¡'{target_table_id}' encontrado en un comentario!")
                table_match = re.search(rf'<table[^>]+id="{target_table_id}"[^>]*>(.*?)</table>', c, re.DOTALL | re.IGNORECASE)
                if table_match:
                    headers = re.findall(r'<th[^>]+data-stat="([^"]+)"[^>]*>([^<]*)</th>', table_match.group(1), re.IGNORECASE)
                    print("Columnas de teams_standard_pitching (comentario):")
                    print([h[0] for h in headers])
                break

except Exception as e:
    print(f"Error: {e}")
