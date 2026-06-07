import logging
import json

import pandas as pd
import requests

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://understat.com/",
    "X-Requested-With": "XMLHttpRequest",
}

ESPN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def extraer_stats_understat(league: str, season: int) -> pd.DataFrame:
    url = config.UNDERSTAT_API.format(league=league, season=season)
    n_rec = config.PARTIDOS_RECIENTES
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            logger.error(f"Understat HTTP {r.status_code} para {league}/{season}")
            return pd.DataFrame()
        data = r.json()
        teams = data.get("teams", {})
        if not teams:
            logger.warning(f"{league}/{season}: sin datos de equipos")
            return pd.DataFrame()
        rows = []
        for tid, tdata in teams.items():
            name = tdata["title"]
            history = tdata.get("history", [])
            n = len(history)
            if n == 0:
                continue
            total_xg = sum(float(g["xG"]) for g in history)
            total_xga = sum(float(g["xGA"]) for g in history)
            total_gls = sum(int(g["scored"]) for g in history)
            all_ppda = []
            all_deep = []
            for g in history:
                ppda = g.get("ppda", {})
                if isinstance(ppda, dict) and ppda.get("def", 0) > 0:
                    all_ppda.append(round(ppda["att"] / ppda["def"], 2))
                all_deep.append(int(g.get("deep", 0)))
            avg_ppda = round(sum(all_ppda) / len(all_ppda), 2) if all_ppda else 15.0
            avg_deep = round(sum(all_deep) / len(all_deep), 2) if all_deep else 0.0
            last_n = min(n, n_rec)
            xg_last5 = [round(float(g["xG"]), 2) for g in history[-last_n:]]
            xga_last5 = [round(float(g["xGA"]), 2) for g in history[-last_n:]]
            ppda_last5 = all_ppda[-last_n:] if all_ppda else [15.0] * last_n
            rows.append({
                "equipo": name.strip(),
                "xg_por_90": round(total_xg / n, 2),
                "xga_por_90": round(total_xga / n, 2),
                "goles_reales_90": round(total_gls / n, 2),
                "partidos": n,
                "ppda": avg_ppda,
                "final_third_por_90": avg_deep,
                "xg_last5": json.dumps(xg_last5),
                "xga_last5": json.dumps(xga_last5),
                "ppda_last5": json.dumps(ppda_last5),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        logger.exception(f"Error extrayendo Understat {league}/{season}: {e}")
        return pd.DataFrame()


def _parse_display_value(s: dict) -> int:
    """Parse displayValue from ESPN stat object (string -> int)."""
    raw = s.get("displayValue", "0")
    if raw is None:
        return 0
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return 0


def extraer_stats_espn(slug: str, season: int) -> pd.DataFrame:
    """
    Scrapea ESPN scoreboard y calcula xG por fórmula:
      xG  = (total_shots * 0.05) + (shots_on_target * 0.12)
      xGA = (opp_shots   * 0.05) + (opp_sot        * 0.12)
    Retorna DataFrame con columnas estándar del caché.
    """
    url = config.ESPN_SOCCER_API.format(slug=slug)
    n_rec = config.PARTIDOS_RECIENTES
    try:
        r = requests.get(url, params={"dates": season}, headers=ESPN_HEADERS, timeout=30)
        if r.status_code != 200:
            logger.error(f"ESPN HTTP {r.status_code} para {slug}")
            return pd.DataFrame()
        data = r.json()
        events = data.get("events", [])
        if not events:
            logger.warning(f"{slug}: sin eventos")
            return pd.DataFrame()

        team_data = {}
        for event in events:
            comps = event.get("competitions", [])
            for comp in comps:
                competitors = comp.get("competitors", [])
                if len(competitors) < 2:
                    continue
                scores = {}
                stats = {}  # tid -> {stat_name: value}
                for c in competitors:
                    tid = c.get("team", {}).get("id")
                    name = c.get("team", {}).get("displayName", "?")
                    scores[tid] = int(c.get("score", 0))
                    stats[tid] = {}
                    for s in c.get("statistics", []):
                        stats[tid][s["name"]] = _parse_display_value(s)
                # Assign per-match data for each competitor
                tids = list(stats.keys())
                for c in competitors:
                    tid = c.get("team", {}).get("id")
                    name = c.get("team", {}).get("displayName", "?")
                    if tid not in team_data:
                        team_data[tid] = {
                            "name": name, "pj": 0, "gf": 0, "ga": 0,
                            "shots": 0, "sot": 0,
                            "shots_against": 0, "sot_against": 0,
                            "gf_history": [], "ga_history": [],
                            "xg_history": [], "xga_history": [],
                        }
                    team_data[tid]["pj"] += 1
                    gf = scores.get(tid, 0)
                    ga = sum(v for k, v in scores.items() if k != tid)
                    team_data[tid]["gf"] += gf
                    team_data[tid]["ga"] += ga
                    team_data[tid]["gf_history"].append(gf)
                    team_data[tid]["ga_history"].append(ga)

                    own_shots = stats.get(tid, {}).get("totalShots", 0)
                    own_sot   = stats.get(tid, {}).get("shotsOnTarget", 0)
                    team_data[tid]["shots"] += own_shots
                    team_data[tid]["sot"]   += own_sot

                    # Opponent shots
                    opp_id = next((k for k in tids if k != tid), None)
                    if opp_id:
                        opp_shots = stats.get(opp_id, {}).get("totalShots", 0)
                        opp_sot   = stats.get(opp_id, {}).get("shotsOnTarget", 0)
                        team_data[tid]["shots_against"] += opp_shots
                        team_data[tid]["sot_against"]   += opp_sot

                    # Per-match xG from formula
                    xg_match  = (own_shots * 0.05) + (own_sot * 0.12)
                    xga_match = 0.0
                    if opp_id:
                        opp_shots = stats.get(opp_id, {}).get("totalShots", 0)
                        opp_sot   = stats.get(opp_id, {}).get("shotsOnTarget", 0)
                        xga_match = (opp_shots * 0.05) + (opp_sot * 0.12)
                    team_data[tid]["xg_history"].append(round(xg_match, 2))
                    team_data[tid]["xga_history"].append(round(xga_match, 2))

        if not team_data:
            logger.warning(f"{slug}: sin datos de equipos agregados")
            return pd.DataFrame()

        rows = []
        for tid, td in team_data.items():
            n = td["pj"]
            if n == 0:
                continue
            last_n = min(n, n_rec)
            xg_avg  = round(sum(td["xg_history"]) / n, 2)
            xga_avg = round(sum(td["xga_history"]) / n, 2)
            goles_avg = round(td["gf"] / n, 2)
            tiros_p90  = round(td["shots"] / n, 2)
            sot_p90    = round(td["sot"] / n, 2)
            rows.append({
                "equipo": td["name"],
                "xg_por_90": xg_avg,
                "xga_por_90": xga_avg,
                "goles_reales_90": goles_avg,
                "partidos": n,
                "ppda": 15.0,
                "final_third_por_90": 0.0,
                "tiros_totales_por_90": tiros_p90,
                "tiros_puerta_por_90": sot_p90,
                "xg_last5": json.dumps(td["xg_history"][-last_n:]),
                "xga_last5": json.dumps(td["xga_history"][-last_n:]),
                "ppda_last5": json.dumps([15.0] * last_n),
            })
        df = pd.DataFrame(rows)
        logger.info(f"{slug}: {len(df)} equipos vía ESPN (fórmula xG)")
        return df
    except Exception as e:
        logger.exception(f"Error extrayendo ESPN {slug}: {e}")
        return pd.DataFrame()





def actualizar_base_datos_soccer():
    dfs = []

    for nombre_liga, info in config.SOCCER_LEAGUES_V1.items():
        logger.info(f"Extrayendo {nombre_liga}...")
        # Siempre obtener fórmula xG desde ESPN
        df = extraer_stats_espn(info["espn_slug"], info["season"])
        if df.empty:
            logger.warning(f"{nombre_liga} (ESPN): sin datos")
            continue

        # Para ligas con Understat: mergear ppda/final_third encima
        if "understat_league" in info:
            df_under = extraer_stats_understat(info["understat_league"], info["season"])
            if not df_under.empty:
                under_cols = df_under[["equipo", "ppda", "final_third_por_90", "ppda_last5"]].copy()
                # Hacer merge sobre equipo (fuzzy aproximado: exacto)
                for col in ["ppda", "final_third_por_90"]:
                    for eq in under_cols["equipo"]:
                        mask = df["equipo"].str.lower() == eq.lower().strip()
                        if mask.any():
                            df.loc[mask, col] = under_cols.loc[under_cols["equipo"] == eq, col].values[0]

                # Mergear ppda_last5 (json)
                for _, urow in under_cols.iterrows():
                    mask = df["equipo"].str.lower() == urow["equipo"].lower().strip()
                    if mask.any():
                        df.loc[mask, "ppda_last5"] = urow["ppda_last5"]

        df["liga"] = nombre_liga
        dfs.append(df)
        logger.info(f"{nombre_liga}: {len(df)} equipos")

    if dfs:
        df_final = pd.concat(dfs, ignore_index=True)
        df_final.to_csv(config.CACHE_STATS_PATH, index=False)
        logger.info(f"Cache actualizado: {config.CACHE_STATS_PATH} ({len(df_final)} filas)")
        return df_final
    logger.error("No se pudo obtener datos de ninguna liga")
    return pd.DataFrame()
