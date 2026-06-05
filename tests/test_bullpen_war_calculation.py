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
        relievers = []
        starters = []
        for r_html in rows:
            cells = re.findall(r'<(?:td|th)[^>]+data-stat="([^"]+)"[^>]*>(.*?)</(?:td|th)>', r_html, re.DOTALL | re.IGNORECASE)
            row = {}
            for k, v in cells:
                clean_val = re.sub(r'<[^>]+>', '', v).strip()
                row[k] = clean_val
            
            player_name = row.get("name_display")
            if not player_name or player_name in ("Player", "League Average", "Totals", "Tm") or "Name" in player_name:
                continue
                
            try:
                g = int(row.get("p_g", 0))
                gs = int(row.get("p_gs", 0))
                war = float(row.get("p_war", 0.0))
                
                # Criterio para relevista: gs es 0 o gs es menor al 10% de g
                if gs < 3 or (gs / g < 0.1):
                    relievers.append((player_name, g, gs, war))
                else:
                    starters.append((player_name, g, gs, war))
            except ValueError:
                continue
        
        print("\n--- RELEVISTAS ENCONTRADOS ---")
        total_reliever_war = 0.0
        for name, g, gs, war in relievers:
            print(f"{name}: G={g}, GS={gs}, WAR={war}")
            total_reliever_war += war
            
        print("\n--- ABRIDORES ENCONTRADOS ---")
        total_starter_war = 0.0
        for name, g, gs, war in starters:
            print(f"{name}: G={g}, GS={gs}, WAR={war}")
            total_starter_war += war
            
        print(f"\nWAR Bullpen Dodgers (Calculado): {total_reliever_war:.2f}")
        print(f"WAR Abridores Dodgers (Calculado): {total_starter_war:.2f}")
        print(f"WAR Pitcheo Total (Suma): {total_reliever_war + total_starter_war:.2f}")
except Exception as e:
    print(f"Error: {e}")
