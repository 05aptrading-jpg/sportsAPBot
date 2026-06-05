import sys
import os

sys.path.append(os.path.abspath('.'))
from api_client import savant

print("Fetching Savant leaderboard...")
data = savant.get_pitcher_leaderboard(2025)
if data:
    print(f"Total pitchers: {len(data.get('data', []))}")
    print("Primeros 10 lanzadores en Savant:")
    for p in data.get('data', [])[:10]:
        print(f"- Name: '{p.get('Name')}', player_id: {p.get('player_id')}")
        
    print("\nBuscando 'Mitch Keller'...")
    match = savant.find_pitcher(data, "Mitch Keller")
    print(f"Resultado para 'Mitch Keller': {match}")
else:
    print("No se pudo obtener el leaderboard.")
