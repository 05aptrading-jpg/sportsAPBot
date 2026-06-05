import sys
import os
import re
import requests

sys.path.append(os.path.abspath('.'))
import config

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
    print(f"Status Code: {r.status_code}")
    html = r.text
    print(f"HTML length: {len(html)}")

    # Encontrar todas las IDs de las tablas
    table_ids = re.findall(r'<table[^>]+id="([^"]+)"', html)
    print("IDs de tablas encontradas directamente en HTML:")
    print(table_ids)

    # Buscar tablas dentro de comentarios (B-Ref oculta muchas tablas en comentarios para carga diferida)
    comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
    print(f"Encontrados {len(comments)} comentarios HTML.")
    commented_table_ids = []
    for c in comments:
        commented_ids = re.findall(r'<table[^>]+id="([^"]+)"', c)
        commented_table_ids.extend(commented_ids)
    print("IDs de tablas encontradas en comentarios:")
    print(commented_table_ids)

    # Verificar si 'reliever_pitching' está en algún lado
    if "reliever_pitching" in html:
        print("¡'reliever_pitching' encontrado en el HTML directo!")
    else:
        found_in_comment = False
        for i, c in enumerate(comments):
            if "reliever_pitching" in c:
                print(f"¡'reliever_pitching' encontrado en el comentario index {i}!")
                found_in_comment = True
                # Ver el contenido del comentario o parte de él
                print("Muestra del comentario:")
                print(c[:500])
                break
        if not found_in_comment:
            print("No se encontró 'reliever_pitching' en el HTML ni en comentarios.")

except Exception as e:
    print(f"Error fetching URL: {e}")
