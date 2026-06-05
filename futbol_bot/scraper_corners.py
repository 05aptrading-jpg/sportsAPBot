import logging
import time
import json
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

CORNERS_CACHE_PATH = os.path.join(os.path.dirname(__file__), "corners_cache.json")


def _load_cache() -> dict:
    if os.path.exists(CORNERS_CACHE_PATH):
        try:
            with open(CORNERS_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    try:
        with open(CORNERS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Error guardando corners cache: {e}")


def _safe_float(val, default=0.0) -> float:
    try:
        if val is None or val == "" or val == "-":
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def scrape_fotmob_league(league_id: int) -> dict:
    results = {}
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        home_url = f"https://www.fotmob.com/en/leagues/{league_id}/overview"
        session.get(home_url, timeout=10)
        time.sleep(1)
        api_url = f"https://www.fotmob.com/api/leagues?id={league_id}&tab=stats&type=team"
        r = session.get(api_url, timeout=10)
        if r.status_code != 200:
            logger.warning(f"FotMob API {r.status_code} for league {league_id}")
            return results
        data = r.json()
        stats_data = data.get("stats", {}).get("playersStats", [])
        if not stats_data:
            stats_data = data.get("stats", {}).get("teamStats", [])
        for team_entry in stats_data:
            team_name = team_entry.get("name", "")
            stats_list = team_entry.get("stats", [])
            centros = 0.0
            tiros = 0.0
            bloqueos = 0.0
            despejes = 0.0
            for stat_group in stats_list:
                title = stat_group.get("title", "").lower()
                items = stat_group.get("items", [])
                if not items:
                    continue
                val = _safe_float(items[0].get("value", 0)) if items else 0.0
                if "cross" in title:
                    centros = val
                elif "shot" in title:
                    tiros = val
                elif "block" in title:
                    bloqueos = val
                elif "clear" in title:
                    despejes = val
            if centros > 0 or tiros > 0:
                results[team_name] = {
                    "centros": centros,
                    "tiros": tiros,
                    "bloqueos": bloqueos,
                    "despejes": despejes,
                }
    except Exception as e:
        logger.warning(f"Error FotMob league {league_id}: {e}")
    return results


def scrape_fbref_team_stats() -> dict:
    results = {}
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        time.sleep(3)
        url = "https://fbref.com/en/comps/9/Premier-League-Stats"
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            logger.warning(f"FBref status {r.status_code}")
            return results
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", {"id": "stats_squads_standard_for"})
        if not table:
            for t in soup.find_all("table"):
                if t.find("th", string=lambda x: x and "cross" in x.lower() if x else False):
                    table = t
                    break
        if not table:
            logger.warning("No stats table found on FBref")
            return results
        thead = table.find("thead")
        headers_row = thead.find_all("th") if thead else []
        col_map = {}
        for i, th in enumerate(headers_row):
            text = th.get_text(strip=True).lower()
            if "crs" in text or "cross" in text:
                col_map["centros"] = i
            elif text == "sh":
                col_map["tiros"] = i
            elif "blk" in text or "block" in text:
                col_map["bloqueos"] = i
            elif "clr" in text or "clear" in text:
                col_map["despejes"] = i
        tbody = table.find("tbody")
        if not tbody:
            return results
        for row in tbody.find_all("tr"):
            if row.get("class") and "thead" in " ".join(row.get("class", [])):
                continue
            cols = row.find_all(["td", "th"])
            team_link = row.find("a")
            team_name = team_link.get_text(strip=True) if team_link else ""
            if not team_name:
                continue
            data = {}
            for key, idx in col_map.items():
                if idx < len(cols):
                    data[key] = _safe_float(cols[idx].get_text(strip=True))
            if data:
                results[team_name] = data
    except Exception as e:
        logger.warning(f"Error FBref: {e}")
    return results


def curar_datos_para_corners(stats_scraped: dict, promedios_historicos_liga: dict) -> dict:
    datos_limpios = {}
    for key in ["centros", "tiros", "bloqueos", "despejes"]:
        val = stats_scraped.get(key, 0.0)
        if val == 0.0 or val is None:
            datos_limpios[key] = promedios_historicos_liga.get(key, 0.0)
        else:
            datos_limpios[key] = val
    return datos_limpios


FOTMOB_LEAGUE_IDS = {
    "PREMIER_LEAGUE": 47,
    "LA_LIGA": 87,
    "BUNDESLIGA": 54,
    "SERIE_A": 55,
    "LIGUE_1": 53,
    "LIGA_MX": 65,
    "EREDIVISIE": 23,
    "PRIMEIRA_LIGA": 24,
    "SUPER_LIG": 56,
    "CHAMPIONSHIP": 34,
}


def scrape_corners_for_league(liga: str, team_names: list) -> dict:
    results = {}
    cache = _load_cache()
    cache_key = f"{liga}_{time.strftime('%Y%m%d')}"
    if cache_key in cache:
        logger.info(f"Corners desde cache: {liga}")
        return cache[cache_key]
    fotmob_id = FOTMOB_LEAGUE_IDS.get(liga)
    if fotmob_id:
        fotmob_data = scrape_fotmob_league(fotmob_id)
        for team in team_names:
            for fbt_name, stats in fotmob_data.items():
                if team.lower() in fbt_name.lower() or fbt_name.lower() in team.lower():
                    results[team] = stats
                    break
        if results:
            logger.info(f"FotMob: {len(results)}/{len(team_names)} equipos para {liga}")
    if len(results) < len(team_names) and liga == "PREMIER_LEAGUE":
        fbref_data = scrape_fbref_team_stats()
        for team in team_names:
            if team not in results:
                for fb_name, stats in fbref_data.items():
                    if team.lower() in fb_name.lower() or fb_name.lower() in team.lower():
                        results[team] = stats
                        break
        if fbref_data:
            logger.info(f"FBref: {len(fbref_data)} equipos, total {len(results)}/{len(team_names)}")
    if results:
        cache[cache_key] = results
        _save_cache(cache)
    return results


def scrape_all_corners(liga: str, team_names: list) -> dict:
    logger.info(f"Scraping corners: {liga} ({len(team_names)} equipos)")
    results = scrape_corners_for_league(liga, team_names)
    from config import CORNER_LEAGUE_AVG
    promedios = CORNER_LEAGUE_AVG.get(liga, CORNER_LEAGUE_AVG["DEFAULT"])
    for team in team_names:
        if team not in results:
            results[team] = promedios.copy()
            logger.debug(f"  {team}: usando promedios de liga como fallback")
    logger.info(f"  Resultado final: {len(results)} equipos con datos")
    return results
