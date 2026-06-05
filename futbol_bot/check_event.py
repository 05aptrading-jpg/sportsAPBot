import requests, json
from datetime import date

hoy_str = date.today().strftime("%Y%m%d")
url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={hoy_str}"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
events = r.json().get("events", [])
for ev in events[:3]:
    comp = (ev.get("competitions") or [{}])[0]
    print(json.dumps({
        "name": ev.get("name"),
        "date": ev.get("date"),
        "league_slug": comp.get("league", {}).get("slug"),
        "league_name": comp.get("league", {}).get("name"),
        "season_slug": comp.get("season", {}).get("slug"),
        "type": comp.get("type", {}).get("slug"),
    }, indent=2))
    print("---")
