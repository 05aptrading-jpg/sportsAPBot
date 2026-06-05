import requests
from datetime import datetime, timedelta

team_id = 119  # Dodgers
url_season = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&group=hitting"

print("Fetching season stats from MLB Stats API...")
try:
    r = requests.get(url_season, timeout=10)
    data = r.json()
    splits = data.get("stats", [{}])[0].get("splits", [])
    if splits:
        stat = splits[0].get("stat", {})
        ops_season = stat.get("ops")
        print(f"Season OPS: {ops_season} | AVG: {stat.get('avg')} | OBP: {stat.get('obp')} | SLG: {stat.get('slg')}")
except Exception as e:
    print(f"Error season: {e}")

# Últimos 7 días
hoy = datetime.now()
inicio = (hoy - timedelta(days=7)).strftime("%Y-%m-%d")
fin = hoy.strftime("%Y-%m-%d")
url_7d = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=byDateRange&group=hitting&startDate={inicio}&endDate={fin}"

print(f"\nFetching last 7 days stats ({inicio} to {fin})...")
try:
    r = requests.get(url_7d, timeout=10)
    data = r.json()
    splits = data.get("stats", [{}])[0].get("splits", [])
    if splits:
        stat = splits[0].get("stat", {})
        ops_7d = stat.get("ops")
        print(f"7-day OPS: {ops_7d} | AVG: {stat.get('avg')} | OBP: {stat.get('obp')} | SLG: {stat.get('slg')}")
    else:
        print("No se encontraron estadísticas para este rango de fechas (¿quizás no hay juegos en este periodo?).")
except Exception as e:
    print(f"Error 7d: {e}")
