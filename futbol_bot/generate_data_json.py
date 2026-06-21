import csv
import json
import math
import os
from datetime import datetime, date, timedelta

import config

try:
    import requests
except ImportError:
    requests = None

def _sanitize_nan(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj

LIGA_LABELS = {
    "PREMIER_LEAGUE": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
    "LA_LIGA": "🇪🇸 La Liga",
    "BUNDESLIGA": "🇩🇪 Bundesliga",
    "SERIE_A": "🇮🇹 Serie A",
    "LIGUE_1": "🇫🇷 Ligue 1",
    "LIGA_MX": "🇲🇽 Liga MX",
    "MLS": "🇺🇸 MLS",
    "BRASILEIRAO": "🇧🇷 Brasileirao",
    "EREDIVISIE": "🇳🇱 Eredivisie",
    "PRIMEIRA_LIGA": "🇵🇹 Primeira Liga",
    "SUPER_LIG": "🇹🇷 Süper Lig",
    "CHAMPIONSHIP": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Championship",
    "PRIMERA_DIVISION_ARG": "🇦🇷 Liga Profesional",
    "MUNDIAL": "🌍 FIFA World Cup 2026",
    "AMISTOSOS_INT": "🏳️ Amistosos Internacionales",
}

TEAM_TRANSLATIONS = {
    "Netherlands": "Países Bajos",
    "Sweden": "Suecia",
    "Denmark": "Dinamarca",
    "Germany": "Alemania",
    "France": "Francia",
    "England": "Inglaterra",
    "Spain": "España",
    "Portugal": "Portugal",
    "Italy": "Italia",
    "Czechia": "Chequia",
    "Türkiye": "Turquía",
    "Curaçao": "Curazao",
    "Congo DR": "RD Congo",
    "Belgium": "Bélgica",
    "Switzerland": "Suiza",
    "Croatia": "Croacia",
    "Argentina": "Argentina",
    "Brazil": "Brasil",
    "Colombia": "Colombia",
    "Ecuador": "Ecuador",
    "Uruguay": "Uruguay",
    "Mexico": "México",
    "USA": "Estados Unidos",
    "United States": "Estados Unidos",
    "Canada": "Canadá",
    "Japan": "Japón",
    "South Korea": "Corea del Sur",
    "Australia": "Australia",
    "Morocco": "Marruecos",
    "Senegal": "Senegal",
    "Ghana": "Ghana",
    "Cameroon": "Camerún",
    "Tunisia": "Túnez",
    "Iran": "Irán",
    "Saudi Arabia": "Arabia Saudita",
    "Qatar": "Catar",
    "Serbia": "Serbia",
    "Poland": "Polonia",
    "Ukraine": "Ucrania",
    "Austria": "Austria",
    "Czech Republic": "Chequia",
    "Scotland": "Escocia",
    "Wales": "Gales",
    "Norway": "Noruega",
    "Ireland": "Irlanda",
    "Romania": "Rumanía",
    "Hungary": "Hungría",
    "Greece": "Grecia",
    "Algeria": "Argelia",
    "Nigeria": "Nigeria",
    "Ivory Coast": "Costa de Marfil",
    "Mali": "Malí",
    "Burkina Faso": "Burkina Faso",
    "DR Congo": "RD Congo",
    "South Africa": "Sudáfrica",
    "Paraguay": "Paraguay",
    "Peru": "Perú",
    "Chile": "Chile",
    "Bolivia": "Bolivia",
    "Venezuela": "Venezuela",
    "Honduras": "Honduras",
    "Costa Rica": "Costa Rica",
    "Panama": "Panamá",
    "Jamaica": "Jamaica",
    "Trinidad and Tobago": "Trinidad y Tobago",
    "Haiti": "Haití",
    "Cuba": "Cuba",
    "El Salvador": "El Salvador",
    "Guatemala": "Guatemala",
    "New Zealand": "Nueva Zelanda",
    "China": "China",
    "India": "India",
    "Thailand": "Tailandia",
    "Vietnam": "Vietnam",
    "Iraq": "Irak",
    "Syria": "Siria",
    "Lebanon": "Líbano",
    "Jordan": "Jordania",
    "Saudi Arabia": "Arabia Saudita",
    "UAE": "Emiratos Árabes Unidos",
    "Oman": "Omán",
    "Bahrain": "Baréin",
    "Kuwait": "Kuwait",
    "Qatar": "Catar",
    "Australia": "Australia",
}

def _traducir_equipo(nombre: str) -> str:
    return TEAM_TRANSLATIONS.get(nombre, nombre)

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
                h_logo = home.get("team", {}).get("logo", "") or \
                         (home.get("team", {}).get("logos") or [{}])[0].get("href", "")
                a_logo = away.get("team", {}).get("logo", "") or \
                         (away.get("team", {}).get("logos") or [{}])[0].get("href", "")
                ev_raw = ev.get("date", "")
                # Convertir de UTC a hora local (Cd. Juárez UTC-6)
                LOCAL_OFFSET = -6
                try:
                    from datetime import timezone as _tz
                    dt_utc = datetime.fromisoformat(ev_raw.replace("Z", "+00:00"))
                    dt_local = dt_utc + timedelta(hours=LOCAL_OFFSET)
                    ev_date = dt_local.strftime("%Y-%m-%d")
                    ev_time = dt_local.strftime("%H:%M")
                except Exception:
                    ev_date = ev_raw[:10]
                    ev_time = ev_raw[11:16]
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
                    "local_logo": h_logo,
                    "visitante_logo": a_logo,
                    "xg_local": 0.0,
                    "xg_visit": 0.0,
                    "xg_total": 0.0,
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
    try:
        from futbol_bot import data_manager as dm
    except ImportError:
        import data_manager as dm
    rows = dm.cargar_partidos_xlsx()
    if not rows:
        return {}
    hoy = date.today()
    ayer = hoy - timedelta(days=1)
    manana = hoy + timedelta(days=1)
    fechas_validas = {hoy.isoformat(), ayer.isoformat(), manana.isoformat()}
    mundial_start = date(2026, 6, 11)
    mundial_end = date(2026, 7, 19)
    d = mundial_start
    while d <= mundial_end:
        fechas_validas.add(d.isoformat())
        d += timedelta(days=1)
    output = []
    for row in rows:
        fecha_partido = row.get("fecha_partido", "")
        if fecha_partido and fecha_partido not in fechas_validas:
            continue
        liga_label = LIGA_LABELS.get(row["liga"], row["liga"])
        favorito = ""
        ah0 = row.get("senal_ah0", "NO_APOSTAR")
        if ah0 and ah0 != "NO_APOSTAR":
            favorito = ah0.replace("AH0 - ", "")
        def _f(v, default=0.0):
            try:
                return float(v) if v else default
            except (ValueError, TypeError):
                return default
        output.append({
            "liga": liga_label,
            "liga_key": row["liga"],
            "local": row["local"],
            "visitante": row["visitante"],
            "local_logo": "",
            "visitante_logo": "",
            "xg_local": _f(row.get("xg_local")),
            "xg_visit": _f(row.get("xg_visit")),
            "xg_total": _f(row.get("xg_total")),
            "diff_xg": _f(row.get("diff_xg")),
            "xcorner_total": _f(row.get("xcorner_total")),
            "favorito": row.get("llm_favorito", "") or (ah0.replace("AH0 - ", "") if ah0 and ah0 != "NO_APOSTAR" else ""),
            "senal_ah0": row.get("senal_ah0", ""),
            "confianza_ah0": row.get("confianza_ah0", ""),
            "senal_ou25": row.get("senal_ou25", ""),
            "confianza_ou25": row.get("confianza_ou25", ""),
            "senal_corners": row.get("senal_corners", ""),
            "confianza_corners": row.get("confianza_corners", ""),
            "resultado": row.get("resultado", ""),
            "resultado_ah0": row.get("resultado_ah0", ""),
            "resultado_ou25": row.get("resultado_ou25", ""),
            "resultado_corners": row.get("resultado_corners", ""),
            "marcador_final": row.get("marcador_final", ""),
            "fecha_partido": row.get("fecha_partido", ""),
            "hora_partido": row.get("hora_partido", ""),
            "id_partido": row.get("id_partido", ""),
            "llm_favorito": row.get("llm_favorito", ""),
            "llm_ir_favorito": row.get("llm_ir_favorito", ""),
            "llm_goles": row.get("llm_goles", ""),
            "llm_corners_est": row.get("llm_corners_est", ""),
            "llm_tiros_porteria": row.get("llm_tiros_porteria", ""),
            "llm_lineas": row.get("llm_lineas", ""),
            "llm_resultado": row.get("llm_resultado", ""),
            "llm_porque": row.get("llm_porque", ""),
            "llm_factores": row.get("llm_ah0", ""),
        })
    data = {
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "games": output,
        "stats": {},
    }
    mundial_games = _fetch_mundial_fixtures()
    if mundial_games:
        data["games"].extend(mundial_games)
        dm.guardar_mundial_csv(mundial_games)
    # Deduplicar por local+visitante (ignorar fecha para evitar duplicados UTC vs local)
    seen = {}
    for g in data["games"]:
        key = (g.get("local", ""), g.get("visitante", ""))
        if key not in seen:
            seen[key] = g
        else:
            existing = seen[key]
            if not existing.get("local_logo") and g.get("local_logo"):
                existing["local_logo"] = g["local_logo"]
            if not existing.get("visitante_logo") and g.get("visitante_logo"):
                existing["visitante_logo"] = g["visitante_logo"]
    unique_games = list(seen.values())
    data["games"] = unique_games
    for g in data["games"]:
        if g.get("liga_key") == "MUNDIAL":
            g["local"] = _traducir_equipo(g["local"])
            g["visitante"] = _traducir_equipo(g["visitante"])
    data["stats"] = dm.obtener_estadisticas_soccer()
    data = _sanitize_nan(data)
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
