"""
GitHub Actions: Fetch MLB/LMB live scores + analysis data → JSON for GitHub Pages.
Runs every 2 minutes during game hours via cron.
Self-contained — no import of config.py (which has secrets).
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
import httpx

logger = logging.getLogger(__name__)

# ── Constants (mirrored from config.py) ─────────────────────────────
PROB_MINIMA_ANALISIS = 57.0
EDGE_MINIMO = 4.0
HORA_ANALISIS_MANANA = "08:00"
LMB_HORA_MANANA = "10:00"
TELEGRAM_BOT_USERNAME = "MLBAnalyticsAPBot"
MT_OFFSET = -6  # Ciudad Juarez UTC-6


def fetch_live_scores(api_date: str, sport_id: int) -> dict:
    """Fetch live scores from MLB Stats API for a given date and sport."""
    live = {}
    try:
        url = "https://statsapi.mlb.com/api/v1/schedule"
        params = {"sportId": sport_id, "date": api_date, "hydrate": "linescore"}
        r = httpx.get(url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return live
        for d in r.json().get("dates", []):
            for g in d.get("games", []):
                pk = str(g.get("gamePk"))
                state = g.get("status", {}).get("detailedState", "")
                ls = g.get("linescore", {})
                teams = ls.get("teams", {}) if ls else {}
                is_final = state in ("Final", "Game Over", "Completed Early")
                is_live = state in ("In Progress", "Live", "Delayed") or (
                    not is_final and state not in ("Scheduled", "Pre-Game", "Warmup", "")
                )
                inning = ls.get("currentInning", "") if ls else ""
                inning_state = ls.get("inningState", "") if ls else ""
                display_inning = f"{inning_state} {inning}" if inning_state and inning else inning_state or str(inning) or ""
                innings_data = g.get("linescore", {}).get("innings", [])
                ins = []
                for inn in innings_data:
                    ins.append({
                        "num": inn.get("num", 0),
                        "away_runs": inn.get("away", {}).get("runs") or 0,
                        "home_runs": inn.get("home", {}).get("runs") or 0,
                        "away_hits": inn.get("away", {}).get("hits") or 0,
                        "home_hits": inn.get("home", {}).get("hits") or 0,
                        "away_errors": inn.get("away", {}).get("errors") or 0,
                        "home_errors": inn.get("home", {}).get("errors") or 0,
                    })
                ls_detail = g.get("linescore", {})
                bases_raw = g.get("linescore", {}).get("bases", {}) or {}
                away_team_obj = g.get("teams", {}).get("away", {}).get("team", {})
                home_team_obj = g.get("teams", {}).get("home", {}).get("team", {})
                live[pk] = {
                    "sport_id": sport_id,
                    "status": state,
                    "is_final": is_final,
                    "is_live": is_live,
                    "inning": str(inning),
                    "inning_state": inning_state,
                    "display_inning": display_inning,
                    "away_runs": teams.get("away", {}).get("runs", 0) or 0,
                    "home_runs": teams.get("home", {}).get("runs", 0) or 0,
                    "away_hits": teams.get("away", {}).get("hits", 0) or 0,
                    "home_hits": teams.get("home", {}).get("hits", 0) or 0,
                    "away_errors": teams.get("away", {}).get("errors", 0) or 0,
                    "home_errors": teams.get("home", {}).get("errors", 0) or 0,
                    "away_team_name": away_team_obj.get("name", ""),
                    "home_team_name": home_team_obj.get("name", ""),
                    "linescore": {
                        "innings": ins,
                        "outs": ls_detail.get("outs", 0) or 0,
                        "balls": ls_detail.get("balls", 0) or 0,
                        "strikes": ls_detail.get("strikes", 0) or 0,
                        "current_inning": ls_detail.get("currentInning", 0) or 0,
                        "inning_state": ls_detail.get("inningState", ""),
                        "inning_half": ls_detail.get("inningHalf", ""),
                        "is_top": ls_detail.get("isTopInning", True),
                        "inning_ordinal": ls_detail.get("inningOrdinal", ""),
                        "bases": {
                            "first": bool(bases_raw.get("first", {}).get("occupied", False)) if isinstance(bases_raw.get("first"), dict) else False,
                            "second": bool(bases_raw.get("second", {}).get("occupied", False)) if isinstance(bases_raw.get("second"), dict) else False,
                            "third": bool(bases_raw.get("third", {}).get("occupied", False)) if isinstance(bases_raw.get("third"), dict) else False,
                        },
                    },
                }
    except Exception as e:
        print(f"Error fetching sportId={sport_id} date={api_date}: {e}")
    return live


def load_estado() -> list:
    """Load analysis estado from partidos_seguimiento.json."""
    for path in ["partidos_seguimiento.json", "../partidos_seguimiento.json"]:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return []


def _load_autorizados() -> list:
    """Load authorized user IDs from suscriptores.json for mini app auth."""
    for path in ["suscriptores.json", "../suscriptores.json"]:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                # Support both formats: {autorizados: [...]} or {suscripciones: {...}}
                if "autorizados" in data:
                    return [int(uid) for uid in data["autorizados"]]
                elif "suscripciones" in data:
                    return [int(uid) for uid in data["suscripciones"].keys()]
            except Exception:
                pass
    return []


def main():
    now_utc = datetime.now(tz=timezone.utc)
    mt_tz = timezone(timedelta(hours=MT_OFFSET))
    now_local = datetime.now(tz=mt_tz)

    today_str = now_local.strftime("%Y-%m-%d")
    yesterday_str = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_str = (now_local + timedelta(days=1)).strftime("%Y-%m-%d")
    accepted_dates = {today_str, yesterday_str, tomorrow_str}

    api_date = now_local.strftime("%m/%d/%Y")

    live_mlb = fetch_live_scores(api_date, 1)
    live_lmb = fetch_live_scores(api_date, 23)

    all_live = {}
    dupes = set(live_mlb) & set(live_lmb)
    if dupes:
        logger.warning(f"gamePk duplicados entre MLB y LMB: {dupes}")
    all_live.update(live_mlb)
    all_live.update(live_lmb)

    has_live = any(v.get("is_live") for v in all_live.values())
    has_scheduled = any(v.get("status") in ("Scheduled", "Pre-Game") for v in all_live.values())

    estado = load_estado()

    def norm(n):
        return n.strip().lower()

    def find_live_pk(pk_str, away, home):
        live = all_live.get(pk_str, {})
        if live:
            return live
        away_lower = away.strip().lower()
        home_lower = home.strip().lower()
        for lpk, ldata in all_live.items():
            at = ldata.get("away_team_name", "").strip().lower()
            ht = ldata.get("home_team_name", "").strip().lower()
            if (away_lower in at or at in away_lower) and (home_lower in ht or ht in home_lower):
                return ldata
        return {}

    games = []
    seen = set()

    # Fallback: if estado is empty (CI has no partidos_seguimiento.json),
    # build games directly from MLB Stats API data
    if not estado:
        for pk, ldata in all_live.items():
            away_name = ldata.get("away_team_name", "")
            home_name = ldata.get("home_team_name", "")
            if not away_name or not home_name:
                continue
            game_date = today_str
            key = (game_date, norm(away_name), norm(home_name))
            if key in seen:
                continue
            seen.add(key)

            is_final = ldata.get("is_final", False)
            is_live = ldata.get("is_live", False)

            if is_final:
                emoji = "🏁"
                state = "Final"
                result = "final"
            elif is_live:
                emoji = "🔴"
                state = ldata.get("display_inning", "En Vivo")
                result = "live"
            else:
                emoji = "⏳"
                state = "Pend."
                result = "pending"

            liga = "LMB" if ldata.get("sport_id") == 23 else "MLB"
            games.append({
                "liga": liga,
                "game_date": game_date,
                "status_emoji": emoji,
                "fav_team": away_name,
                "opp_team": home_name,
                "score_fav": str(ldata.get("away_runs", "")),
                "score_opp": str(ldata.get("home_runs", "")),
                "state": state,
                "result": result,
                "label": "📋",
                "senal": "",
                "certidumbre": "",
                "game_pk": int(pk) if pk.isdigit() else 0,
            })
    else:
        for sg in estado:
            favorito = sg.get("favorito", "")
            away = sg.get("away_team", "")
            home = sg.get("home_team", "")
            fecha_sg = sg.get("game_date", "")[:10]
            if fecha_sg not in accepted_dates:
                continue
            key = (fecha_sg, norm(away), norm(home))
            if key in seen:
                continue
            seen.add(key)

            prob = sg.get("prob_favorito", 0) or 0
            mercado = sg.get("odds_mercado")
            edge = round(prob - (mercado or 0), 2) if mercado else None
            nivel_cert = sg.get("nivel_certidumbre", "").strip()
            if nivel_cert in ("ALTA", "MEDIA") and prob >= 57.0:
                label = "🎯"
            else:
                label = "📋"

            pk = sg.get("game_pk", 0)
            is_lmb = sg.get("liga") == "LMB"
            live = find_live_pk(str(pk), away, home)

            if live.get("is_final"):
                emoji = "✅" if sg.get("resultado") == "acertado" else "❌"
                state = "Final"
                if favorito and (norm(favorito) in norm(home)):
                    s_fav = str(live.get("home_runs", ""))
                    s_opp = str(live.get("away_runs", ""))
                else:
                    s_fav = str(live.get("away_runs", ""))
                    s_opp = str(live.get("home_runs", ""))
                result = "win" if sg.get("resultado") == "acertado" else "loss"
            elif live.get("is_live"):
                emoji = "🔴"
                state = live.get("display_inning", live.get("inning_state", "En Vivo"))
                if favorito and (norm(favorito) in norm(home)):
                    s_fav = str(live.get("home_runs", ""))
                    s_opp = str(live.get("away_runs", ""))
                else:
                    s_fav = str(live.get("away_runs", ""))
                    s_opp = str(live.get("home_runs", ""))
                result = "live"
            else:
                emoji = "⏳"
                state = "Pend."
                s_fav, s_opp = "", ""
                result = "pending"

            _fav_in_home = favorito and (norm(favorito) in norm(home) or norm(home) in norm(favorito))
            fav = home if _fav_in_home else away
            opp = away if _fav_in_home else home

            liga = sg.get("liga", "MLB")
            games.append({
                "liga": liga,
                "game_date": fecha_sg,
                "status_emoji": emoji,
                "fav_team": fav,
                "opp_team": opp,
                "score_fav": s_fav,
                "score_opp": s_opp,
                "state": state,
                "result": result,
                "label": label,
                "senal": sg.get("senal_moneyline", "NO APOSTAR"),
                "certidumbre": sg.get("nivel_certidumbre", ""),
                "game_pk": pk,
            })

    games.sort(key=lambda x: (x.get("game_date", ""), {"🎯": 0, "📋": 1}.get(x.get("label", ""), 2)))

    dias_set = set()
    for g in games:
        d = g.get("game_date", "")
        if d:
            dias_set.add(d)
    dias_disponibles = sorted(dias_set, reverse=True)

    ahora_str = now_local.strftime("%d/%m/%Y %H:%M")
    prox = HORA_ANALISIS_MANANA
    prox_lmb = LMB_HORA_MANANA

    def _hoy_a_ts(hora_str):
        try:
            hh, mm = hora_str.split(":")
            target = now_local.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if target <= now_local:
                target += timedelta(days=1)
            return int(target.timestamp())
        except Exception:
            return 0

    def bs(s):
        return {
            "total": s.get("total", 0), "acertados": s.get("acertados", 0), "fallidos": s.get("fallidos", 0),
            "win_rate": s.get("win_rate", 0),
            "alta_total": s.get("alta_total", 0), "alta_acertados": s.get("alta_acertados", 0), "alta_fallidos": s.get("alta_fallidos", 0), "alta_win_rate": s.get("alta_win_rate", 0),
            "media_total": s.get("media_total", 0), "media_acertados": s.get("media_acertados", 0), "media_fallidos": s.get("media_fallidos", 0), "media_win_rate": s.get("media_win_rate", 0),
            "baja_total": s.get("baja_total", 0), "baja_acertados": s.get("baja_acertados", 0), "baja_fallidos": s.get("baja_fallidos", 0), "baja_win_rate": s.get("baja_win_rate", 0),
            "valor_ok": s.get("valor_ok", 0), "valor_total": s.get("valor_total", 0), "valor_rate": s.get("valor_rate", 0),
        }

    stats_data = {"total": 0, "acertados": 0, "fallidos": 0, "win_rate": 0}
    stats_mlb = {"total": 0, "acertados": 0, "fallidos": 0, "win_rate": 0}
    stats_lmb = {"total": 0, "acertados": 0, "fallidos": 0, "win_rate": 0}

    try:
        import csv
        for csv_path in ["apuestas.csv", "../apuestas.csv"]:
            if not os.path.exists(csv_path):
                continue
            with open(csv_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            for row in rows:
                res = row.get("resultado", "")
                liga = row.get("liga", "MLB")
                stats_data["total"] += 1
                if res == "acertado":
                    stats_data["acertados"] += 1
                elif res == "fallido":
                    stats_data["fallidos"] += 1
                if liga == "LMB":
                    stats_lmb["total"] += 1
                    if res == "acertado":
                        stats_lmb["acertados"] += 1
                    elif res == "fallido":
                        stats_lmb["fallidos"] += 1
                else:
                    stats_mlb["total"] += 1
                    if res == "acertado":
                        stats_mlb["acertados"] += 1
                    elif res == "fallido":
                        stats_mlb["fallidos"] += 1
            if stats_data["total"] > 0:
                stats_data["win_rate"] = round(stats_data["acertados"] / (stats_data["acertados"] + stats_data["fallidos"]) * 100, 1) if (stats_data["acertados"] + stats_data["fallidos"]) > 0 else 0
            if stats_mlb["total"] > 0:
                stats_mlb["win_rate"] = round(stats_mlb["acertados"] / (stats_mlb["acertados"] + stats_mlb["fallidos"]) * 100, 1) if (stats_mlb["acertados"] + stats_mlb["fallidos"]) > 0 else 0
            if stats_lmb["total"] > 0:
                stats_lmb["win_rate"] = round(stats_lmb["acertados"] / (stats_lmb["acertados"] + stats_lmb["fallidos"]) * 100, 1) if (stats_lmb["acertados"] + stats_lmb["fallidos"]) > 0 else 0
            break
    except Exception as e:
        print(f"Error loading CSV stats: {e}")

    data = {
        "fecha": ahora_str,
        "proxima_actualizacion": prox,
        "proxima_actualizacion_lmb": prox_lmb,
        "proxima_actualizacion_ts": _hoy_a_ts(prox),
        "proxima_actualizacion_lmb_ts": _hoy_a_ts(prox_lmb),
        "dias": dias_disponibles,
        "games": games,
        "bot_username": TELEGRAM_BOT_USERNAME,
        "stats": bs(stats_data),
        "stats_mlb": bs(stats_mlb),
        "stats_lmb": bs(stats_lmb),
        "live_data": all_live,
        "has_live": has_live,
        "has_scheduled": has_scheduled,
        "updated_at": now_utc.isoformat(),
        "autorizados": _load_autorizados(),
    }

    os.makedirs("docs", exist_ok=True)
    with open("docs/live_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    for pk, ldata in all_live.items():
        with open(f"docs/linescore_{pk}.json", "w", encoding="utf-8") as f:
            json.dump(ldata.get("linescore", {}), f, ensure_ascii=False, indent=2, default=str)

    status = "LIVE" if has_live else ("SCHEDULED" if has_scheduled else "NO GAMES")
    print(f"[{status}] {len(games)} games | {len(all_live)} live scores | {ahora_str}")


if __name__ == "__main__":
    main()
