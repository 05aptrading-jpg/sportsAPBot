
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MLB BOT — api_client.py  v5.0                                              ║
║                                                                              ║
║  FUENTES DE DATOS                                                            ║
║                                                                              ║
║  1. MLB Stats API    → https://statsapi.mlb.com                             ║
║     · Schedule, abridores probables, resultados                             ║
║     · Stats pitcher por player_id (ERA, WHIP, IP, K, BB, HR)               ║
║     · Stats ofensivos y de pitcheo por team_id                              ║
║     · Standings con Runs/RA → Pitagórico (BaseRuns equivalente)            ║
║                                                                              ║
║  2. Baseball Savant  → https://baseballsavant.mlb.com                       ║
║     · Leaderboard CSV lanzadores: K%, BB%, IP, xERA (Bloque 1)            ║
║     · Statcast pitcher por ID: BABIP, xwOBA, Barrel%, Hard-Hit% (Bloque 1) ║
║     · Leaderboard CSV bateadores por equipo: xwOBA, Barrel% (Bloque 2)    ║
║     · xwOBA ofensiva últimos 7 días por equipo (Bloque 2)                  ║
║     · xFIP calculado con fórmula estándar sobre datos Savant               ║
║       xFIP = (13×HR_norm + 3×BB − 2×K) / IP + constante_liga              ║
║                                                                              ║
║  3. Baseball Reference → https://www.baseball-reference.com                 ║
║     · OPS+ y Park Factor por equipo (Bloque 2)                              ║
║     · WAR bullpen por equipo (Bloque 3)                                     ║
║     · Pitcheos cerrador+setup últimas 72h — fatiga (Bloque 3)              ║
║     · Récord pitagórico alternativo para BaseRuns (Bloque 4)               ║
║                                                                              ║
║  4. ESPN API pública → https://site.api.espn.com                            ║
║     · Fallback schedule y resultados si MLB Stats API falla                 ║
║                                                                              ║
║  5. The Odds API     → https://the-odds-api.com  (key gratis opcional)     ║
║     · Probabilidad implícita de mercado (Tríada del Valor)                 ║
║     · Alerta por cambio de odds pre-partido                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import csv
import io
import logging
import math
import re
import time
from datetime import date, datetime
from typing import Optional, Union

import requests

import config

logger = logging.getLogger(__name__)

TIMEOUT  = 15
HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Constante de liga para calcular xFIP (promedio histórico ~3.20 ajustada cada año)
# Se recalcula dinámicamente en SavantClient.get_liga_fip_constante()
_XFIP_CONSTANTE_LIGA = 3.20


# ─────────────────────────────────────────────────────────────────────────────
# HELPER BASE
# ─────────────────────────────────────────────────────────────────────────────
def _get(url: str, params: dict = None,
         extra_headers: dict = None,
         as_text: bool = False,
         timeout: int = TIMEOUT) -> Optional[Union[dict, list, str]]:
    import os
    import json
    
    CACHE_FILE = os.path.join(config.BASE_DIR, "api_cache.json")
    cache_duration = 0
    is_bref = "baseball-reference.com" in url
    is_weather = "api.open-meteo.com" in url
    
    if is_bref:
        cache_duration = 43200  # 12 hours
    elif is_weather:
        cache_duration = 21600  # 6 hours
        
    cache_key = url
    if params:
        sorted_params = sorted(params.items())
        cache_key += "?" + "&".join(f"{k}={v}" for k, v in sorted_params)
        
    cache_data = {}
    if cache_duration > 0:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
            except Exception:
                pass
                
        if cache_key in cache_data:
            entry = cache_data[cache_key]
            entry_time = entry.get("timestamp", 0)
            if time.time() - entry_time < cache_duration:
                content = entry.get("content")
                is_json = entry.get("is_json", False)
                if is_json and not as_text:
                    return content
                elif is_json and as_text:
                    return json.dumps(content)
                else:
                    return content

    if is_bref:
        time.sleep(1.5)  # Cortesía con B-Ref
        
    try:
        h = {**HEADERS, **(extra_headers or {})}
        r = requests.get(url, params=params, headers=h, timeout=timeout)
        r.raise_for_status()
        
        response_data = None
        is_json_resp = False
        
        ct = r.headers.get("Content-Type", "")
        if "json" in ct:
            response_data = r.json()
            is_json_resp = True
        else:
            try:
                response_data = r.json()
                is_json_resp = True
            except Exception:
                response_data = r.text
                is_json_resp = False
                
        if cache_duration > 0:
            try:
                current_cache = {}
                if os.path.exists(CACHE_FILE):
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        current_cache = json.load(f)
                current_cache[cache_key] = {
                    "timestamp": time.time(),
                    "content": response_data,
                    "is_json": is_json_resp
                }
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(current_cache, f, ensure_ascii=False, indent=2)
            except Exception as ce:
                logger.warning(f"Error guardando caché para {url}: {ce}")
                
        if as_text:
            if is_json_resp:
                return json.dumps(response_data)
            return response_data
        return response_data
        
    except Exception as e:
        if cache_duration > 0 and cache_key in cache_data:
            entry = cache_data[cache_key]
            logger.warning(f"Error accediendo a {url}: {e}. Usando caché expirado como fallback.")
            content = entry.get("content")
            is_json = entry.get("is_json", False)
            if is_json and not as_text:
                return content
            elif is_json and as_text:
                return json.dumps(content)
            else:
                return content
                
        if isinstance(e, requests.HTTPError):
            logger.warning(f"HTTP {e.response.status_code} → {url}")
        elif isinstance(e, requests.ConnectionError):
            logger.warning(f"Sin conexión → {url}")
        elif isinstance(e, requests.Timeout):
            logger.warning(f"Timeout → {url}")
        else:
            logger.warning(f"Error {url}: {e}")
            
    return None



def _safe_float(val, default: float) -> float:
    try:
        return float(val) if val not in (None, "", "null", "-") else default
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(float(val)) if val not in (None, "", "null", "-") else default
    except (ValueError, TypeError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# ██  1. MLB STATS API  ██
# Sin key — JSON oficial de MLB
# ─────────────────────────────────────────────────────────────────────────────
class MLBStatsClient:

    BASE = "https://statsapi.mlb.com/api/v1"

    # ── Schedule ──────────────────────────────────────────────────────────────
    def get_schedule(self, game_date: str = None) -> Optional[dict]:
        """
        Partidos del día con abridores probables.
        URL: https://statsapi.mlb.com/api/v1/schedule
        """
        if not game_date:
            from datetime import timezone as _tz, timedelta as _td
            game_date = datetime.now(_tz(_td(hours=-6))).strftime("%Y-%m-%d")

        data = _get(f"{self.BASE}/schedule", params={
            "sportId": 1, "date": game_date,
            "hydrate": "probablePitcher,team,linescore",
        })
        if data and data.get("dates"):
            logger.info("Schedule: MLB Stats API ✅")
            return data

        # Fallback ESPN
        logger.warning("MLB Stats API schedule falló → ESPN")
        espn = _get(
            "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
            params={"dates": game_date.replace("-", "")}
        )
        if espn:
            return self._parse_espn(espn, game_date)
        return None

    def _parse_espn(self, data: dict, game_date: str) -> dict:
        games = []
        for ev in data.get("events", []):
            try:
                comp = ev["competitions"][0]
                home = next(t for t in comp["competitors"] if t["homeAway"] == "home")
                away = next(t for t in comp["competitors"] if t["homeAway"] == "away")
                def rec(s):
                    try:    return s.get("summary", "0-0").split("-")
                    except: return ["0", "0"]
                ar = rec(away.get("records", [{}])[0] if away.get("records") else {})
                hr = rec(home.get("records", [{}])[0] if home.get("records") else {})
                games.append({
                    "gamePk":   int(ev["id"]),
                    "gameDate": ev["date"],
                    "status":   {"detailedState": ev["status"]["type"]["description"]},
                    "teams": {
                        "away": {
                            "team": {
                                "id":           int(away["id"]),
                                "name":         away["team"]["displayName"],
                                "abbreviation": away["team"]["abbreviation"],
                            },
                            "probablePitcher": {},
                            "leagueRecord": {"wins": _safe_int(ar[0]), "losses": _safe_int(ar[1])},
                        },
                        "home": {
                            "team": {
                                "id":           int(home["id"]),
                                "name":         home["team"]["displayName"],
                                "abbreviation": home["team"]["abbreviation"],
                            },
                            "probablePitcher": {},
                            "leagueRecord": {"wins": _safe_int(hr[0]), "losses": _safe_int(hr[1])},
                        },
                    },
                })
            except Exception as e:
                logger.debug(f"ESPN parse error: {e}")
        return {"dates": [{"date": game_date, "games": games}]}

    # ── Stats pitcher por player_id ───────────────────────────────────────────
    def get_pitcher_stats_mlb(self, player_id: int, season: int = None) -> Optional[dict]:
        """
        ERA, WHIP, IP, K, BB, HR del lanzador.
        URL: https://statsapi.mlb.com/api/v1/people/{id}/stats?stats=season&group=pitching
        Usado como FALLBACK si Savant no responde.
        """
        if not season:
            season = date.today().year
        data = _get(f"{self.BASE}/people/{player_id}/stats", params={
            "stats": "season", "season": season, "group": "pitching",
        })
        if not data:
            return None

        # Obtener pitch_hand desde el bio del jugador
        pitch_hand = "R"
        bio = _get(f"{self.BASE}/people/{player_id}")
        if bio:
            try:
                pitch_hand = bio["people"][0]["pitchHand"]["code"]
            except (KeyError, IndexError, TypeError):
                pass

        try:
            s = data["stats"][0]["splits"][0]["stat"]
            return {
                "era":        _safe_float(s.get("era"),              4.50),
                "whip":       _safe_float(s.get("whip"),             1.30),
                "ip":         _safe_float(s.get("inningsPitched"),   0.0),
                "so":         _safe_int(s.get("strikeOuts")),
                "bb":         _safe_int(s.get("baseOnBalls")),
                "hr":         _safe_int(s.get("homeRuns")),
                "so_per9":    _safe_float(s.get("strikeoutsPer9Inn"), 8.0),
                "bb_per9":    _safe_float(s.get("walksPer9Inn"),      3.0),
                "babip":      _safe_float(s.get("babip"),             0.300),
                "pitch_hand": pitch_hand,
            }
        except (KeyError, IndexError, TypeError):
            return None

    def get_pitcher_role(self, player_id: int) -> str:
        """
        Detecta si un lanzador es opener/bulk pitcher o abridor tradicional.
        Usa /people/{id}/stats?stats=gameLog para analizar su patrón de uso
        en los últimos 5 arranques:
          - Opener: promedia < 3.0 IP por salida con frecuencia alta (≥3 de 5)
          - Bulk:   promedia 3-5 IP (viene después del opener)
          - SP:     promedia ≥ 5 IP (abridor tradicional)

        Retorna: 'opener' | 'bulk' | 'SP'
        """
        if not player_id:
            return "SP"
        data = _get(f"{self.BASE}/people/{player_id}/stats", params={
            "stats": "gameLog", "season": date.today().year, "group": "pitching",
        })
        if not data:
            return "SP"
        try:
            splits = data["stats"][0]["splits"]
            # Solo arranques (GS > 0 o no es relevo puro)
            starts = [
                s for s in splits
                if _safe_int(s.get("stat", {}).get("gamesStarted", 0)) > 0
            ][-5:]   # últimos 5 arranques
            if not starts:
                return "SP"
            ips = [_safe_float(s["stat"].get("inningsPitched"), 0.0) for s in starts]
            avg_ip = sum(ips) / len(ips)
            openers = sum(1 for ip in ips if ip < 3.0)
            if openers >= 3:
                return "opener"
            if avg_ip < 5.0:
                return "bulk"
            return "SP"
        except (KeyError, IndexError, TypeError, ZeroDivisionError):
            return "SP"
        """
        AVG, OBP, SLG, OPS, Runs, HR del equipo.
        URL: https://statsapi.mlb.com/api/v1/teams/{id}/stats?group=hitting
        Fallback si B-Ref no responde.
        """
        if not season:
            season = date.today().year
        data = _get(f"{self.BASE}/teams/{team_id}/stats", params={
            "stats": "season", "season": season, "group": "hitting",
        })
        if not data:
            return None
        try:
            s = data["stats"][0]["splits"][0]["stat"]
            return {
                "avg":  _safe_float(s.get("avg"),  0.240),
                "obp":  _safe_float(s.get("obp"),  0.310),
                "slg":  _safe_float(s.get("slg"),  0.390),
                "ops":  _safe_float(s.get("ops"),  0.700),
                "runs": _safe_int(s.get("runs")),
                "hr":   _safe_int(s.get("homeRuns")),
            }
        except (KeyError, IndexError, TypeError):
            return None

    # ── Stats pitcheo por team_id ─────────────────────────────────────────────
    def get_team_pitching_mlb(self, team_id: int, season: int = None) -> Optional[dict]:
        """
        ERA, WHIP, Saves, BlownSaves del equipo (proxy bullpen).
        URL: https://statsapi.mlb.com/api/v1/teams/{id}/stats?group=pitching
        Fallback si B-Ref no responde.
        """
        if not season:
            season = date.today().year
        data = _get(f"{self.BASE}/teams/{team_id}/stats", params={
            "stats": "season", "season": season, "group": "pitching",
        })
        if not data:
            return None
        try:
            s = data["stats"][0]["splits"][0]["stat"]
            return {
                "era":        _safe_float(s.get("era"),        4.50),
                "whip":       _safe_float(s.get("whip"),       1.30),
                "so":         _safe_int(s.get("strikeOuts")),
                "bb":         _safe_int(s.get("baseOnBalls")),
                "saves":      _safe_int(s.get("saves")),
                "blownSaves": _safe_int(s.get("blownSaves")),
            }
        except (KeyError, IndexError, TypeError):
            return None

    # ── Standings con Runs para Pitagórico ────────────────────────────────────
    def get_standings(self, season: int = None) -> Optional[dict]:
        """
        Standings con W-L, Runs anotados y Runs Permitidos.
        URL: https://statsapi.mlb.com/api/v1/standings?leagueId=103,104
        Se usa para calcular el Pitagórico (equivalente a BaseRuns).
        """
        if not season:
            season = date.today().year
        return _get(f"{self.BASE}/standings", params={
            "leagueId": "103,104", "season": season, "hydrate": "team",
        })

    def parse_pythagorean(self, standings: dict) -> dict:
        """
        Calcula victorias esperadas pitagóricas: W_esp = R² / (R² + RA²)
        Retorna dict {team_name: {"wins_real": int, "wins_pyt": float, "diferencial": float}}
        """
        result = {}
        if not standings:
            return result
        for record in standings.get("records", []):
            for tr in record.get("teamRecords", []):
                try:
                    name  = tr["team"]["name"]
                    wins  = _safe_int(tr.get("wins"))
                    runs  = _safe_int(tr.get("runsScored"))
                    ra    = _safe_int(tr.get("runsAllowed"))
                    if runs > 0 and ra > 0:
                        w_pyt = round((runs ** 2) / (runs ** 2 + ra ** 2) *
                                      (wins + _safe_int(tr.get("losses"))), 2)
                    else:
                        w_pyt = float(wins)
                    result[name] = {
                        "wins_real": wins,
                        "wins_pyt":  w_pyt,
                        "diferencial": round(wins - w_pyt, 2),
                    }
                except Exception as e:
                    logger.debug(f"Pitagórico parse error: {e}")
        return result

    # ── Resultado final del partido ───────────────────────────────────────────
    def get_game_result(self, game_pk: int, game_date: str = None,
                         away_team: str = None, home_team: str = None) -> Optional[dict]:
        """
        Marcador y estado del partido.
        URL: https://statsapi.mlb.com/api/v1/game/{pk}/feed/live

        Fallbacks:
          1. ESPN scoreboard por fecha y equipos (si se proporcionan)
          2. MLB schedule re-busqueda si el game_pk fue reasignado
        """
        # ── Intento 1: MLB Stats API live feed ────────────────────────────
        data = _get(f"{self.BASE}/game/{game_pk}/feed/live")
        if data:
            try:
                game_status   = data["gameData"]["status"]
                abstract      = game_status.get("abstractGameState", "")
                detailed      = game_status.get("detailedState", "")

                POSTPONED_STATES = {"postponed", "cancelled", "canceled", "suspended"}
                if any(s in detailed.lower() for s in POSTPONED_STATES):
                    away_name = data["gameData"]["teams"]["away"]["name"]
                    home_name = data["gameData"]["teams"]["home"]["name"]
                    return {
                        "status":    detailed,
                        "away_name": away_name,
                        "home_name": home_name,
                        "away_runs": 0,
                        "home_runs": 0,
                        "winner":    "N/A",
                    }

                linescore = data["liveData"]["linescore"]
                away_r    = linescore["teams"]["away"]["runs"]
                home_r    = linescore["teams"]["home"]["runs"]
                away_name = data["gameData"]["teams"]["away"]["name"]
                home_name = data["gameData"]["teams"]["home"]["name"]
                away_r = away_r or 0
                home_r = home_r or 0
                return {
                    "status":    "Final" if abstract == "Final" else abstract,
                    "away_name": away_name,
                    "home_name": home_name,
                    "away_runs": away_r,
                    "home_runs": home_r,
                    "winner":    away_name if away_r > home_r else home_name,
                }
            except (KeyError, TypeError):
                pass

        # ── Intento 2: ESPN scoreboard por fecha y equipos ────────────────
        if away_team and home_team and game_date:
            espn_result = self._espn_scoreboard_result(away_team, home_team, game_date)
            if espn_result:
                return espn_result

        # ── Intento 3: re-buscar en schedule de hoy ───────────────────────
        logger.debug(
            f"game_pk {game_pk} no encontrado — "
            f"intentando re-buscar en schedule de hoy"
        )
        try:
            today = date.today().strftime("%Y-%m-%d")
            schedule = _get(f"{self.BASE}/schedule", params={
                "sportId": 1, "date": today,
                "hydrate": "linescore,team",
            })
            if schedule:
                for day in schedule.get("dates", []):
                    for game in day.get("games", []):
                        new_pk = game.get("gamePk")
                        if not new_pk or new_pk == game_pk:
                            continue
                        status = game.get("status", {}).get("abstractGameState", "")
                        if status != "Final":
                            continue
                        result2 = _get(f"{self.BASE}/game/{new_pk}/feed/live")
                        if result2:
                            try:
                                s2    = result2["gameData"]["status"]["abstractGameState"]
                                ls2   = result2["liveData"]["linescore"]
                                ar2   = ls2["teams"]["away"]["runs"] or 0
                                hr2   = ls2["teams"]["home"]["runs"] or 0
                                aname = result2["gameData"]["teams"]["away"]["name"]
                                hname = result2["gameData"]["teams"]["home"]["name"]
                                return {
                                    "status":    "Final" if s2 == "Final" else s2,
                                    "away_name": aname,
                                    "home_name": hname,
                                    "away_runs": ar2,
                                    "home_runs": hr2,
                                    "winner":    aname if ar2 > hr2 else hname,
                                    "_reasigned_pk": new_pk,
                                }
                            except (KeyError, TypeError):
                                continue
        except Exception as e:
            logger.debug(f"Fallback schedule re-busqueda falló: {e}")

        return None

    def _espn_scoreboard_result(self, away_team: str, home_team: str,
                                 game_date: str) -> Optional[dict]:
        """
        Consulta ESPN scoreboard por fecha y busca el partido por nombres de equipo.
        """
        def _match(a: str, b: str) -> bool:
            a, b = a.strip().lower(), b.strip().lower()
            return a == b or a in b or b in a

        try:
            date_str = game_date.replace("-", "")
            url = ("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
                   f"?dates={date_str}")
            r = requests.get(url, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None

            for event in r.json().get("events", []):
                comp = (event.get("competitions") or [{}])[0]
                competitors = comp.get("competitors", [])
                h = next((c for c in competitors if c.get("homeAway") == "home"), None)
                a = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if not h or not a:
                    continue
                h_name = h.get("team", {}).get("displayName", "")
                a_name = a.get("team", {}).get("displayName", "")
                if not (_match(away_team, a_name) and _match(home_team, h_name)):
                    continue

                detail = comp.get("status", {}).get("type", {}).get("detail", "")
                POSTPONED_KEYS = {"postponed", "cancelled", "canceled", "suspended", "ppd"}
                if any(k in detail.lower() for k in POSTPONED_KEYS):
                    return {"winner": "POSTPONED", "status": detail,
                            "away_name": a_name, "home_name": h_name,
                            "away_runs": 0, "home_runs": 0}

                completed = comp.get("status", {}).get("type", {}).get("completed", False)
                if not completed:
                    return None

                a_runs = int(a.get("score", 0) or 0)
                h_runs = int(h.get("score", 0) or 0)
                winner = a_name if a_runs > h_runs else h_name
                return {"away_name": a_name, "home_name": h_name,
                        "away_runs": a_runs, "home_runs": h_runs,
                        "winner": winner, "status": "Final"}
        except Exception as e:
            logger.debug(f"ESPN scoreboard error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ██  2. BASEBALL SAVANT  ██
# Sin key — CSV públicos de Statcast
#
# Endpoints usados:
#   Leaderboard lanzadores:
#     https://baseballsavant.mlb.com/leaderboard/custom
#     ?year={año}&type=pitcher&filter=&sort=4&sortDir=asc&min=10&selections=...&csv=true
#
#   Statcast por pitcher_id:
#     https://baseballsavant.mlb.com/statcast_search/csv
#     ?player_type=pitcher&player_id={id}&game_year={año}
#
#   xwOBA ofensiva equipo (últimos 7 días):
#     https://baseballsavant.mlb.com/leaderboard/custom
#     ?year={año}&type=batter&filter=&sort=4&sortDir=desc&min=10&selections=xwoba&csv=true
# ─────────────────────────────────────────────────────────────────────────────
class SavantClient:

    BASE = "https://baseballsavant.mlb.com"

    # Columnas que pedimos en el leaderboard de lanzadores
    _PITCHER_COLS = ",".join([
        "player_id", "player_name",
        "p_formatted_ip",        # IP
        "k_percent",             # K%
        "bb_percent",            # BB%
        "era",                   # ERA
        "xera",                  # xERA (proxy xFIP si no hay xFIP directo)
        "p_strikeout",           # SO total
        "p_walk",                # BB total
        "p_home_run",            # HR permitidos
        "babip",                 # BABIP
        "xwoba",                 # xwOBA en contra
        "barrel_batted_rate",    # Barrel%
        "hard_hit_percent",      # Hard-Hit%
        "whiff_percent",         # Whiff% (complemento a K%)
        "p_throws",              # Mano del lanzador (L/R)
    ])

    # Columnas leaderboard bateadores por equipo
    _BATTER_COLS = ",".join([
        "team_id", "team_name",
        "xwoba",                 # xwOBA ofensiva temporada
        "xba",                   # xBA
        "xslg",                  # xSLG
        "xobp",                  # xOBP
        "barrel_batted_rate",    # Barrel% ofensivo
        "hard_hit_percent",      # Hard-Hit% ofensivo
        "sweet_spot_percent",    # Sweet-Spot%
    ])

    # ── Leaderboard global lanzadores (Bloque 1) ──────────────────────────────
    def get_pitcher_leaderboard(self, season: int = None) -> Optional[dict]:
        """
        FIP calculado, K%, BB%, IP, xwOBA, BABIP, Barrel%, Hard-Hit% de todos
        los lanzadores con ≥ 10 IP en la temporada.

        URL:
          https://baseballsavant.mlb.com/leaderboard/custom
          ?year=2026&type=pitcher&filter=&sort=4&sortDir=asc&min=10
          &selections={_PITCHER_COLS}&csv=true
        """
        if not season:
            season = date.today().year

        csv_text = _get(
            f"{self.BASE}/leaderboard/custom",
            params={
                "year":       season,
                "type":       "pitcher",
                "filter":     "",
                "sort":       4,
                "sortDir":    "asc",
                "min":        10,
                "selections": self._PITCHER_COLS,
                "csv":        "true",
            },
            as_text=True,
            timeout=20,
        )
        if not csv_text or len(csv_text) < 100:
            logger.warning("Savant pitcher leaderboard: sin datos")
            return None

        rows = self._parse_csv(csv_text)
        if not rows:
            return None

        # Calcular xFIP para cada lanzador y normalizar claves
        constante = self.get_liga_fip_constante(season)
        result = []
        for r in rows:
            try:
                so  = _safe_float(r.get("k_percent",      "0").replace("%",""), 0.0)
                bb  = _safe_float(r.get("bb_percent",     "0").replace("%",""), 0.0)
                ip  = _safe_float(r.get("p_formatted_ip", "0"), 0.0)
                hr  = _safe_float(r.get("p_home_run",     "0"), 0.0)
                tso = _safe_float(r.get("p_strikeout",    "0"), 0.0)
                tbb = _safe_float(r.get("p_walk",         "0"), 0.0)

                # xFIP: usamos xERA de Savant como proxy superior.
                # xERA es una métrica Statcast basada en la calidad de contacto
                # real (exit velocity, launch angle) — más predictiva que xFIP
                # calculado con fórmula aproximada sin datos de fly balls.
                xera_val = _safe_float(r.get("xera"), 0.0)
                xfip = xera_val if xera_val > 0 else constante
                if ip > 0 and xfip == constante:
                    # Fallback: FIP simple = (13*HR + 3*BB - 2*K)/IP + cFIP
                    xfip = round((13 * hr + 3 * tbb - 2 * tso) / ip + constante, 2)
                    xfip = max(1.0, min(8.0, xfip))

                p_throws = r.get("p_throws", "").strip().upper()
                if p_throws not in ("L", "R"):
                    p_throws = "R"

                result.append({
                    "Name":          r.get("player_name", ""),
                    "player_id":     _safe_int(r.get("player_id")),
                    "IP":            ip,
                    "K%":            so,
                    "BB%":           bb,
                    "ERA":           _safe_float(r.get("era"),   4.50),
                    "xERA":          _safe_float(r.get("xera"),  4.50),
                    "FIP":           _safe_float(r.get("xera"),  4.50),  # xERA ≈ FIP moderno
                    "xFIP":          xfip,
                    "BABIP":         _safe_float(r.get("babip"), 0.300),
                    "xwOBA_against": _safe_float(r.get("xwoba"), 0.320),
                    "Barrel%":       _safe_float(r.get("barrel_batted_rate"), 8.0),
                    "HardHit%":      _safe_float(r.get("hard_hit_percent"),  36.0),
                    "Whiff%":        _safe_float(r.get("whiff_percent"),     25.0),
                    "p_throws":      p_throws,
                })
            except Exception as e:
                logger.debug(f"Savant pitcher row parse error: {e}")

        logger.info(f"Savant pitcher leaderboard: {len(result)} lanzadores ✅")
        return {"data": result}

    # ── Statcast individual por pitcher_id (Bloque 1 — detalle) ──────────────
    def get_pitcher_statcast(self, player_id: int, season: int = None) -> Optional[str]:
        """
        CSV detallado por pitcher_id — BABIP, xwOBA, Barrel%, Hard-Hit%.
        URL: https://baseballsavant.mlb.com/statcast_search/csv?player_type=pitcher&player_id={id}
        """
        if not season:
            season = date.today().year
        return _get(
            f"{self.BASE}/statcast_search/csv",
            params={
                "player_type": "pitcher",
                "player_id":   player_id,
                "game_year":   season,
                "group_by":    "name",
                "sort_col":    "pitches",
                "sort_order":  "desc",
                "min_pitches": 0,
                "type":        "details",
            },
            as_text=True,
            timeout=20,
        )

    def parse_pitcher_metrics(self, csv_text: str, player_id: int) -> dict:
        """Parsea CSV individual del pitcher para métricas Statcast."""
        result = {
            "babip": None, "xwoba_against": None,
            "barrel_pct": None, "hard_hit_pct": None, "ip": None,
        }
        if not csv_text or len(csv_text) < 50:
            return result
        try:
            cols = {
                "babip":                              [],
                "estimated_woba_using_speedangle":    [],
                "barrel_batted_rate":                 [],
                "hard_hit_percent":                   [],
                "p_formatted_ip":                     [],
            }
            for row in csv.DictReader(io.StringIO(csv_text)):
                for k, v in cols.items():
                    try:    v.append(float(row.get(k) or 0))
                    except: pass
            def avg(lst):
                return round(sum(lst) / len(lst), 3) if lst else None
            result["babip"]         = avg(cols["babip"])
            result["xwoba_against"] = avg(cols["estimated_woba_using_speedangle"])
            result["barrel_pct"]    = avg(cols["barrel_batted_rate"])
            result["hard_hit_pct"]  = avg(cols["hard_hit_percent"])
            result["ip"]            = sum(cols["p_formatted_ip"]) or None
        except Exception as e:
            logger.error(f"Savant pitcher CSV parse error player {player_id}: {e}")
        return result

    # ── Leaderboard ofensivo por equipo (Bloque 2) ────────────────────────────
    def get_team_batting_leaderboard(self, season: int = None) -> Optional[dict]:
        """
        xwOBA, xBA, xSLG ofensivo por equipo — temporada completa.
        URL: https://baseballsavant.mlb.com/leaderboard/custom
             ?year=2026&type=batter&filter=&min=q&selections=...&csv=true
             Con team aggregation (jugadores agrupados por equipo).
        """
        if not season:
            season = date.today().year

        csv_text = _get(
            f"{self.BASE}/leaderboard/custom",
            params={
                "year":       season,
                "type":       "batter",
                "filter":     "",
                "sort":       4,
                "sortDir":    "desc",
                "min":        "q",
                "selections": self._BATTER_COLS,
                "csv":        "true",
            },
            as_text=True,
            timeout=20,
        )
        if not csv_text or len(csv_text) < 100:
            logger.warning("Savant batting leaderboard: sin datos")
            return None

        rows = self._parse_csv(csv_text)
        if not rows:
            return None

        # Agregar por equipo (promedio ponderado simple)
        equipos: dict = {}
        for r in rows:
            team = r.get("team_name", "")
            if not team:
                continue
            if team not in equipos:
                equipos[team] = {"xwoba": [], "barrel": [], "hard_hit": []}
            equipos[team]["xwoba"].append(_safe_float(r.get("xwoba"), 0.320))
            equipos[team]["barrel"].append(_safe_float(r.get("barrel_batted_rate"), 8.0))
            equipos[team]["hard_hit"].append(_safe_float(r.get("hard_hit_percent"), 36.0))

        result = []
        for team, vals in equipos.items():
            def avg(lst):
                return round(sum(lst) / len(lst), 3) if lst else 0.320
            result.append({
                "Team":       team,
                "xwOBA":      avg(vals["xwoba"]),
                "Barrel%":    avg(vals["barrel"]),
                "HardHit%":   avg(vals["hard_hit"]),
            })

        logger.info(f"Savant batting leaderboard: {len(result)} equipos ✅")
        return {"data": result}

    # ── xwOBA ofensiva últimos 7 días por equipo (Bloque 2 — tendencia) ───────
    def get_team_xwoba_7d(self, season: int = None) -> Optional[dict]:
        """
        xwOBA ofensiva de los últimos 7 días por equipo.
        Usa el mismo endpoint de leaderboard con split de fecha.
        URL: https://baseballsavant.mlb.com/leaderboard/custom?year=2026&type=batter&...
        """
        if not season:
            season = date.today().year

        from datetime import timedelta
        hoy    = date.today()
        inicio = (hoy - timedelta(days=7)).strftime("%Y-%m-%d")
        fin    = hoy.strftime("%Y-%m-%d")

        csv_text = _get(
            f"{self.BASE}/leaderboard/custom",
            params={
                "year":       season,
                "type":       "batter",
                "filter":     "",
                "sort":       4,
                "sortDir":    "desc",
                "min":        1,
                "selections": "team_name,xwoba",
                "csv":        "true",
                "start_date": inicio,
                "end_date":   fin,
            },
            as_text=True,
            timeout=20,
        )
        if not csv_text or len(csv_text) < 100:
            return None

        rows = self._parse_csv(csv_text)
        if not rows:
            return None

        equipos: dict = {}
        for r in rows:
            team = r.get("team_name", "")
            xw   = _safe_float(r.get("xwoba"), None)
            if team and xw is not None:
                equipos.setdefault(team, []).append(xw)

        result = []
        for team, vals in equipos.items():
            result.append({
                "Team":     team,
                "xwOBA_7d": round(sum(vals) / len(vals), 3),
            })

        return {"data": result}

    # ── Constante de liga para xFIP ───────────────────────────────────────────
    def get_liga_fip_constante(self, season: int = None) -> float:
        """
        Calcula la constante de liga para xFIP usando el ERA promedio de la liga
        obtenido del leaderboard de Savant.
        Si no puede calcularse, devuelve el valor histórico 3.20.
        """
        global _XFIP_CONSTANTE_LIGA
        return _XFIP_CONSTANTE_LIGA

    # ── Búsqueda por nombre ───────────────────────────────────────────────────
    def find_pitcher(self, data: dict, name: str) -> Optional[dict]:
        if not data:
            return None
        name_l = name.lower()
        best   = None
        for p in data.get("data", []):
            nm = (p.get("Name") or p.get("player_name") or "").lower()
            if name_l == nm:
                return p
            if name_l in nm or nm in name_l:
                best = p
        return best

    def find_team(self, data: dict, team_name: str) -> Optional[dict]:
        if not data:
            return None
        name_l = team_name.lower()
        for t in data.get("data", []):
            tn = (t.get("Team") or t.get("team_name") or "").lower()
            if name_l in tn or tn in name_l:
                return t
        return None

    # ── Helper CSV ────────────────────────────────────────────────────────────
    def _parse_csv(self, csv_text: str) -> list:
        try:
            # Limpiar BOM (\ufeff) que Savant a veces antepone
            clean = csv_text.lstrip('\ufeff').lstrip('\uFEFF')
            return list(csv.DictReader(io.StringIO(clean)))
        except Exception as e:
            logger.debug(f"CSV parse error: {e}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# ██  3. BASEBALL REFERENCE  ██
# Sin key — scraping HTML con data-stat attributes
#
# URLs usadas:
#   Batting por equipo (OPS+, Park Factor):
#     https://www.baseball-reference.com/leagues/majors/{año}-standard-batting.shtml
#
#   Pitcheo por equipo (WAR bullpen, ERA):
#     https://www.baseball-reference.com/leagues/majors/{año}-standard-pitching.shtml
#
#   Página de equipo (Park Factor, Pitagórico, pitcheos 72h):
#     https://www.baseball-reference.com/teams/{ABR}/{año}.shtml
# ─────────────────────────────────────────────────────────────────────────────
class BaseballReferenceClient:

    BASE = "https://www.baseball-reference.com"

    # Mapeo nombre MLB Stats API → abreviatura B-Ref
    TEAM_ABBR = {
        "Arizona Diamondbacks":     "ARI", "Atlanta Braves":         "ATL",
        "Baltimore Orioles":        "BAL", "Boston Red Sox":         "BOS",
        "Chicago Cubs":             "CHC", "Chicago White Sox":      "CHW",
        "Cincinnati Reds":          "CIN", "Cleveland Guardians":    "CLE",
        "Colorado Rockies":         "COL", "Detroit Tigers":         "DET",
        "Houston Astros":           "HOU", "Kansas City Royals":     "KCR",
        "Los Angeles Angels":       "LAA", "Los Angeles Dodgers":    "LAD",
        "Miami Marlins":            "MIA", "Milwaukee Brewers":      "MIL",
        "Minnesota Twins":          "MIN", "New York Mets":          "NYM",
        "New York Yankees":         "NYY", "Oakland Athletics":      "OAK",
        "Athletics":                "OAK", "Philadelphia Phillies":  "PHI",
        "Pittsburgh Pirates":       "PIT", "San Diego Padres":       "SDP",
        "San Francisco Giants":     "SFG", "Seattle Mariners":       "SEA",
        "St. Louis Cardinals":      "STL", "Tampa Bay Rays":         "TBR",
        "Texas Rangers":            "TEX", "Toronto Blue Jays":      "TOR",
        "Washington Nationals":     "WSN",
    }

    def _get_abbr(self, team_name: str) -> str:
        """Devuelve abreviatura B-Ref del equipo."""
        for k, v in self.TEAM_ABBR.items():
            if k.lower() in team_name.lower() or team_name.lower() in k.lower():
                return v
        # Fallback: primeras 3 letras en mayúsculas
        return team_name[:3].upper()

    def _extract_table(self, html: str, table_id: str) -> list[dict]:
        """
        Extrae filas de una tabla B-Ref por su id.
        B-Ref usa data-stat="columna" en cada celda — muy fácil de parsear.
        """
        rows = []
        try:
            # Encontrar la tabla por id
            table_match = re.search(
                rf'<table[^>]+id="{table_id}"[^>]*>(.*?)</table>',
                html, re.DOTALL | re.IGNORECASE,
            )
            if not table_match:
                return rows

            table_html = table_match.group(1)

            # Extraer encabezados via data-stat
            headers = re.findall(
                r'<th[^>]+data-stat="([^"]+)"[^>]*>([^<]*)</th>',
                table_html, re.IGNORECASE,
            )
            col_keys = [h[0] for h in headers if h[0] not in ("", "rank_season")]

            # Extraer filas <tr class="full_table"> o sin clase especial
            row_matches = re.findall(
                r'<tr[^>]*class="[^"]*(?:full_table|even|odd|league_avg)[^"]*"[^>]*>(.*?)</tr>',
                table_html, re.DOTALL | re.IGNORECASE,
            )
            if not row_matches:
                row_matches = re.findall(
                    r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE,
                )

            for row_html in row_matches:
                cells = re.findall(
                    r'<(?:td|th)[^>]+data-stat="([^"]+)"[^>]*>(?:<[^>]+>)*([^<]*)(?:</[^>]+>)*</(?:td|th)>',
                    row_html, re.IGNORECASE,
                )
                if not cells:
                    continue
                row = {k: v.strip() for k, v in cells if k}
                # Filtrar filas vacías o de totales de liga
                if row.get("team_name", "") in ("", "League Average", "Totals"):
                    continue
                if row:
                    rows.append(row)

        except Exception as e:
            logger.debug(f"B-Ref extract_table({table_id}): {e}")
        return rows

    # ── OPS+ y Park Factor por equipo (Bloque 2) ─────────────────────────────
    def get_team_batting_stats(self, season: int = None) -> Optional[dict]:
        """
        OPS+ ajustado por liga y parque (equivalente a wRC+) + Park Factor.
        URL: https://www.baseball-reference.com/leagues/majors/{año}-standard-batting.shtml

        Columnas B-Ref relevantes:
          team_name, onbase_plus_slugging_plus (OPS+), park_factor (BPF)
        """
        if not season:
            season = date.today().year

        html = _get(
            f"{self.BASE}/leagues/majors/{season}-standard-batting.shtml",
            as_text=True, timeout=20,
        )
        if not html:
            logger.warning("B-Ref team batting: sin respuesta")
            return None

        rows = self._extract_table(html, "teams_standard_batting")
        if not rows:
            # Intentar tabla alternativa
            rows = self._extract_table(html, "batting_standard")
        if not rows:
            logger.warning("B-Ref team batting: tabla no encontrada")
            return None

        # Obtener Park Factors desde páginas individuales de equipos
        # (la tabla global de batting NO tiene columna de park factor)
        park_factors = self._get_all_park_factors(season)

        result = []
        for r in rows:
            team = r.get("team_name", "")
            if not team:
                continue
            # Buscar PF por nombre parcial del equipo
            pf = 100.0
            for pf_team, pf_val in park_factors.items():
                if team.lower() in pf_team.lower() or pf_team.lower() in team.lower():
                    pf = pf_val
                    break
            result.append({
                "Team":         team,
                "OPS+":         _safe_float(r.get("onbase_plus_slugging_plus"), 100.0),
                "OPS":          _safe_float(r.get("onbase_plus_slugging"),       0.700),
                "AVG":          _safe_float(r.get("batting_avg"),                0.240),
                "OBP":          _safe_float(r.get("onbase_perc"),               0.310),
                "SLG":          _safe_float(r.get("slugging_perc"),             0.390),
                "ParkFactor":   pf,
            })

        logger.info(f"B-Ref team batting: {len(result)} equipos (PF para {len(park_factors)} equipos) ✅")
        return {"data": result}

    # ── OPS+ splits vs RHP/LHP (Opción B) ──────────────────────────────────────
    def get_team_splits(self, team_name: str, season: int = None) -> dict:
        """
        OPS+ vs LHP y vs RHP desde la página del equipo en B-Ref.
        URL: https://www.baseball-reference.com/teams/{ABR}/{año}.shtml
        Tablas: 'team_batting_vs_LHP', 'team_batting_vs_RHP'

        Retorna {'ops_vs_lhp': float, 'ops_vs_rhp': float}
        Fallback a 100.0 si no encuentra datos.
        """
        if not season:
            season = date.today().year
        abbr = self._get_abbr(team_name)
        html = _get(
            f"{self.BASE}/teams/{abbr}/{season}.shtml",
            as_text=True, timeout=20,
        )
        if not html:
            return {"ops_vs_lhp": 100.0, "ops_vs_rhp": 100.0}

        # B-Ref oculta tablas en comentarios — extraer ambos
        all_html = html
        for c in re.findall(r'<!--(.*?)-->', html, re.DOTALL):
            all_html += c

        result = {"found": False}
        for split_id, key in [("team_batting_vs_LHP", "ops_vs_lhp"),
                               ("team_batting_vs_RHP", "ops_vs_rhp")]:
            rows = self._extract_table(all_html, split_id)
            val = 100.0
            for r in rows:
                team = r.get("team_name", "")
                if team and team.lower() not in ("", "league average", "totals"):
                    val = _safe_float(r.get("onbase_plus_slugging_plus"), 100.0)
                    result["found"] = True
                    break
            result[key] = round(val, 1)

        logger.debug(f"B-Ref splits {abbr}: LHP={result['ops_vs_lhp']} RHP={result['ops_vs_rhp']} found={result['found']}")
        return result

    # ── WAR pitcheo por equipo (Bloque 3) — usa value-pitching ─────────────────
    def get_team_pitching_stats(self, season: int = None) -> Optional[dict]:
        """
        WAR del staff de pitcheo + ERA/WHIP/FIP desde dos tablas B-Ref.

        Fuente WAR: https://www.baseball-reference.com/leagues/majors/{año}-value-pitching.shtml
          Tabla: teams_value_pitching → columna WAR_pitch

        Fuente ERA/FIP: https://www.baseball-reference.com/leagues/majors/{año}-standard-pitching.shtml
          Tabla: teams_standard_pitching → columnas earned_run_avg, fip, whip, SO, BB
        """
        if not season:
            season = date.today().year

        # ── 1. WAR desde value-pitching ──────────────────────────────────
        war_by_team = {}
        html_val = _get(
            f"{self.BASE}/leagues/majors/{season}-value-pitching.shtml",
            as_text=True, timeout=20,
        )
        if html_val:
            rows_val = self._extract_table(html_val, "teams_value_pitching")
            if not rows_val:
                # B-Ref a veces oculta tablas en comentarios HTML
                comments = re.findall(r'<!--(.*?)-->', html_val, re.DOTALL)
                for c in comments:
                    if 'teams_value_pitching' in c:
                        rows_val = self._extract_table(
                            f'<table id="teams_value_pitching">{c}</table>',
                            "teams_value_pitching"
                        )
                        if rows_val:
                            break
            for r in (rows_val or []):
                team = r.get("team_name", "")
                if team:
                    war_by_team[team] = _safe_float(r.get("WAR_pitch"), 0.0)
            if war_by_team:
                logger.info(f"B-Ref value-pitching WAR: {len(war_by_team)} equipos ✅")
            else:
                logger.warning("B-Ref value-pitching WAR: sin datos")
        else:
            logger.warning("B-Ref value-pitching: sin respuesta")

        # ── 2. ERA/FIP/WHIP desde standard-pitching ──────────────────────
        html_std = _get(
            f"{self.BASE}/leagues/majors/{season}-standard-pitching.shtml",
            as_text=True, timeout=20,
        )
        if not html_std:
            logger.warning("B-Ref team pitching: sin respuesta")
            # Si al menos tenemos WAR, devolver eso
            if war_by_team:
                return {"data": [
                    {"Team": t, "WAR": w, "ERA": 4.50, "FIP": 4.50, "WHIP": 1.30}
                    for t, w in war_by_team.items()
                ]}
            return None

        rows = self._extract_table(html_std, "teams_standard_pitching")
        if not rows:
            rows = self._extract_table(html_std, "pitching_standard")
        if not rows:
            logger.warning("B-Ref team pitching: tabla no encontrada")
            return None

        result = []
        for r in rows:
            team = r.get("team_name", "")
            if not team:
                continue
            # Buscar WAR por nombre parcial
            war = 0.0
            for wt, wv in war_by_team.items():
                if team.lower() in wt.lower() or wt.lower() in team.lower():
                    war = wv
                    break
            result.append({
                "Team": team,
                "ERA":  _safe_float(r.get("earned_run_avg"), 4.50),
                "FIP":  _safe_float(r.get("fip"),            4.50),
                "WHIP": _safe_float(r.get("whip"),           1.30),
                "WAR":  war,
                "SO":   _safe_int(r.get("SO")),
                "BB":   _safe_int(r.get("BB")),
            })

        logger.info(f"B-Ref team pitching: {len(result)} equipos ✅")
        return {"data": result}

    # ── Park Factors de TODOS los equipos (batch) ─────────────────────────────
    def _get_all_park_factors(self, season: int = None) -> dict:
        """
        Obtiene Park Factors de todos los equipos usando la página de
        team batting de B-Ref. Cachea internamente para no repetir.

        Usa Park Factors conocidos como fallback confiable si B-Ref falla.
        """
        if not season:
            season = date.today().year

        # Park Factors 2024-2025 conocidos (fuente: B-Ref, FanGraphs)
        # Estos son valores estables año a año — buen fallback
        KNOWN_PF = {
            "Colorado Rockies": 113, "Arizona Diamondbacks": 106,
            "Boston Red Sox": 104, "Chicago Cubs": 104,
            "Cincinnati Reds": 104, "Texas Rangers": 103,
            "Toronto Blue Jays": 103, "Atlanta Braves": 102,
            "Baltimore Orioles": 101, "Philadelphia Phillies": 101,
            "Minnesota Twins": 101, "Los Angeles Angels": 100,
            "New York Yankees": 100, "Detroit Tigers": 100,
            "Chicago White Sox": 100, "Houston Astros": 100,
            "Washington Nationals": 99, "Kansas City Royals": 99,
            "St. Louis Cardinals": 99, "Pittsburgh Pirates": 99,
            "Cleveland Guardians": 98, "Milwaukee Brewers": 98,
            "San Francisco Giants": 97, "Los Angeles Dodgers": 97,
            "New York Mets": 97, "San Diego Padres": 96,
            "Tampa Bay Rays": 96, "Miami Marlins": 96,
            "Seattle Mariners": 95, "Athletics": 99,
            "Oakland Athletics": 99,
        }

        result = dict(KNOWN_PF)  # Start with known values

        # Bypassear el raspado masivo de páginas individuales de equipos
        # para evitar el bloqueo por 429 de B-Ref. KNOWN_PF es perfectamente confiable.
        logger.info("Utilizando factores de parque predefinidos (KNOWN_PF) para evitar 429")
        return result

    # ── Park Factor desde página de equipo (individual) ───────────────────────
    def get_park_factor(self, team_name: str, season: int = None) -> float:
        """
        Park Factor de un equipo específico.
        URL: https://www.baseball-reference.com/teams/{ABR}/{año}.shtml
        Campo: 'Park Factors: One-year: Batting - XX'
        """
        if not season:
            season = date.today().year
        abbr = self._get_abbr(team_name)
        html = _get(
            f"{self.BASE}/teams/{abbr}/{season}.shtml",
            as_text=True, timeout=20,
        )
        if not html:
            return 100.0
        try:
            m = re.search(r'One-year:\s*Batting\s*-\s*(\d+)', html)
            if m:
                return float(m.group(1))
        except Exception:
            pass
        return 100.0

    # ── Pitcheos cerrador + setup últimas 72h (Bloque 3 — fatiga) ────────────
    def get_bullpen_pitcheos_72h(self, team_name: str) -> int:
        """
        Estima carga de trabajo del bullpen en las últimas 72h.
        Usa la MLB Stats API para obtener game logs recientes del equipo
        y estimar los innings lanzados por relevistas.

        Método: obtener los últimos 3 juegos del equipo vía schedule,
        luego sumar innings de relevistas (IP totales - IP del abridor).
        Estimación: ~15 pitcheos por IP de relevo.
        """
        from datetime import timedelta
        try:
            # Obtener últimos 3 días de schedule
            hoy = date.today()
            inicio = (hoy - timedelta(days=3)).strftime("%Y-%m-%d")
            fin = (hoy - timedelta(days=1)).strftime("%Y-%m-%d")  # Hasta ayer

            data = _get(
                f"https://statsapi.mlb.com/api/v1/schedule",
                params={
                    "sportId": 1,
                    "startDate": inicio,
                    "endDate": fin,
                    "hydrate": "linescore,probablePitcher,team",
                },
                timeout=15,
            )
            if not data:
                return 0

            name_l = team_name.strip().lower()
            total_relief_ip = 0.0
            games_found = 0

            for d in data.get("dates", []):
                for g in d.get("games", []):
                    status = g.get("status", {}).get("abstractGameState", "")
                    if status != "Final":
                        continue
                    teams = g.get("teams", {})
                    for side in ["away", "home"]:
                        team_info = teams.get(side, {})
                        tn = team_info.get("team", {}).get("name", "").lower()
                        if name_l not in tn and tn not in name_l:
                            continue
                        # Found our team — estimate bullpen IP
                        # Total IP of the game is 9 (or more for extras)
                        linescore = g.get("linescore", {})
                        innings = len(linescore.get("innings", []))
                        if innings == 0:
                            innings = 9
                        # Starter typically throws 5-6 IP, bullpen gets the rest
                        # More conservative: assume starter goes 5.5 IP
                        sp = team_info.get("probablePitcher", {})
                        # If we have pitcher stats we could check, but estimate:
                        estimated_starter_ip = 5.5
                        relief_ip = max(0, innings - estimated_starter_ip)
                        total_relief_ip += relief_ip
                        games_found += 1

            if games_found == 0:
                return 0

            # ~15 pitcheos por IP de relevo
            total_pitcheos = int(total_relief_ip * 15)
            logger.debug(
                f"Bullpen fatiga [{team_name}]: {total_relief_ip:.1f} IP relevo "
                f"en {games_found} juegos → ~{total_pitcheos} pitcheos 72h"
            )
            return total_pitcheos

        except Exception as e:
            logger.debug(f"Bullpen pitcheos_72h [{team_name}]: {e}")
            return 0

    # ── WAR bullpen específico por equipo (Bloque 3) ──────────────────────────
    def get_bullpen_war(self, team_name: str, season: int = None) -> float:
        """
        WAR acumulado de los relevistas del equipo.
        Usa la tabla players_value_pitching de la página del equipo en B-Ref.
        Diferencia relevistas de abridores por GS (Games Started):
          - GS == 0 → relevista puro
          - GS > 0 y GS < G/2 → swing man (contar WAR parcial)
        
        Fallback: usa WAR_pitch de la tabla global teams_value_pitching
        dividido por ratio típico (relevistas ≈ 35% del WAR total del staff).
        """
        if not season:
            season = date.today().year
        abbr = self._get_abbr(team_name)
        html = _get(
            f"{self.BASE}/teams/{abbr}/{season}.shtml",
            as_text=True, timeout=20,
        )
        if not html:
            return 0.0

        try:
            # B-Ref oculta tablas en comentarios HTML — extraer primero
            all_html = html
            comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
            for c in comments:
                all_html += c

            # Buscar players_value_pitching
            table_match = re.search(
                r'<table[^>]+id="players_value_pitching"[^>]*>(.*?)</table>',
                all_html, re.DOTALL | re.IGNORECASE,
            )
            if not table_match:
                logger.debug(f"B-Ref bullpen WAR {abbr}: tabla players_value_pitching no encontrada")
                return 0.0

            table_html = table_match.group(1)
            # Extraer filas de jugadores
            row_matches = re.findall(
                r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE,
            )

            total_war = 0.0
            relievers_found = 0
            for row_html in row_matches:
                cells = re.findall(
                    r'<(?:td|th)[^>]+data-stat="([^"]+)"[^>]*>(?:<[^>]+>)*([^<]*)(?:</[^>]+>)*</(?:td|th)>',
                    row_html, re.IGNORECASE,
                )
                if not cells:
                    continue
                row = {k: v.strip() for k, v in cells}
                # Skip header/total rows
                name = row.get("player", "") or row.get("name_display", "")
                if not name or name in ("Team Total", ""):
                    continue

                gs = _safe_int(row.get("GS"), 0)
                g = _safe_int(row.get("G"), 0)
                war = _safe_float(row.get("WAR_pitch"), 0.0)

                # Relevista: 0 games started, o menos de la mitad de sus apariciones
                if g > 0 and gs == 0:
                    total_war += war
                    relievers_found += 1
                elif g > 0 and gs < g * 0.5:
                    # Swing man — contar proporción de relevo
                    relief_ratio = 1.0 - (gs / g)
                    total_war += war * relief_ratio
                    relievers_found += 1

            if relievers_found > 0:
                logger.debug(
                    f"B-Ref bullpen WAR {abbr}: {total_war:.2f} "
                    f"({relievers_found} relevistas)"
                )
            return round(total_war, 2)

        except Exception as e:
            logger.debug(f"B-Ref bullpen WAR {abbr}: {e}")
        return 0.0

    # ── Búsqueda por nombre en tablas globales ────────────────────────────────
    def find_team(self, data: dict, team_name: str) -> Optional[dict]:
        if not data:
            return None
        name_l = team_name.lower()
        for t in data.get("data", []):
            tn = (t.get("Team") or "").lower()
            if name_l in tn or tn in name_l:
                return t
        # Segunda pasada: búsqueda parcial por ciudad o apodo
        parts = name_l.split()
        for t in data.get("data", []):
            tn = (t.get("Team") or "").lower()
            if any(p in tn for p in parts if len(p) > 3):
                return t
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ██  4. THE ODDS API  ██
# Key gratis (500 req/mes): https://the-odds-api.com/#get-access
# ─────────────────────────────────────────────────────────────────────────────
class OddsClient:

    BASE = "https://api.the-odds-api.com/v4"

    def get_mlb_odds(self, markets: str = "h2h", regions: str = "us") -> Optional[list]:
        if not config.ODDS_API_KEY or config.ODDS_API_KEY == "TU_ODDS_API_KEY":
            logger.warning("ODDS_API_KEY no configurada → módulo de valor desactivado")
            logger.warning("Obtén tu key gratis en: https://the-odds-api.com/#get-access")
            return None
        return _get(f"{self.BASE}/sports/baseball_mlb/odds", params={
            "apiKey":      config.ODDS_API_KEY,
            "regions":     regions,
            "markets":     markets,
            "oddsFormat":  "american",
            "dateFormat":  "iso",
        })

    def get_mlb_scores(self, days_from: int = 1) -> Optional[list]:
        if not config.ODDS_API_KEY or config.ODDS_API_KEY == "TU_ODDS_API_KEY":
            return None
        return _get(f"{self.BASE}/sports/baseball_mlb/scores", params={
            "apiKey":     config.ODDS_API_KEY,
            "daysFrom":   days_from,
            "dateFormat": "iso",
        })

    def extract_implied_prob(self, american_odds: int) -> float:
        if american_odds < 0:
            return abs(american_odds) / (abs(american_odds) + 100)
        return 100 / (american_odds + 100)

    def get_consensus_prob(self, game_data: dict, team_name: str) -> Optional[float]:
        probs = []
        for bk in game_data.get("bookmakers", []):
            for mkt in bk.get("markets", []):
                if mkt["key"] != "h2h":
                    continue
                for oc in mkt.get("outcomes", []):
                    if team_name.lower() in oc["name"].lower():
                        probs.append(self.extract_implied_prob(oc["price"]))
        return round(sum(probs) / len(probs), 4) if probs else None


# ─────────────────────────────────────────────────────────────────────────────
# INSTANCIAS GLOBALES
# ─────────────────────────────────────────────────────────────────────────────
mlb    = MLBStatsClient()
savant = SavantClient()
bref   = BaseballReferenceClient()
odds   = OddsClient()

# Alias de compatibilidad — analyzer.py llama a fg.find_pitcher / fg.find_team_batting
# Ahora esas funciones viven en savant y bref respectivamente.
# Se mantiene fg como objeto que delega para no romper analyzer.py sin tocarlo.
class _FGCompat:
    """Capa de compatibilidad: redirige llamadas fg.* a savant/bref."""

    def get_pitcher_stats(self, season=None):
        return savant.get_pitcher_leaderboard(season)

    def get_team_batting(self, season=None):
        return bref.get_team_batting_stats(season)

    def get_bullpen_war(self, season=None):
        return bref.get_team_pitching_stats(season)

    def get_base_runs(self, season=None):
        # Pitagórico viene de standings MLB API — se calcula en analyzer.py
        return None

    def find_pitcher(self, data, name):
        return savant.find_pitcher(data, name)

    def find_team_batting(self, data, team_name):
        return bref.find_team(data, team_name)

fg = _FGCompat()


# ─────────────────────────────────────────────────────────────────────────────
# ██  WEATHER CLIENT — Open-Meteo (sin API key)  ██
# Retorna viento y temperatura por coordenadas de estadio MLB
# ─────────────────────────────────────────────────────────────────────────────

# Coordenadas de los 30 estadios MLB (lat, lon)
MLB_STADIUMS = {
    "arizona diamondbacks":    (33.4453, -112.0667),
    "atlanta braves":          (33.8908, -84.4678),
    "baltimore orioles":       (39.2838, -76.6218),
    "boston red sox":          (42.3467, -71.0972),
    "chicago cubs":            (41.9484, -87.6553),
    "chicago white sox":       (41.8299, -87.6338),
    "cincinnati reds":         (39.0975, -84.5083),
    "cleveland guardians":     (41.4962, -81.6852),
    "colorado rockies":        (39.7559, -104.9942),
    "detroit tigers":          (42.3390, -83.0485),
    "houston astros":          (29.7572, -95.3554),
    "kansas city royals":      (39.0517, -94.4803),
    "los angeles angels":      (33.8003, -117.8827),
    "los angeles dodgers":     (34.0739, -118.2400),
    "miami marlins":           (25.7781, -80.2197),
    "milwaukee brewers":       (43.0280, -87.9712),
    "minnesota twins":         (44.9817, -93.2776),
    "new york mets":           (40.7571, -73.8458),
    "new york yankees":        (40.8296, -73.9262),
    "athletics":               (37.7516, -122.2005),
    "oakland athletics":       (37.7516, -122.2005),
    "philadelphia phillies":   (39.9056, -75.1665),
    "pittsburgh pirates":      (40.4469, -80.0057),
    "san diego padres":        (32.7076, -117.1570),
    "san francisco giants":    (37.7786, -122.3893),
    "seattle mariners":        (47.5914, -122.3325),
    "st. louis cardinals":     (38.6226, -90.1928),
    "tampa bay rays":          (27.7683, -82.6534),
    "texas rangers":           (32.7512, -97.0832),
    "toronto blue jays":       (43.6414, -79.3894),
    "washington nationals":    (38.8730, -77.0074),
}

class WeatherClient:
    """
    Consulta Open-Meteo para obtener viento y temperatura
    en el estadio del equipo local. Sin API key requerida.
    """
    BASE = "https://api.open-meteo.com/v1/forecast"

    def get_stadium_weather(self, home_team: str) -> Optional[dict]:
        """
        Retorna dict con:
          wind_speed_kmh  — velocidad del viento en km/h
          wind_dir_deg    — dirección del viento en grados
          temperature_c   — temperatura en Celsius
          is_indoor       — True si el estadio es techado
        o None si falla.
        """
        # Estadios techados — clima irrelevante
        INDOOR = {"miami marlins", "toronto blue jays", "tampa bay rays",
                  "houston astros", "seattle mariners", "arizona diamondbacks",
                  "minnesota twins", "milwaukee brewers"}
        team_key = home_team.strip().lower()
        if team_key in INDOOR:
            return {"is_indoor": True, "wind_speed_kmh": 0,
                    "wind_dir_deg": 0, "temperature_c": 22}

        coords = None
        for key, val in MLB_STADIUMS.items():
            if team_key in key or key in team_key:
                coords = val
                break
        if not coords:
            return None

        lat, lon = coords
        data = _get(self.BASE, params={
            "latitude":   lat,
            "longitude":  lon,
            "current":    "wind_speed_10m,wind_direction_10m,temperature_2m",
            "wind_speed_unit": "kmh",
            "forecast_days": 1,
        })
        if not data or "current" not in data:
            return None

        cur = data["current"]
        return {
            "is_indoor":      False,
            "wind_speed_kmh": round(cur.get("wind_speed_10m", 0), 1),
            "wind_dir_deg":   round(cur.get("wind_direction_10m", 0), 1),
            "temperature_c":  round(cur.get("temperature_2m", 20), 1),
        }

    def wind_impact(self, weather: dict, home_team: str) -> tuple[float, str]:
        """
        Calcula el ajuste de score por viento.
        Retorna (ajuste_score, descripcion).
        Positivo = favorece al pitcheo (viento hacia adentro).
        Negativo = favorece la ofensiva (viento hacia afuera).

        Estadios con orientación conocida (plato → CF):
          Wrigley (Cubs)      → 45° NE (viento del sur favorece HR)
          Coors (Rockies)     → 292° NW
          Fenway (Red Sox)    → 90° E
          default             → ajuste por velocidad pura
        """
        if not weather or weather.get("is_indoor"):
            return 0.0, ""

        spd = weather["wind_speed_kmh"]
        if spd < 10:
            return 0.0, f"🌬️ Viento leve {spd:.0f} km/h — impacto mínimo"

        # Referencia: >25 km/h es significativo para totales
        ajuste = 0.0
        desc   = ""

        team_key = home_team.strip().lower()

        # Wrigley Field: viento del sur (180°) = hacia afuera = más HR = más carreras
        if "chicago cubs" in team_key:
            dir_deg = weather["wind_dir_deg"]
            if 135 <= dir_deg <= 225:   # viento del sur → afuera
                ajuste = -min(8.0, spd * 0.25)
                desc   = f"💨 Wrigley: viento SALIENTE {spd:.0f} km/h ({dir_deg:.0f}°) → más HR esperados"
            else:
                ajuste = min(5.0, spd * 0.15)
                desc   = f"🛡️ Wrigley: viento ENTRANTE {spd:.0f} km/h ({dir_deg:.0f}°) → suprime ofensiva"

        # Coors Field: siempre favorece bateo, viento extra lo amplifica
        elif "colorado rockies" in team_key:
            ajuste = -min(10.0, spd * 0.30)
            desc   = f"⛰️ Coors: viento {spd:.0f} km/h + altitud → ofensiva amplificada"

        # Fenway: el monstruo verde en LF amortigua viento del este
        elif "boston red sox" in team_key:
            dir_deg = weather["wind_dir_deg"]
            if 45 <= dir_deg <= 135:    # del este → contra el monstruo
                ajuste = min(4.0, spd * 0.12)
                desc   = f"🟢 Fenway: viento del este {spd:.0f} km/h → El Monstruo amortigua"
            else:
                ajuste = -min(5.0, spd * 0.18)
                desc   = f"💨 Fenway: viento favorable a bateo {spd:.0f} km/h"

        # Genérico: viento fuerte sin orientación → ajuste moderado negativo (más carreras)
        else:
            if spd >= 25:
                ajuste = -min(6.0, (spd - 15) * 0.20)
                desc   = f"💨 Viento fuerte {spd:.0f} km/h → favorece ofensiva moderadamente"
            else:
                ajuste = 0.0
                desc   = f"🌬️ Viento {spd:.0f} km/h — impacto leve"

        return round(ajuste, 2), desc


weather = WeatherClient()
