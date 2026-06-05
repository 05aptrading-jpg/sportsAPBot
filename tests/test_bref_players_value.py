import re
import requests

url = "https://www.baseball-reference.com/teams/LAD/2025.shtml"
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
    html = r.text
    
    # Buscar "players_value_pitching"
    target_table_id = "players_value_pitching"
    
    # Nota: B-Ref oculta tables como players_value_pitching en comentarios!
    # Vamos a buscar en el HTML completo (directo + comentarios)
    table_match = re.search(rf'<table[^>]+id="{target_table_id}"[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    if not table_match:
        comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
        for c in comments:
            if target_table_id in c:
                table_match = re.search(rf'<table[^>]+id="{target_table_id}"[^>]*>(.*?)</table>', c, re.DOTALL | re.IGNORECASE)
                break

    if table_match:
        print(f"¡'{target_table_id}' encontrada!")
        headers = re.findall(r'<th[^>]+data-stat="([^"]+)"[^>]*>([^<]*)</th>', table_match.group(1), re.IGNORECASE)
        print("Columnas:")
        print([h[0] for h in headers])
        
        # Muestra las primeras 3 filas
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_match.group(1), re.DOTALL)
        count = 0
        for r_html in rows:
            cells = re.findall(r'<(?:td|th)[^>]+data-stat="([^"]+)"[^>]*>(?:<[^>]+>)*([^<]*)(?:</[^>]+>)*</(?:td|th)>', r_html, re.IGNORECASE)
            row = {k: v.strip() for k, v in cells if k}
            if row and row.get("player") not in ("", "League Average", "Totals", "Tm") and "Name" not in row.get("player", ""):
                print("Fila:", row)
                count += 1
                if count >= 5:
                    break
    else:
        print(f"No se encontró '{target_table_id}'")
except Exception as e:
    print(f"Error: {e}")
