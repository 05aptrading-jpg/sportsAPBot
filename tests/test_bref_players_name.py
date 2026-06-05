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

try:
    r = requests.get(url, headers=headers, timeout=15)
    html = r.text
    
    target_table_id = "players_value_pitching"
    comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
    table_html = None
    for c in comments:
        if target_table_id in c:
            table_match = re.search(rf'<table[^>]+id="{target_table_id}"[^>]*>(.*?)</table>', c, re.DOTALL | re.IGNORECASE)
            if table_match:
                table_html = table_match.group(1)
                break

    if table_html:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        # Buscar la primera fila de datos reales y mostrar su HTML completo
        for r_html in rows[2:5]:
            print("--- FILA RAW HTML ---")
            print(r_html)
            
            # Intentar parsear las celdas de forma más robusta
            # Buscaremos celdas <td ... data-stat="col">...</td>
            cells = re.findall(r'<(?:td|th)[^>]+data-stat="([^"]+)"[^>]*>(.*?)</(?:td|th)>', r_html, re.DOTALL | re.IGNORECASE)
            print("Celdas parseadas con HTML interno:")
            row_dict = {}
            for k, v in cells:
                # Limpiar etiquetas HTML de los valores
                clean_val = re.sub(r'<[^>]+>', '', v).strip()
                row_dict[k] = clean_val
            print(row_dict)
            print()
except Exception as e:
    print(f"Error: {e}")
