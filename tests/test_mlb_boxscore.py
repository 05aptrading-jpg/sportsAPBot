import requests
import json

game_pk = 823786  # Dodgers @ Brewers (2026-05-24)
url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"

print(f"Fetching boxscore for game {game_pk}...")
try:
    r = requests.get(url, timeout=10)
    print(f"Status Code: {r.status_code}")
    data = r.json()
    
    # Ver los pitchers del equipo visitante (Dodgers)
    teams = data.get("teams", {})
    away_pitchers = teams.get("away", {}).get("pitchers", [])
    away_players = teams.get("away", {}).get("players", {})
    
    print("\nDodgers Pitchers in this game:")
    # El primer pitcher en la lista suele ser el abridor, pero vamos a confirmarlo
    for pid in away_pitchers:
        player_key = f"ID{pid}"
        player = away_players.get(player_key, {})
        person = player.get("person", {})
        name = person.get("fullName")
        stats = player.get("stats", {}).get("pitching", {})
        
        # Un relevista es alguien que entró al juego pero no lo empezó (gamesStarted = 0)
        gs = stats.get("gamesStarted", 0)
        pitches = stats.get("pitchesThrown", 0)
        ip = stats.get("inningsPitched", "0.0")
        
        role = "Abridor" if gs > 0 else "Relevista"
        print(f"- {name} ({role}): IP={ip}, Pitches={pitches}")
        
except Exception as e:
    print(f"Error: {e}")
