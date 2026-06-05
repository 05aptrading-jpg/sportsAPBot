import requests
from datetime import datetime, timedelta

def get_team_recent_bullpen_pitches(team_name: str, target_date_str: str) -> int:
    # 1. Encontrar el teamId del equipo
    # Hacemos una llamada rápida a MLB Stats API para buscar el equipo
    teams_url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    r = requests.get(teams_url, timeout=10)
    teams_data = r.json()
    
    team_id = None
    for t in teams_data.get("teams", []):
        if team_name.lower() in t.get("name", "").lower():
            team_id = t.get("id")
            break
            
    if not team_id:
        print(f"Equipo {team_name} no encontrado.")
        return 0
        
    print(f"Team ID para {team_name}: {team_id}")
    
    # 2. Obtener partidos de los últimos 3 días (72h antes del partido)
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    date_3d_ago = (target_dt - timedelta(days=3)).strftime("%Y-%m-%d")
    date_1d_ago = (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"Buscando partidos para {team_name} entre {date_3d_ago} y {date_1d_ago}...")
    
    schedule_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={date_3d_ago}&endDate={date_1d_ago}&teamId={team_id}"
    r = requests.get(schedule_url, timeout=10)
    schedule_data = r.json()
    
    game_pks = []
    for date_obj in schedule_data.get("dates", []):
        for game in date_obj.get("games", []):
            # Solo partidos finalizados o en juego que tengan data
            status = game.get("status", {}).get("abstractGameState", "")
            if status in ("Final", "Live"):
                game_pks.append(game.get("gamePk"))
                
    print(f"Partidos encontrados (gamePks): {game_pks}")
    
    # 3. Para cada partido, obtener el boxscore y sumar los pitches de los relevistas
    total_pitches = 0
    for gpk in game_pks:
        boxscore_url = f"https://statsapi.mlb.com/api/v1/game/{gpk}/boxscore"
        r = requests.get(boxscore_url, timeout=10)
        box_data = r.json()
        
        teams = box_data.get("teams", {})
        # Determinar si el equipo era local o visitante
        away_team_id = teams.get("away", {}).get("team", {}).get("id")
        home_team_id = teams.get("home", {}).get("team", {}).get("id")
        
        if away_team_id == team_id:
            role_key = "away"
        elif home_team_id == team_id:
            role_key = "home"
        else:
            continue
            
        pitchers = teams.get(role_key, {}).get("pitchers", [])
        players = teams.get(role_key, {}).get("players", {})
        
        # En el bullpen del cerrador + setup (los relevistas que pitchearon)
        for pid in pitchers:
            player_key = f"ID{pid}"
            player_stats = players.get(player_key, {}).get("stats", {}).get("pitching", {})
            
            gs = player_stats.get("gamesStarted", 0)
            if gs == 0:  # Es relevista
                pitches = player_stats.get("pitchesThrown", 0)
                player_name = players.get(player_key, {}).get("person", {}).get("fullName")
                print(f"  - Partido {gpk} | Relevista {player_name} lanzó {pitches} pitcheos")
                total_pitches += pitches
                
    return total_pitches

# Probar con los Dodgers en la fecha de la primera fila del CSV (2026-05-24)
dodgers_pitches = get_team_recent_bullpen_pitches("Los Angeles Dodgers", "2026-05-24")
print(f"\nTotal pitcheos del bullpen de los Dodgers en las últimas 72h: {dodgers_pitches}")
