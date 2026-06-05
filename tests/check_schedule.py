import sys
sys.stdout.reconfigure(encoding='utf-8')
import api_client
from datetime import date

today = date.today().strftime("%Y-%m-%d")
data = api_client.mlb.get_schedule()
if data:
    all_games = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            all_games.append(g)

    print(f"Total juegos en el schedule: {len(all_games)}")
    print(f"Fecha de hoy: {today}\n")
    for g in all_games:
        gdate = g.get("gameDate", "?")[:10]
        status = g.get("status", {}).get("detailedState", "?")
        away = g.get("teams", {}).get("away", {}).get("team", {}).get("name", "?")
        home = g.get("teams", {}).get("home", {}).get("team", {}).get("name", "?")
        marca = "<-- HOY" if gdate == today else f"<-- OTRA FECHA ({gdate})"
        print(f"  [{status}] {away} @ {home}  {marca}")
