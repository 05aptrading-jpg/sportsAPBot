"""
Genera index.html para la Telegram Mini App y lo pushea a GitHub Pages.
"""

import json
import logging
import os
from datetime import datetime, date, timedelta

import requests

import config
import data_manager as dm
from generar_hits_xlsx import top_hits_por_equipo

logger = logging.getLogger(__name__)

GITHUB_TOKEN = getattr(config, "GITHUB_TOKEN", "")
REPO_OWNER   = "05aptrading-jpg"
REPO_NAME    = "sportsAPBot"
API_BASE     = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "miniapp", "template.html")
SUSCRIPTORES_PATH = os.path.join(os.path.dirname(__file__), "suscriptores.json")


def cargar_suscriptores() -> list[int]:
    """Retorna lista de IDs de Telegram con suscripción vigente."""
    try:
        from datetime import date as _date
        with open(SUSCRIPTORES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Migrar formato antiguo
        if "autorizados" in data and "suscripciones" not in data:
            from datetime import date as _date_m, timedelta
            expira = (_date_m.today() + timedelta(days=30)).isoformat()
            suscripciones = {}
            for uid in data.get("autorizados", []):
                uid_str = str(uid)
                if uid_str == str(data.get("admin_id")):
                    suscripciones[uid_str] = None
                else:
                    suscripciones[uid_str] = expira
            data["suscripciones"] = suscripciones
            del data["autorizados"]
            with open(SUSCRIPTORES_PATH, "w", encoding="utf-8") as f_w:
                json.dump(data, f_w, ensure_ascii=False, indent=2)
        hoy = _date.today().isoformat()
        suscripciones = data.get("suscripciones", {})
        admin = data.get("admin_id")
        validos = []
        for uid_str, expira in suscripciones.items():
            uid = int(uid_str)
            if expira is None or expira >= hoy:
                validos.append(uid)
        if admin and admin not in validos:
            validos.append(admin)
        return validos
    except Exception:
        return []


def _get_espn_scoreboard(game_date: str) -> list:
    """
    Consulta ESPN y retorna lista de todos los partidos con su estado.
    Cada elemento: {"game_date", "a_name", "h_name", "a_runs", "h_runs", "detail", "completed", "is_live", "is_post"}
    """
    def _m(a, b):
        return a.strip().lower() in b.strip().lower() or b.strip().lower() in a.strip().lower()

    try:
        date_str = game_date.replace("-", "")
        url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={date_str}"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []

        games = []
        for ev in r.json().get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            h = next((c for c in competitors if c.get("homeAway") == "home"), None)
            a = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not h or not a:
                continue
            h_name = h.get("team", {}).get("displayName", "")
            a_name = a.get("team", {}).get("displayName", "")
            h_abbr = h.get("team", {}).get("abbreviation", "")
            a_abbr = a.get("team", {}).get("abbreviation", "")
            detail    = comp.get("status", {}).get("type", {}).get("detail", "")
            completed = comp.get("status", {}).get("type", {}).get("completed", False)
            a_runs    = int(a.get("score", 0) or 0)
            h_runs    = int(h.get("score", 0) or 0)
            is_live   = any(s in detail.lower() for s in ("top", "bot", "end", "middle", "live", "in progress"))
            POSTPONED = {"postponed", "cancelled", "canceled", "suspended", "ppd"}
            is_post   = any(k in detail.lower() for k in POSTPONED)
            espn_pk = int(ev.get("id", 0) or 0)
            games.append({
                "game_date": game_date, "espn_pk": espn_pk,
                "a_name": a_name, "h_name": h_name, "a_runs": a_runs, "h_runs": h_runs,
                "a_abbr": a_abbr, "h_abbr": h_abbr,
                "detail": detail, "completed": completed, "is_live": is_live, "is_post": is_post,
            })
        return games
    except Exception:
        return []


def _espn_to_game(espn: dict, favorito: str = None, liga: str = "MLB") -> dict:
    """Convierte un registro ESPN a formato game de la Mini App."""
    detail = espn["detail"]
    a_runs = espn["a_runs"]
    h_runs = espn["h_runs"]
    a_name = espn["a_name"]
    h_name = espn["h_name"]
    a_abbr = espn.get("a_abbr", "")
    h_abbr = espn.get("h_abbr", "")

    # Determinar qué equipo resaltar y orientar score
    def _fav_info():
        if not favorito:
            return {"fav_team": a_name, "opp_team": h_name, "score_fav": str(a_runs), "score_opp": str(h_runs)}
        fav_is_away = favorito.strip().lower() in a_name.strip().lower() or a_name.strip().lower() in favorito.strip().lower()
        fav_is_home = favorito.strip().lower() in h_name.strip().lower() or h_name.strip().lower() in favorito.strip().lower()
        if fav_is_home and not fav_is_away:
            return {"fav_team": h_name, "opp_team": a_name, "score_fav": str(h_runs), "score_opp": str(a_runs)}
        return {"fav_team": a_name, "opp_team": h_name, "score_fav": str(a_runs), "score_opp": str(h_runs)}

    def _fav_abbr():
        if not favorito:
            return a_abbr, h_abbr
        fav_is_away = favorito.strip().lower() in a_name.strip().lower() or a_name.strip().lower() in favorito.strip().lower()
        fav_is_home = favorito.strip().lower() in h_name.strip().lower() or h_name.strip().lower() in favorito.strip().lower()
        if fav_is_home and not fav_is_away:
            return h_abbr, a_abbr
        return a_abbr, h_abbr

    def _win(fav_info):
        return int(fav_info["score_fav"]) > int(fav_info["score_opp"])

    fi = _fav_info()
    fav_abbr, opp_abbr = _fav_abbr()
    gd = espn.get("game_date", "")

    if espn["is_post"]:
        return {"liga": liga, "game_date": gd, "status_emoji": "🚫", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": "—", "score_opp": "", "state": "Posp.", "result": "pending", "label": "", "game_pk": espn.get("espn_pk", 0), "fav_abbr": fav_abbr, "opp_abbr": opp_abbr, "home_team": h_name, "away_team": a_name}

    if espn["is_live"]:
        return {"liga": liga, "game_date": gd, "status_emoji": "🔴", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": fi["score_fav"], "score_opp": fi["score_opp"], "state": detail, "result": "live", "label": "", "game_pk": espn.get("espn_pk", 0), "fav_abbr": fav_abbr, "opp_abbr": opp_abbr, "home_team": h_name, "away_team": a_name}

    if espn["completed"]:
        if favorito:
            acertado = _win(fi)
            return {"liga": liga, "game_date": gd, "status_emoji": "✅" if acertado else "❌", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": fi["score_fav"], "score_opp": fi["score_opp"], "state": "Final", "result": "win" if acertado else "loss", "label": "", "game_pk": espn.get("espn_pk", 0), "fav_abbr": fav_abbr, "opp_abbr": opp_abbr, "home_team": h_name, "away_team": a_name}
        else:
            return {"liga": liga, "game_date": gd, "status_emoji": "🏁", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": fi["score_fav"], "score_opp": fi["score_opp"], "state": "Final", "result": "completed", "label": "", "game_pk": espn.get("espn_pk", 0), "fav_abbr": fav_abbr, "opp_abbr": opp_abbr, "home_team": h_name, "away_team": a_name}

    return {"liga": liga, "game_date": gd, "status_emoji": "⏳", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": "—", "score_opp": "", "state": "Pend.", "result": "pending", "label": "", "game_pk": espn.get("espn_pk", 0), "fav_abbr": fav_abbr, "opp_abbr": opp_abbr, "home_team": h_name, "away_team": a_name}


def _annotate_linescores_mlb(games: list):
    """Fetch linescore from MLB Stats API by date and annotate games."""
    import requests as _req
    from collections import defaultdict
    from datetime import datetime as _dt, timedelta as _td

    def _norm(n):
        return n.strip().lower() if n else ""

    _ls_cache = {}

    def _fetch_for_date(date_str: str, sport_id: int):
        """Fetch linescores for all games on a date from one API call."""
        try:
            url = f"https://statsapi.mlb.com/api/v1/schedule?sportId={sport_id}&date={date_str}&hydrate=linescore"
            r = _req.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return
            for date_block in r.json().get("dates", []):
                for game in date_block.get("games", []):
                    pk = game.get("gamePk", 0)
                    ls = game.get("linescore")
                    if not pk or not ls:
                        continue
                    innings = []
                    for inn in ls.get("innings", []):
                        innings.append({
                            "away_runs": inn.get("away", {}).get("runs", 0),
                            "home_runs": inn.get("home", {}).get("runs", 0),
                        })
                    status = game.get("status", {}).get("detailedState", "")
                    status_code = game.get("status", {}).get("statusCode", "")
                    is_final = status_code == "F" or "final" in status.lower()
                    is_live = status_code == "I" or "in progress" in status.lower() or any(s in status.lower() for s in ("top", "bot", "end", "middle"))
                    a_runs = ls.get("teams", {}).get("away", {}).get("runs", 0) or 0
                    h_runs = ls.get("teams", {}).get("home", {}).get("runs", 0) or 0
                    a_team = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "")
                    h_team = game.get("teams", {}).get("home", {}).get("team", {}).get("name", "")

                    status_emoji = "🔴" if is_live else ("🏁" if is_final else "⏳")
                    game_result = "live" if is_live else ("completed" if is_final else "pending")

                    _ls_cache[pk] = {
                        "innings": innings,
                        "current_inning": ls.get("currentInning", 1),
                        "is_top": ls.get("isTopInning", True),
                        "inning_ordinal": ls.get("currentInningOrdinal", ""),
                        "outs": ls.get("outs", 0),
                        "balls": ls.get("balls", 0),
                        "strikes": ls.get("strikes", 0),
                        "away_runs": a_runs,
                        "home_runs": h_runs,
                        "away_hits": ls.get("teams", {}).get("away", {}).get("hits", 0),
                        "home_hits": ls.get("teams", {}).get("home", {}).get("hits", 0),
                        "away_errors": ls.get("teams", {}).get("away", {}).get("errors", 0),
                        "home_errors": ls.get("teams", {}).get("home", {}).get("errors", 0),
                        "away_team_name": a_team,
                        "home_team_name": h_team,
                        "bases": {
                            "first": ls.get("offensive", {}).get("first", False),
                            "second": ls.get("offensive", {}).get("second", False),
                            "third": ls.get("offensive", {}).get("third", False),
                        },
                        "status_emoji": status_emoji,
                        "result": game_result,
                        "state": status,
                        "fav_score": str(a_runs),
                        "opp_score": str(h_runs),
                        "score_fav": str(a_runs),
                        "score_opp": str(h_runs),
                    }
                    # Also cache by team names for games with pk=0
                    if a_team and h_team:
                        _ls_cache[(date_str, _norm(a_team), _norm(h_team))] = _ls_cache[pk]
        except Exception:
            pass

    # Group by (date, sport_id)
    by_ds = defaultdict(set)
    for g in games:
        gd = g.get("game_date", "")
        liga = g.get("liga", "MLB")
        sport_id = 1 if liga in ("MLB", None, "") else 23
        by_ds[(gd, sport_id)].add(gd)
        # LMB: API may group game under different date (TZ mismatch)
        if sport_id == 23:
            try:
                dt_ref = _dt.strptime(gd, "%Y-%m-%d")
                for delta in (-1, 1):
                    adj = (dt_ref + _td(days=delta)).strftime("%Y-%m-%d")
                    by_ds[(adj, sport_id)].add(adj)
            except Exception:
                pass

    for (date_str, sport_id) in by_ds:
        _fetch_for_date(date_str, sport_id)

    # Annotate games
    for g in games:
        pk = g.get("game_pk", 0)
        gd = g.get("game_date", "")
        fav = _norm(g.get("fav_team", ""))
        opp = _norm(g.get("opp_team", ""))
        key = (gd, opp, fav)
        ls_data = None
        if pk and pk in _ls_cache and isinstance(_ls_cache[pk], dict):
            ls_data = _ls_cache[pk]
        elif key in _ls_cache:
            ls_data = _ls_cache[key]
        else:
            # Fallback: search by team names ignoring date (handles LMB date mismatch)
            for ck, cd in _ls_cache.items():
                if not isinstance(ck, tuple) or len(ck) != 3:
                    continue
                _, cat, cht = ck
                if (opp in cat or cat in opp) and (fav in cht or cht in fav):
                    ls_data = cd
                    break
        if ls_data and "innings" in ls_data:
            g["linescore"] = ls_data
            if g.get("result") in ("pending", "completed", None):
                g["status_emoji"] = ls_data.get("status_emoji", g.get("status_emoji", "⏳"))
                g["result"] = ls_data.get("result", g.get("result", "pending"))
                g["state"] = ls_data.get("state", g.get("state", ""))
            # Update score_fav/score_opp if empty (LMB: ESPN doesn't have data)
            if not g.get("score_fav"):
                a_name = _norm(ls_data.get("away_team_name", ""))
                h_name = _norm(ls_data.get("home_team_name", ""))
                a_runs = ls_data.get("away_runs", 0)
                h_runs = ls_data.get("home_runs", 0)
                if fav in h_name or h_name in fav:
                    g["score_fav"] = str(h_runs)
                    g["score_opp"] = str(a_runs)
                else:
                    g["score_fav"] = str(a_runs)
                    g["score_opp"] = str(h_runs)
            # Recompute win/loss from scores when result is still "completed"
            if g.get("result") == "completed":
                try:
                    sf = float(g.get("score_fav", 0) or 0)
                    so = float(g.get("score_opp", 0) or 0)
                    if sf > so:
                        g["result"] = "win"
                        g["status_emoji"] = "✅"
                    elif so > sf:
                        g["result"] = "loss"
                        g["status_emoji"] = "❌"
                except (ValueError, TypeError):
                    pass


# ─── Basketball helpers (NBA + WNBA) ──────────────────────────────────────


def _get_espn_nfl_scoreboard(game_date: str) -> list:
    """Consulta ESPN NFL y retorna lista de partidos con spread, O/U, moneyline."""
    try:
        date_str = game_date.replace("-", "")
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={date_str}"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        games = []
        for ev in r.json().get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            h = next((c for c in competitors if c.get("homeAway") == "home"), None)
            a = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not h or not a:
                continue
            h_team = h.get("team", {})
            a_team = a.get("team", {})
            h_name = h_team.get("displayName", "")
            a_name = a_team.get("displayName", "")
            h_abbr = h_team.get("abbreviation", "")
            a_abbr = a_team.get("abbreviation", "")
            status_type = comp.get("status", {}).get("type", {})
            detail    = status_type.get("detail", "")
            completed = status_type.get("completed", False)
            state_val = status_type.get("state", "")
            clock     = comp.get("status", {}).get("displayClock", "")
            period    = comp.get("status", {}).get("period", 0)
            a_score   = int(a.get("score", 0) or 0)
            h_score   = int(h.get("score", 0) or 0)
            is_live   = state_val == "in"
            is_pre    = state_val == "pre"
            is_post   = state_val == "post"
            POSTPONED = {"postponed", "cancelled", "canceled", "suspended", "ppd"}
            postponed = any(k in detail.lower() for k in POSTPONED)
            status_emoji = "🚫" if postponed else ("🔴" if is_live else ("🏁" if completed else "⏳"))
            result = "postponed" if postponed else ("live" if is_live else ("completed" if completed else "pending"))
            quarter_label = ""
            if is_live:
                if period <= 4:
                    quarter_label = f"Q{period}"
                else:
                    quarter_label = "OT"
                quarter_label += " " + clock
            elif completed:
                quarter_label = "Final"
            elif is_pre:
                quarter_label = detail if detail else "Pend."
            else:
                quarter_label = detail if detail else "Pend."
            odds = comp.get("odds") or []
            odds_data = odds[0] if odds else {}
            spread_details = odds_data.get("details", "")
            over_under = odds_data.get("overUnder", "")
            ml_home = ""
            ml_away = ""
            ml_raw = odds_data.get("moneyline", {})
            if ml_raw:
                ml_home = ml_raw.get("home", {}).get("close", {}).get("odds", "")
                ml_away = ml_raw.get("away", {}).get("close", {}).get("odds", "")
            h_record = h.get("records", [])
            a_record = a.get("records", [])
            h_rec_str = ""
            a_rec_str = ""
            if h_record:
                h_rec_str = h_record[0].get("summary", "")
            if a_record:
                a_rec_str = a_record[0].get("summary", "")
            espn_pk = int(ev.get("id", 0) or 0)
            week_info = ev.get("week", {})
            week_num = week_info.get("number", 0)
            season_info = ev.get("season", {})
            season_year = season_info.get("year", 0)
            season_type = season_info.get("type", 0)
            games.append({
                "game_date": game_date,
                "espn_pk": espn_pk,
                "a_name": a_name, "h_name": h_name,
                "a_abbr": a_abbr, "h_abbr": h_abbr,
                "a_score": a_score, "h_score": h_score,
                "clock": clock, "period": period,
                "is_live": is_live, "is_pre": is_pre, "is_post": is_post,
                "completed": completed, "postponed": postponed,
                "status_emoji": status_emoji, "result": result,
                "quarter_label": quarter_label,
                "spread_details": spread_details,
                "over_under": over_under,
                "ml_home": ml_home, "ml_away": ml_away,
                "h_record": h_rec_str, "a_record": a_rec_str,
                "week_num": week_num, "season_year": season_year,
                "season_type": season_type,
            })
        return games
    except Exception:
        return []


def _get_espn_basketball_scoreboard(game_date: str, sport: str = "nba") -> list:
    """
    Consulta ESPN basketball (nba o wnba) y retorna lista de partidos con periodos.
    """
    try:
        date_str = game_date.replace("-", "")
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard?dates={date_str}"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []

        liga = "WNBA" if sport == "wnba" else "NBA"
        games = []
        for ev in r.json().get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            h = next((c for c in competitors if c.get("homeAway") == "home"), None)
            a = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not h or not a:
                continue
            h_name = h.get("team", {}).get("displayName", "")
            a_name = a.get("team", {}).get("displayName", "")
            h_abbr = h.get("team", {}).get("abbreviation", "")
            a_abbr = a.get("team", {}).get("abbreviation", "")

            status_type = comp.get("status", {}).get("type", {})
            detail    = status_type.get("detail", "")
            completed = status_type.get("completed", False)
            state_val = status_type.get("state", "")
            clock     = comp.get("status", {}).get("displayClock", "")
            period    = comp.get("status", {}).get("period", 0)

            a_runs    = int(a.get("score", 0) or 0)
            h_runs    = int(h.get("score", 0) or 0)
            is_live   = state_val == "in"
            is_pre    = state_val == "pre"
            POSTPONED = {"postponed", "cancelled", "canceled", "suspended", "ppd"}
            is_post   = any(k in detail.lower() for k in POSTPONED)
            espn_pk = int(ev.get("id", 0) or 0)

            status_emoji = "🚫" if is_post else ("🔴" if is_live else ("🏁" if completed else "⏳"))
            result = "postponed" if is_post else ("live" if is_live else ("completed" if completed else "pending"))
            state = ("Q" + str(period) + " " + clock) if is_live else ("Posp." if is_post else ("Final" if completed else "Pend."))

            def _get_linescores(comp):
                raw = comp.get("linescores") or []
                return [{"period": p.get("period", i+1), "value": int(p.get("value", 0) or 0), "display": p.get("displayValue", "0")} for i, p in enumerate(raw)]
            a_line = _get_linescores(a)
            h_line = _get_linescores(h)

            games.append({
                "game_date": game_date,
                "espn_pk": espn_pk,
                "a_name": a_name, "h_name": h_name,
                "a_abbr": a_abbr, "h_abbr": h_abbr,
                "a_runs": a_runs, "h_runs": h_runs,
                "a_linescores": a_line,
                "h_linescores": h_line,
                "clock": clock, "period": period,
                "is_live": is_live, "is_pre": is_pre, "is_post": is_post, "completed": completed,
                "status_emoji": status_emoji,
                "result": result,
                "state": state,
                "liga": liga,
            })
        return games
    except Exception:
        return []


HITS_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hits_board_cache.json")


def _build_hits_board(live_games: dict = None) -> dict:
    """Genera top 3 hitters por equipo separado por liga.
    Retorna {"MLB": {"Equipo": [{...}, ...]}, "LMB": {...}}."""
    import time

    try:
        if os.path.exists(HITS_CACHE_PATH):
            cache_age = time.time() - os.path.getmtime(HITS_CACHE_PATH)
            if cache_age < 900:
                with open(HITS_CACHE_PATH, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if cached:
                    logger.info(f"Hits board desde cache ({cache_age:.0f}s)")
                    if live_games:
                        from generar_hits_xlsx import actualizar_hits_en_vivo
                        for liga in ("MLB", "LMB"):
                            if cached.get(liga):
                                cached[liga] = actualizar_hits_en_vivo(cached[liga], live_games)
                    return cached
    except Exception:
        pass

    board = {"MLB": {}, "LMB": {}}
    for attempt in range(2):
        try:
            from generar_hits_xlsx import top_hits_por_equipo, actualizar_hits_en_vivo
            raw = top_hits_por_equipo()
            if raw:
                board = raw
                if live_games:
                    for liga in ("MLB", "LMB"):
                        if board.get(liga):
                            board[liga] = actualizar_hits_en_vivo(board[liga], live_games)
                try:
                    with open(HITS_CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(board, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                return board
            if attempt == 0:
                logger.warning("Hits board vacío, reintentando en 3s...")
                time.sleep(3)
        except Exception as e:
            logger.warning(f"Intento {attempt + 1} hits_board falló: {e}")
            if attempt == 0:
                time.sleep(3)

    try:
        if os.path.exists(HITS_CACHE_PATH):
            with open(HITS_CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached:
                logger.info("Usando hits_board_cache.json stale como fallback")
                return cached
    except Exception as e:
        logger.warning(f"Error leyendo cache hits: {e}")

    return {"MLB": {}, "LMB": {}}


LLM_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_cache.json")


def _load_llm_cache() -> dict:
    if not os.path.exists(LLM_CACHE_PATH):
        return {}
    try:
        with open(LLM_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_llm_cache(cache: dict):
    try:
        with open(LLM_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando LLM cache: {e}")


LLM_PERSISTENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_persistent.json")

def _load_llm_from_files() -> dict:
    """Carga análisis LLM desde archivo persistente. Key: {sport}_{date}_{team1}_{team2}
    Si el archivo local falla, intenta descargar desde GitHub (llm_backup.json)."""
    if os.path.exists(LLM_PERSISTENT_PATH):
        try:
            with open(LLM_PERSISTENT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.warning("llm_persistent.json corrupto — intentando recovery desde GitHub")
    else:
        logger.info("llm_persistent.json no encontrado — intentando descarga desde GitHub")
    # Fallback: descargar backup desde GitHub
    try:
        backup_url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/llm_backup.json"
        r = requests.get(backup_url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            logger.info(f"LLM recovery desde GitHub: {len(data)} entradas")
            # Guardar localmente para futuros usos
            with open(LLM_PERSISTENT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return data
        else:
            logger.warning(f"No se pudo recuperar LLM desde GitHub: HTTP {r.status_code}")
    except Exception as e:
        logger.warning(f"Error recovery LLM desde GitHub: {e}")
    return {}

def _save_llm_to_file(file_key: str, ir: str, pq: str, factores: list, favorito: str, sport: str,
                       goles: str = "", corners=0, tiros_porteria: list = None, lineas: dict = None,
                       ranking_local: str = "", ranking_visitante: str = "",
                       puntos_local=None, puntos_visitante=None, spread=None,
                       confianza_ou=None, linea_ou=None, b2b_impacto="", lesion_clave="",
                       jugadores_clave=None,
                       carreras_esperadas="", abridor_local="", abridor_visitante="",
                       bateadores_clave=None, relevo_local="", relevo_visitante="",
                       stats_comparison=None, lineas_ou=None,
                       anotadores=None, defensores=None, armadores=None):
    """Guarda un resultado LLM al archivo persistente."""
    data = _load_llm_from_files()
    entry = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito, "sport": sport}
    if sport == "soccer":
        entry["goles"] = goles
        entry["corners"] = corners
        entry["tiros_porteria"] = tiros_porteria or []
        entry["lineas"] = lineas or {}
        entry["ranking_local"] = ranking_local
        entry["ranking_visitante"] = ranking_visitante
    if sport == "nba":
        entry["puntos_local"] = puntos_local
        entry["puntos_visitante"] = puntos_visitante
        entry["spread"] = spread
        entry["confianza_ou"] = confianza_ou
        entry["linea_ou"] = linea_ou
        entry["b2b_impacto"] = b2b_impacto
        entry["lesion_clave"] = lesion_clave
        entry["jugadores_clave"] = jugadores_clave or []
        entry["anotadores"] = anotadores or []
        entry["defensores"] = defensores or []
        entry["armadores"] = armadores or []
        entry["ranking_local"] = ranking_local
        entry["ranking_visitante"] = ranking_visitante
        entry["stats_comparison"] = stats_comparison or {}
        entry["lineas_ou"] = lineas_ou or {}
    if sport == "nfl":
        entry["puntos_local"] = puntos_local
        entry["puntos_visitante"] = puntos_visitante
        entry["spread"] = spread
        entry["confianza_ou"] = confianza_ou
        entry["over_under"] = linea_ou
        entry["jugadores_clave"] = jugadores_clave or []
        entry["ranking_local"] = ranking_local
        entry["ranking_visitante"] = ranking_visitante
        entry["stats_comparison"] = stats_comparison or {}
    if sport == "baseball":
        entry["carreras_esperadas"] = carreras_esperadas
        entry["carreras_lineas"] = lineas or {}
        entry["ranking_local"] = ranking_local
        entry["ranking_visitante"] = ranking_visitante
        entry["abridor_local"] = abridor_local
        entry["abridor_visitante"] = abridor_visitante
        entry["bateadores_clave"] = bateadores_clave or []
        entry["relevo_local"] = relevo_local
        entry["relevo_visitante"] = relevo_visitante
    data[file_key] = entry
    try:
        with open(LLM_PERSISTENT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando LLM persistente: {e}")


def _apply_nba_llm_fields(game: dict, entry: dict):
    """Apply NBA-specific LLM fields from a cache/file entry onto a game dict."""
    if entry.get("puntos_local") is not None:
        game["llm_puntos_local"] = entry["puntos_local"]
    if entry.get("puntos_visitante") is not None:
        game["llm_puntos_visitante"] = entry["puntos_visitante"]
    if entry.get("spread") is not None:
        game["llm_spread"] = entry["spread"]
    if entry.get("confianza_ou") is not None:
        game["llm_confianza_ou"] = entry["confianza_ou"]
    if entry.get("linea_ou") is not None:
        game["llm_linea_ou"] = entry["linea_ou"]
    if entry.get("b2b_impacto"):
        game["llm_b2b_impacto"] = entry["b2b_impacto"]
    if entry.get("lesion_clave"):
        game["llm_lesion_clave"] = entry["lesion_clave"]
    if entry.get("jugadores_clave"):
        game["llm_jugadores_clave"] = entry["jugadores_clave"]
    if entry.get("anotadores"):
        game["llm_anotadores"] = entry["anotadores"]
    if entry.get("defensores"):
        game["llm_defensores"] = entry["defensores"]
    if entry.get("armadores"):
        game["llm_armadores"] = entry["armadores"]
    if entry.get("ranking_local"):
        game["llm_ranking_local"] = entry["ranking_local"]
    if entry.get("ranking_visitante"):
        game["llm_ranking_visitante"] = entry["ranking_visitante"]
    if entry.get("stats_comparison"):
        game["llm_stats_comparison"] = entry["stats_comparison"]
    if entry.get("lineas_ou"):
        game["llm_lineas_ou"] = entry["lineas_ou"]


def _apply_baseball_llm_fields(game: dict, entry: dict):
    """Apply baseball-specific LLM fields from a cache/file entry onto a game dict."""
    if entry.get("carreras_esperadas"):
        game["llm_carreras"] = entry["carreras_esperadas"]
    if entry.get("carreras_lineas"):
        game["llm_carreras_lineas"] = entry["carreras_lineas"]
    if entry.get("ranking_local"):
        game["llm_ranking_local"] = entry["ranking_local"]
    if entry.get("ranking_visitante"):
        game["llm_ranking_visitante"] = entry["ranking_visitante"]
    if entry.get("abridor_local"):
        game["llm_abridor_local"] = entry["abridor_local"]
    if entry.get("abridor_visitante"):
        game["llm_abridor_visitante"] = entry["abridor_visitante"]
    if entry.get("bateadores_clave"):
        game["llm_bateadores_clave"] = entry["bateadores_clave"]
    if entry.get("relevo_local"):
        game["llm_relevo_local"] = entry["relevo_local"]
    if entry.get("relevo_visitante"):
        game["llm_relevo_visitante"] = entry["relevo_visitante"]


def _build_nba_llm_entry(ir: str, pq: str, factores: list, favorito: str, extra: dict) -> dict:
    """Build an NBA llm_data entry dict combining base fields + extra NBA fields."""
    entry = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito}
    for k in ("puntos_local", "puntos_visitante", "spread", "confianza_ou", "linea_ou", "b2b_impacto", "lesion_clave", "jugadores_clave", "anotadores", "defensores", "armadores", "ranking_local", "ranking_visitante", "stats_comparison", "lineas_ou"):
        if extra.get(k) is not None:
            entry[k] = extra[k]
    return entry


def _fetch_basketball_team_context(need_nba_games):
    """
    Fetch real team season stats + records + leaders from ESPN for NBA/WNBA games
    that need fresh LLM analysis. Returns dict: team_name -> {records, stats, leaders}.
    """
    groups = {}
    for item in need_nba_games:
        sport = "wnba" if item.get("liga", "NBA") == "WNBA" else "nba"
        gd = item["game"].get("game_date", "")
        groups.setdefault((sport, gd), set()).add((item["game"].get("home", ""), item["game"].get("away", "")))

    team_context = {}
    for (sport, game_date), _ in groups.items():
        if not game_date:
            continue
        date_str = game_date.replace("-", "")
        try:
            r = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard?dates={date_str}",
                timeout=15, headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code != 200:
                continue
            data = r.json()
            for ev in data.get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                for c in comp.get("competitors", []):
                    team_name = c.get("team", {}).get("displayName", "")
                    team_id = c.get("team", {}).get("id", "")
                    if not team_id or not team_name or team_name in team_context:
                        continue

                    records_parts = []
                    for rec in c.get("records", []):
                        records_parts.append(f"{rec.get('type', '')}: {rec.get('summary', '')}")
                    records_text = " | ".join(records_parts)

                    leaders_parts = []
                    for l in c.get("leaders", []):
                        ld = l.get("leaders", [{}])[0]
                        athlete = ld.get("athlete", {})
                        val = ld.get("value", "")
                        leaders_parts.append(f"{l.get('name', '')}: {athlete.get('displayName', '')} ({val})")
                    leaders_text = " | ".join(leaders_parts)

                    stats_text = ""
                    try:
                        r2 = requests.get(
                            f"https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams/{team_id}/statistics",
                            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
                        )
                        if r2.status_code == 200:
                            stats_data = r2.json()
                            cats = stats_data.get("results", {}).get("stats", {}).get("categories", [])
                            summary = {}
                            for cat in cats:
                                for s in cat.get("stats", []):
                                    if isinstance(s, dict) and s.get("displayValue"):
                                        summary[s["name"]] = s["displayValue"]
                            stat_parts = []
                            for key, label in (
                                ("avgPoints", "PPG"), ("fieldGoalPct", "FG%"), ("threePointPct", "3P%"),
                                ("freeThrowPct", "FT%"), ("avgRebounds", "REB"), ("avgAssists", "AST"),
                                ("avgTurnovers", "TOV"), ("avgSteals", "STL"), ("avgBlocks", "BLK"),
                                ("avgOffensiveRebounds", "OREB"), ("avgDefensiveRebounds", "DREB"),
                                ("scoringEfficiency", "Eff"),
                            ):
                                if summary.get(key):
                                    stat_parts.append(f"{label}: {summary[key]}")
                            if summary.get("avgFieldGoalsMade") and summary.get("avgFieldGoalsAttempted"):
                                stat_parts.append(f"FGM/A: {summary['avgFieldGoalsMade']}-{summary['avgFieldGoalsAttempted']}")
                            stats_text = " | ".join(stat_parts)
                    except Exception:
                        pass

                    team_context[team_name] = {
                        "records": records_text,
                        "stats": stats_text,
                        "leaders": leaders_text,
                    }
        except Exception:
            continue
    return team_context


def _save_llm_to_csv(ir: str, pq: str, factores: list, game: dict):
    """Guarda el resultado LLM en el CSV para el partido indicado."""
    import csv, os
    import data_manager as dm
    csv_path = getattr(config, "CSV_PATH", os.path.join(os.path.dirname(__file__), "apuestas.csv"))
    if not os.path.exists(csv_path):
        return
    # Asegurar que las columnas LLM existan
    dm.inicializar_csv()
    try:
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cols = list(reader.fieldnames or [])
            rows = list(reader)
        game_pk = game.get("game_pk", 0)
        game_date = (game.get("game_date") or "").strip()
        fav = (game.get("fav_team") or "").strip()
        opp = (game.get("opp_team") or "").strip()
        from datetime import datetime as _dt, date as _d
        # Normalizar fecha ISO → DD/MM/YYYY para match CSV
        csv_fecha = ""
        try:
            csv_fecha = _dt.strptime(game_date[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            pass
        updated = False
        for row in rows:
            match = False
            if game_pk and str(row.get("id_partido", "")).strip() == str(game_pk):
                match = True
            elif csv_fecha and fav and opp:
                row_fav = (row.get("favorito_sabermetrico") or "").strip().lower()
                row_local = (row.get("equipo_local") or "").strip().lower()
                row_visit = (row.get("equipo_visitante") or "").strip().lower()
                row_fecha = (row.get("fecha_hora") or "").strip()[:10]
                if row_fecha == csv_fecha:
                    if (fav.lower() in row_local or row_local in fav.lower()) and \
                       (opp.lower() in row_visit or row_visit in opp.lower()):
                        match = True
                    elif (fav.lower() in row_visit or row_visit in fav.lower()) and \
                         (opp.lower() in row_local or row_local in opp.lower()):
                        match = True
            if match:
                row["llm_ir_favorito"] = ir
                row["llm_porque"] = pq
                row["llm_factores"] = json.dumps(factores, ensure_ascii=False) if factores else ""
                row["resultado_llm"] = dm._computar_resultado_llm(ir, row.get("resultado", "pendiente"))
                # Guardar campos detallados del LLM para comparar predicción vs resultado
                row["llm_carreras"] = game.get("llm_carreras", "")
                row["llm_carreras_lineas"] = json.dumps(game.get("llm_carreras_lineas", {}), ensure_ascii=False) if game.get("llm_carreras_lineas") else ""
                row["llm_ranking_local"] = str(game.get("llm_ranking_local", ""))
                row["llm_ranking_visitante"] = str(game.get("llm_ranking_visitante", ""))
                row["llm_abridor_local"] = game.get("llm_abridor_local", "")
                row["llm_abridor_visitante"] = game.get("llm_abridor_visitante", "")
                row["llm_bateadores_clave"] = json.dumps(game.get("llm_bateadores_clave", []), ensure_ascii=False) if game.get("llm_bateadores_clave") else ""
                row["llm_relevo_local"] = game.get("llm_relevo_local", "")
                row["llm_relevo_visitante"] = game.get("llm_relevo_visitante", "")
                updated = True
        if updated:
            # Asegurar que las columnas LLM estén en fieldnames
            llm_cols = ["llm_ir_favorito", "llm_porque", "llm_factores", "resultado_llm",
                        "llm_carreras", "llm_carreras_lineas", "llm_ranking_local", "llm_ranking_visitante",
                        "llm_abridor_local", "llm_abridor_visitante", "llm_bateadores_clave",
                        "llm_relevo_local", "llm_relevo_visitante"]
            for c in llm_cols:
                if c not in cols:
                    cols.append(c)
            import csv as _csv_out
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = _csv_out.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)
            logger.info(f"CSV actualizado con LLM: {fav} vs {opp}")
    except Exception as e:
        logger.warning(f"Error guardando LLM en CSV: {e}")


def _inject_llm_analysis(games: list[dict], llm_data: dict = None):
    """Inyecta análisis LLM a juegos de béisbol (MLB/LMB), fútbol y NBA.
    Flujo: 1) Cargar desde archivos persistentes, 2) Si falta, llamar LLM, 3) Guardar a archivos."""
    cache = _load_llm_cache()
    today = datetime.now().strftime("%Y-%m-%d")
    total_inyectado = 0

    # ── Cargar LLM previo desde archivos persistentes ──
    llm_from_files = _load_llm_from_files()

    # ── Béisbol (MLB/LMB) ──
    baseball_games = [g for g in games if g.get("liga") in ("MLB", "LMB") and g.get("fav_team")]
    need_llm_baseball = []
    for g in baseball_games:
        away = g.get("opp_team", "")
        fav = g.get("fav_team", "")
        liga = g.get("liga", "")
        game_date = (g.get("game_date") or "")[:10]
        is_today_game = (game_date == today)
        key = f"{today}_{liga}_{fav}_{away}"
        file_key = f"{liga}_{today}_{fav}_{away}"

        # Buscar en archivos persistentes primero
        if file_key in llm_from_files:
            entry = llm_from_files[file_key]
            ir = entry.get("ir", "")
            pq = entry.get("pq", "")
            factores = entry.get("factores", [])
            favorito_f = entry.get("favorito", "")
            if not is_today_game:
                continue
            g["llm_ir_favorito"] = ir
            g["llm_porque"] = pq
            g["llm_factores"] = factores
            if favorito_f:
                g["llm_favorito"] = favorito_f
            _apply_baseball_llm_fields(g, entry)
            # Ensure all baseball-specific fields exist with defaults
            for fld, dfl in [("llm_carreras",""),("llm_carreras_lineas",{}),("llm_ranking_local",""),
                             ("llm_ranking_visitante",""),("llm_abridor_local",""),("llm_abridor_visitante",""),
                             ("llm_bateadores_clave",[]),("llm_relevo_local",""),("llm_relevo_visitante","")]:
                g.setdefault(fld, dfl)
            if llm_data is not None:
                llm_key_b = f"{g.get('game_date', today)}___{liga}___{g.get('home_team', fav)}___{g.get('away_team', away)}"
                llm_data[llm_key_b] = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_f,
                                       "carreras_esperadas": g.get("llm_carreras", ""),
                                       "carreras_lineas": g.get("llm_carreras_lineas", {}),
                                       "ranking_local": g.get("llm_ranking_local", ""),
                                       "ranking_visitante": g.get("llm_ranking_visitante", ""),
                                       "abridor_local": g.get("llm_abridor_local", ""),
                                       "abridor_visitante": g.get("llm_abridor_visitante", ""),
                                       "bateadores_clave": g.get("llm_bateadores_clave", []),
                                       "relevo_local": g.get("llm_relevo_local", ""),
                                       "relevo_visitante": g.get("llm_relevo_visitante", "")}
            cache[key] = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_f}
            home = g.get("home_team") or g.get("fav_team", "")
            away_t = g.get("away_team") or g.get("opp_team", "")
            _save_llm_to_csv(ir, pq, factores, g)
            # If today's game lacks enriched fields (old format), analyze once to migrate
            bk = g.get("llm_bateadores_clave") or []
            needs_migration = (not g.get("llm_carreras") or len(bk) < 4 or
                               (len(bk) > 0 and not any(b.get("confianza_bateo") for b in bk)))
            if needs_migration:
                need_llm_baseball.append({"game": g, "key": key, "file_key": file_key, "partido": f"{home} vs {away_t} ({g.get('game_date', today)})", "match_key": f"{home} vs {away_t}", "liga": liga, "datos": {}, "sport": "baseball"})
            continue

        if key in cache:
            ir = cache[key].get("ir", "")
            pq = cache[key].get("pq", "")
            factores = cache[key].get("factores", [])
            favorito_cache = cache[key].get("favorito", "")
            if not is_today_game:
                continue
            g["llm_ir_favorito"] = ir
            g["llm_porque"] = pq
            g["llm_factores"] = factores
            if favorito_cache:
                g["llm_favorito"] = favorito_cache
            _apply_baseball_llm_fields(g, cache[key])
            # Ensure all baseball-specific fields exist with defaults
            for fld, dfl in [("llm_carreras",""),("llm_carreras_lineas",{}),("llm_ranking_local",""),
                             ("llm_ranking_visitante",""),("llm_abridor_local",""),("llm_abridor_visitante",""),
                             ("llm_bateadores_clave",[]),("llm_relevo_local",""),("llm_relevo_visitante","")]:
                g.setdefault(fld, dfl)
            if llm_data is not None:
                llm_key_b = f"{g.get('game_date', today)}___{liga}___{g.get('home_team', fav)}___{g.get('away_team', away)}"
                llm_data[llm_key_b] = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_cache,
                                       "carreras_esperadas": g.get("llm_carreras", ""),
                                       "carreras_lineas": g.get("llm_carreras_lineas", {}),
                                       "ranking_local": g.get("llm_ranking_local", ""),
                                       "ranking_visitante": g.get("llm_ranking_visitante", ""),
                                       "abridor_local": g.get("llm_abridor_local", ""),
                                       "abridor_visitante": g.get("llm_abridor_visitante", ""),
                                       "bateadores_clave": g.get("llm_bateadores_clave", []),
                                       "relevo_local": g.get("llm_relevo_local", ""),
                                       "relevo_visitante": g.get("llm_relevo_visitante", "")}
            _save_llm_to_file(file_key, ir, pq, factores, favorito_cache, "baseball",
                              carreras_esperadas=g.get("llm_carreras", ""),
                              lineas=g.get("llm_carreras_lineas", {}),
                              ranking_local=g.get("llm_ranking_local", ""),
                              ranking_visitante=g.get("llm_ranking_visitante", ""),
                              abridor_local=g.get("llm_abridor_local", ""),
                              abridor_visitante=g.get("llm_abridor_visitante", ""),
                              bateadores_clave=g.get("llm_bateadores_clave", []),
                              relevo_local=g.get("llm_relevo_local", ""),
                              relevo_visitante=g.get("llm_relevo_visitante", ""))
            _save_llm_to_csv(ir, pq, factores, g)
            bk = g.get("llm_bateadores_clave") or []
            needs_migration = (not g.get("llm_carreras") or len(bk) < 4 or
                               (len(bk) > 0 and not any(b.get("confianza_bateo") for b in bk)))
            if needs_migration:
                need_llm_baseball.append({"game": g, "key": key, "file_key": file_key, "partido": f"{home} vs {away_t} ({g.get('game_date', today)})", "match_key": f"{home} vs {away_t}", "liga": liga, "datos": {}, "sport": "baseball"})
            continue

        # Fallback: not in persistent file or cache → add to need_* for fresh analysis (today only)
        if is_today_game and (not g.get("llm_ir_favorito") or not g.get("llm_carreras")):
            datos = {}
            is_final = g.get("result") in ("win", "loss", "completed")
            if not is_final:
                if g.get("score_fav") and g.get("score_opp"):
                    datos["marcador"] = f"{g['score_fav']}-{g['score_opp']}"
                if g.get("result"):
                    datos["resultado"] = g["result"]
            home = g.get("home_team") or g.get("fav_team", "")
            away_t = g.get("away_team") or g.get("opp_team", "")
            need_llm_baseball.append({"game": g, "key": key, "file_key": file_key, "partido": f"{home} vs {away_t} ({g.get('game_date', today)})", "match_key": f"{home} vs {away_t}", "liga": liga, "datos": datos, "sport": "baseball"})

    # ── Fútbol (soccer_data) ──
    soccer_games = [g for g in games if g.get("liga_key") and g.get("local") and g.get("visitante")]
    need_llm_soccer = []
    for g in soccer_games:
        home = g.get("local", "")
        away = g.get("visitante", "")
        favorito = g.get("favorito", "")
        liga = g.get("liga_key", "FUTBOL")
        key = f"{today}_FUTBOL_{home}_{away}"
        file_key = f"FUTBOL_{today}_{home}_{away}"
        fecha_key = g.get("fecha_partido", g.get("game_date", today))

        if favorito:
            fav_first = favorito
            opp_first = away if favorito == home else home
        else:
            fav_first = home
            opp_first = away

        if file_key in llm_from_files:
            entry = llm_from_files[file_key]
            ir = entry.get("ir", "")
            pq = entry.get("pq", "")
            factores = entry.get("factores", [])
            favorito_f = entry.get("favorito", "")
            goles_f = entry.get("goles", "")
            corners_f = entry.get("corners", 0)
            tiros_f = entry.get("tiros_porteria", [])
            lineas_f = entry.get("lineas", {})
            ranking_loc = entry.get("ranking_local", "")
            ranking_vis = entry.get("ranking_visitante", "")
            g["llm_ir_favorito"] = ir
            g["llm_porque"] = pq
            g["llm_factores"] = factores
            g["llm_goles"] = goles_f
            g["llm_corners_est"] = corners_f
            g["llm_tiros_porteria"] = tiros_f
            g["llm_lineas"] = lineas_f
            if favorito_f:
                g["llm_favorito"] = favorito_f
            if llm_data is not None:
                llm_key = f"{fecha_key}___{home}___{away}"
                llm_analysis_entry = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_f,
                                      "goles": goles_f, "corners": corners_f, "tiros_porteria": tiros_f,
                                      "lineas": lineas_f, "ranking_local": ranking_loc, "ranking_visitante": ranking_vis}
                llm_data[llm_key] = llm_analysis_entry
            cache[key] = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_f,
                          "goles": goles_f, "corners": corners_f, "tiros_porteria": tiros_f,
                          "lineas": lineas_f, "ranking_local": ranking_loc, "ranking_visitante": ranking_vis}
            # Save to XLSX for soccer
            if g.get("id_partido"):
                try:
                    from futbol_bot.data_manager import guardar_llm_soccer
                    guardar_llm_soccer(g["id_partido"], favorito_f, ir, goles_f, corners_f, tiros_f,
                                       porque=pq, factores=factores, lineas=lineas_f,
                                       ranking_local=ranking_loc, ranking_visitante=ranking_vis)
                except Exception:
                    pass
            continue

        if key in cache:
            ir = cache[key].get("ir", "")
            pq = cache[key].get("pq", "")
            factores = cache[key].get("factores", [])
            favorito_cache = cache[key].get("favorito", "")
            goles_c = cache[key].get("goles", "")
            corners_c = cache[key].get("corners", 0)
            tiros_c = cache[key].get("tiros_porteria", [])
            lineas_c = cache[key].get("lineas", {})
            ranking_loc = cache[key].get("ranking_local", "")
            ranking_vis = cache[key].get("ranking_visitante", "")
            g["llm_ir_favorito"] = ir
            g["llm_porque"] = pq
            g["llm_factores"] = factores
            g["llm_goles"] = goles_c
            g["llm_corners_est"] = corners_c
            g["llm_tiros_porteria"] = tiros_c
            g["llm_lineas"] = lineas_c
            if favorito_cache:
                g["llm_favorito"] = favorito_cache
            if llm_data is not None:
                llm_key = f"{fecha_key}___{home}___{away}"
                llm_analysis_entry = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_cache,
                                      "goles": goles_c, "corners": corners_c, "tiros_porteria": tiros_c,
                                      "lineas": lineas_c, "ranking_local": ranking_loc, "ranking_visitante": ranking_vis}
                llm_data[llm_key] = llm_analysis_entry
            _save_llm_to_file(file_key, ir, pq, factores, favorito_cache, "soccer",
                              goles_c, corners_c, tiros_c, lineas_c,
                              ranking_local=ranking_loc, ranking_visitante=ranking_vis)
            # Save to XLSX for soccer
            if g.get("id_partido"):
                try:
                    from futbol_bot.data_manager import guardar_llm_soccer
                    guardar_llm_soccer(g["id_partido"], favorito_cache, ir, goles_c, corners_c, tiros_c,
                                       porque=pq, factores=factores, lineas=lineas_c,
                                       ranking_local=ranking_loc, ranking_visitante=ranking_vis)
                except Exception:
                    pass
            continue

        if not g.get("llm_ir_favorito"):
            datos = {
                "local": home,
                "visitante": away,
                "fecha": g.get("fecha_partido", g.get("game_date", today)),
                "hora": g.get("hora_partido", ""),
                "liga": liga,
            }
            if g.get("xg_total") and g["xg_total"] > 0:
                datos["xG_total"] = round(g["xg_total"], 2)
                datos["diff_xG"] = round(g["diff_xg"], 2)
            if g.get("senal_ah0") and g["senal_ah0"] != "NO_APOSTAR":
                datos["señal_AH0"] = g["senal_ah0"]
            need_llm_soccer.append({"game": g, "key": key, "file_key": file_key, "partido": f"{home} vs {away} ({g.get('fecha_partido', g.get('game_date', today))})", "match_key": f"{home} vs {away}", "liga": liga, "datos": datos, "sport": "soccer", "id_partido": g.get("id_partido", "")})

    # ── NFL ──
    nfl_games = [g for g in games if g.get("liga") == "NFL" and g.get("game_id") and g.get("away") and g.get("home")]
    need_llm_nfl = []
    for g in nfl_games:
        away = g.get("away", "")
        home = g.get("home", "")
        _gdate = g.get("game_date", today)
        key = f"{_gdate}_NFL_{home}_{away}"
        file_key = f"NFL_{_gdate}_{home}_{away}"
        nba_match_key = f"{home} vs {away}"
        llm_nfl_key = f"{_gdate}___NFL___{home}___{away}"
        if file_key in llm_from_files:
            entry = llm_from_files[file_key]
            ir = entry.get("ir", "")
            pq = entry.get("pq", "")
            factores = entry.get("factores", [])
            favorito_f = entry.get("favorito", "")
            g["llm_ir_favorito"] = ir
            g["llm_porque"] = pq
            g["llm_factores"] = factores
            if favorito_f:
                g["llm_favorito"] = favorito_f
            if llm_data is not None:
                llm_analysis_entry = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_f,
                                      "spread": entry.get("spread"), "over_under": entry.get("over_under"),
                                      "puntos_local": entry.get("puntos_local"), "puntos_visitante": entry.get("puntos_visitante"),
                                      "ranking_local": entry.get("ranking_local", ""), "ranking_visitante": entry.get("ranking_visitante", ""),
                                      "stats_comparison": entry.get("stats_comparison", {}), "jugadores_clave": entry.get("jugadores_clave", [])}
                llm_data[llm_nfl_key] = llm_analysis_entry
            cache[key] = entry
            continue
        if key in cache:
            entry = cache[key]
            ir = entry.get("ir", "")
            pq = entry.get("pq", "")
            factores = entry.get("factores", [])
            favorito_f = entry.get("favorito", "")
            g["llm_ir_favorito"] = ir
            g["llm_porque"] = pq
            g["llm_factores"] = factores
            if favorito_f:
                g["llm_favorito"] = favorito_f
            if llm_data is not None:
                llm_analysis_entry = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_f,
                                      "spread": entry.get("spread"), "over_under": entry.get("over_under"),
                                      "puntos_local": entry.get("puntos_local"), "puntos_visitante": entry.get("puntos_visitante"),
                                      "ranking_local": entry.get("ranking_local", ""), "ranking_visitante": entry.get("ranking_visitante", ""),
                                      "stats_comparison": entry.get("stats_comparison", {}), "jugadores_clave": entry.get("jugadores_clave", [])}
                llm_data[llm_nfl_key] = llm_analysis_entry
            continue
        if not g.get("llm_ir_favorito"):
            datos = {
                "local": home,
                "visitante": away,
                "fecha": _gdate,
                "liga": "NFL",
                "spread": g.get("spread_details", ""),
                "over_under": g.get("over_under", ""),
                "moneyline_home": g.get("ml_home", ""),
                "moneyline_away": g.get("ml_away", ""),
                "record_local": g.get("home_record", ""),
                "record_visitante": g.get("away_record", ""),
                "semana": g.get("week_num", 0),
            }
            need_llm_nfl.append({"game": g, "key": key, "file_key": file_key, "partido": f"{home} vs {away} ({_gdate})", "match_key": nba_match_key, "liga": "NFL", "datos": datos, "sport": "nfl"})

    # ── NBA ──
    nba_games = [g for g in games if g.get("game_id") and g.get("away") and g.get("home")]
    need_llm_nba = []
    for g in nba_games:
        away = g.get("away", "")
        home = g.get("home", "")
        gliga = g.get("liga", "NBA")
        liga_pref = "WNBA" if gliga == "WNBA" else "NBA"
        _gdate = g.get('game_date', today)
        key = f"{_gdate}_{liga_pref}_{home}_{away}"
        file_key = f"{liga_pref}_{_gdate}_{home}_{away}"
        nba_match_key = f"{home} vs {away}"
        llm_nba_key = f"{g.get('game_date', today)}___{liga_pref}___{home}___{away}"

        if file_key in llm_from_files:
            entry = llm_from_files[file_key]
            ir = entry.get("ir", "")
            pq = entry.get("pq", "")
            factores = entry.get("factores", [])
            favorito_f = entry.get("favorito", "")
            g["llm_ir_favorito"] = ir
            g["llm_porque"] = pq
            g["llm_factores"] = factores
            _apply_nba_llm_fields(g, entry)
            for fld, dfl in [("llm_puntos_local",0),("llm_puntos_visitante",0),("llm_spread",0.0),
                             ("llm_confianza_ou",0),("llm_linea_ou",0.0),("llm_b2b_impacto",""),
                             ("llm_lesion_clave",""),("llm_jugadores_clave",[]),
                             ("llm_anotadores",[]),("llm_defensores",[]),("llm_armadores",[]),
                             ("llm_ranking_local",""),("llm_ranking_visitante",""),
                             ("llm_stats_comparison",{}),("llm_lineas_ou",{}),
                             ("llm_favorito","")]:
                g.setdefault(fld, dfl)
            if favorito_f:
                g["llm_favorito"] = favorito_f
            if llm_data is not None:
                llm_data[llm_nba_key] = _build_nba_llm_entry(ir, pq, factores, favorito_f, entry)
            cache[key] = _build_nba_llm_entry(ir, pq, factores, favorito_f, entry)
            # Backup to XLSX
            try:
                from basquetbol_bot.data_manager import guardar_llm_xlsx as _guardar_bb_xlsx
                _guardar_bb_xlsx(
                    str(g.get("game_id", "")), gliga, home, away,
                    favorito_f, ir,
                    entry.get("spread"), entry.get("confianza_ou"),
                    entry.get("linea_ou"),
                    entry.get("puntos_local"), entry.get("puntos_visitante"),
                    entry.get("b2b_impacto", ""), entry.get("lesion_clave", ""),
                    entry.get("pq", ""), entry.get("factores", []),
                    ranking_local=entry.get("ranking_local", ""),
                    ranking_visitante=entry.get("ranking_visitante", ""),
                    stats_comparison=entry.get("stats_comparison", {}),
                    anotadores=entry.get("anotadores", []),
                    defensores=entry.get("defensores", []),
                    armadores=entry.get("armadores", []),
                    lineas_ou=entry.get("lineas_ou", {}),
                )
            except Exception:
                pass
            # Migrate old entries that lack new enriched fields
            if g.get("llm_anotadores") is None or (isinstance(g.get("llm_anotadores"), list) and len(g["llm_anotadores"]) == 0):
                need_llm_nba.append({"game": g, "key": key, "file_key": file_key, "partido": f"{home} vs {away} ({g.get('game_date', today)})", "match_key": nba_match_key, "liga": liga_pref, "datos": {}, "sport": "nba"})
            continue

        if key in cache:
            ir = cache[key].get("ir", "")
            pq = cache[key].get("pq", "")
            factores = cache[key].get("factores", [])
            favorito_cache = cache[key].get("favorito", "")
            g["llm_ir_favorito"] = ir
            g["llm_porque"] = pq
            g["llm_factores"] = factores
            _apply_nba_llm_fields(g, cache[key])
            for fld, dfl in [("llm_puntos_local",0),("llm_puntos_visitante",0),("llm_spread",0.0),
                             ("llm_confianza_ou",0),("llm_linea_ou",0.0),("llm_b2b_impacto",""),
                             ("llm_lesion_clave",""),("llm_jugadores_clave",[]),
                             ("llm_anotadores",[]),("llm_defensores",[]),("llm_armadores",[]),
                             ("llm_ranking_local",""),("llm_ranking_visitante",""),
                             ("llm_stats_comparison",{}),("llm_lineas_ou",{})]:
                g.setdefault(fld, dfl)
            if favorito_cache:
                g["llm_favorito"] = favorito_cache
            if llm_data is not None:
                llm_data[llm_nba_key] = _build_nba_llm_entry(ir, pq, factores, favorito_cache, cache[key])
            _save_llm_to_file(file_key, ir, pq, factores, favorito_cache, "nba",
                              puntos_local=g.get("llm_puntos_local"),
                              puntos_visitante=g.get("llm_puntos_visitante"),
                              spread=g.get("llm_spread"),
                              confianza_ou=g.get("llm_confianza_ou"),
                              linea_ou=g.get("llm_linea_ou"),
                              b2b_impacto=g.get("llm_b2b_impacto"),
                              lesion_clave=g.get("llm_lesion_clave"),
                              jugadores_clave=g.get("llm_jugadores_clave", []),
                              anotadores=g.get("llm_anotadores", []),
                              defensores=g.get("llm_defensores", []),
                              armadores=g.get("llm_armadores", []),
                              ranking_local=g.get("llm_ranking_local", ""),
                              ranking_visitante=g.get("llm_ranking_visitante", ""),
                              stats_comparison=g.get("llm_stats_comparison", {}),
                               lineas_ou=g.get("llm_lineas_ou", {}))
            # Backup to XLSX
            try:
                from basquetbol_bot.data_manager import guardar_llm_xlsx as _guardar_bb_xlsx
                _guardar_bb_xlsx(
                    str(g.get("game_id", "")), gliga, home, away,
                    favorito_cache, ir,
                    g.get("llm_spread"), g.get("llm_confianza_ou"),
                    g.get("llm_linea_ou"),
                    g.get("llm_puntos_local"), g.get("llm_puntos_visitante"),
                    g.get("llm_b2b_impacto", ""), g.get("llm_lesion_clave", ""),
                    pq, factores,
                    ranking_local=g.get("llm_ranking_local", ""),
                    ranking_visitante=g.get("llm_ranking_visitante", ""),
                    stats_comparison=g.get("llm_stats_comparison", {}),
                    anotadores=g.get("llm_anotadores", []),
                    defensores=g.get("llm_defensores", []),
                    armadores=g.get("llm_armadores", []),
                    lineas_ou=g.get("llm_lineas_ou", {}),
                )
            except Exception:
                pass
            # Migrate old entries that lack new enriched fields
            if g.get("llm_anotadores") is None or (isinstance(g.get("llm_anotadores"), list) and len(g["llm_anotadores"]) == 0):
                need_llm_nba.append({"game": g, "key": key, "file_key": file_key, "partido": f"{home} vs {away} ({g.get('game_date', today)})", "match_key": nba_match_key, "liga": liga_pref, "datos": {}, "sport": "nba"})
            continue

        if not g.get("llm_ir_favorito") or g.get("llm_anotadores") is None or (isinstance(g.get("llm_anotadores"), list) and len(g["llm_anotadores"]) == 0):
            datos = {}
            is_final = g.get("result") in ("win", "loss", "completed")
            if not is_final:
                if g.get("away_score") is not None and g.get("home_score") is not None:
                    datos["marcador"] = f"{g['away_score']}-{g['home_score']}"
                if g.get("state"):
                    datos["estado"] = g["state"]
                if g.get("result"):
                    datos["resultado"] = g["result"]
                datos["home_abbr"] = g.get("home_abbr", "")
                datos["away_abbr"] = g.get("away_abbr", "")
            need_llm_nba.append({"game": g, "key": key, "file_key": file_key, "partido": f"{home} vs {away} ({g.get('game_date', today)})", "match_key": nba_match_key, "liga": liga_pref, "datos": datos, "sport": "nba"})

    # ── Enrich NBA LLM context with real team stats from ESPN ──
    if need_llm_nba:
        team_ctx = _fetch_basketball_team_context(need_llm_nba)
        for item in need_llm_nba:
            g = item["game"]
            h = g.get("home", "")
            a = g.get("away", "")
            ctx_h = team_ctx.get(h, {})
            ctx_a = team_ctx.get(a, {})
            parts = []
            if ctx_h.get("records") or ctx_a.get("records"):
                parts.append(f"RÉCORDS — Local {h}: [{ctx_h.get('records', 'N/A')}] | Visitante {a}: [{ctx_a.get('records', 'N/A')}]")
            if ctx_h.get("stats") or ctx_a.get("stats"):
                parts.append(f"LOCAL {h} stats: {ctx_h.get('stats', 'N/A')}")
                parts.append(f"VISITANTE {a} stats: {ctx_a.get('stats', 'N/A')}")
            if ctx_h.get("leaders") or ctx_a.get("leaders"):
                parts.append(f"LÍDERES {h}: {ctx_h.get('leaders', 'N/A')}")
                parts.append(f"LÍDERES {a}: {ctx_a.get('leaders', 'N/A')}")
            if parts:
                item["datos"]["contexto"] = " | ".join(parts)

    # ── LLM call (todos los deportes juntos) ──
    all_need = need_llm_baseball + need_llm_soccer + need_llm_nba
    if not all_need:
        _save_llm_cache(cache)
        return

    try:
        from llm_analyzer import analizar_partidos as llm_analizar
        partidos = [{"partido": x["partido"], "liga": x["liga"], "datos": x.get("datos", {})} for x in all_need]
        resultados = llm_analizar(partidos)

        def _fuzzy_match_llm(llm_partido: str, match_key: str) -> bool:
            """Match LLM result to game by checking if both team names appear in either order."""
            llm_lower = llm_partido.lower()
            mk_lower = match_key.lower()
            if llm_lower == mk_lower:
                return True
            # Extract team names from "Team A vs Team B"
            llm_parts = [p.strip() for p in llm_lower.split(" vs ")]
            mk_parts = [p.strip() for p in mk_lower.split(" vs ")]
            if len(llm_parts) == 2 and len(mk_parts) == 2:
                # Check if team names match (substring match for partial names)
                l0, l1 = llm_parts
                m0, m1 = mk_parts
                forward = (m0 in l0 or l0 in m0) and (m1 in l1 or l1 in m1)
                reverse = (m0 in l1 or l1 in m0) and (m1 in l0 or l0 in m1)
                return forward or reverse
            return False

        used_results = set()
        for item in all_need:
            for ri, r in enumerate(resultados):
                if ri in used_results:
                    continue
                if _fuzzy_match_llm(r.get("partido", ""), item.get("match_key", item["partido"])):
                    used_results.add(ri)
                    ir = r.get("ir_con_favorito", "N/D")
                    pq = r.get("porque", "")
                    factores = r.get("factores", [])
                    favorito_llm = r.get("favorito", "")
                    goles = r.get("goles_esperados", "")
                    corners = r.get("corners_esperados", 0)
                    tiros = r.get("tiros_porteria", [])
                    goles_lineas = r.get("goles_lineas", {})
                    corners_lineas = r.get("corners_lineas", {})
                    lineas = {"goles": goles_lineas, "corners": corners_lineas}
                    item["game"]["llm_ir_favorito"] = ir
                    item["game"]["llm_porque"] = pq
                    item["game"]["llm_factores"] = factores
                    item["game"]["llm_goles"] = goles
                    item["game"]["llm_corners_est"] = corners
                    item["game"]["llm_tiros_porteria"] = tiros
                    item["game"]["llm_lineas"] = lineas
                    if favorito_llm:
                        item["game"]["llm_favorito"] = favorito_llm
                    # NBA-specific fields
                    if item["sport"] == "nba":
                        item["game"]["llm_puntos_local"] = r.get("puntos_local")
                        item["game"]["llm_puntos_visitante"] = r.get("puntos_visitante")
                        item["game"]["llm_spread"] = r.get("spread_estimado")
                        item["game"]["llm_confianza_ou"] = r.get("confianza_over_under")
                        item["game"]["llm_linea_ou"] = r.get("linea_over_under")
                        item["game"]["llm_b2b_impacto"] = r.get("b2b_impacto", "")
                        item["game"]["llm_lesion_clave"] = r.get("lesion_clave", "")
                        item["game"]["llm_jugadores_clave"] = r.get("jugadores_clave", [])
                        item["game"]["llm_anotadores"] = r.get("anotadores", [])
                        item["game"]["llm_defensores"] = r.get("defensores", [])
                        item["game"]["llm_armadores"] = r.get("armadores", [])
                        item["game"]["llm_ranking_local"] = r.get("ranking_local", "")
                        item["game"]["llm_ranking_visitante"] = r.get("ranking_visitante", "")
                        item["game"]["llm_stats_comparison"] = r.get("stats_comparison", {})
                        item["game"]["llm_lineas_ou"] = r.get("lineas_ou", {})
                    # Baseball-specific fields
                    if item["sport"] == "baseball":
                        item["game"]["llm_carreras"] = r.get("carreras_esperadas", "")
                        item["game"]["llm_carreras_lineas"] = r.get("carreras_lineas", {})
                        item["game"]["llm_ranking_local"] = r.get("ranking_local", "")
                        item["game"]["llm_ranking_visitante"] = r.get("ranking_visitante", "")
                        item["game"]["llm_abridor_local"] = r.get("abridor_local", "")
                        item["game"]["llm_abridor_visitante"] = r.get("abridor_visitante", "")
                        item["game"]["llm_bateadores_clave"] = r.get("bateadores_clave", [])
                        item["game"]["llm_relevo_local"] = r.get("relevo_local", "")
                        item["game"]["llm_relevo_visitante"] = r.get("relevo_visitante", "")
                    cache[item["key"]] = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_llm,
                                          "goles": goles, "corners": corners, "tiros_porteria": tiros,
                                          "lineas": lineas}
                    if item["sport"] == "nba":
                        cache[item["key"]].update({
                            "jugadores_clave": item["game"].get("llm_jugadores_clave", []),
                            "anotadores": item["game"].get("llm_anotadores", []),
                            "defensores": item["game"].get("llm_defensores", []),
                            "armadores": item["game"].get("llm_armadores", []),
                            "ranking_local": item["game"].get("llm_ranking_local", ""),
                            "ranking_visitante": item["game"].get("llm_ranking_visitante", ""),
                            "stats_comparison": item["game"].get("llm_stats_comparison", {}),
                            "lineas_ou": item["game"].get("llm_lineas_ou", {}),
                        })
                    # Guardar a archivo persistente
                    extra_kw = {}
                    if item["sport"] == "baseball":
                        extra_kw = {
                            "carreras_esperadas": item["game"].get("llm_carreras", ""),
                            "ranking_local": item["game"].get("llm_ranking_local", ""),
                            "ranking_visitante": item["game"].get("llm_ranking_visitante", ""),
                            "abridor_local": item["game"].get("llm_abridor_local", ""),
                            "abridor_visitante": item["game"].get("llm_abridor_visitante", ""),
                            "bateadores_clave": item["game"].get("llm_bateadores_clave", []),
                            "relevo_local": item["game"].get("llm_relevo_local", ""),
                            "relevo_visitante": item["game"].get("llm_relevo_visitante", ""),
                        }
                    elif item["sport"] in ("nba", "nfl"):
                        extra_kw = {
                            "ranking_local": item["game"].get("llm_ranking_local", ""),
                            "ranking_visitante": item["game"].get("llm_ranking_visitante", ""),
                        }
                    _save_llm_to_file(item["file_key"], ir, pq, factores, favorito_llm, item["sport"],
                                      goles, corners, tiros,
                                      item["game"].get("llm_carreras_lineas", {}) if item["sport"] == "baseball" else lineas,
                                      puntos_local=item["game"].get("llm_puntos_local"),
                                      puntos_visitante=item["game"].get("llm_puntos_visitante"),
                                      spread=item["game"].get("llm_spread"),
                                      confianza_ou=item["game"].get("llm_confianza_ou"),
                                      linea_ou=item["game"].get("llm_linea_ou"),
                                      b2b_impacto=item["game"].get("llm_b2b_impacto"),
                                      lesion_clave=item["game"].get("llm_lesion_clave"),
                                      jugadores_clave=item["game"].get("llm_jugadores_clave", []) if item["sport"] in ("nba", "nfl") else [],
                                      anotadores=item["game"].get("llm_anotadores", []) if item["sport"] == "nba" else None,
                                      defensores=item["game"].get("llm_defensores", []) if item["sport"] == "nba" else None,
                                      armadores=item["game"].get("llm_armadores", []) if item["sport"] == "nba" else None,
                                      stats_comparison=item["game"].get("llm_stats_comparison", {}) if item["sport"] in ("nba", "nfl") else None,
                                      lineas_ou=item["game"].get("llm_lineas_ou", {}) if item["sport"] == "nba" else None,
                                      **extra_kw)
                    # Guardar a CSV para béisbol (MLB/LMB)
                    if item["sport"] == "baseball":
                        _save_llm_to_csv(ir, pq, factores, item["game"])
                    # Guardar a XLSX para fútbol
                    if item["sport"] == "soccer" and item.get("id_partido"):
                        try:
                            from futbol_bot.data_manager import guardar_llm_soccer
                            guardar_llm_soccer(item["id_partido"], favorito_llm, ir, goles, corners, tiros, pq, factores, lineas)
                        except Exception as e:
                            logger.warning(f"Error guardando LLM en XLSX soccer: {e}")
                    # Guardar a XLSX para basketball (NBA/WNBA)
                    if item["sport"] == "nba" and item["game"].get("game_id"):
                        try:
                            gliga = item["game"].get("liga", "NBA")
                            ghome = item["game"].get("home", "")
                            gaway = item["game"].get("away", "")
                            from basquetbol_bot.data_manager import guardar_llm_xlsx
                            guardar_llm_xlsx(
                                item["game"]["game_id"], gliga, ghome, gaway,
                                favorito_llm, ir,
                                r.get("spread_estimado"), r.get("confianza_over_under"),
                                r.get("linea_over_under"),
                                r.get("puntos_local"), r.get("puntos_visitante"),
                                r.get("b2b_impacto", ""), r.get("lesion_clave", ""),
                                pq, factores,
                                ranking_local=r.get("ranking_local", ""),
                                ranking_visitante=r.get("ranking_visitante", ""),
                                stats_comparison=r.get("stats_comparison"),
                                anotadores=r.get("anotadores"),
                                defensores=r.get("defensores"),
                                armadores=r.get("armadores"),
                                lineas_ou=r.get("lineas_ou"),
                            )
                        except Exception as e:
                            logger.warning(f"Error guardando LLM en XLSX basketball: {e}")
                    if llm_data is not None:
                        team = item["game"].get("local") or item["game"].get("home", "")
                        base_entry = {"ir": ir, "pq": pq, "factores": factores, "favorito": favorito_llm,
                                      "goles": goles, "corners": corners, "tiros_porteria": tiros,
                                      "lineas": lineas}
                        if item["sport"] == "nba":
                            gliga = item["game"].get("liga", "NBA")
                            liga_p = "WNBA" if gliga == "WNBA" else "NBA"
                            llm_key = f"{item['game'].get('game_date', today)}___{liga_p}___{item['game'].get('home','')}___{item['game'].get('away','')}"
                            base_entry.update({
                                "puntos_local": item["game"].get("llm_puntos_local"),
                                "puntos_visitante": item["game"].get("llm_puntos_visitante"),
                                "spread": item["game"].get("llm_spread"),
                                "confianza_ou": item["game"].get("llm_confianza_ou"),
                                "linea_ou": item["game"].get("llm_linea_ou"),
                                "b2b_impacto": item["game"].get("llm_b2b_impacto"),
                                "lesion_clave": item["game"].get("llm_lesion_clave"),
                                "jugadores_clave": item["game"].get("llm_jugadores_clave", []),
                                "anotadores": item["game"].get("llm_anotadores", []),
                                "defensores": item["game"].get("llm_defensores", []),
                                "armadores": item["game"].get("llm_armadores", []),
                                "ranking_local": item["game"].get("llm_ranking_local", ""),
                                "ranking_visitante": item["game"].get("llm_ranking_visitante", ""),
                                "stats_comparison": item["game"].get("llm_stats_comparison", {}),
                                "lineas_ou": item["game"].get("llm_lineas_ou", {}),
                            })
                            llm_data[llm_key] = base_entry
                        elif item["sport"] == "baseball":
                            llm_key = f"{item['game'].get('game_date', today)}___{item['liga']}___{item['game'].get('home_team', item['game'].get('fav_team',''))}___{item['game'].get('away_team', item['game'].get('opp_team',''))}"
                            base_entry.update({
                                "carreras_esperadas": item["game"].get("llm_carreras", ""),
                                "carreras_lineas": item["game"].get("llm_carreras_lineas", {}),
                                "ranking_local": item["game"].get("llm_ranking_local", ""),
                                "ranking_visitante": item["game"].get("llm_ranking_visitante", ""),
                                "abridor_local": item["game"].get("llm_abridor_local", ""),
                                "abridor_visitante": item["game"].get("llm_abridor_visitante", ""),
                                "bateadores_clave": item["game"].get("llm_bateadores_clave", []),
                                "relevo_local": item["game"].get("llm_relevo_local", ""),
                                "relevo_visitante": item["game"].get("llm_relevo_visitante", ""),
                            })
                            llm_data[llm_key] = base_entry
                        elif item["sport"] == "soccer":
                            llm_key = f"{item['game'].get('fecha_partido', item['game'].get('game_date', today))}___{item['game'].get('local','')}___{item['game'].get('visitante','')}"
                            llm_data[llm_key] = base_entry
                        elif item["sport"] == "nfl":
                            llm_key = f"{item['game'].get('game_date', today)}___NFL___{item['game'].get('home','')}___{item['game'].get('away','')}"
                            base_entry.update({
                                "spread": r.get("spread_estimado"),
                                "confianza_spread": r.get("confianza_spread"),
                                "over_under": r.get("over_under"),
                                "confianza_ou": r.get("confianza_ou"),
                                "puntos_local": r.get("puntos_local"),
                                "puntos_visitante": r.get("puntos_visitante"),
                                "ranking_local": r.get("ranking_local", ""),
                                "ranking_visitante": r.get("ranking_visitante", ""),
                                "stats_comparison": r.get("stats_comparison", {}),
                                "jugadores_clave": r.get("jugadores_clave", []),
                            })
                            llm_data[llm_key] = base_entry
                            _apply_nba_llm_fields(item["game"], base_entry)
                        else:
                            llm_data[team] = base_entry
                    total_inyectado += 1
                    break

        _save_llm_cache(cache)
        logger.info(f"LLM inyectado: {total_inyectado} juegos (béisbol + fútbol + NBA + NFL)")
    except ImportError:
        logger.info("LLM no disponible — omitiendo")
    except Exception as e:
        logger.error(f"Error LLM: {e}")


def _build_data(skip_llm: bool = False) -> dict:
    """Construye el JSON con partidos + stats para la Mini App.
       skip_llm=True omite el contra-análisis LLM (más rápido)."""
    from datetime import timedelta
    hoy       = datetime.now()
    ayer      = hoy - timedelta(days=1)
    anteayer  = hoy - timedelta(days=2)
    hoy_str    = hoy.strftime("%Y-%m-%d")
    ayer_str   = ayer.strftime("%Y-%m-%d")
    anteayer_str = anteayer.strftime("%Y-%m-%d")

    # ESPN scoreboard solo para días recientes (live data)
    fechas_espn = {hoy_str, ayer_str, anteayer_str}
    espn_games = []
    for f in fechas_espn:
        espn_games += _get_espn_scoreboard(f)

    # Indexar seguimiento para cruzar
    estado  = dm.cargar_estado()
    seguimiento = list(estado)

    def _norm(n):
        return n.strip().lower()

    games = []
    seen = set()

    # ── Leer CSV histórico para partidos de días anteriores ──
    import csv as _csv, os as _os, re as _re
    csv_path = config.CSV_PATH

    def _csv_date_to_iso(csv_fecha: str) -> str:
        try:
            from datetime import datetime as _dt
            s = csv_fecha.strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
                try:
                    return _dt.strptime(s, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return ""
        except Exception:
            return ""

    def _extraer_prob(val: str) -> float:
        try:
            return float(val.replace("%", "").strip())
        except (ValueError, AttributeError):
            return 0.0

    def _make_key(fecha, away, home):
        return (fecha, _norm(away), _norm(home))

    def _process_csv_row(_row: dict):
        nonlocal games, seen
        csv_fecha = _csv_date_to_iso(_row.get("fecha_hora", ""))
        if not csv_fecha:
            return
        away_csv = _row.get("equipo_visitante", "").strip()
        home_csv = _row.get("equipo_local", "").strip()
        key = _make_key(csv_fecha, away_csv, home_csv)
        if key in seen:
            return
        favorito_csv = _row.get("favorito_sabermetrico", "").strip()
        prob_csv = _extraer_prob(_row.get("probabilidad_inicial", "0"))
        mercado_str = _row.get("prob_mercado", "N/D").strip()
        mercado_csv = _extraer_prob(mercado_str)
        edge_csv = round(prob_csv - mercado_csv, 2) if mercado_str != "N/D" else None
        resultado_csv = _row.get("resultado", "").strip().lower()
        marcador = _row.get("marcador_final", "").strip()
        nivel_cert = _row.get("nivel_certidumbre", "").strip()
        if nivel_cert in ("ALTA", "MEDIA") and prob_csv >= 57.0:
            label = "🎯"
        else:
            label = "📋"
        # Buscar match en ESPN
        match = None
        for eg in espn_games:
            if eg["game_date"] != csv_fecha:
                continue
            if (_norm(away_csv) in _norm(eg["a_name"]) or _norm(eg["a_name"]) in _norm(away_csv)) and \
               (_norm(home_csv) in _norm(eg["h_name"]) or _norm(eg["h_name"]) in _norm(home_csv)):
                match = eg
                break
        if match:
            g = _espn_to_game(match, favorito_csv)
        else:
            scores = _re.findall(r'(\d+)\s*[–\-]\s*(\d+)', marcador.lower())
            if scores:
                s_a, s_h = scores[0]
            else:
                s_a, s_h = "", ""
            _fav_in_home = favorito_csv and (_norm(favorito_csv) in _norm(home_csv) or _norm(home_csv) in _norm(favorito_csv))
            fav = home_csv if _fav_in_home else away_csv
            opp = away_csv if _fav_in_home else home_csv
            s_fav = s_h if _fav_in_home else s_a
            s_opp = s_a if _fav_in_home else s_h
            es_acertado = resultado_csv == "acertado"
            emoji = "✅" if es_acertado else "❌" if resultado_csv == "fallido" else "🏁"
            has_score = bool(s_a or s_h)
            in_progress = resultado_csv == "pendiente" and has_score
            state = "En Vivo" if in_progress else "Final" if resultado_csv in ("acertado", "fallido") else "Pend."
            csv_liga = (_row.get("liga", "MLB") or "MLB").strip()
            g = {
                "liga": csv_liga,
                "game_date": csv_fecha, "status_emoji": emoji,
                "fav_team": fav, "opp_team": opp,
                "score_fav": str(s_fav), "score_opp": str(s_opp),
                "state": state,
                "result": "win" if es_acertado else "loss" if resultado_csv == "fallido" else "completed",
                "home_team": home_csv, "away_team": away_csv,
            }
        g["label"] = label
        g["game_date"] = csv_fecha
        g["llm_ir_favorito"] = _row.get("llm_ir_favorito", "")
        g["llm_porque"] = _row.get("llm_porque", "")
        g["llm_factores"] = _row.get("llm_factores", "")
        g["resultado_llm"] = _row.get("resultado_llm", "")
        games.append(g)
        seen.add(key)

    try:
        with open(csv_path, "r", encoding="utf-8") as _f:
            for _row in _csv.DictReader(_f):
                try:
                    _process_csv_row(_row)
                except Exception as exc:
                    logger.warning(f"Error en fila CSV ({_row.get('equipo_visitante','')} vs {_row.get('equipo_local','')}): {exc}")
    except Exception as exc:
        logger.warning(f"No se pudo abrir/leer el CSV: {exc}")

    for sg in seguimiento:
        favorito = sg.get("favorito", "")
        away     = sg.get("away_team", "")
        home     = sg.get("home_team", "")
        fecha    = sg.get("game_date", "")[:10]
        key_sg = _make_key(fecha, away, home)
        if key_sg in seen:
            continue
        prob     = sg.get("prob_favorito", 0) or 0
        mercado  = sg.get("odds_mercado")
        edge     = round(prob - mercado, 2) if mercado else None
        nivel_cert = sg.get("nivel_certidumbre", "").strip()
        if nivel_cert in ("ALTA", "MEDIA") and prob >= 57.0:
            label = "🎯"
        else:
            label = "📋"

        match = None
        for eg in espn_games:
            if eg["game_date"] != fecha:
                continue
            if (_norm(away) in _norm(eg["a_name"]) or _norm(eg["a_name"]) in _norm(away)) and \
               (_norm(home) in _norm(eg["h_name"]) or _norm(eg["h_name"]) in _norm(home)):
                match = eg
                break

        if match:
            g = _espn_to_game(match, favorito)
        else:
            _fav_in_home = favorito and (_norm(favorito) in _norm(home) or _norm(home) in _norm(favorito))
            fav = home if _fav_in_home else away
            opp = away if _fav_in_home else home
            sg_liga = sg.get("liga", "MLB")
            # Check if JSON entry has marcador (from LMB sync)
            marcador_sg = sg.get("marcador", "")
            sg_scores = _re.findall(r'(\d+)\s*[–\-]\s*(\d+)', marcador_sg.lower()) if marcador_sg else []
            if sg_scores:
                s_fav = sg_scores[0][1] if _fav_in_home else sg_scores[0][0]
                s_opp = sg_scores[0][0] if _fav_in_home else sg_scores[0][1]
                state = "En Vivo"
            else:
                s_fav, s_opp = "", ""
                state = "Pend."
            g = {
                "liga": sg_liga,
                "game_date": fecha, "status_emoji": "⏳",
                "fav_team": fav, "opp_team": opp,
                "score_fav": s_fav, "score_opp": s_opp,
                "state": state,
                "result": "pending",
                "home_team": home, "away_team": away,
            }

        g["label"] = label
        g["game_date"] = fecha
        games.append(g)
        seen.add(key_sg)

    # Agregar partidos de ESPN que NO están en seguimiento (informativos) — todas las fechas
    for eg in espn_games:
        key = _make_key(eg["game_date"], eg["a_name"], eg["h_name"])
        if key in seen:
            continue
        g = _espn_to_game(eg)
        g["label"] = "📋"
        g["game_date"] = eg["game_date"]
        games.append(g)

    # ── Annotate game_pk from seguimiento ──
    sg_map = {}
    for sg in seguimiento:
        pk = sg.get("game_pk", 0)
        if pk:
            key = (_norm(sg.get("game_date", "")[:10]), _norm(sg.get("away_team", "")), _norm(sg.get("home_team", "")))
            sg_map[key] = {"game_pk": pk}
    for g in games:
        gd = g.get("game_date", "")
        fav = _norm(g.get("fav_team", ""))
        opp = _norm(g.get("opp_team", ""))
        entry = sg_map.get((gd, opp, fav)) or sg_map.get((gd, fav, opp))
        if entry:
            g["game_pk"] = entry["game_pk"]
        else:
            g.setdefault("game_pk", 0)
        g.setdefault("linescore", {})

    # ── Fetch live linescores from MLB Stats API ──
    try:
        _annotate_linescores_mlb(games)
    except Exception as e:
        logger.warning(f"Error fetching linescores: {e}")

    # Ordenar partidos por fecha (más reciente primero) y dentro de cada fecha por label
    games.sort(key=lambda x: (x.get("game_date", ""), {"🎯":0,"📋":1}.get(x.get("label",""), 2)))

    # ── Team logo URLs ──
    ESPN_LOGO_TMPL = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/{liga}/500/{abbr}.png&h=40&w=40"
    for g in games:
        liga = (g.get("liga", "MLB") or "MLB").upper()
        if liga not in ("MLB",):
            continue
        fav_abbr = g.get("fav_abbr", "")
        opp_abbr = g.get("opp_abbr", "")
        if fav_abbr:
            g["fav_logo"] = ESPN_LOGO_TMPL.format(liga="mlb", abbr=fav_abbr)
        if opp_abbr:
            g["opp_logo"] = ESPN_LOGO_TMPL.format(liga="mlb", abbr=opp_abbr)

    # Extraer fechas disponibles ordenadas (más reciente primero)
    dias_set = set()
    for g in games:
        d = g.get("game_date", "")
        if d:
            dias_set.add(d)
    dias_disponibles = sorted(dias_set, reverse=True)

    stats = dm.obtener_estadisticas()
    stats_mlb = dm.obtener_estadisticas(liga="MLB")
    stats_lmb = dm.obtener_estadisticas(liga="LMB")

    # LLM stats per sport (con try/except individual por deporte)
    _llm_zero = {"llm_total": 0, "llm_acertados": 0, "llm_fallidos": 0, "llm_win_rate": 0}
    try: llm_mlb = dm.obtener_estadisticas_llm(liga="MLB")
    except Exception as e: logger.warning(f"LLM stats MLB failed: {e}"); llm_mlb = dict(_llm_zero)
    try: llm_lmb = dm.obtener_estadisticas_llm(liga="LMB")
    except Exception as e: logger.warning(f"LLM stats LMB failed: {e}"); llm_lmb = dict(_llm_zero)
    try: llm_nba = dm.obtener_estadisticas_llm(liga="NBA")
    except Exception as e: logger.warning(f"LLM stats NBA failed: {e}"); llm_nba = dict(_llm_zero)
    try: llm_wnba = dm.obtener_estadisticas_llm(liga="WNBA")
    except Exception as e: logger.warning(f"LLM stats WNBA failed: {e}"); llm_wnba = dict(_llm_zero)
    try: llm_nfl = dm.obtener_estadisticas_llm(liga="NFL")
    except Exception as e: logger.warning(f"LLM stats NFL failed: {e}"); llm_nfl = dict(_llm_zero)
    try: llm_soccer = dm.obtener_estadisticas_llm(liga="SOCCER")
    except Exception as e: logger.warning(f"LLM stats SOCCER failed: {e}"); llm_soccer = dict(_llm_zero)

    # Stats por rango de fecha para filtros del frontend
    hoy = date.today()
    stats_hoy = dm.obtener_estadisticas(fecha_desde=hoy.isoformat(), fecha_hasta=hoy.isoformat())
    stats_hoy_mlb = dm.obtener_estadisticas(liga="MLB", fecha_desde=hoy.isoformat(), fecha_hasta=hoy.isoformat())
    stats_hoy_lmb = dm.obtener_estadisticas(liga="LMB", fecha_desde=hoy.isoformat(), fecha_hasta=hoy.isoformat())
    stats_3dias = dm.obtener_estadisticas(fecha_desde=(hoy - timedelta(days=2)).isoformat(), fecha_hasta=hoy.isoformat())
    stats_3dias_mlb = dm.obtener_estadisticas(liga="MLB", fecha_desde=(hoy - timedelta(days=2)).isoformat(), fecha_hasta=hoy.isoformat())
    stats_3dias_lmb = dm.obtener_estadisticas(liga="LMB", fecha_desde=(hoy - timedelta(days=2)).isoformat(), fecha_hasta=hoy.isoformat())
    stats_semanal = dm.obtener_estadisticas(fecha_desde=(hoy - timedelta(days=6)).isoformat(), fecha_hasta=hoy.isoformat())
    stats_semanal_mlb = dm.obtener_estadisticas(liga="MLB", fecha_desde=(hoy - timedelta(days=6)).isoformat(), fecha_hasta=hoy.isoformat())
    stats_semanal_lmb = dm.obtener_estadisticas(liga="LMB", fecha_desde=(hoy - timedelta(days=6)).isoformat(), fecha_hasta=hoy.isoformat())

    # Stats por cada fecha individual (para selector de día)
    fechas_csv = dm.fechas_disponibles_csv()
    stats_por_fecha = {}
    stats_por_fecha_mlb = {}
    stats_por_fecha_lmb = {}
    for fecha_iso in fechas_csv:
        stats_por_fecha[fecha_iso] = dm.obtener_estadisticas(fecha_desde=fecha_iso, fecha_hasta=fecha_iso)
        stats_por_fecha_mlb[fecha_iso] = dm.obtener_estadisticas(liga="MLB", fecha_desde=fecha_iso, fecha_hasta=fecha_iso)
        stats_por_fecha_lmb[fecha_iso] = dm.obtener_estadisticas(liga="LMB", fecha_desde=fecha_iso, fecha_hasta=fecha_iso)
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Obtener hora del próximo análisis (re-análisis fijo para countdown)
    import pytz as _pytz
    _tz = _pytz.timezone(config.TIMEZONE)
    _now = datetime.now(_tz)

    prox_actualizacion = getattr(config, "REANALISIS_MLB_HORA", config.HORA_ANALISIS_MANANA)
    prox_actualizacion_lmb = getattr(config, "REANALISIS_LMB_HORA", getattr(config, "LMB_HORA_MANANA", "10:00"))
    try:
        from scheduler import obtener_hora_reanalisis, obtener_hora_reanalisis_lmb
        prox_actualizacion = obtener_hora_reanalisis()
        prox_actualizacion_lmb = obtener_hora_reanalisis_lmb()
    except Exception:
        pass

    def _hoy_a_ts(hora_str: str) -> int:
        """Convierte 'HH:MM' a Unix timestamp (epoch seconds) para hoy en TIMEZONE."""
        try:
            hh, mm = hora_str.split(":")
            target = _now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if target <= _now:
                target += timedelta(days=1)
            return int(target.timestamp())
        except Exception:
            return 0

    def _build_stats(s):
        return {
            "total": s["total"],
            "acertados": s["acertados"],
            "fallidos": s["fallidos"],
            "win_rate": s["win_rate"],
            "alta_total": s["alta_total"],
            "alta_acertados": s["alta_acertados"],
            "alta_fallidos": s["alta_fallidos"],
            "alta_win_rate": s["alta_win_rate"],
            "media_total": s["media_total"],
            "media_acertados": s["media_acertados"],
            "media_fallidos": s["media_fallidos"],
            "media_win_rate": s["media_win_rate"],
            "baja_total": s["baja_total"],
            "baja_acertados": s["baja_acertados"],
            "baja_fallidos": s["baja_fallidos"],
            "baja_win_rate": s["baja_win_rate"],
            "valor_ok": s["valor_ok"],
            "valor_total": s["valor_total"],
            "valor_rate": s["valor_rate"],
            "llm_total": s.get("llm_total", 0),
            "llm_acertados": s.get("llm_acertados", 0),
            "llm_fallidos": s.get("llm_fallidos", 0),
            "llm_win_rate": s.get("llm_win_rate", 0),
        }

    has_live = any(g.get("result") == "live" for g in games)
    has_scheduled = any(g.get("result") == "pending" for g in games)

    live_data = {}
    for g in games:
        pk = g.get("game_pk", 0)
        if pk:
            ls = g.get("linescore", {})
            try:
                _fav = int(g.get("score_fav", 0) or 0)
                _opp = int(g.get("score_opp", 0) or 0)
            except (ValueError, TypeError):
                _fav = 0
                _opp = 0
            live_data[str(pk)] = {
                "is_live": g.get("result") == "live",
                "is_final": g.get("result") in ("win", "loss", "completed"),
                "status": g.get("state", ""),
                "away_runs": _fav,
                "home_runs": _opp,
                "away_team_name": g.get("opp_team", ""),
                "home_team_name": g.get("fav_team", ""),
                "linescore": ls,
            }

    # ── Basketball data (NBA + WNBA) ──
    basketball_espn_games = []
    for sport in ("nba", "wnba"):
        for f in fechas_espn:
            basketball_espn_games += _get_espn_basketball_scoreboard(f, sport)
    nba_games = []
    wnba_games = []
    for eg in basketball_espn_games:
        gliga = eg.get("liga", "NBA")
        g = {
            "game_date": eg["game_date"],
            "game_id": str(eg.get("espn_pk", "")),
            "status_emoji": eg["status_emoji"],
            "home": eg["h_name"],
            "away": eg["a_name"],
            "home_abbr": eg.get("h_abbr", ""),
            "away_abbr": eg.get("a_abbr", ""),
            "home_score": eg["h_runs"],
            "away_score": eg["a_runs"],
            "home_linescores": eg.get("h_linescores", []),
            "away_linescores": eg.get("a_linescores", []),
            "clock": eg.get("clock", ""),
            "period": eg.get("period", 0),
            "state": eg["state"],
            "result": eg["result"],
            "liga": gliga,
        }
        if gliga == "WNBA":
            wnba_games.append(g)
        else:
            nba_games.append(g)
    # ── Basketball team logo URLs ──
    NBA_LOGO_TMPL = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nba/500/{abbr}.png&h=40&w=40"
    WNBA_LOGO_TMPL = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/wnba/500/{abbr}.png&h=40&w=40"
    for ng in nba_games:
        if ng.get("home_abbr"):
            ng["home_logo"] = NBA_LOGO_TMPL.format(abbr=ng["home_abbr"])
        if ng.get("away_abbr"):
            ng["away_logo"] = NBA_LOGO_TMPL.format(abbr=ng["away_abbr"])
    for ng in wnba_games:
        if ng.get("home_abbr"):
            ng["home_logo"] = WNBA_LOGO_TMPL.format(abbr=ng["home_abbr"])
        if ng.get("away_abbr"):
            ng["away_logo"] = WNBA_LOGO_TMPL.format(abbr=ng["away_abbr"])

    # ── NFL data ──
    nfl_espn_games = []
    for f in fechas_espn:
        nfl_espn_games += _get_espn_nfl_scoreboard(f)
    nfl_games = []
    for eg in nfl_espn_games:
        g = {
            "game_date": eg["game_date"],
            "game_id": str(eg.get("espn_pk", "")),
            "status_emoji": eg["status_emoji"],
            "home": eg["h_name"],
            "away": eg["a_name"],
            "home_abbr": eg.get("h_abbr", ""),
            "away_abbr": eg.get("a_abbr", ""),
            "home_score": eg["h_score"],
            "away_score": eg["a_score"],
            "clock": eg.get("clock", ""),
            "period": eg.get("period", 0),
            "state": eg["quarter_label"],
            "result": eg["result"],
            "liga": "NFL",
            "spread_details": eg.get("spread_details", ""),
            "over_under": eg.get("over_under", ""),
            "ml_home": eg.get("ml_home", ""),
            "ml_away": eg.get("ml_away", ""),
            "home_record": eg.get("h_record", ""),
            "away_record": eg.get("a_record", ""),
            "week_num": eg.get("week_num", 0),
            "season_year": eg.get("season_year", 0),
            "season_type": eg.get("season_type", 0),
        }
        nfl_games.append(g)
    NFL_LOGO_TMPL = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nfl/500/{abbr}.png&h=40&w=40"
    for ng in nfl_games:
        if ng.get("home_abbr"):
            ng["home_logo"] = NFL_LOGO_TMPL.format(abbr=ng["home_abbr"])
        if ng.get("away_abbr"):
            ng["away_logo"] = NFL_LOGO_TMPL.format(abbr=ng["away_abbr"])

    # ── Soccer data ──
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    soccer_local_path = os.path.join(bot_dir, "soccer_data.json")
    soccer_games = []
    if os.path.exists(soccer_local_path):
        try:
            with open(soccer_local_path, "r", encoding="utf-8") as f:
                soccer_data = json.load(f)
            soccer_games = soccer_data.get("games", [])
        except Exception as e:
            logger.warning(f"Error cargando soccer_data.json: {e}")

    # ── LLM contra-análisis para todos los deportes (desde cache o en vivo) ──
    llm_data = {}
    # Preserve existing NBA/WNBA LLM entries from current live_data.json
    _existing_llm = {}
    try:
        existing_live_path = os.path.join(bot_dir, "live_data.json")
        if os.path.exists(existing_live_path):
            with open(existing_live_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            for k, v in (existing_data.get("llm_analysis") or {}).items():
                if "NBA" in k or "WNBA" in k:
                    llm_data[k] = v
                    _existing_llm[k] = v
    except Exception:
        pass
    # Apply preserved NBA/WNBA LLM fields to freshly built game objects
    for _g in nba_games + wnba_games:
        _gliga = (_g.get("liga") or "NBA")
        if _gliga == "WNBA":
            _gliga = "WNBA"
        _lk = _g.get("game_date", "") + "___" + _gliga + "___" + _g.get("home", "") + "___" + _g.get("away", "")
        if _lk in _existing_llm:
            _apply_nba_llm_fields(_g, _existing_llm[_lk])
    if not skip_llm:
        all_games_for_llm = games + nba_games + wnba_games + soccer_games + nfl_games
        _inject_llm_analysis(all_games_for_llm, llm_data)

    data = {
        "fecha": ahora,
        "proxima_actualizacion": prox_actualizacion,
        "proxima_actualizacion_lmb": prox_actualizacion_lmb,
        "proxima_actualizacion_ts": _hoy_a_ts(prox_actualizacion),
        "proxima_actualizacion_lmb_ts": _hoy_a_ts(prox_actualizacion_lmb),
        "dias": dias_disponibles,
        "games": games,
        "bot_username": config.TELEGRAM_BOT_USERNAME,
        "autorizados": cargar_suscriptores(),
        "has_live": has_live,
        "has_scheduled": has_scheduled,
        "live_data": live_data,
        "updated_at": ahora,
        "stats": _build_stats(stats),
        "stats_mlb": _build_stats(stats_mlb),
        "stats_lmb": _build_stats(stats_lmb),
        "stats_hoy": _build_stats(stats_hoy),
        "stats_hoy_mlb": _build_stats(stats_hoy_mlb),
        "stats_hoy_lmb": _build_stats(stats_hoy_lmb),
        "stats_3dias": _build_stats(stats_3dias),
        "stats_3dias_mlb": _build_stats(stats_3dias_mlb),
        "stats_3dias_lmb": _build_stats(stats_3dias_lmb),
        "stats_semanal": _build_stats(stats_semanal),
        "stats_semanal_mlb": _build_stats(stats_semanal_mlb),
        "stats_semanal_lmb": _build_stats(stats_semanal_lmb),
        "fechas_disponibles": fechas_csv,
        "stats_por_fecha": {k: _build_stats(v) for k, v in stats_por_fecha.items()},
        "stats_por_fecha_mlb": {k: _build_stats(v) for k, v in stats_por_fecha_mlb.items()},
        "stats_por_fecha_lmb": {k: _build_stats(v) for k, v in stats_por_fecha_lmb.items()},
        "hits_board": _build_hits_board(live_games=live_data),
        "llm_analysis": llm_data,
        "llm_by_sport": {
            "MLB": llm_mlb,
            "LMB": llm_lmb,
            "NBA": llm_nba,
            "WNBA": llm_wnba,
            "NFL": llm_nfl,
            "SOCCER": llm_soccer,
        },
        "nba_games": nba_games,
        "wnba_games": wnba_games,
        "nfl_games": nfl_games,
    }

    # hits_llm: preservar existente o generar automáticamente
    live_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_data.json")
    try:
        if os.path.exists(live_json_path):
            with open(live_json_path, encoding="utf-8") as _f:
                _existing = json.load(_f)
            if "hits_llm" in _existing:
                data["hits_llm"] = _existing["hits_llm"]
        if "hits_llm" not in data or not data["hits_llm"]:
            try:
                from generar_hits_xlsx import ejecutar_hits_llm
                hits_llm = ejecutar_hits_llm()
                if hits_llm:
                    data["hits_llm"] = hits_llm
            except Exception as e:
                logger.warning(f"No se pudo generar hits_llm automático: {e}")
    except Exception:
        pass

    # llm_by_sport: preservar del archivo existente si la computación dio todos 0
    try:
        _has_llm_data = any(
            v.get("llm_total", 0) > 0
            for v in data.get("llm_by_sport", {}).values()
        )
        if not _has_llm_data and os.path.exists(live_json_path):
            with open(live_json_path, encoding="utf-8") as _f:
                _prev = json.load(_f)
            _prev_llm = _prev.get("llm_by_sport", {})
            if _prev_llm and any(v.get("llm_total", 0) > 0 for v in _prev_llm.values()):
                data["llm_by_sport"] = _prev_llm
                logger.info("llm_by_sport preservado del live_data.json existente")
    except Exception:
        pass

    # llm_sections: desglose por secciones por deporte (equipo, lanzadores, bateadores, etc.)
    try:
        _sports_for_sections = ("MLB", "LMB", "NBA", "WNBA", "SOCCER", "NFL")
        _sections_data = {}
        for _sp in _sports_for_sections:
            try:
                _sec = dm.obtener_secciones_llm(_sp)
                if _sec:
                    _sections_data[_sp] = _sec
            except Exception:
                pass
        if _sections_data:
            data["llm_sections"] = _sections_data
        # Preservar llm_sections del archivo existente si la computación dio vacío
        elif not _sections_data and os.path.exists(live_json_path):
            with open(live_json_path, encoding="utf-8") as _f:
                _prev = json.load(_f)
            _prev_sec = _prev.get("llm_sections", {})
            if _prev_sec:
                data["llm_sections"] = _prev_sec
                logger.info("llm_sections preservado del live_data.json existente")
    except Exception:
        pass

    return data


def _actualizar_datos_en_html(data: dict) -> str:
    """Genera HTML desde la plantilla. Si la plantilla tiene __DATA__, lo reemplaza.
    Si ya usa fetch('live_data.json'), solo retorna la plantilla tal cual."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    if "__DATA__" in html:
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        html = html.replace("__DATA__", json_str)
        html = html.replace("__BOT_USERNAME__", data.get("bot_username", ""))
    return html


def generar_html() -> str:
    """Genera el index.html completo con datos actuales."""
    data = _build_data()
    return _actualizar_datos_en_html(data)


def pushear_archivo(ruta_repo: str, contenido: str, mensaje: str = None) -> bool:
    """
    Sube un archivo al repo via GitHub API.
    ruta_repo: ej. "index.html", "privacy.html"
    """
    token = GITHUB_TOKEN
    if not token:
        logger.error("GITHUB_TOKEN no configurado en config.py")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    sha = None
    r = requests.get(f"{API_BASE}/contents/{ruta_repo}", headers=headers)
    if r.status_code == 200:
        sha = r.json().get("sha")
    elif r.status_code != 404:
        logger.error(f"GitHub API error checking {ruta_repo}: {r.status_code} {r.text[:200]}")
        return False

    import binascii
    payload = {
        "message": mensaje or f"Actualizar {ruta_repo}",
        "content": binascii.b2a_base64(contenido.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(f"{API_BASE}/contents/{ruta_repo}", json=payload, headers=headers)
    if r.status_code in (200, 201):
        logger.info(f"{ruta_repo} subido a GitHub ✅")
        return True
    else:
        logger.error(f"GitHub push error ({ruta_repo}): {r.status_code} {r.text[:300]}")
        return False


def pushear_a_github(html_content: str) -> bool:
    """Wrapper para subir index.html (compatibilidad)."""
    return pushear_archivo("index.html", html_content, "Actualizar resultados MLB + LMB")


def _git_push_fallback(files: list[str], mensaje: str) -> bool:
    """Fallback: push via git CLI when GitHub API token is invalid."""
    import subprocess
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        for f in files:
            full = os.path.join(bot_dir, f) if not os.path.isabs(f) else f
            if os.path.exists(full):
                subprocess.run(["git", "add", f], cwd=bot_dir, capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=bot_dir, capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("Git fallback: sin cambios para push")
            return True
        subprocess.run(
            ["git", "commit", "-m", mensaje],
            cwd=bot_dir, capture_output=True, timeout=15,
        )
        push = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=bot_dir, capture_output=True, text=True, timeout=30,
        )
        if push.returncode == 0:
            logger.info(f"Git push exitoso: {mensaje}")
            return True
        else:
            logger.error(f"Git push falló: {push.stderr[:200]}")
            return False
    except Exception as e:
        logger.error(f"Git fallback error: {e}")
        return False


def habilitar_pages() -> bool:
    """Activa GitHub Pages desde main branch / (root)."""
    token = GITHUB_TOKEN
    if not token:
        return False
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "source": {"branch": "main", "path": "/"},
    }
    r = requests.post(f"{API_BASE}/pages", json=payload, headers=headers)
    if r.status_code in (200, 201, 204):
        logger.info("GitHub Pages habilitado ✅")
        return True
    # Si ya está habilitado, 409 Conflict es esperado
    if r.status_code == 409:
        logger.info("GitHub Pages ya estaba habilitado")
        return True
    logger.error(f"GitHub Pages error: {r.status_code} {r.text[:200]}")
    return False


def publicar() -> bool:
    """Genera HTML + live_data.json, sube a GitHub y habilita Pages."""
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(bot_dir)
    miniapp_dir = os.path.join(bot_dir, "miniapp")

    html = generar_html()

    ok_index = pushear_a_github(html)

    try:
        data = _build_data()
        live_json = json.dumps(data, ensure_ascii=False, indent=2)
        live_path = os.path.join(bot_dir, "live_data.json")
        with open(live_path, "w", encoding="utf-8") as f:
            f.write(live_json)
        # Copiar a docs/ para GitHub Pages si existe
        docs_path = os.path.join(bot_dir, "docs", "live_data.json")
        if os.path.isdir(os.path.join(bot_dir, "docs")):
            import shutil
            shutil.copy2(live_path, docs_path)
        pushear_archivo("live_data.json", live_json, "Actualizar live_data.json")
        pushear_archivo("docs/live_data.json", live_json, "Actualizar docs/live_data.json")
    except Exception as e:
        logger.error(f"Error generando live_data.json: {e}")

    soccer_path = os.path.join(config.FUTBOL_DIR, "soccer_data.json")
    if os.path.exists(soccer_path):
        try:
            import shutil
            dst = os.path.join(bot_dir, "soccer_data.json")
            shutil.copy2(soccer_path, dst)
            with open(dst, "r", encoding="utf-8") as f:
                soccer_data = json.load(f)
            soccer_games = soccer_data.get("games", [])
            soccer_llm = {}
            _inject_llm_analysis(soccer_games, soccer_llm)
            soccer_data["llm_analysis"] = soccer_llm
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(soccer_data, f, ensure_ascii=False, indent=2)
            docs_soccer = os.path.join(bot_dir, "docs", "soccer_data.json")
            if os.path.isdir(os.path.join(bot_dir, "docs")):
                shutil.copy2(dst, docs_soccer)
            soccer_json = json.dumps(soccer_data, ensure_ascii=False, indent=2)
            pushear_archivo("soccer_data.json", soccer_json, "Actualizar soccer_data.json")
            pushear_archivo("docs/soccer_data.json", soccer_json, "Actualizar docs/soccer_data.json")
        except Exception as e:
            logger.error(f"Error subiendo soccer_data.json: {e}")

    for archivo in ("privacy.html", "terms.html"):
        ruta_local = os.path.join(miniapp_dir, archivo)
        if os.path.exists(ruta_local):
            with open(ruta_local, "r", encoding="utf-8") as f:
                contenido = f.read()
            pushear_archivo(archivo, contenido, f"Actualizar {archivo}")

    # Push dashboard + index.html to docs/ for GitHub Pages
    for archivo in ("index.html", "dashboard.html"):
        ruta_local = os.path.join(miniapp_dir, archivo)
        if os.path.exists(ruta_local):
            with open(ruta_local, "r", encoding="utf-8") as f:
                contenido = f.read()
            pushear_archivo(f"docs/{archivo}", contenido, f"Actualizar docs/{archivo}")

    habilitar_pages()

    if not ok_index:
        files = ["live_data.json"]
        if os.path.exists(os.path.join(bot_dir, "soccer_data.json")):
            files.append("soccer_data.json")
        for f in ("index.html", "privacy.html", "terms.html"):
            ruta = os.path.join(miniapp_dir, f)
            if os.path.exists(ruta):
                import shutil
                dst = os.path.join(bot_dir, f)
                shutil.copy2(ruta, dst)
                files.append(f)
        return _git_push_fallback(files, "Actualizar Mini App via git")

    return True


def publicar_live_data() -> bool:
    """Sube live_data.json + soccer_data.json (para updates frecuentes sin regenerar HTML)."""
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(bot_dir)
    ok_live = False
    ok_soccer = False
    try:
        data = _build_data()
        live_json = json.dumps(data, ensure_ascii=False, indent=2)
        live_path = os.path.join(bot_dir, "live_data.json")
        with open(live_path, "w", encoding="utf-8") as f:
            f.write(live_json)
        # Copiar a docs/ para GitHub Pages si existe
        docs_path = os.path.join(bot_dir, "docs", "live_data.json")
        if os.path.isdir(os.path.join(bot_dir, "docs")):
            import shutil
            shutil.copy2(live_path, docs_path)
        ok_live = pushear_archivo("live_data.json", live_json, "Update live scores")
        pushear_archivo("docs/live_data.json", live_json, "Update docs/live scores")

        # Soccer: copiar, inyectar LLM y subir
        soccer_path = os.path.join(config.FUTBOL_DIR, "soccer_data.json")
        soccer_local = os.path.join(bot_dir, "soccer_data.json")
        if os.path.exists(soccer_path):
            import shutil
            shutil.copy2(soccer_path, soccer_local)
        if os.path.exists(soccer_local):
            try:
                with open(soccer_local, "r", encoding="utf-8") as f:
                    soccer_data = json.load(f)
                soccer_games = soccer_data.get("games", [])
                soccer_llm = {}
                _inject_llm_analysis(soccer_games, soccer_llm)
                soccer_data["llm_analysis"] = soccer_llm
                with open(soccer_local, "w", encoding="utf-8") as f:
                    json.dump(soccer_data, f, ensure_ascii=False, indent=2)
                # Copiar a docs/ DESPUÉS de inyectar LLM
                docs_soccer = os.path.join(bot_dir, "docs", "soccer_data.json")
                if os.path.isdir(os.path.join(bot_dir, "docs")):
                    import shutil
                    shutil.copy2(soccer_local, docs_soccer)
                soccer_json = json.dumps(soccer_data, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Error inyectando LLM en soccer: {e}")
                with open(soccer_local, "r", encoding="utf-8") as f:
                    soccer_json = f.read()
            ok_soccer = pushear_archivo("soccer_data.json", soccer_json, "Update soccer data")
            pushear_archivo("docs/soccer_data.json", soccer_json, "Update docs/soccer data")
        else:
            ok_soccer = True
    except Exception as e:
        logger.error(f"Error generando live_data: {e}")

    if not ok_live or not ok_soccer:
        logger.info("API push falló, intentando git push fallback...")
        files = ["live_data.json"]
        soccer_local = os.path.join(bot_dir, "soccer_data.json")
        if os.path.exists(soccer_local):
            files.append("soccer_data.json")
        git_ok = _git_push_fallback(files, "Update live scores via git")
        return git_ok

    # Backup llm_persistent.json a GitHub
    try:
        backup_path = os.path.join(bot_dir, "llm_persistent.json")
        if os.path.exists(backup_path):
            with open(backup_path, "r", encoding="utf-8") as f:
                backup_content = f.read()
            pushear_archivo("llm_backup.json", backup_content, "Backup LLM persistent data")
            logger.info("llm_persistent.json respaldado como llm_backup.json en GitHub")
    except Exception as e:
        logger.warning(f"Error respaldando llm_persistent.json: {e}")

    return True



