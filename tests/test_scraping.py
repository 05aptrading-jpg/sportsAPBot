import sys
import os

# Añadir el directorio del bot al path
sys.path.append(os.path.abspath('.'))

import config
from api_client import bref, fg, savant

print("--- Probando get_team_pitching_stats ---")
pitching_stats = bref.get_team_pitching_stats(2025)
if pitching_stats:
    print(f"Total equipos: {len(pitching_stats.get('data', []))}")
    for team in pitching_stats.get('data', [])[:5]:
        print(team)
else:
    print("No se pudieron obtener estadísticas de pitcheo.")

print("\n--- Probando find_team con 'Los Angeles Dodgers' ---")
dodgers_pitching = bref.find_team(pitching_stats, "Los Angeles Dodgers")
print("Dodgers pitcheo:", dodgers_pitching)

print("\n--- Probando get_bullpen_pitcheos_72h ---")
try:
    pitcheos = bref.get_bullpen_pitcheos_72h("Los Angeles Dodgers")
    print(f"Pitcheos 72h Dodgers: {pitcheos}")
except Exception as e:
    print(f"Error get_bullpen_pitcheos_72h: {e}")

print("\n--- Probando get_bullpen_war ---")
try:
    war = bref.get_bullpen_war("Los Angeles Dodgers", 2025)
    print(f"WAR bullpen Dodgers: {war}")
except Exception as e:
    print(f"Error get_bullpen_war: {e}")
