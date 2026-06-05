import requests
from datetime import date

# Check eng.1 without date filter
r = requests.get("https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard", 
                  headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
events = r.json().get("events", [])
print(f"Premier League: {len(events)} eventos")
for ev in events:
    d = ev.get("date", "")[:10]
    comp = (ev.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    h = home.get("team", {}).get("displayName", "?")
    a = away.get("team", {}).get("displayName", "?")
    status = comp.get("status", {}).get("type", {}).get("description", "?")
    print(f"  {d} {h} vs {a} [{status}]")

print()
# Also check mex.1
r2 = requests.get("https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard",
                   headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
events2 = r2.json().get("events", [])
print(f"Liga MX: {len(events2)} eventos")
for ev in events2[:5]:
    d = ev.get("date", "")[:10]
    comp = (ev.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    h = home.get("team", {}).get("displayName", "?")
    a = away.get("team", {}).get("displayName", "?")
    print(f"  {d} {h} vs {a}")
