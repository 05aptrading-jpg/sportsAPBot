import requests
from datetime import date

hoy_str = date.today().strftime("%Y%m%d")
# Try different URL patterns
tests = [
    ("eng.1", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={d}"),
    ("soccer/eng.1", "https://site.api.espn.com/apis/site/v2/sports/soccer/soccer.eng.1/scoreboard?dates={d}"),
    ("premierleague", "https://site.api.espn.com/apis/site/v2/sports/soccer/premierleague/scoreboard?dates={d}"),
    ("eng", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng/scoreboard?dates={d}"),
    # Liga MX
    ("mex.1", "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates={d}"),
    ("mex", "https://site.api.espn.com/apis/site/v2/sports/soccer/mex/scoreboard?dates={d}"),
    # Also try without dates to see what ESPN returns
    ("eng.1 no date", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"),
]

for name, tpl in tests:
    url = tpl.format(d=hoy_str)
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        events = r.json().get("events", [])
        print(f"  {name:25s} -> {len(events)} events (status {r.status_code})")
    except Exception as e:
        print(f"  {name:25s} -> ERROR: {e}")
