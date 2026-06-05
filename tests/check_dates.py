import sys
sys.stdout.reconfigure(encoding='utf-8')
import api_client

data = api_client.mlb.get_schedule()
games = []
for d in data.get("dates", []):
    for g in d.get("games", []):
        games.append(g)

print(f"Total juegos en schedule: {len(games)}\n")
for g in games:
    gdate = g.get("gameDate", "?")
    status = g.get("status", {}).get("detailedState", "?")
    away = g.get("teams", {}).get("away", {}).get("team", {}).get("name", "?")
    home = g.get("teams", {}).get("home", {}).get("team", {}).get("name", "?")
    print(f"  {gdate}  [{status}]  {away} @ {home}")
