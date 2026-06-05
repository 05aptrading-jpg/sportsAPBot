import sys
import os

sys.path.append(os.path.abspath('.'))
from api_client import savant

print("Fetching Savant batting leaderboard...")
data = savant.get_team_batting_leaderboard(2025)
if data:
    print(f"Total teams: {len(data.get('data', []))}")
    print("Primeros 5 equipos:")
    for t in data.get('data', [])[:5]:
        print(t)
else:
    print("No se pudo obtener el leaderboard de bateo.")
