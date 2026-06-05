"""Test script to verify the MLB bot fixes are working correctly."""
import sys
import os
sys.path.append(os.path.abspath('.'))

import config
from api_client import bref, mlb

print("=" * 60)
print("TEST 1: Team Pitching Stats (WAR from value-pitching)")
print("=" * 60)
pitching = bref.get_team_pitching_stats()
if pitching:
    data = pitching.get("data", [])
    print(f"Total equipos: {len(data)}")
    # Show first 5 teams with WAR values
    war_teams = [(d["Team"], d["WAR"], d["ERA"], d.get("FIP", "N/A")) for d in data[:10]]
    print(f"{'Equipo':<25} {'WAR':>6} {'ERA':>6} {'FIP':>6}")
    print("-" * 50)
    for t, w, e, f in war_teams:
        print(f"{t:<25} {w:>6.2f} {e:>6.2f} {str(f):>6}")
    
    # Check if WAR values are non-zero
    non_zero = sum(1 for d in data if d["WAR"] != 0.0)
    print(f"\nEquipos con WAR != 0: {non_zero}/{len(data)}")
else:
    print("ERROR: No pitching data returned!")

print("\n" + "=" * 60)
print("TEST 2: Bullpen Pitcheos 72h (MLB Stats API)")
print("=" * 60)
for team in ["Los Angeles Dodgers", "New York Yankees", "Houston Astros"]:
    pitcheos = bref.get_bullpen_pitcheos_72h(team)
    print(f"  {team}: {pitcheos} pitcheos en 72h")

print("\n" + "=" * 60)
print("TEST 3: Bullpen WAR individual (players_value_pitching)")
print("=" * 60)
for team in ["Los Angeles Dodgers", "New York Yankees"]:
    war = bref.get_bullpen_war(team)
    print(f"  {team}: WAR bullpen = {war:.2f}")

print("\n" + "=" * 60)
print("TEST 4: Park Factors")
print("=" * 60)
batting = bref.get_team_batting_stats()
if batting:
    data = batting.get("data", [])
    pf_teams = [(d["Team"], d["ParkFactor"]) for d in data]
    pf_teams.sort(key=lambda x: x[1], reverse=True)
    print(f"{'Equipo':<25} {'ParkFactor':>10}")
    print("-" * 40)
    for t, pf in pf_teams[:10]:
        marker = " <<<" if pf > 104 or pf < 96 else ""
        print(f"{t:<25} {pf:>10.0f}{marker}")
    print("...")
    for t, pf in pf_teams[-5:]:
        marker = " <<<" if pf > 104 or pf < 96 else ""
        print(f"{t:<25} {pf:>10.0f}{marker}")
    
    non_100 = sum(1 for d in data if d["ParkFactor"] != 100.0)
    print(f"\nEquipos con PF != 100: {non_100}/{len(data)}")
else:
    print("ERROR: No batting data returned!")

print("\n✅ All tests complete!")
