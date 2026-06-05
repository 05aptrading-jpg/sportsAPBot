import requests
from datetime import date

hoy_str = date.today().strftime("%Y%m%d")
url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={hoy_str}"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
events = r.json().get("events", [])
ligas = {}
for ev in events:
    comp = (ev.get("competitions") or [{}])[0]
    league_name = comp.get("league", {}).get("slug", "?")
    league_display = comp.get("league", {}).get("name", "?")
    ligas.setdefault(league_display, {"slug": league_name, "count": 0})
    ligas[league_display]["count"] += 1

for name, info in sorted(ligas.items(), key=lambda x: -x[1]["count"]):
    print(f"  {info['slug']:20s} {name:40s} {info['count']} partidos")
