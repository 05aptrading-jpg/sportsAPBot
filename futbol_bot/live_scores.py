"""
Live scores updater - fetches ESPN scores every 20 min,
updates CSV results, regenerates JSON, pushes to GitHub.
"""
import csv
import logging
import os
import re
from datetime import datetime, date

import requests

import config
import data_manager as dm

logger = logging.getLogger(__name__)

ESPN_LEAGUES = {
    "PREMIER_LEAGUE": "eng.1",
    "LA_LIGA": "esp.1",
    "BUNDESLIGA": "ger.1",
    "SERIE_A": "ita.1",
    "LIGUE_1": "fra.1",
    "LIGA_MX": "mex.1",
}

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"


def _norm(name: str) -> str:
    """Normaliza nombre para comparación fuzzy."""
    if not name:
        return ""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _fuzzy_match(espn_name: str, csv_name: str) -> bool:
    """Match flexible entre nombres de ESPN y CSV."""
    e = _norm(espn_name)
    c = _norm(csv_name)
    if not e or not c:
        return False
    if e == c:
        return True
    if e in c or c in e:
        return True
    e_words = set(e.split())
    c_words = set(c.split())
    if len(e_words & c_words) >= min(len(e_words), len(c_words)) and len(e_words & c_words) >= 2:
        return True
    return False


def _fetch_espn(slug: str) -> list:
    """Fetch scoreboard from ESPN for the current game window."""
    try:
        url = ESPN_URL.format(slug=slug)
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code != 200:
            logger.warning(f"ESPN {slug} returned {r.status_code}")
            return []
        events = r.json().get("events", [])
        for ev in events:
            ev["_liga_slug"] = slug
        return events
    except Exception as e:
        logger.error(f"ESPN fetch error ({slug}): {e}")
        return []


def _parse_espn_event(event: dict) -> list:
    """Parse ESPN event into list of match results. Returns list of dicts."""
    comp = (event.get("competitions") or [{}])[0]
    status = comp.get("status", {}).get("type", {})
    detail = status.get("detail", "")
    completed = status.get("completed", False)
    event_date = event.get("date", "")[:10]

    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})

    h_name = home.get("team", {}).get("displayName", "")
    a_name = away.get("team", {}).get("displayName", "")
    h_score = int(home.get("score", 0) or 0)
    a_score = int(away.get("score", 0) or 0)

    return [{
        "home_name": h_name,
        "away_name": a_name,
        "home_score": h_score,
        "away_score": a_score,
        "completed": completed,
        "detail": detail,
        "date": event_date,
        "liga_slug": event.get("_liga_slug", ""),
    }]


def _evaluar_ah0(senal_ah0: str, local_name: str, visit_name: str, h_score: int, a_score: int) -> str:
    if not senal_ah0 or senal_ah0 == "NO_APOSTAR":
        return "no_apostar"
    equipo = senal_ah0.replace("AH0 - ", "").strip()
    es_local = _fuzzy_match(equipo, local_name)
    es_visitante = _fuzzy_match(equipo, visit_name)
    if not es_local and not es_visitante:
        return "no_apostar"
    if h_score == a_score:
        return "devuelto"
    if es_local and h_score > a_score:
        return "acertado"
    if es_visitante and a_score > h_score:
        return "acertado"
    return "fallido"


def _evaluar_ou25(senal_ou25: str, h_score: int, a_score: int) -> str:
    if not senal_ou25 or senal_ou25 == "NO_APOSTAR":
        return "no_apostar"
    total = h_score + a_score
    if senal_ou25 == "Over 2.5":
        return "acertado" if total > 2 else "fallido"
    elif senal_ou25 == "Under 2.5":
        return "acertado" if total < 3 else "fallido"
    return "no_apostar"


def actualizar_resultados() -> dict:
    """
    Main updater. Called every 20 min.
    Returns dict with stats of what was updated.
    """
    today = date.today().isoformat()
    stats = {"updated": 0, "pending": 0, "completed": 0, "errors": 0}

    if not os.path.exists(config.CSV_SOCCER_PATH):
        logger.info("CSV no existe, saltando live scores")
        return stats

    csv_rows = []
    with open(config.CSV_SOCCER_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_rows.append(row)

    pending_rows = [r for r in csv_rows if r.get("resultado", "pendiente") == "pendiente"]
    if not pending_rows:
        logger.info("Sin partidos pendientes, live scores detenido")
        return stats

    pending_ligas = set(r.get("liga", "") for r in pending_rows)

    espn_matches = []
    for liga_key, slug in ESPN_LEAGUES.items():
        events = _fetch_espn(slug)
        for ev in events:
            espn_matches.extend(_parse_espn_event(ev))

    updates_applied = 0
    for row in pending_rows:
        csv_liga = row.get("liga", "")
        csv_local = row.get("local", "")
        csv_visit = row.get("visitante", "")
        csv_id = row.get("id_partido", "")

        espn_match = None
        csv_liga_slug = ESPN_LEAGUES.get(csv_liga, "")
        for em in espn_matches:
            if em.get("liga_slug") != csv_liga_slug:
                continue
            home_match = _fuzzy_match(em["home_name"], csv_local) and _fuzzy_match(em["away_name"], csv_visit)
            away_match = _fuzzy_match(em["home_name"], csv_visit) and _fuzzy_match(em["away_name"], csv_local)
            if home_match or away_match:
                espn_match = em
                break

        if not espn_match or not espn_match["completed"]:
            stats["pending"] += 1
            continue

        h_score = espn_match["home_score"]
        a_score = espn_match["away_score"]
        marcador = f"{h_score} - {a_score}."

        resultado_ah0 = _evaluar_ah0(
            row.get("senal_ah0", "NO_APOSTAR"),
            espn_match["home_name"], espn_match["away_name"],
            h_score, a_score,
        )
        resultado_ou25 = _evaluar_ou25(
            row.get("senal_ou25", "NO_APOSTAR"),
            h_score, a_score,
        )

        ok = dm.actualizar_resultados(csv_id, marcador, resultado_ah0, resultado_ou25)
        if ok:
            updates_applied += 1
            stats["updated"] += 1
            logger.info(f"  {csv_local} vs {csv_visit}: {marcador} -> AH0={resultado_ah0} O/U={resultado_ou25}")

    if updates_applied > 0:
        stats["completed"] = updates_applied
        from generate_data_json import generar_soccer_data_json
        generar_soccer_data_json()
        logger.info(f"Live scores: {updates_applied} partidos actualizados")

    return stats


def hay_partidos_pendientes_hoy() -> bool:
    """Check if there are any pending matches in the CSV."""
    if not os.path.exists(config.CSV_SOCCER_PATH):
        return False
    try:
        with open(config.CSV_SOCCER_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("resultado_ah0", "pendiente") == "pendiente":
                    return True
                if row.get("resultado_ou25", "pendiente") == "pendiente":
                    return True
    except Exception:
        pass
    return False
