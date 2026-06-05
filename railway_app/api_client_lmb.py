"""
API Client for Liga Mexicana de Béisbol (LMB)
Fuentes: Baseball Reference Register — tablas ocultas en comentarios HTML
"""

import json
import logging
import os
import re
import time
from datetime import datetime, date, timedelta
from typing import Optional

import cloudscraper
from bs4 import BeautifulSoup, Comment

import config

logger = logging.getLogger(__name__)

TIMEOUT = 30
_scraper = cloudscraper.create_scraper()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

LMB_LEAGUE_ID = "f6efe3f3"
SEASON = getattr(config, "SEASON_LMB", 2026)

LEAGUE_URL = (
    f"https://www.baseball-reference.com/register/league.cgi?id={LMB_LEAGUE_ID}"
)

PITCHER_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "pitcher_db_lmb.json",
)

TEAM_URL_TEMPLATE = (
    "https://www.baseball-reference.com/register/team.cgi?id={}"
)


def _safe_float(v, default=None):
    if v is None or v == "" or v == "N/D":
        return default
    try:
        return float(v.replace(",", ""))
    except (ValueError, TypeError):
        return default


def _get_soup(url: str) -> Optional[BeautifulSoup]:
    """Fetch URL via cloudscraper (bypass Cloudflare) y retorna BeautifulSoup."""
    try:
        time.sleep(1.0)
        r = _scraper.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
        return None


def _tabla_desde_comentario(soup: BeautifulSoup, table_id: str) -> Optional[BeautifulSoup]:
    """
    Extrae una tabla de BR desde comentario HTML.
    BR oculta sus tablas dentro de <!-- ... -->, JS las activa.
    Retorna BeautifulSoup del <table>.
    """
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        txt = str(comment)
        if table_id not in txt:
            continue
        cs = BeautifulSoup(txt, "lxml")
        table = cs.find("table")
        if table:
            return table
    return None


def _extraer_datos_tabla(table) -> list[dict]:
    """
    Convierte <table> BR en lista de dicts.
    BR usa <th> para todos los encabezados (incluyendo nombre de división).
    """
    if not table:
        return []
    headers = []
    datos = []
    current_division = ""

    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        vals = [c.get_text(strip=True) for c in cells]
        if not vals:
            continue

        # Detectar fila de encabezado: todos los elementos son <th>
        all_th = all(c.name == "th" for c in cells)

        if all_th and vals:
            # Buscar división en cualquier celda
            for v in vals:
                if "Division" in v:
                    current_division = v.replace(" Division", "")
                    break
            # Usar TODOS los valores como encabezados (aunque contenga división)
            headers = vals
            continue

        # Fila de datos
        if not headers:
            continue

        row = {"division": current_division, "Tm": vals[0] if vals else ""}
        for idx, val in enumerate(vals):
            if idx > 0 and idx < len(headers):
                row[headers[idx]] = val
        row["_team"] = vals[0] if vals else ""
        datos.append(row)

    return datos


class LMBClientBR:
    """Cliente para datos LMB via Baseball Reference Register."""

    def _fetch_league_tables(self):
        """
        Obtiene todas las tablas de la página de liga.
        Cachea para no refetchear en cada llamada.
        """
        soup = _get_soup(LEAGUE_URL)
        if not soup:
            return None, None, None

        stand_t = _tabla_desde_comentario(soup, "standings_pitching")
        bat_t   = _tabla_desde_comentario(soup, "league_batting")
        pitch_t = _tabla_desde_comentario(soup, "league_pitching")

        return stand_t, bat_t, pitch_t

    def get_standings(self) -> Optional[list[dict]]:
        """
        Retorna standings LMB.
        Cada dict: {team, w, l, pct, gb, zone}
        """
        stand_t, _, _ = self._fetch_league_tables()
        if not stand_t:
            logger.warning("No se encontró tabla de standings LMB")
            return None

        standings = []
        current_zone = "?"
        for tr in stand_t.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            vals = [c.get_text(strip=True) for c in cells]
            if not vals:
                continue
            first = vals[0]
            if "Division" in first:
                current_zone = first.replace(" Division", "")
                continue
            if first in ("W", "L", "W-L%", "GB", ""):
                continue
            if len(vals) >= 5:
                standings.append({
                    "team": first,
                    "w": int(vals[1]) if vals[1].isdigit() else 0,
                    "l": int(vals[2]) if vals[2].isdigit() else 0,
                    "pct": float(vals[3]) if vals[3] else 0.0,
                    "gb": vals[4] if len(vals) > 4 else "-",
                    "zone": current_zone,
                })
        return standings if standings else None

    def get_all_team_stats(self) -> Optional[dict[str, dict]]:
        """
        Obtiene stats de bateo y pitcheo de TODOS los equipos LMB en una sola request.
        Retorna dict: team_name -> {batting: {...}, pitching: {...}}
        """
        _, bat_t, pitch_t = self._fetch_league_tables()
        if not bat_t or not pitch_t:
            logger.warning("No se encontraron tablas de stats LMB")
            return None

        batting_rows = _extraer_datos_tabla(bat_t)
        pitching_rows = _extraer_datos_tabla(pitch_t)

        result = {}
        for br in batting_rows:
            team = br.get("_team", "")
            if not team or team == "League Totals":
                continue
            result[team] = {"batting": br, "pitching": {}}

        for pr in pitching_rows:
            team = pr.get("_team", "")
            if not team or team == "League Totals":
                continue
            if team not in result:
                result[team] = {"batting": {}, "pitching": {}}
            result[team]["pitching"] = pr

        return result

    def get_real_schedule(self, game_date: str = None) -> Optional[list[dict]]:
        """
        Obtiene el calendario REAL de LMB desde MLB StatsAPI (sportId=23).
        Retorna lista de juegos con: gamePk, gameDate, away_team, home_team,
        away_pitcher, home_pitcher, status, scores.
        """
        import requests as _req
        from datetime import datetime as _dt, timezone as _tz

        if not game_date:
            game_date = date.today().strftime("%m/%d/%Y")

        url = (
            "https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=23&date={game_date}"
            "&hydrate=probablePitcher,linescore"
        )
        try:
            r = _req.get(url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                logger.warning(f"StatsAPI LMB schedule: HTTP {r.status_code}")
                return None
            games = []
            for d in r.json().get("dates", []):
                for g in d.get("games", []):
                    away_t = g.get("teams",{}).get("away",{}).get("team",{}).get("name","")
                    home_t = g.get("teams",{}).get("home",{}).get("team",{}).get("name","")
                    if not away_t or not home_t:
                        continue
                    gid = g.get("gamePk")
                    gdate = g.get("gameDate", "")
                    status = g.get("status", {}).get("detailedState", "Scheduled")
                    ap = g.get("teams",{}).get("away",{}).get("probablePitcher",{})
                    hp = g.get("teams",{}).get("home",{}).get("probablePitcher",{})
                    ls = g.get("linescore", {})
                    away_runs = ls.get("teams",{}).get("away",{}).get("runs") if ls else None
                    home_runs = ls.get("teams",{}).get("home",{}).get("runs") if ls else None

                    games.append({
                        "game_pk": gid,
                        "game_date_utc": gdate,
                        "away_team": away_t,
                        "home_team": home_t,
                        "away_pitcher_name": ap.get("fullName") if ap else None,
                        "away_pitcher_id": ap.get("id") if ap else None,
                        "home_pitcher_name": hp.get("fullName") if hp else None,
                        "home_pitcher_id": hp.get("id") if hp else None,
                        "status": status,
                        "away_runs": away_runs,
                        "home_runs": home_runs,
                    })
            return games if games else None
        except Exception as e:
            logger.warning(f"Error fetching LMB schedule: {e}")
            return None

    def get_team_stats(self, team_name: str) -> Optional[dict]:
        """
        Obtiene stats de un equipo específico.
        Retorna dict: {team, batting: {...}, pitching: {...}, record: {...}}
        """
        all_stats = self.get_all_team_stats()
        if not all_stats:
            return None

        # Fuzzy match por nombre
        best = None
        best_score = 0
        t_lower = team_name.lower()
        for key in all_stats:
            score = 0
            k_lower = key.lower()
            if t_lower == k_lower:
                score = 100
            elif t_lower in k_lower or k_lower in t_lower:
                score = 50
            if score > best_score:
                best_score = score
                best = key

        if not best:
            logger.warning(f"Team {team_name} no encontrado en stats LMB")
            return None

        data = all_stats[best]
        batting = data.get("batting", {})
        pitching = data.get("pitching", {})

        record = {}
        if pitching:
            try:
                record["w"] = int(pitching.get("W", 0))
                record["l"] = int(pitching.get("L", 0))
            except (ValueError, TypeError):
                record = {}
            try:
                record["rs"] = int(batting.get("R", 0)) if batting else 0
                record["ra"] = int(pitching.get("R", 0)) if pitching else 0
            except (ValueError, TypeError):
                pass

        return {
            "team": team_name,
            "batting": batting,
            "pitching": pitching,
            "record": record,
        }

    def get_first_game_time(self, game_date: str = None) -> Optional[str]:
        """
        Scrapea el primer partido LMB del día.
        BR no expone schedule en HTML para register league - solo JS.
        Retorna None = no se puede determinar, usar fallback.
        """
        return None

    def _extraer_team_ids(self) -> Optional[dict[str, str]]:
        """
        Extrae mapeo nombre_equipo → team_id desde la tabla standings_pitching.
        Busca links del tipo /register/team.cgi?id=XXXXXXXX en los comentarios HTML.
        """
        soup = _get_soup(LEAGUE_URL)
        if not soup:
            return None
        stand_t = _tabla_desde_comentario(soup, "standings_pitching")
        if not stand_t:
            return None
        result = {}
        for a in stand_t.find_all("a", href=re.compile(r"/register/team\.cgi\?id=")):
            href = a["href"]
            team_id = href.split("id=")[-1].split("&")[0]
            name = a.get_text(strip=True)
            if name and team_id:
                result[name] = team_id
        return result if result else None

    def _scrape_team_pitchers(self, team_id: str) -> list[dict]:
        """
        Raspa una página de equipo BR y extrae stats individuales de pitchers.
        Retorna lista de dicts: {name, era, ip, h, er, hr, bb, so, hbp, whip, kbb, so9, bb9, gs}
        """
        url = TEAM_URL_TEMPLATE.format(team_id)
        soup = _get_soup(url)
        if not soup:
            return []
        table = _tabla_desde_comentario(soup, "team_pitching")
        if not table:
            return []
        pitchers = []
        headers = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            vals = [c.get_text(strip=True) for c in cells]
            if not vals:
                continue
            all_th = all(c.name == "th" for c in cells)
            if all_th:
                headers = vals
                continue
            if not headers or len(vals) < len(headers):
                continue
            row = dict(zip(headers, vals))
            name = row.get("Name", "").replace("*", "").strip()
            if not name or name in ("Team Totals", "League Totals"):
                continue
            ip = _safe_float(row.get("IP"))
            h = _safe_float(row.get("H"))
            er = _safe_float(row.get("ER"))
            hr = _safe_float(row.get("HR"))
            bb = _safe_float(row.get("BB"))
            so = _safe_float(row.get("SO"))
            hbp = _safe_float(row.get("HBP"))
            gs = _safe_float(row.get("GS"))
            whip = _safe_float(row.get("WHIP"))
            kbb = _safe_float(row.get("SO/W"))
            era = _safe_float(row.get("ERA"))
            so9 = _safe_float(row.get("SO9"))
            bb9 = _safe_float(row.get("BB9"))
            pitchers.append({
                "name": name,
                "era": era,
                "ip": ip,
                "h": h,
                "er": er,
                "hr": hr,
                "bb": bb,
                "so": so,
                "hbp": hbp,
                "gs": gs or 0,
                "whip": whip,
                "kbb": kbb,
                "so9": so9,
                "bb9": bb9,
            })
        return pitchers

    def get_individual_pitcher_stats(self, force_refresh: bool = False
                                     ) -> dict[str, dict]:
        """
        Obtiene stats individuales de TODOS los pitchers LMB desde las
        páginas de equipo de BR, con cache JSON.
        Retorna dict: pitcher_name -> {era, ip, h, er, hr, bb, so, hbp, 
                                        whip, kbb, so9, bb9, team, gs}
        """
        cache_age = timedelta(hours=6)
        if not force_refresh and os.path.exists(PITCHER_DB_PATH):
            mtime = datetime.fromtimestamp(os.path.getmtime(PITCHER_DB_PATH))
            if datetime.now() - mtime < cache_age:
                try:
                    with open(PITCHER_DB_PATH, "r", encoding="utf-8") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

        team_ids = self._extraer_team_ids()
        if not team_ids:
            logger.warning("No se pudieron extraer IDs de equipos LMB")
            return {}

        all_pitchers: dict[str, dict] = {}
        br_name_to_api_name = {
            "Tecolotes de los Dos Laredos": "Tecos de los Dos Laredos",
            "Acereros de Monclova": "Acereros del Norte",
            "Algodoneros de Union Laguna": "Algodoneros Union Laguna",
        }

        for br_team_name, team_id in team_ids.items():
            api_team = br_name_to_api_name.get(br_team_name, br_team_name)
            logger.info(f"Raspando pitchers de {br_team_name} ({team_id})")
            pitchers = self._scrape_team_pitchers(team_id)
            for p in pitchers:
                p["team"] = api_team
                all_pitchers[p["name"]] = p

        if all_pitchers:
            os.makedirs(os.path.dirname(PITCHER_DB_PATH), exist_ok=True)
            with open(PITCHER_DB_PATH, "w", encoding="utf-8") as f:
                json.dump(all_pitchers, f, ensure_ascii=False, indent=2)

        logger.info(f"Pitchers LMB cargados: {len(all_pitchers)}")
        return all_pitchers

    def get_team_form(self, game_date: str = None) -> Optional[dict[str, dict]]:
        """
        Obtiene forma real (últimos 10 juegos) de cada equipo LMB vía StatsAPI.
        Consulta schedule con rango (20 días atrás → game_date), extrae resultados.
        Retorna: team_name -> {"record":"6-4","wins":N,"losses":N,
                                "streak_type":"wins"/"losses","streak_number":N}
        """
        import requests as _req
        if not game_date:
            game_date = date.today().strftime("%Y-%m-%d")
        try:
            dt_end = datetime.strptime(game_date, "%Y-%m-%d").date()
            dt_start = dt_end - timedelta(days=20)
            start_str = dt_start.strftime("%m/%d/%Y")
            end_str = dt_end.strftime("%m/%d/%Y")

            r = _req.get(
                "https://statsapi.mlb.com/api/v1/schedule"
                f"?sportId=23&startDate={start_str}&endDate={end_str}&hydrate=linescore",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=15,
            )
            if r.status_code != 200:
                logger.warning(f"StatsAPI form schedule: HTTP {r.status_code}")
                return None

            team_games: dict[str, list[tuple[str, bool]]] = {}
            for d in r.json().get("dates", []):
                for g in d.get("games", []):
                    if g.get("status", {}).get("detailedState") != "Final":
                        continue
                    ls = g.get("linescore", {})
                    if not ls:
                        continue
                    ar = ls.get("teams", {}).get("away", {}).get("runs")
                    hr = ls.get("teams", {}).get("home", {}).get("runs")
                    if ar is None or hr is None:
                        continue
                    away = g["teams"]["away"]["team"]["name"]
                    home = g["teams"]["home"]["team"]["name"]
                    gdate = g.get("gameDate", "")
                    for team, rf, ra in [(away, ar, hr), (home, hr, ar)]:
                        team_games.setdefault(team, []).append((gdate, rf > ra))

            result = {}
            for team, games in team_games.items():
                games.sort(key=lambda x: x[0])
                last10 = games[-10:]
                wins = sum(1 for _, w in last10 if w)
                losses = len(last10) - wins
                consec = 0
                if last10:
                    lr = last10[-1][1]
                    for i in range(len(last10) - 1, -1, -1):
                        if last10[i][1] == lr:
                            consec += 1
                        else:
                            break
                result[team] = {
                    "record": f"{wins}-{losses}",
                    "wins": wins, "losses": losses,
                    "streak_type": "wins" if last10 and last10[-1][1] else "losses",
                    "streak_number": consec,
                }
            return result if result else None
        except Exception as e:
            logger.warning(f"Error computing LMB form: {e}")
            return None


mlb_lmb = LMBClientBR()
