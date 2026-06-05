import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import pandas as pd
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


@dataclass
class TeamSoccerStats:
    team_name: str
    liga: str
    xg_for_90: float = 0.0
    xg_against_90: float = 0.0
    goles_reales_90: float = 0.0
    ppda: float = 15.0
    final_third_entries: float = 0.0
    bajas_clave: int = 0
    forma_reciente: list = field(default_factory=list)
    xg_last5: list = field(default_factory=list)
    xga_last5: list = field(default_factory=list)
    ppda_last5: list = field(default_factory=list)


@dataclass
class SoccerMatch:
    id_partido: int
    liga: str
    local: TeamSoccerStats
    visitante: TeamSoccerStats
    factor_localia: float = config.FACTOR_LOCALIA
    fecha_partido: str = ""
    hora_partido: str = ""


@dataclass
class MatchAnalysis:
    id_partido: int
    liga: str
    equipo_local: str
    equipo_visitante: str
    proyeccion_local: float
    proyeccion_visitante: float
    xg_total: float
    diff_xg: float
    senal_ah0: str
    confianza_ah0: str
    senal_ou25: str
    confianza_ou25: str
    fecha_partido: str = ""
    hora_partido: str = ""


def _rolling_avg(values: list, n: int = None) -> float:
    if not values:
        return 0.0
    if n is None:
        n = config.PARTIDOS_RECIENTES
    subset = values[-n:]
    return round(sum(subset) / len(subset), 2)


def calcular_score_volatilidad(local: TeamSoccerStats, visitante: TeamSoccerStats) -> float:
    avg_xg_local = _rolling_avg(local.xg_last5) if local.xg_last5 else local.xg_for_90
    avg_xg_visit = _rolling_avg(visitante.xg_last5) if visitante.xg_last5 else visitante.xg_for_90
    prom_xg = (avg_xg_local + avg_xg_visit) / 2
    avg_ppda = _rolling_avg(local.ppda_last5 + visitante.ppda_last5) if (local.ppda_last5 or visitante.ppda_last5) else (local.ppda + visitante.ppda) / 2
    factor_ppda = avg_ppda / 15.0
    sv = prom_xg * (1 + factor_ppda)
    return round(sv, 2)


def analizar_partido_soccer(match: SoccerMatch) -> MatchAnalysis:
    home_xg_list = match.local.xg_last5 if match.local.xg_last5 else []
    home_xga_list = match.local.xga_last5 if match.local.xga_last5 else []
    away_xg_list = match.visitante.xg_last5 if match.visitante.xg_last5 else []
    away_xga_list = match.visitante.xga_last5 if match.visitante.xga_last5 else []

    if home_xg_list and away_xga_list:
        avg_home_attack = _rolling_avg(home_xg_list)
        avg_away_defense = _rolling_avg(away_xga_list)
        exp_goals_home_raw = (avg_home_attack + avg_away_defense) / 2
    else:
        exp_goals_home_raw = (match.local.xg_for_90 + match.visitante.xg_against_90) / 2

    if away_xg_list and home_xga_list:
        avg_away_attack = _rolling_avg(away_xg_list)
        avg_home_defense = _rolling_avg(home_xga_list)
        exp_goals_away_raw = (avg_away_attack + avg_home_defense) / 2
    else:
        exp_goals_away_raw = (match.visitante.xg_for_90 + match.local.xg_against_90) / 2

    exp_goals_home = exp_goals_home_raw + match.factor_localia
    exp_goals_away = exp_goals_away_raw

    home_ppda_list = match.local.ppda_last5 if match.local.ppda_last5 else []
    away_ppda_list = match.visitante.ppda_last5 if match.visitante.ppda_last5 else []
    avg_home_ppda = _rolling_avg(home_ppda_list) if home_ppda_list else match.local.ppda
    avg_away_ppda = _rolling_avg(away_ppda_list) if away_ppda_list else match.visitante.ppda

    if avg_away_ppda < config.PPDA_BAJO:
        exp_goals_away += 0.15
    if avg_home_ppda > config.PPDA_ALTO:
        exp_goals_home -= 0.10

    if match.visitante.goles_reales_90 > match.visitante.xg_for_90 * config.REGRESION_UMBRAL:
        exp_goals_away -= 0.10
    if match.local.goles_reales_90 > match.local.xg_for_90 * config.REGRESION_UMBRAL:
        exp_goals_home -= 0.10

    exp_goals_away -= match.visitante.bajas_clave * config.PENALIZACION_BAJA
    exp_goals_home -= match.local.bajas_clave * config.PENALIZACION_BAJA

    exp_goals_away = max(0.1, round(exp_goals_away, 2))
    exp_goals_home = max(0.1, round(exp_goals_home, 2))

    diff_xg = exp_goals_home - exp_goals_away
    xg_total = exp_goals_home + exp_goals_away

    sv = calcular_score_volatilidad(match.local, match.visitante)

    senal_ah0 = "NO_APOSTAR"
    confianza_ah0 = "BAJA"
    if diff_xg >= config.XG_DIFF_MINIMA:
        senal_ah0 = f"AH0 - {match.local.team_name}"
        confianza_ah0 = "ALTA" if diff_xg >= config.XG_DIFF_ALTA else "MEDIA"
    elif diff_xg <= -config.XG_DIFF_MINIMA:
        senal_ah0 = f"AH0 - {match.visitante.team_name}"
        confianza_ah0 = "ALTA" if diff_xg <= -config.XG_DIFF_ALTA else "MEDIA"

    if sv > config.SV_ALTO_UMBRAL and confianza_ah0 == "ALTA":
        confianza_ah0 = "MEDIA"
        logger.debug(f"SV alto ({sv}) redujo confianza AH0 a MEDIA")

    senal_ou25 = "NO_APOSTAR"
    confianza_ou25 = "BAJA"
    if xg_total >= config.UMBRAL_OVER_25:
        senal_ou25 = "Over 2.5"
        confianza_ou25 = "ALTA" if xg_total >= config.UMBRAL_OVER_ALTA else "MEDIA"
    elif xg_total <= config.UMBRAL_UNDER_25:
        senal_ou25 = "Under 2.5"
        confianza_ou25 = "ALTA" if xg_total <= config.UMBRAL_UNDER_ALTA else "MEDIA"

    if sv >= config.SV_OVER_UMBRAL and senal_ou25 == "Over 2.5":
        confianza_ou25 = "ALTA"
        logger.debug(f"SV ({sv}) confirmó Over 2.5 ALTA")
    elif sv > config.SV_ALTO_UMBRAL and confianza_ou25 == "ALTA":
        confianza_ou25 = "MEDIA"
        logger.debug(f"SV alto ({sv}) redujo confianza O/U a MEDIA")

    logger.info(f"SV={sv} | xG_home={exp_goals_home} xG_away={exp_goals_away} | AH0={senal_ah0} O/U={senal_ou25}")

    return MatchAnalysis(
        id_partido=match.id_partido,
        liga=match.liga,
        equipo_local=match.local.team_name,
        equipo_visitante=match.visitante.team_name,
        proyeccion_local=exp_goals_home,
        proyeccion_visitante=exp_goals_away,
        xg_total=round(xg_total, 2),
        diff_xg=round(diff_xg, 2),
        senal_ah0=senal_ah0,
        confianza_ah0=confianza_ah0,
        senal_ou25=senal_ou25,
        confianza_ou25=confianza_ou25,
        fecha_partido=match.fecha_partido,
        hora_partido=match.hora_partido,
    )


def _norm(name: str) -> str:
    if not name:
        return ""
    import re
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _fuzzy_in(name_a: str, name_b: str) -> bool:
    a = _norm(name_a)
    b = _norm(name_b)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    aw = set(a.split())
    bw = set(b.split())
    overlap = aw & bw
    return len(overlap) >= min(len(aw), len(bw)) and len(overlap) >= 2


def fetch_fixtures_dia() -> dict:
    """
    Consulta ESPN para obtener fixtures reales de hoy.
    Retorna dict: { (liga, local_norm, visitante_norm): { home_name, away_name, date, time } }
    """
    from datetime import date as _date
    hoy_str = _date.today().strftime("%Y%m%d")
    fixtures = {}
    for liga_key, slug in ESPN_LEAGUES.items():
        try:
            url = ESPN_URL.format(slug=slug) + f"?dates={hoy_str}"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
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
                fixtures[(liga_key, _norm(a_name), _norm(h_name))] = {
                    "home_name": h_name,
                    "away_name": a_name,
                    "date": ev_date,
                    "time": ev_time,
                }
        except Exception as e:
            logger.warning(f"Error fetching fixtures {liga_key}: {e}")
    return fixtures


def generar_partidos_desde_cache(df_stats: pd.DataFrame) -> list[SoccerMatch]:
    """
    Genera partidos SOLO para fixtures reales de ESPN.
    Si ESPN no tiene fixtures para hoy, retorna lista vacía.
    """
    hoy = date.today().isoformat()
    fixtures = fetch_fixtures_dia()
    if not fixtures:
        logger.info("Sin fixtures reales en ESPN para hoy")
        return []

    partidos = []
    for liga_name in config.SOCCER_LEAGUES_V1:
        df_liga = df_stats[df_stats["liga"] == liga_name]
        if df_liga.empty:
            continue
        equipos = df_liga["equipo"].tolist()

        for (fk_liga, fk_away, fk_home), fixture_info in fixtures.items():
            if fk_liga != liga_name:
                continue

            if fixture_info["date"] != hoy:
                logger.debug(f"Fixture fecha {fixture_info['date']} ≠ hoy {hoy}, saltando")
                continue

            local_row = None
            visit_row = None
            for eq in equipos:
                if _fuzzy_in(eq, fixture_info["home_name"]):
                    local_row = df_liga[df_liga["equipo"] == eq].iloc[0]
                if _fuzzy_in(eq, fixture_info["away_name"]):
                    visit_row = df_liga[df_liga["equipo"] == eq].iloc[0]

            if local_row is None or visit_row is None:
                logger.debug(f"Fixture sin stats: {fixture_info['away_name']} vs {fixture_info['home_name']}")
                continue

            local_name = local_row["equipo"]
            visit_name = visit_row["equipo"]

            local = TeamSoccerStats(
                team_name=local_name,
                liga=liga_name,
                xg_for_90=float(local_row["xg_por_90"]),
                xg_against_90=float(local_row["xga_por_90"]),
                goles_reales_90=float(local_row["goles_reales_90"]),
                ppda=float(local_row.get("ppda", 15.0)),
                final_third_entries=float(local_row.get("final_third_por_90", 0.0)),
                xg_last5=local_row.get("xg_last5", []),
                xga_last5=local_row.get("xga_last5", []),
                ppda_last5=local_row.get("ppda_last5", []),
            )
            visit = TeamSoccerStats(
                team_name=visit_name,
                liga=liga_name,
                xg_for_90=float(visit_row["xg_por_90"]),
                xg_against_90=float(visit_row["xga_por_90"]),
                goles_reales_90=float(visit_row["goles_reales_90"]),
                ppda=float(visit_row.get("ppda", 15.0)),
                final_third_entries=float(visit_row.get("final_third_por_90", 0.0)),
                xg_last5=visit_row.get("xg_last5", []),
                xga_last5=visit_row.get("xga_last5", []),
                ppda_last5=visit_row.get("ppda_last5", []),
            )
            pk = dm.game_pk(liga_name, local_name, visit_name, hoy)
            match = SoccerMatch(
                id_partido=pk,
                liga=liga_name,
                local=local,
                visitante=visit,
            )
            match.fecha_partido = fixture_info["date"]
            match.hora_partido = fixture_info["time"]
            partidos.append(match)

    logger.info(f"Fixtures reales encontrados: {len(partidos)}")
    return partidos
