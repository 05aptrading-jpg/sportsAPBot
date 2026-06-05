"""Reprocess existing CSV rows with new calcular_trigger and B-Ref splits."""
import csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyzer import calcular_trigger
from data_manager import CSV_COLUMNAS
from api_client import bref

def to_float(v):
    if not v: return 0.0
    v = str(v).replace('%', '').strip()
    try: return float(v)
    except: return 0.0

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apuestas.csv')
rows = []
with open(path, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

splits_cache = {}
for r in rows:
    fa = to_float(r.get('fip_away')); xa = to_float(r.get('xfip_away')); ka = to_float(r.get('kbb_away'))
    fh = to_float(r.get('fip_home')); xh = to_float(r.get('xfip_home')); kh = to_float(r.get('kbb_home'))
    wa = to_float(r.get('wrc_away')); wh = to_float(r.get('wrc_home'))
    liga = r.get('liga', 'MLB')
    s, n, usa_sp = calcular_trigger(
        fa, xa, ka, fh, xh, kh, wa, wh, liga,
        wrc_rhp_a=to_float(r.get('wrc_vs_rhp_away', 0)),
        wrc_lhp_a=to_float(r.get('wrc_vs_lhp_away', 0)),
        wrc_rhp_h=to_float(r.get('wrc_vs_rhp_home', 0)),
        wrc_lhp_h=to_float(r.get('wrc_vs_lhp_home', 0)),
        abridor_mano_a=r.get('abridor_mano_away', None),
        abridor_mano_h=r.get('abridor_mano_home', None),
    )
    r['senal_moneyline'] = s
    r['nivel_certidumbre'] = n

    for team_key, wrc_col in [('equipo_visitante', 'wrc_away'), ('equipo_local', 'wrc_home')]:
        for side in ['rhp', 'lhp']:
            col = f'wrc_vs_{side}_{"away" if team_key == "equipo_visitante" else "home"}'
            if col not in r or not r[col]:
                r[col] = r.get(wrc_col, '100')
        abr_col = f'abridor_mano_{"away" if team_key == "equipo_visitante" else "home"}'
        if abr_col not in r or not r[col]:
            r[abr_col] = 'N/D'

    if liga == 'MLB':
        for team_key, suffix in [('equipo_visitante', 'away'), ('equipo_local', 'home')]:
            team_name = r.get(team_key, '')
            if team_name and (r.get(f'wrc_vs_rhp_{suffix}') == r.get(f'wrc_{suffix}', '100')
                              or not r.get(f'wrc_vs_rhp_{suffix}')):
                if team_name not in splits_cache:
                    splits_cache[team_name] = bref.get_team_splits(team_name)
                sp = splits_cache[team_name]
                r[f'wrc_vs_rhp_{suffix}'] = str(sp.get('ops_vs_rhp', 100.0))
                r[f'wrc_vs_lhp_{suffix}'] = str(sp.get('ops_vs_lhp', 100.0))

with open(path, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=CSV_COLUMNAS)
    w.writeheader()
    for r in rows:
        out = {}
        for col in CSV_COLUMNAS:
            out[col] = r.get(col, '')
        w.writerow(out)

print(f'Reprocesados {len(rows)} juegos con nueva logica trigger OK')
if splits_cache:
    print(f'Splits B-Ref cargados para: {", ".join(sorted(splits_cache.keys()))}')

from data_manager import obtener_estadisticas
stats = obtener_estadisticas()
print(f'Total: {stats["total"]} | WR: {stats["win_rate"]}%')
