import asyncio
import json
import logging
import math
import os
import sys
from datetime import datetime, date, timedelta, timezone
from typing import Optional

import httpx
import pytz

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_SCRIPT_DIR))

import config
import data_manager as dm
import telegram_handler
from analyzer import analizar_dia, GameAnalysis
from analyzer_lmb import analizar_lmb_dia
from api_client import mlb as _mlb_api
from railway_app import persistencia

logger = logging.getLogger(__name__)

MT_TZ = pytz.timezone(config.TIMEZONE)

BASE_DIR = os.path.dirname(_SCRIPT_DIR)

_cache: dict = {
    "games": [],
    "stats": {},
    "stats_mlb": {},
    "stats_lmb": {},
    "fecha": "",
    "proxima_actualizacion": "",
    "proxima_actualizacion_lmb": "",
    "live_data": {},
    "dias": [],
}


def _build_data() -> dict:
    from datetime import datetime as _dt
    ahora = _dt.now(MT_TZ)
    hoy = ahora
    ayer = hoy - timedelta(days=1)
    anteayer = hoy - timedelta(days=2)
    maniana = hoy + timedelta(days=1)
    fechas = {
        hoy.strftime("%Y-%m-%d"),
        ayer.strftime("%Y-%m-%d"),
        anteayer.strftime("%Y-%m-%d"),
        maniana.strftime("%Y-%m-%d"),
    }

    estado = dm.cargar_estado()
    games = []
    seen = set()
    live_data = _cache.get("live_data", {})

    def norm(n):
        return n.strip().lower()

    def make_key(fecha, away, home):
        return (fecha, norm(away), norm(home))

    stats = dm.obtener_estadisticas()
    stats_mlb = dm.obtener_estadisticas(liga="MLB")
    stats_lmb = dm.obtener_estadisticas(liga="LMB")

    p_min = config.PROB_MINIMA_ANALISIS
    e_min = config.EDGE_MINIMO

    lmb_live_by_teams = {}
    for lpk, ldata in live_data.items():
        at = ldata.get("away_team_name", "").strip().lower()
        ht = ldata.get("home_team_name", "").strip().lower()
        if at and ht:
            lmb_live_by_teams[(at, ht)] = lpk

    def _match(a, b):
        a, b = a.strip().lower(), b.strip().lower()
        return a == b or a in b or b in a

    def _find_live(pk, away, home, is_lmb):
        live = live_data.get(str(pk), {})
        if live:
            return live
        if is_lmb:
            away_lower = away.strip().lower()
            home_lower = home.strip().lower()
            for (lat, lht), lpk in lmb_live_by_teams.items():
                if _match(away_lower, lat) and _match(home_lower, lht):
                    return live_data.get(lpk, {})
        return {}

    for sg in estado:
        favorito = sg.get("favorito", "")
        away = sg.get("away_team", "")
        home = sg.get("home_team", "")
        fecha_sg = sg.get("game_date", "")[:10]
        if fecha_sg not in fechas:
            continue
        key = make_key(fecha_sg, away, home)
        if key in seen:
            continue
        seen.add(key)

        prob = sg.get("prob_favorito", 0) or 0
        mercado = sg.get("odds_mercado")
        edge = round(prob - mercado, 2) if mercado else None
        if prob >= p_min and edge is not None and edge >= e_min:
            label = "🎯"
        elif prob >= p_min:
            label = "📊"
        else:
            label = "📋"

        pk = sg.get("game_pk", 0)
        is_lmb = sg.get("liga") == "LMB"
        live = _find_live(pk, away, home, is_lmb)

        if live.get("is_final"):
            emoji = "✅" if sg.get("resultado") == "acertado" else "❌"
            state = "Final"
            s_fav = str(live.get("home_runs", "")) if favorito and (norm(favorito) in norm(home)) else str(live.get("away_runs", ""))
            s_opp = str(live.get("away_runs", "")) if favorito and (norm(favorito) in norm(home)) else str(live.get("home_runs", ""))
            result = "win" if sg.get("resultado") == "acertado" else "loss"
        elif live.get("is_live"):
            emoji = "🔴"
            state = live.get("display_inning", live.get("inning_state", "En Vivo"))
            s_fav = str(live.get("home_runs", "")) if favorito and (norm(favorito) in norm(home)) else str(live.get("away_runs", ""))
            s_opp = str(live.get("away_runs", "")) if favorito and (norm(favorito) in norm(home)) else str(live.get("home_runs", ""))
            result = "live"
        else:
            emoji = "⏳"
            state = "Pend."
            s_fav, s_opp = "", ""
            result = "pending"

        _fav_in_home = favorito and (norm(favorito) in norm(home) or norm(home) in norm(favorito))
        fav = home if _fav_in_home else away
        opp = away if _fav_in_home else home
        if not s_fav and not s_opp:
            s_fav, s_opp = "", ""

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

    ahora_str = ahora.strftime("%d/%m/%Y %H:%M")
    prox = getattr(config, "HORA_ANALISIS_MANANA", "08:00")
    prox_lmb = getattr(config, "LMB_HORA_MANANA", "10:00")

    def _hoy_a_ts(hora_str: str) -> int:
        try:
            hh, mm = hora_str.split(":")
            target = ahora.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if target <= ahora:
                target += timedelta(days=1)
            return int(target.timestamp())
        except Exception:
            return 0

    def bs(s):
        return {
            "total": s["total"], "acertados": s["acertados"], "fallidos": s["fallidos"],
            "win_rate": s["win_rate"],
            "alta_total": s["alta_total"], "alta_acertados": s["alta_acertados"], "alta_fallidos": s["alta_fallidos"], "alta_win_rate": s["alta_win_rate"],
            "media_total": s["media_total"], "media_acertados": s["media_acertados"], "media_fallidos": s["media_fallidos"], "media_win_rate": s["media_win_rate"],
            "baja_total": s["baja_total"], "baja_acertados": s["baja_acertados"], "baja_fallidos": s["baja_fallidos"], "baja_win_rate": s["baja_win_rate"],
            "valor_ok": s["valor_ok"], "valor_total": s["valor_total"], "valor_rate": s["valor_rate"],
        }

    has_live = any(g.get("result") == "live" for g in games)
    has_scheduled = any(g.get("result") == "pending" for g in games)
    has_lmb = any(g.get("liga") == "LMB" for g in games)

    return {
        "fecha": ahora_str,
        "proxima_actualizacion": prox,
        "proxima_actualizacion_lmb": prox_lmb,
        "proxima_actualizacion_ts": _hoy_a_ts(prox),
        "proxima_actualizacion_lmb_ts": _hoy_a_ts(prox_lmb),
        "dias": dias_disponibles,
        "games": games,
        "has_live": has_live,
        "has_scheduled": has_scheduled,
        "has_lmb": has_lmb,
        "bot_username": config.TELEGRAM_BOT_USERNAME,
        "autorizados": _cargar_suscriptores(),
        "stats": bs(stats),
        "stats_mlb": bs(stats_mlb),
        "stats_lmb": bs(stats_lmb),
    }


def _cargar_suscriptores() -> list[int]:
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "suscriptores.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "suscriptores.json"),
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            suscripciones = data.get("suscripciones", {})
            admin = data.get("admin_id")
            hoy = datetime.now(MT_TZ).date().isoformat()
            validos = []
            for uid_str, expira in suscripciones.items():
                uid = int(uid_str)
                if expira is None or expira >= hoy:
                    validos.append(uid)
            if admin and admin not in validos:
                validos.append(admin)
            return validos
        except Exception:
            continue
    return []


# ── Tareas del scheduler ──────────────────────────────────────────────

def _backup():
    try:
        persistencia.respaldar_a_github(BASE_DIR)
    except Exception as e:
        logger.warning(f"Backup a GitHub falló: {e}")

def tarea_analisis_mlb():
    logger.info("=== Ejecutando análisis MLB ===")
    try:
        partidos = analizar_dia()
        if partidos:
            dm.guardar_analisis(partidos)
            dm.guardar_estado(partidos)
            _backup()
            logger.info(f"MLB: {len(partidos)} partidos analizados")
        else:
            logger.info("MLB: sin partidos para hoy")
    except Exception as e:
        logger.error(f"Error análisis MLB: {e}")


def tarea_analisis_lmb():
    if not getattr(config, "LMB_ACTIVO", False):
        return
    logger.info("=== Ejecutando análisis LMB ===")
    try:
        result = analizar_lmb_dia()
        if result:
            dm.guardar_analisis_lmb(result)
            dm.guardar_estado_lmb(result)
            _backup()
            logger.info(f"LMB: {len(result)} partidos analizados")
    except Exception as e:
        logger.error(f"Error análisis LMB: {e}")


def tarea_resultados():
    logger.info("=== Verificando resultados ===")
    try:
        from api_client import mlb
        estado = dm.cargar_estado()
        actualizados = 0
        for p in estado:
            pk = p.get("game_pk")
            if not pk:
                continue
            if p.get("resultado") in ("acertado", "fallido"):
                continue
            try:
                feed = mlb.game_feed(pk)
                status = (feed.get("gameData", {}).get("status", {}) or
                          feed.get("liveData", {}).get("linescore", {}))
                detailed_state = (feed.get("gameData", {}).get("status", {}).get("detailedState", "") or
                                  status.get("status", {}).get("detailedState", ""))
                if detailed_state in ("Final", "Game Over", "Completed Early"):
                    away_runs = feed.get("liveData", {}).get("linescore", {}).get("teams", {}).get("away", {}).get("runs", 0)
                    home_runs = feed.get("liveData", {}).get("linescore", {}).get("teams", {}).get("home", {}).get("runs", 0)
                    away_name = p.get("away_team", "")
                    home_name = p.get("home_team", "")
                    ganador = away_name if away_runs > home_runs else home_name
                    marcador = f"{away_name} {away_runs} - {home_runs} {home_name}"
                    dm.actualizar_resultado(pk, ganador, marcador)
                    dm.actualizar_estado_resultado(pk, "acertado" if ganador == p.get("favorito") else "fallido", ganador)
                    actualizados += 1
            except Exception:
                continue
        if actualizados:
            logger.info(f"Resultados actualizados: {actualizados}")
            _backup()
    except Exception as e:
        logger.error(f"Error en tarea_resultados: {e}")


def tarea_publicar_miniapp():
    if not config.GITHUB_TOKEN:
        return
    try:
        from miniapp_publisher import publicar
        if publicar():
            logger.info("Mini App publicada")
    except Exception as e:
        logger.error(f"Error publicando Mini App: {e}")


def tarea_publicar_datos():
    """Push live_data.json + soccer_data.json a GitHub Pages (sin tocar HTML)."""
    if not config.GITHUB_TOKEN:
        return
    try:
        from miniapp_publisher import publicar_live_data
        if publicar_live_data():
            logger.info("Data publicada a GitHub Pages")
    except Exception as e:
        logger.error(f"Error publicando data: {e}")


def tarea_analisis_futbol():
    try:
        import subprocess
        result = subprocess.run(
            ["python", "main.py", "--ahora"],
            cwd=config.FUTBOL_DIR,
            capture_output=True, text=True, timeout=120, encoding="utf-8",
        )
        if result.returncode == 0:
            logger.info("Fútbol: análisis completado")
            _backup()
        else:
            logger.error(f"Fútbol error: {result.stderr[:200]}")
    except Exception as e:
        logger.error(f"Error análisis fútbol: {e}")


# ── Scheduler principal ──────────────────────────────────────────────

def _hora_a_segundos(hora_str: str) -> int:
    try:
        hh, mm = hora_str.split(":")
        return int(hh) * 3600 + int(mm) * 60
    except Exception:
        return 0


async def ejecutar_en_horario(hora_str: str, tarea, nombre: str):
    """Espera hasta la hora indicada y ejecuta la tarea, luego espera 24h."""
    while True:
        ahora = datetime.now(MT_TZ)
        seg_objetivo = _hora_a_segundos(hora_str)
        seg_ahora = ahora.hour * 3600 + ahora.minute * 60 + ahora.second
        seg_espera = seg_objetivo - seg_ahora
        if seg_espera <= 0:
            seg_espera += 86400
        logger.info(f"{nombre}: próxima ejecución en {seg_espera // 60} min")
        await asyncio.sleep(seg_espera)
        try:
            tarea()
        except Exception as e:
            logger.error(f"Error en {nombre}: {e}")
        await asyncio.sleep(86400)


async def ejecutar_cada_intervalo(intervalo_seg: int, tarea, nombre: str, primera_vez: float = None):
    """Ejecuta una tarea cada intervalo_seg segundos."""
    if primera_vez is not None:
        await asyncio.sleep(primera_vez)
    while True:
        try:
            tarea()
            logger.debug(f"{nombre}: ejecutada")
        except Exception as e:
            logger.error(f"Error en {nombre}: {e}")
        await asyncio.sleep(intervalo_seg)


async def iniciar_scheduler(run_initial: bool = True):
    """Arranca todas las tareas del scheduler como background tasks."""
    logger.info("=== Iniciando scheduler Railway ===")

    if run_initial:
        # Ejecutar análisis inmediatamente al arrancar
        tarea_analisis_mlb()
        tarea_analisis_lmb()
        tarea_resultados()

    # Recalcular hora análisis dinámico cada día a las 05:00
    asyncio.create_task(ejecutar_en_horario(
        config.HORA_RECALCULO_DIARIO, tarea_analisis_mlb, "Análisis MLB diario"
    ))

    # Re-análisis fijo MLB a las 08:00
    asyncio.create_task(ejecutar_en_horario(
        config.REANALISIS_MLB_HORA, tarea_analisis_mlb, "Re-análisis MLB"
    ))

    # Re-análisis fijo LMB a las 12:30
    if getattr(config, "LMB_ACTIVO", False):
        asyncio.create_task(ejecutar_en_horario(
            config.REANALISIS_LMB_HORA, tarea_analisis_lmb, "Re-análisis LMB"
        ))

    # Resultados cada 2 horas (sincronizado a la hora par)
    ahora = datetime.now(MT_TZ)
    hora_sig = (math.floor(ahora.hour / 2) + 1) * 2
    if hora_sig >= 24:
        seg_primera = 86400 - (ahora.hour * 3600 + ahora.minute * 60 + ahora.second)
        seg_primera += 0 * 3600
    else:
        seg_primera = (hora_sig - ahora.hour) * 3600 - ahora.minute * 60 - ahora.second
    if seg_primera < 0:
        seg_primera += 7200
    asyncio.create_task(ejecutar_cada_intervalo(
        7200, tarea_resultados,
        "Resultados cada 2h", primera_vez=max(seg_primera, 60)
    ))

    # Mini App cada 15 min — solo data (HTML solo en deploy manual)
    asyncio.create_task(ejecutar_cada_intervalo(
        900, tarea_publicar_datos, "Mini App data cada 15 min"
    ))

    # Análisis fútbol cada 20 min (live scores)
    asyncio.create_task(ejecutar_cada_intervalo(
        1200, tarea_analisis_futbol, "Fútbol cada 20 min"
    ))

    logger.info("Scheduler Railway: todas las tareas registradas")


# ── Live scores (existente) ───────────────────────────────────────────

async def fetch_live_data() -> dict:
    live = {}
    today = datetime.now(MT_TZ).date()
    date_str = today.strftime("%m/%d/%Y")

    async with httpx.AsyncClient(timeout=15) as client:
        for sport_id, name in [(1, "MLB"), (23, "LMB")]:
            try:
                r = await client.get(
                    "https://statsapi.mlb.com/api/v1/schedule",
                    params={"sportId": sport_id, "date": date_str, "hydrate": "linescore"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if r.status_code != 200:
                    continue
                for d in r.json().get("dates", []):
                    for g in d.get("games", []):
                        pk = str(g.get("gamePk"))
                        state = g.get("status", {}).get("detailedState", "")
                        ls = g.get("linescore", {})
                        teams = ls.get("teams", {}) if ls else {}
                        inning = ls.get("currentInning", "") if ls else ""
                        inning_state = ls.get("inningState", "") if ls else ""
                        is_final = state in ("Final", "Game Over", "Completed Early")
                        is_live = state in ("In Progress", "Live", "Delayed") or (
                            not is_final and state not in ("Scheduled", "Pre-Game", "Warmup", "")
                        )
                        display_inning = f"{inning_state} {inning}" if inning_state and inning else inning_state or inning or ""
                        innings_data = g.get("linescore", {}).get("innings", [])
                        ins = []
                        for inn in innings_data:
                            ins.append({
                                "num": inn.get("num", 0),
                                "away_runs": _safe_int(inn.get("away", {}).get("runs")),
                                "home_runs": _safe_int(inn.get("home", {}).get("runs")),
                                "away_hits": _safe_int(inn.get("away", {}).get("hits")),
                                "home_hits": _safe_int(inn.get("home", {}).get("hits")),
                                "away_errors": _safe_int(inn.get("away", {}).get("errors")),
                                "home_errors": _safe_int(inn.get("home", {}).get("errors")),
                            })
                        away_team_obj = g.get("teams", {}).get("away", {}).get("team", {})
                        home_team_obj = g.get("teams", {}).get("home", {}).get("team", {})
                        live[pk] = {
                            "status": state,
                            "is_final": is_final,
                            "is_live": is_live,
                            "inning": inning or "",
                            "inning_state": inning_state or "",
                            "display_inning": display_inning,
                            "away_runs": _safe_int(teams.get("away", {}).get("runs")),
                            "home_runs": _safe_int(teams.get("home", {}).get("runs")),
                            "away_hits": _safe_int(teams.get("away", {}).get("hits")),
                            "home_hits": _safe_int(teams.get("home", {}).get("hits")),
                            "away_errors": _safe_int(teams.get("away", {}).get("errors")),
                            "home_errors": _safe_int(teams.get("home", {}).get("errors")),
                            "away_team_name": away_team_obj.get("name", ""),
                            "home_team_name": home_team_obj.get("name", ""),
                            "linescore": {"innings": ins},
                        }
            except Exception as e:
                logger.warning(f"{name} live fetch error: {e}")

    return live


def _safe_int(v, default=0):
    try:
        return int(v) if v is not None else default
    except (ValueError, TypeError):
        return default


async def ciclo_actualizacion(ws_manager):
    logger.info("=== Ciclo de actualización en vivo iniciado ===")

    while True:
        try:
            live = await fetch_live_data()
            _cache["live_data"] = live

            estado = dm.cargar_estado()

            def _match(a, b):
                a, b = a.strip().lower(), b.strip().lower()
                return a == b or a in b or b in a

            lmb_live_by_teams = {}
            for lpk, ldata in live.items():
                at = ldata.get("away_team_name", "").strip().lower()
                ht = ldata.get("home_team_name", "").strip().lower()
                if at and ht:
                    lmb_live_by_teams[(at, ht)] = lpk

            for p in estado:
                pk = str(p.get("game_pk", ""))
                is_lmb = p.get("liga") == "LMB"

                matched_pk = pk if pk in live else None

                if not matched_pk and is_lmb:
                    away_lower = p.get("away_team", "").strip().lower()
                    home_lower = p.get("home_team", "").strip().lower()
                    for (lat, lht), lpk in lmb_live_by_teams.items():
                        if _match(away_lower, lat) and _match(home_lower, lht):
                            matched_pk = lpk
                            break

                if not matched_pk:
                    continue

                ldata = live[matched_pk]
                if not ldata.get("is_final"):
                    continue
                if p.get("resultado") in ("acertado", "fallido"):
                    continue

                ar = ldata.get("away_runs", 0)
                hr = ldata.get("home_runs", 0)
                away_name = p.get("away_team", "")
                home_name = p.get("home_team", "")
                ganador = away_name if ar > hr else home_name
                marcador = f"{away_name} {ar} - {hr} {home_name}"
                dm.actualizar_resultado(int(pk), ganador, marcador)
                acertado = _match(ganador, p.get("favorito", ""))
                dm.actualizar_estado_resultado(int(pk), "acertado" if acertado else "fallido", ganador)
                logger.info(f"Resultado actualizado ({p.get('liga','MLB')}): {marcador} -> {'acertado' if acertado else 'fallido'}")

            _backup()
            data = _build_data()
            await ws_manager.broadcast({"type": "full_update", "data": data})

        except Exception as e:
            logger.error(f"Error en ciclo actualización: {e}")

        await asyncio.sleep(60)


def run_initial_analysis():
    logger.info("=== Inicializando análisis MLB ===")
    try:
        tarea_analisis_mlb()
    except Exception as e:
        logger.error(f"MLB initial analysis error: {e}")

    if getattr(config, "LMB_ACTIVO", False):
        logger.info("=== Inicializando análisis LMB ===")
        try:
            tarea_analisis_lmb()
        except Exception as e:
            logger.error(f"LMB initial analysis error: {e}")

    _backup()
    _cache["live_data"] = {}
