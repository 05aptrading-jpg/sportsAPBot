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

FOTMOB_STAT_KEYS = {
    "crosses": "accurate_cross_team",
    "shots": "ontarget_scoring_att_team",
    "blocks": "total_tackle_team",
    "clearances": "effective_clearance_team",
    "corners": "corner_taken_team",
}

_driver = None


def _get_driver():
    global _driver
    if _driver is not None:
        try:
            _driver.title
            return _driver
        except Exception:
            _driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-software-rasterizer")
        opts.add_argument("--log-level=3")

        service = Service(ChromeDriverManager().install())
        _driver = webdriver.Chrome(service=service, options=opts)
        _driver.set_page_load_timeout(60)
        logger.info("Selenium ChromeDriver initialized")
    except Exception as e:
        logger.error(f"Error initializing Selenium: {e}")
        _driver = None
    return _driver


def _close_driver():
    global _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None


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


def _fetch_fotmob_stats_selenium(league_id: int) -> dict:
    """Fetch all team stats from FotMob using Selenium + browser fetch()"""
    import re
    driver = _get_driver()
    if not driver:
        return {}
    try:
        url = f"https://www.fotmob.com/en/leagues/{league_id}/stats"
        driver.get(url)
        time.sleep(8)

        src = driver.page_source
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            src,
        )
        if not match:
            logger.warning(f"FotMob: No __NEXT_DATA__ for league {league_id}")
            return {}

        data = json.loads(match.group(1))
        props = data.get("props", {}).get("pageProps", {})
        teams_stats = props.get("stats", {}).get("teams", [])

        fetch_urls = {}
        for cat in teams_stats:
            cat_name = cat.get("name", "")
            url_val = cat.get("fetchAllUrl", "")
            for our_key, fotmob_key in FOTMOB_STAT_KEYS.items():
                if cat_name == fotmob_key:
                    fetch_urls[our_key] = url_val

        all_team_data = {}
        for stat_name, fetch_url in fetch_urls.items():
            try:
                result = driver.execute_script(
                    f'return fetch("{fetch_url}").then(r => r.json())'
                )
                for top_list in result.get("TopLists", []):
                    for entry in top_list.get("StatList", []):
                        team = entry.get("ParticipantName", "")
                        val = entry.get("StatValue", 0)
                        mp = entry.get("MatchesPlayed", 1)
                        if team:
                            if team not in all_team_data:
                                all_team_data[team] = {}
                            if stat_name == "corners":
                                per_90 = round(val / max(mp, 1), 2)
                                all_team_data[team]["corners_total"] = val
                                all_team_data[team][stat_name] = per_90
                            else:
                                all_team_data[team][stat_name] = val
                logger.debug(f"FotMob {stat_name}: {sum(1 for t in all_team_data if stat_name in all_team_data[t])} equipos")
            except Exception as e:
                logger.warning(f"Error fetching {stat_name}: {e}")

        logger.info(f"FotMob Selenium: {len(all_team_data)} equipos para liga {league_id}")
        return all_team_data
    except Exception as e:
        logger.error(f"Error Selenium FotMob league {league_id}: {e}")
        return {}


def scrape_fotmob_league(league_id: int) -> dict:
    """Legacy function - now uses Selenium"""
    return _fetch_fotmob_stats_selenium(league_id)


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


def scrape_corners_for_league(liga: str, team_names: list) -> dict:
    results = {}
    cache = _load_cache()
    cache_key = f"{liga}_{time.strftime('%Y%m%d')}"
    if cache_key in cache:
        logger.info(f"Corners desde cache: {liga}")
        return cache[cache_key]
    from config import CORNER_LEAGUE_AVG
    promedios = CORNER_LEAGUE_AVG.get(liga, CORNER_LEAGUE_AVG["DEFAULT"])

    fotmob_id = FOTMOB_LEAGUE_IDS.get(liga)
    if fotmob_id:
        fotmob_data = scrape_fotmob_league(fotmob_id)
        for team in team_names:
            for fbt_name, stats in fotmob_data.items():
                if team.lower() in fbt_name.lower() or fbt_name.lower() in team.lower():
                    mapped = {
                        "centros": stats.get("crosses", 0.0),
                        "tiros": stats.get("shots", 0.0),
                        "bloqueos": stats.get("blocks", 0.0),
                        "despejes": stats.get("clearances", 0.0),
                    }
                    curated = curar_datos_para_corners(mapped, promedios)
                    if "corners" in stats:
                        curated["corners_per_90"] = stats["corners"]
                    if "corners_total" in stats:
                        curated["corners_total"] = stats["corners_total"]
                    results[team] = curated
                    break
        if results:
            logger.info(f"FotMob Selenium: {len(results)}/{len(team_names)} equipos para {liga}")

    if len(results) < len(team_names) and liga == "PREMIER_LEAGUE":
        fbref_data = scrape_fbref_team_stats()
        for team in team_names:
            if team not in results:
                for fb_name, stats in fbref_data.items():
                    if team.lower() in fb_name.lower() or fb_name.lower() in team.lower():
                        curated = curar_datos_para_corners(stats, promedios)
                        results[team] = curated
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
