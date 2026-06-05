import json, re, sys
sys.stdout.reconfigure(encoding='utf-8')
html = open("index.html", "r", encoding="utf-8").read()
m = re.search(r"const DATA = ({.*?});\s*$", html, re.MULTILINE | re.DOTALL)
d = json.loads(m.group(1))
lmb = [g for g in d["games"] if g.get("liga") == "LMB" and g.get("game_date") == "2026-05-31"]
for g in lmb:
    print(f"  result={g.get('result','?'):10s} state={g.get('state','?'):15s} emoji={g.get('status_emoji','?')} {g.get('fav_team','')} vs {g.get('opp_team','')}")
