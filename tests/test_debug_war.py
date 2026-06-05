import sys
import os
sys.path.append(os.path.abspath('.'))
from api_client import bref
import logging

logging.basicConfig(level=logging.DEBUG)

for team in ["Los Angeles Dodgers", "New York Yankees", "Houston Astros"]:
    print(f"\nTesting {team}:")
    pitches = bref.get_bullpen_pitcheos_72h(team)
    print(f"Total pitches: {pitches}")

