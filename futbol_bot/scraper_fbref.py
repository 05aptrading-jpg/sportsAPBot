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


def extraer_stats_espn(slug: str, season: int) -> pd.DataFrame:
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
            ev_date = event.get("date", "")[:10]
            for comp in comps:
                competitors = comp.get("competitors", [])
                scores = {}
                stats = {}
                for c in competitors:
                    tid = c.get("team", {}).get("id")
                    name = c.get("team", {}).get("displayName", "?")
                    scores[tid] = int(c.get("score", 0))
                    stats[tid] = {}
                    for s in c.get("statistics", []):
                        stats[tid][s["name"]] = int(s.get("value", 0))
                for c in competitors:
                    tid = c.get("team", {}).get("id")
                    name = c.get("team", {}).get("displayName", "?")
                    if tid not in team_data:
                        team_data[tid] = {
                            "name": name, "pj": 0, "gf": 0, "ga": 0,
                            "shots": 0, "sot": 0, "gf_history": [], "ga_history": [],
                        }
                    team_data[tid]["pj"] += 1
                    gf = scores.get(tid, 0)
                    ga = sum(v for k, v in scores.items() if k != tid)
                    team_data[tid]["gf"] += gf
                    team_data[tid]["ga"] += ga
                    team_data[tid]["gf_history"].append(gf)
                    team_data[tid]["ga_history"].append(ga)
                    team_data[tid]["shots"] += stats.get(tid, {}).get("totalShots", 0)
                    team_data[tid]["sot"] += stats.get(tid, {}).get("shotsOnTarget", 0)

        if not team_data:
            logger.warning(f"{slug}: sin datos de equipos agregados")
            return pd.DataFrame()

        rows = []
        for tid, td in team_data.items():
            n = td["pj"]
            if n == 0:
                continue
            last_n = min(n, n_rec)
            xg_last5 = [float(x) for x in td["gf_history"][-last_n:]]
            xga_last5 = [float(x) for x in td["ga_history"][-last_n:]]
            rows.append({
                "equipo": td["name"],
                "xg_por_90": round(td["gf"] / n, 2),
                "xga_por_90": round(td["ga"] / n, 2),
                "goles_reales_90": round(td["gf"] / n, 2),
                "partidos": n,
                "ppda": 15.0,
                "final_third_por_90": 0.0,
                "xg_last5": json.dumps(xg_last5),
                "xga_last5": json.dumps(xga_last5),
                "ppda_last5": json.dumps([15.0] * last_n),
            })
        df = pd.DataFrame(rows)
        logger.info(f"{slug}: {len(df)} equipos vía ESPN (goles/90 como proxy de xG)")
        return df
    except Exception as e:
        logger.exception(f"Error extrayendo ESPN {slug}: {e}")
        return pd.DataFrame()


def actualizar_base_datos_soccer():
    dfs = []
    for nombre_liga, info in config.SOCCER_LEAGUES_V1.items():
        logger.info(f"Extrayendo {nombre_liga}...")
        if "understat_league" in info:
            df = extraer_stats_understat(info["understat_league"], info["season"])
        elif info.get("source") == "espn":
            df = extraer_stats_espn(info["espn_slug"], info["season"])
        else:
            logger.warning(f"{nombre_liga}: fuente no soportada")
            continue
        if df.empty:
            logger.warning(f"{nombre_liga}: sin datos")
            continue
        df["liga"] = nombre_liga
        dfs.append(df)
        logger.info(f"{nombre_liga}: {len(df)} equipos procesados")
    if dfs:
        df_final = pd.concat(dfs, ignore_index=True)
        df_final.to_csv(config.CACHE_STATS_PATH, index=False)
        logger.info(f"Cache actualizado: {config.CACHE_STATS_PATH} ({len(df_final)} filas)")
        return df_final
    logger.error("No se pudo obtener datos de ninguna liga")
    return pd.DataFrame()
