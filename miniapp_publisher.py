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

logger = logging.getLogger(__name__)

GITHUB_TOKEN = getattr(config, "GITHUB_TOKEN", "")
REPO_OWNER   = "05aptrading-jpg"
REPO_NAME    = "ApuestasMLB"
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

    # Determinar qué equipo resaltar y orientar score
    def _fav_info():
        if not favorito:
            return {"fav_team": a_name, "opp_team": h_name, "score_fav": str(a_runs), "score_opp": str(h_runs)}
        fav_is_away = favorito.strip().lower() in a_name.strip().lower() or a_name.strip().lower() in favorito.strip().lower()
        fav_is_home = favorito.strip().lower() in h_name.strip().lower() or h_name.strip().lower() in favorito.strip().lower()
        if fav_is_home and not fav_is_away:
            return {"fav_team": h_name, "opp_team": a_name, "score_fav": str(h_runs), "score_opp": str(a_runs)}
        return {"fav_team": a_name, "opp_team": h_name, "score_fav": str(a_runs), "score_opp": str(h_runs)}

    def _win(fav_info):
        return int(fav_info["score_fav"]) > int(fav_info["score_opp"])

    fi = _fav_info()
    gd = espn.get("game_date", "")

    if espn["is_post"]:
        return {"liga": liga, "game_date": gd, "status_emoji": "🚫", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": "—", "score_opp": "", "state": "Posp.", "result": "pending", "label": "", "game_pk": espn.get("espn_pk", 0)}

    if espn["is_live"]:
        return {"liga": liga, "game_date": gd, "status_emoji": "🔴", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": fi["score_fav"], "score_opp": fi["score_opp"], "state": detail, "result": "live", "label": "", "game_pk": espn.get("espn_pk", 0)}

    if espn["completed"]:
        if favorito:
            acertado = _win(fi)
            return {"liga": liga, "game_date": gd, "status_emoji": "✅" if acertado else "❌", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": fi["score_fav"], "score_opp": fi["score_opp"], "state": "Final", "result": "win" if acertado else "loss", "label": "", "game_pk": espn.get("espn_pk", 0)}
        else:
            return {"liga": liga, "game_date": gd, "status_emoji": "🏁", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": fi["score_fav"], "score_opp": fi["score_opp"], "state": "Final", "result": "completed", "label": "", "game_pk": espn.get("espn_pk", 0)}

    return {"liga": liga, "game_date": gd, "status_emoji": "⏳", "fav_team": fi["fav_team"], "opp_team": fi["opp_team"], "score_fav": "—", "score_opp": "", "state": "Pend.", "result": "pending", "label": "", "game_pk": espn.get("espn_pk", 0)}


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
def _build_data() -> dict:
    """Construye el JSON con partidos + stats para la Mini App."""
    from datetime import timedelta
    hoy       = datetime.now()
    ayer      = hoy - timedelta(days=1)
    anteayer  = hoy - timedelta(days=2)
    hoy_str    = hoy.strftime("%Y-%m-%d")
    ayer_str   = ayer.strftime("%Y-%m-%d")
    anteayer_str = anteayer.strftime("%Y-%m-%d")
    fechas     = {hoy_str, ayer_str, anteayer_str}

    espn_games = []
    for f in fechas:
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
        if csv_fecha not in fechas:
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
        if nivel_cert in ("ALTA", "MEDIA"):
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
            }
        g["label"] = label
        g["game_date"] = csv_fecha
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
        if fecha not in fechas:
            continue
        key_sg = _make_key(fecha, away, home)
        if key_sg in seen:
            continue
        prob     = sg.get("prob_favorito", 0) or 0
        mercado  = sg.get("odds_mercado")
        edge     = round(prob - mercado, 2) if mercado else None
        nivel_cert = sg.get("nivel_certidumbre", "").strip()
        if nivel_cert in ("ALTA", "MEDIA"):
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

    return {
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
    }


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

    # Subir index.html desde railway_app/templates (fuente canonical)
    railway_tpl = os.path.join(bot_dir, "railway_app", "templates", "index.html")
    if os.path.exists(railway_tpl):
        with open(railway_tpl, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        html = generar_html()
    if not pushear_a_github(html):
        return False

    # Subir live_data.json para fetch dinámico
    try:
        data = _build_data()
        live_json = json.dumps(data, ensure_ascii=False, indent=2)
        pushear_archivo("live_data.json", live_json, "Actualizar live_data.json")
    except Exception as e:
        logger.error(f"Error generando live_data.json: {e}")

    # Subir soccer_data.json
    soccer_path = os.path.join(config.FUTBOL_DIR, "soccer_data.json")
    if os.path.exists(soccer_path):
        try:
            with open(soccer_path, "r", encoding="utf-8") as f:
                soccer_json = f.read()
            pushear_archivo("soccer_data.json", soccer_json, "Actualizar soccer_data.json")
        except Exception as e:
            logger.error(f"Error subiendo soccer_data.json: {e}")

    # Subir páginas estáticas (privacy, terms)
    for archivo in ("privacy.html", "terms.html"):
        ruta_local = os.path.join(miniapp_dir, archivo)
        if os.path.exists(ruta_local):
            with open(ruta_local, "r", encoding="utf-8") as f:
                contenido = f.read()
            pushear_archivo(archivo, contenido, f"Actualizar {archivo}")

    habilitar_pages()
    return True


def publicar_live_data() -> bool:
    """Sube live_data.json + soccer_data.json (para updates frecuentes sin regenerar HTML)."""
    bot_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(bot_dir)
    try:
        data = _build_data()
        live_json = json.dumps(data, ensure_ascii=False, indent=2)
        pushear_archivo("live_data.json", live_json, "Update live scores")
        # Also push soccer data
        soccer_path = os.path.join(config.FUTBOL_DIR, "soccer_data.json")
        if os.path.exists(soccer_path):
            with open(soccer_path, "r", encoding="utf-8") as f:
                soccer_json = f.read()
            pushear_archivo("soccer_data.json", soccer_json, "Update soccer data")
        return True
    except Exception as e:
        logger.error(f"Error publicando live_data: {e}")
        return False
