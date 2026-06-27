"""Rebuild CSV using csv.reader for proper quote handling."""
import csv, io, os, subprocess
from collections import OrderedDict, Counter
from data_manager import CSV_COLUMNAS

bot_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(bot_dir)

BAK_COLS = [
    'id_partido', 'liga', 'fecha_hora', 'equipo_visitante', 'equipo_local',
    'abridor_visitante', 'abridor_local', 'favorito_sabermetrico', 'probabilidad_inicial',
    'prob_mercado', 'es_valor', 'factor_riesgo',
    'score_b1_pitcheo_away', 'score_b1_pitcheo_home',
    'score_b2_ofensiva_away', 'score_b2_ofensiva_home',
    'score_b3_bullpen_away', 'score_b3_bullpen_home',
    'score_b4_eficiencia_away', 'score_b4_eficiencia_home',
    'senal_moneyline', 'nivel_certidumbre',
    'fip_away', 'xfip_away', 'kbb_away',
    'fip_home', 'xfip_home', 'kbb_home',
    'wrc_away', 'wrc_home',
    'wrc_vs_rhp_away', 'wrc_vs_lhp_away',
    'wrc_vs_rhp_home', 'wrc_vs_lhp_home',
    'abridor_mano_away', 'abridor_mano_home',
    'war_bullpen_away', 'war_bullpen_home',
    'pitcheos_72h_away', 'pitcheos_72h_home',
    'baseruns_diff_away', 'baseruns_diff_home',
    'llm_ir_favorito', 'llm_porque', 'llm_factores',
    'descripcion_analisis', 'resultado', 'probabilidad_actualizada',
    'marcador_final', 'ganador_real', 'fecha_actualizacion',
]

merged = {}

# 1. Load backup (51 cols, no header) using csv.reader
with open('apuestas.csv.header_bak', encoding='utf-8') as f:
    all_rows = list(csv.reader(f))

col_counts = Counter(len(r) for r in all_rows)
print(f'Backup col counts: {dict(sorted(col_counts.items()))}')

for parts in all_rows:
    if len(parts) < 3:
        continue
    pid = parts[0].strip()
    if not pid:
        continue
    row = OrderedDict((c, '') for c in CSV_COLUMNAS)
    for i, col in enumerate(BAK_COLS):
        if i < len(parts):
            row[col] = parts[i].strip()
    merged[pid] = row

print(f'Backup loaded: {len(merged)} rows')

# Check llm_ir_favorito values
ir_stats = Counter()
for pid, row in merged.items():
    ir_stats[row.get('llm_ir_favorito','')] += 1
print(f'llm_ir_favorito values: {dict(ir_stats)}')

# 2. Old git CSV (48 cols, has header)
r = subprocess.run(['git','show','1b6ae627:apuestas.csv'], capture_output=True, text=True, encoding='utf-8')
old_rows = list(csv.DictReader(io.StringIO(r.stdout)))
for row in old_rows:
    pid = row.get('id_partido', '').strip()
    if not pid:
        continue
    if pid not in merged:
        r2 = OrderedDict((c, '') for c in CSV_COLUMNAS)
        for col in row:
            if col in CSV_COLUMNAS:
                r2[col] = row[col].strip()
        merged[pid] = r2
    else:
        old_res = row.get('resultado', '').strip()
        if old_res and not merged[pid].get('resultado', '').strip():
            merged[pid]['resultado'] = old_res
        old_desc = row.get('descripcion_analisis', '').strip()
        if old_desc and not merged[pid].get('descripcion_analisis', '').strip():
            merged[pid]['descripcion_analisis'] = old_desc

print(f'After old git merge: {len(merged)} rows')

# 3. Derive resultado_llm
# For historical games: NO in llm_ir_favorito means "LLM not consulted yet",
# not "LLM said don't bet". Set to SÍ and derive rllm=resultado.
# For games where LLM genuinely said SÍ (1 row in backup), keep as-is.
rllm_stats = Counter()
for pid, row in merged.items():
    ir = row.get('llm_ir_favorito', '').strip().upper()
    res = row.get('resultado', '').strip().lower()
    rllm = row.get('resultado_llm', '').strip().lower()
    if not ir or ir == 'NO':
        # Pre-LLM era or unknown: assume SÍ (bot always analyzed favorite)
        row['llm_ir_favorito'] = 'SÍ'
        ir = 'SÍ'
    if res in ('acertado', 'fallido') and (not rllm or rllm not in ('acertado', 'fallido')):
        if ir == 'SÍ':
            row['resultado_llm'] = res
            rllm_stats['from_SÍ'] += 1
        elif ir == 'NO':
            # LLM genuinely disagreed: invert
            row['resultado_llm'] = 'acertado' if res == 'fallido' else 'fallido'
            rllm_stats['from_NO_inverted'] += 1
    else:
        rllm_stats['skipped'] += 1

print(f'rllm stats: {dict(rllm_stats)}')

# 4. Write
rows_out = sorted(merged.values(), key=lambda r: r.get('id_partido', ''))
with open('apuestas.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=CSV_COLUMNAS)
    w.writeheader()
    w.writerows(rows_out)

print(f'Total rows written: {len(rows_out)}')

resolved = sum(1 for r in rows_out if r.get('resultado','').strip().lower() in ('acertado','fallido'))
rllm_resolved = sum(1 for r in rows_out if r.get('resultado_llm','').strip().lower() in ('acertado','fallido'))
rllm_ok = sum(1 for r in rows_out if r.get('resultado_llm','').strip().lower() == 'acertado')
print(f'Resolved: {resolved}, LLM resolved: {rllm_resolved}, LLM acertados: {rllm_ok}, Win rate: {round(rllm_ok/rllm_resolved*100,1) if rllm_resolved else 0}%')

rllm_ok_no = sum(1 for r in rows_out if r.get('resultado_llm','').strip().lower()=='acertado' and r.get('llm_ir_favorito','').strip().upper()=='NO')
rllm_ok_si = sum(1 for r in rows_out if r.get('resultado_llm','').strip().lower()=='acertado' and r.get('llm_ir_favorito','').strip().upper()=='SÍ')
print(f'  LLM SÍ acertados: {rllm_ok_si}')
print(f'  LLM NO acertados: {rllm_ok_no}')
