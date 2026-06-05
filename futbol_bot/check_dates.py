import requests
from datetime import date, timedelta

for i in range(-3, 8):
    d = date.today() + timedelta(days=i)
    ds = d.strftime('%Y%m%d')
    url = f'https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}'
    r = requests.get(url, timeout=10)
    data = r.json()
    n = len(data.get('events', []))
    print(f'{d.isoformat()} ({d.strftime("%A")}): {n} partidos')
