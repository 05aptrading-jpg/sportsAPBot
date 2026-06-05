import requests
from datetime import date

ESPN_LEAGUES = {
    "PREMIER_LEAGUE": "eng.1",
    "LA_LIGA": "esp.1",
    "BUNDESLIGA": "ger.1",
    "SERIE_A": "ita.1",
    "LIGUE_1": "fra.1",
    "LIGA_MX": "mex.1",
}
hoy_str = date.today().strftime("%Y%m%d")
print(f"Buscando fixtures para {hoy_str}...")

for liga, slug in ESPN_LEAGUES.items():
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={hoy_str}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    events = r.json().get("events", [])
    print(f"  {liga} ({slug}): {len(events)} partidos")
    for ev in events[:2]:
        comp = (ev.get("competitions") or [{}])[0]
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        h = home.get("team", {}).get("displayName", "?")
        a = away.get("team", {}).get("displayName", "?")
        t = ev.get("date", "")[11:16]
        print(f"    {h} vs {a} ({t})")
