import requests, sys, os
sys.path.insert(0, r'D:\Apuestas\mlb_bot')
import config

token = getattr(config, 'GITHUB_TOKEN', '')
if not token:
    print('No GITHUB_TOKEN')
    exit(1)

headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
api = 'https://api.github.com/repos/05aptrading-jpg/ApuestasMLB'

# Check current Pages
r2 = requests.get(f'{api}/pages', headers=headers)
print(f'Pages GET: {r2.status_code}')
if r2.status_code == 200:
    info = r2.json()
    print(f'  URL: {info.get("html_url", "?")}')
    print(f'  source: {info.get("source", {})}')
else:
    print(f'  {r2.text[:200]}')

# Enable Pages
r = requests.post(f'{api}/pages', json={'source': {'branch': 'main', 'path': '/'}}, headers=headers)
print(f'Pages POST: {r.status_code}')
if r.status_code in (200, 201, 204, 409):
    print('OK or already enabled')
else:
    print(r.text[:300])
