import csv
import json
import os
from datetime import datetime, date, timedelta

import config

LIGA_LABELS = {
    "PREMIER_LEAGUE": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
    "LA_LIGA": "🇪🇸 La Liga",
    "BUNDESLIGA": "🇩🇪 Bundesliga",
    "SERIE_A": "🇮🇹 Serie A",
    "LIGUE_1": "🇫🇷 Ligue 1",
    "LIGA_MX": "🇲🇽 Liga MX",
    "MLS": "🇺🇸 MLS",
    "BRASILEIRAO": "🇧🇷 Brasileirao",
    "PRIMERA_DIVISION_ARG": "🇦🇷 Liga Profesional",
    "LIGA_POSTOBON": "🇨🇴 Liga BetPlay",
    "PRIMERA_DIVISION_CHI": "🇨🇱 Primera División",
    "PRIMERA_DIVISION_PAR": "🇵🇾 Primera División",
    "PRIMERA_DIVISION_URU": "🇺🇾 Primera División",
    "EREDIVISIE": "🇳🇱 Eredivisie",
    "PRIMEIRA_LIGA": "🇵🇹 Primeira Liga",
    "SUPER_LIG": "🇹🇷 Süper Lig",
    "SUPER_LEAGUE_BEL": "🇧🇪 Pro League",
    "PREMIERSHIP": "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Premiership",
    "Serie B": "🇮🇹 Serie B",
    "CHAMPIONSHIP": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Championship",
    "BUNDESLIGA_2": "🇩🇪 2. Bundesliga",
    "LIGA_2": "🇪🇸 La Liga 2",
    "Ligue 2": "🇫🇷 Ligue 2",
    "MUNDIAL": "🌍 FIFA World Cup 2026",
    "AMISTOSOS_INT": "🏳️ Amistosos Internacionales",
    "BRASILEIRAO_B": "🇧🇷 Brasileirão Serie B",
    "LIGA_BOLIVIANA": "🇧🇴 Liga Profesional",
    "PRIMERA_DIVISION_CHILE": "🇨🇱 Primera División Chile",
    "LEAGUE_OF_IRELAND": "🇮🇪 League of Ireland",
    "COPA_LIBERTADORES": "🌎 Copa Libertadores",
    "COPA_SUDAMERICANA": "🌎 Copa Sudamericana",
    "CONCACAF_CHAMPIONS": "🏆 CONCACAF Champions",
    "CHAMPIONS_LEAGUE": "🏆 UEFA Champions League",
    "EUROPA_LEAGUE": "🏆 UEFA Europa League",
}

# Output dirs
MLB_BOT_DIR = os.path.normpath(os.path.join(config.BASE_DIR, "..", "mlb_bot"))


def generar_soccer_data_json():
    if not os.path.exists(config.CSV_SOCCER_PATH):
        return {}
    hoy = date.today()
    ayer = hoy - timedelta(days=1)
    manana = hoy + timedelta(days=1)
    fechas_validas = {hoy.isoformat(), ayer.isoformat(), manana.isoformat()}
    # Mundial 2026: incluir todo el torneo (jun 11 - jul 19)
    mundial_start = date(2026, 6, 11)
    mundial_end = date(2026, 7, 19)
    d = mundial_start
    while d <= mundial_end:
        fechas_validas.add(d.isoformat())
        d += timedelta(days=1)
    rows = []
    with open(config.CSV_SOCCER_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fecha_partido = row.get("fecha_partido", "")
            if fecha_partido and fecha_partido not in fechas_validas:
                continue
            liga_label = LIGA_LABELS.get(row["liga"], row["liga"])
            favorito = ""
            ah0 = row.get("senal_ah0", "NO_APOSTAR")
            if ah0 and ah0 != "NO_APOSTAR":
                favorito = ah0.replace("AH0 - ", "")
            rows.append({
                "liga": liga_label,
                "liga_key": row["liga"],
                "local": row["local"],
                "visitante": row["visitante"],
                "xg_local": float(row.get("xg_local", 0)),
                "xg_visit": float(row.get("xg_visit", 0)),
                "xg_total": float(row.get("xg_total", 0)),
                "diff_xg": float(row.get("diff_xg", 0)),
                "favorito": favorito,
                "senal_ah0": row.get("senal_ah0", "NO_APOSTAR"),
                "confianza_ah0": row.get("confianza_ah0", "BAJA"),
                "senal_ou25": row.get("senal_ou25", "NO_APOSTAR"),
                "confianza_ou25": row.get("confianza_ou25", "BAJA"),
                "resultado_ah0": row.get("resultado_ah0", "pendiente"),
                "resultado_ou25": row.get("resultado_ou25", "pendiente"),
                "marcador_final": row.get("marcador_final", ""),
                "fecha_partido": row.get("fecha_partido", ""),
                "hora_partido": row.get("hora_partido", ""),
            })
    data = {
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "games": rows,
        "stats": {},
    }
    from data_manager import obtener_estadisticas_soccer
    data["stats"] = obtener_estadisticas_soccer()
    # Write to futbol_bot/
    out = os.path.join(config.BASE_DIR, "soccer_data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Write to mlb_bot/ for GitHub Pages Mini App
    if os.path.isdir(MLB_BOT_DIR):
        out2 = os.path.join(MLB_BOT_DIR, "soccer_data.json")
        with open(out2, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return data


if __name__ == "__main__":
    d = generar_soccer_data_json()
    print(f"soccer_data.json generado: {len(d.get('games', []))} partidos")
