import csv
import json
import os
from datetime import datetime, date, timedelta

import config

try:
    import requests
except ImportError:
    requests = None

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

# Output dirs - GitHub Pages root is 1 level up from futbol_bot/
MLB_BOT_DIR = os.path.normpath(os.path.join(config.BASE_DIR, ".."))


def _fetch_mundial_fixtures():
    """Fetch World Cup 2026 fixtures from ESPN for the next 10 days."""
    if not requests:
        return []
    hoy = date.today()
    mundial_start = date(2026, 6, 11)
    fetch_from = max(hoy, mundial_start)
    games = []
    for delta in range(0, 10):
        fetch_date = fetch_from + timedelta(days=delta)
        ds = fetch_date.strftime("%Y%m%d")
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={ds}"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if r.status_code != 200:
                continue
            for ev in r.json().get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                competitors = comp.get("competitors", [])
                home = next((c for c in competitors if c.get("homeAway") == "home"), {})
                away = next((c for c in competitors if c.get("homeAway") == "away"), {})
                h_name = home.get("team", {}).get("displayName", "")
                a_name = away.get("team", {}).get("displayName", "")
                if not h_name or not a_name:
                    continue
                ev_date = ev.get("date", "")[:10]
                ev_time = ev.get("date", "")[11:16]
                status = comp.get("status", {}).get("type", {}).get("name", "")
                is_live = status == "STATUS_IN_PROGRESS"
                is_final = status == "STATUS_FINAL"
                home_score = home.get("score", "")
                away_score = away.get("score", "")
                if is_final and home_score and away_score:
                    resultado_ah0 = "acertado" if int(home_score) > int(away_score) else "fallido"
                elif is_live or (home_score and away_score):
                    resultado_ah0 = "en_vivo" if is_live else "pendiente"
                else:
                    resultado_ah0 = "pendiente"
                games.append({
                    "liga": "🌍 FIFA World Cup 2026",
                    "liga_key": "MUNDIAL",
                    "local": h_name,
                    "visitante": a_name,
                    "xg_local": 1.3,
                    "xg_visit": 1.3,
                    "xg_total": 2.6,
                    "diff_xg": 0.0,
                    "favorito": "",
                    "senal_ah0": "NO_APOSTAR",
                    "confianza_ah0": "BAJA",
                    "senal_ou25": "NO_APOSTAR",
                    "confianza_ou25": "BAJA",
                    "resultado_ah0": resultado_ah0,
                    "resultado_ou25": "pendiente",
                    "marcador_final": f"{home_score}-{away_score}" if home_score and away_score else "",
                    "fecha_partido": ev_date,
                    "hora_partido": ev_time,
                })
        except Exception:
            continue
    return games


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
    mundial_games = _fetch_mundial_fixtures()
    if mundial_games:
        data["games"].extend(mundial_games)
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
