"""
MLB BOT — scheduler_debug.py
Versión con prints de diagnóstico en tarea_resultados y _espn_resultado.
Usar temporalmente para diagnosticar por qué no se actualizan resultados.
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional
import math

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR

import config
import bot
import data_manager as dm
from analyzer import analizar_dia, GameAnalysis
from api_client import mlb as _mlb_api
import requests as _requests
import telegram_handler

# ── LMB ──────────────────────────────────────────────────────────────────────
if getattr(config, "LMB_ACTIVO", False):
    try:
        from analyzer_lmb import analizar_lmb_dia
    except ImportError:
        analizar_lmb_dia = None

logger = logging.getLogger(__name__)

_analyses_hoy: list[GameAnalysis] = []

# ── Programación dinámica ─────────────────────────────────────────────────────
_scheduler: Optional[BlockingScheduler] = None
_hora_analisis_hoy: str = config.HORA_ANALISIS_MANANA
_hora_analisis_lmb: str = getattr(config, "LMB_HORA_MANANA", "10:00")


def _calcular_hora_analisis(game_date: str = None) -> str:
    """
    Calcula la hora óptima para ejecutar el análisis:
    primer partido del día - MINUTOS_PREVIA_ANALISIS (60 min).
    Retorna 'HH:MM' en hora local.
    Fallback a HORA_ANALISIS_MANANA si no hay partidos o falla API.
    """
    try:
        import pytz
        schedule = _mlb_api.get_schedule(game_date)
        if not schedule:
            return config.HORA_ANALISIS_MANANA

        tz_local = pytz.timezone(config.TIMEZONE)
        primer_utc = None

        for d in schedule.get("dates", []):
            for g in d.get("games", []):
                raw_dt = g.get("gameDate", "")
                if "T" in raw_dt:
                    if primer_utc is None or raw_dt < primer_utc:
                        primer_utc = raw_dt

        if not primer_utc:
            return config.HORA_ANALISIS_MANANA

        dt_utc = datetime.fromisoformat(primer_utc.replace("Z", "+00:00"))
        dt_local = dt_utc.astimezone(tz_local)
        dt_analisis = dt_local - timedelta(minutes=config.MINUTOS_PREVIA_ANALISIS)

        ahora = datetime.now(tz_local)
        if dt_analisis <= ahora:
            return ahora.strftime("%H:%M")

        return dt_analisis.strftime("%H:%M")
    except Exception as e:
        logger.warning(f"Error en _calcular_hora_analisis: {e}")
        return config.HORA_ANALISIS_MANANA


def _programar_analisis() -> str:
    """(Re)programa el análisis diario con hora calculada dinámicamente."""
    global _scheduler, _hora_analisis_hoy
    if _scheduler is None:
        return config.HORA_ANALISIS_MANANA

    hora = _calcular_hora_analisis()
    hora_h, hora_m = hora.split(":")

    _scheduler.add_job(
        tarea_analisis_manana,
        CronTrigger(hour=int(hora_h), minute=int(hora_m), timezone=config.TIMEZONE),
        id="analisis_manana",
        name="Análisis MLB (dinámico)",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
        replace_existing=True,
    )
    _hora_analisis_hoy = hora
    logger.info(f"Análisis programado: {hora} ({config.TIMEZONE})")
    return hora


# ── Re-análisis fijo ───────────────────────────────────────────────────────
_hora_reanalisis_mlb: str = getattr(config, "REANALISIS_MLB_HORA", "10:00")
_hora_reanalisis_lmb: str = getattr(config, "REANALISIS_LMB_HORA", "14:00")


def obtener_hora_reanalisis() -> str:
    return _hora_reanalisis_mlb


def obtener_hora_reanalisis_lmb() -> str:
    return _hora_reanalisis_lmb


def tarea_reanalisis_mlb():
    """Re-análisis MLB a hora fija — actualiza datos sin notificar."""
    global _analyses_hoy
    logger.info("=== RE-ANÁLISIS MLB (fijo) ===")
    try:
        _analyses_hoy = analizar_dia()
    except Exception as e:
        logger.error(f"Re-análisis MLB falló: {e}")
        return
    if not _analyses_hoy:
        logger.info("Re-análisis MLB: sin partidos")
        return
    dm.guardar_analisis(_analyses_hoy)
    dm.guardar_estado(_analyses_hoy)
    if config.GITHUB_TOKEN:
        try:
            from miniapp_publisher import publicar
            publicar()
        except Exception as e:
            logger.error(f"Mini App publish error (re-análisis MLB): {e}")
    logger.info(f"Re-análisis MLB: {len(_analyses_hoy)} partidos")


def tarea_reanalisis_lmb():
    """Re-análisis LMB a hora fija — actualiza datos sin notificar."""
    if not getattr(config, "LMB_ACTIVO", False) or analizar_lmb_dia is None:
        return
    logger.info("=== RE-ANÁLISIS LMB (fijo) ===")
    try:
        result = analizar_lmb_dia()
    except Exception as e:
        logger.error(f"Re-análisis LMB falló: {e}")
        return
    if not result:
        logger.info("Re-análisis LMB: sin partidos")
        return
    dm.guardar_analisis_lmb(result)
    dm.guardar_estado_lmb(result)
    bot.enviar_analisis_lmb(result)
    if config.GITHUB_TOKEN:
        try:
            from miniapp_publisher import publicar
            publicar()
        except Exception as e:
            logger.error(f"Mini App publish error (re-análisis LMB): {e}")
    logger.info(f"Re-análisis LMB: {len(result)} partidos")


# ── FÚTBOL ────────────────────────────────────────────────────────────────────
def tarea_analisis_futbol():
    """Ejecuta el análisis de fútbol del día."""
    import subprocess
    logger.info("=== ANÁLISIS FÚTBOL ===")
    try:
        result = subprocess.run(
            [sys.executable, "main.py", "--ahora"],
            cwd=config.FUTBOL_DIR,
            capture_output=True, text=True, timeout=120, encoding="utf-8",
        )
        if result.returncode == 0:
            logger.info("Fútbol: análisis completado")
        else:
            logger.error(f"Fútbol error: {result.stderr[:300]}")
    except Exception as e:
        logger.error(f"Error análisis fútbol: {e}")


def tarea_reanalis_futbol():
    """Re-análisis de fútbol cada 20 min si hay partidos pendientes."""
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "main.py", "--live"],
            cwd=config.FUTBOL_DIR,
            capture_output=True, text=True, timeout=120, encoding="utf-8",
        )
        if result.returncode == 0:
            logger.debug("Fútbol: live scores actualizados")
        else:
            logger.debug(f"Fútbol live: {result.stderr[:200]}")
    except Exception as e:
        logger.debug(f"Error live scores fútbol: {e}")


def obtener_hora_analisis() -> str:
    """Retorna la última hora de análisis programada (para Mini App)."""
    return _hora_analisis_hoy


# ── Programación dinámica LMB ─────────────────────────────────────────────────
def _calcular_hora_analisis_lmb(game_date: str = None) -> str:
    """
    Calcula hora óptima LMB: primer partido LMB - LMB_MINUTOS_PREVIA.
    Scrapea BR para el horario del primer juego.
    Fallback a LMB_HORA_MANANA.
    """
    if not getattr(config, "LMB_ACTIVO", False):
        return getattr(config, "LMB_HORA_MANANA", "10:00")
    try:
        from api_client_lmb import mlb_lmb as _lmb_client
        hora = _lmb_client.get_first_game_time(game_date)
        if hora:
            return hora
    except Exception as e:
        logger.warning(f"Error en _calcular_hora_analisis_lmb: {e}")
    return getattr(config, "LMB_HORA_MANANA", "10:00")


def _programar_analisis_lmb() -> str:
    """(Re)programa el análisis LMB con hora calculada dinámicamente."""
    global _scheduler, _hora_analisis_lmb
    if _scheduler is None:
        return getattr(config, "LMB_HORA_MANANA", "10:00")
    if not getattr(config, "LMB_ACTIVO", False):
        return _hora_analisis_lmb

    hora = _calcular_hora_analisis_lmb()
    hora_h, hora_m = hora.split(":")
    _scheduler.add_job(
        tarea_analisis_lmb,
        CronTrigger(hour=int(hora_h), minute=int(hora_m), timezone=config.TIMEZONE),
        id="analisis_lmb",
        name="Análisis LMB (dinámico)",
        max_instances=1, coalesce=True, misfire_grace_time=600,
        replace_existing=True,
    )
    _hora_analisis_lmb = hora
    logger.info(f"Análisis LMB programado: {hora} ({config.TIMEZONE})")
    return hora


def obtener_hora_analisis_lmb() -> str:
    """Retorna la última hora de análisis LMB programada (para Mini App)."""
    return _hora_analisis_lmb


# ─────────────────────────────────────────────────────────────────────────────
# TAREA 1 — ANÁLISIS MATUTINO
# ─────────────────────────────────────────────────────────────────────────────
def tarea_analisis_manana():
    global _analyses_hoy
    logger.info("=== TAREA 08:00 AM — Análisis matutino iniciado ===")

    for intento in range(1, config.MAX_REINTENTOS_API + 1):
        try:
            _analyses_hoy = analizar_dia()
            break
        except Exception as e:
            logger.error(f"Intento {intento}/{config.MAX_REINTENTOS_API} fallido: {e}")
            if intento < config.MAX_REINTENTOS_API:
                import time
                time.sleep(config.DELAY_ENTRE_REINTENTOS)
            else:
                bot.enviar_mensaje(
                    "🚨 <b>MLB BOT ERROR</b>\n"
                    "No se pudo completar el análisis matutino.\n"
                    "Revisa los logs: mlb_bot.log"
                )
                return

    if not _analyses_hoy:
        bot.enviar_mensaje("⚾ <b>MLB BOT</b>\nℹ️ Sin partidos de MLB programados para hoy.")
        return

    dm.guardar_analisis(_analyses_hoy)
    dm.guardar_estado(_analyses_hoy)
    bot.enviar_notificacion_actualizacion("MLB")
    logger.info(f"Análisis completado: {len(_analyses_hoy)} partidos")


# ─────────────────────────────────────────────────────────────────────────────
# TAREA 1B — ANÁLISIS LMB
# ─────────────────────────────────────────────────────────────────────────────
def tarea_analisis_lmb():
    """Ejecuta análisis LMB y guarda resultados."""
    global _analyses_hoy
    if getattr(config, "LMB_ACTIVO", False) is False:
        return
    if analizar_lmb_dia is None:
        logger.warning("analyzer_lmb no disponible — omitiendo LMB")
        return

    logger.info("=== TAREA LMB — Análisis iniciado ===")
    try:
        result = analizar_lmb_dia()
    except Exception as e:
        logger.error(f"Error en análisis LMB: {e}", exc_info=True)
        bot.enviar_mensaje(
            "🚨 <b>MLB BOT — Error LMB</b>\n"
            f"💥 No se pudo completar el análisis LMB.\n"
            f"🔧 Error: <code>{e}</code>"
        )
        return

    if not result:
        logger.info("LMB: sin partidos analizados hoy")
        return

    dm.guardar_analisis_lmb(result)
    dm.guardar_estado_lmb(result)

    # Enviar mensaje de análisis LMB detallado
    bot.enviar_analisis_lmb(result)

    # Publicar Mini App
    if config.GITHUB_TOKEN:
        try:
            from miniapp_publisher import publicar
            ok = publicar()
            if ok:
                logger.info("Mini App publicada tras análisis LMB")
        except Exception as e:
            logger.error(f"Mini App publish error (LMB): {e}")

    bot.enviar_notificacion_actualizacion("LMB")
    logger.info(f"Análisis LMB completado: {len(result)} partidos")


# ─────────────────────────────────────────────────────────────────────────────
# TAREA 2 — RESULTADOS (con debug completo)
# ─────────────────────────────────────────────────────────────────────────────
def tarea_resultados():
    global _analyses_hoy

    # No ejecutar entre medianoche y 6 AM
    import pytz as _tz
    tz = _tz.timezone(config.TIMEZONE)
    hora = datetime.now(tz).hour
    if 0 <= hora < 6:
        logger.info("Resultados: saltando — hora nocturna (%02d:00)")
        return

    estado = dm.cargar_estado()
    pendientes = [p for p in estado if p.get("resultado") == "pendiente"]

    # ── DIAGNÓSTICO ──
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"[RESULTADOS] Estado total: {len(estado)} | Pendientes: {len(pendientes)}")
    for p in pendientes:
        print(f"  · pk={p.get('game_pk')} {p.get('away_team')} @ {p.get('home_team')} fecha={p.get('game_date','')[:10]} liga={p.get('liga','MLB')}")
    print(f"{sep}\n")
    logger.info(f"[DEBUG] tarea_resultados arrancó — {len(pendientes)} pendientes")

    if not pendientes:
        logger.info("Resultados: sin partidos pendientes")
        return

    for p in pendientes:
        game_pk = p["game_pk"]
        away    = p.get("away_team", "")
        home    = p.get("home_team", "")
        fecha   = p.get("game_date", "")[:10]
        liga    = p.get("liga", "MLB")

        if liga == "LMB":
            resultado = _lmb_stats_resultado(away, home, fecha)
        else:
            print(f"[ESPN] Consultando -> {away} @ {home} ({fecha})")
            resultado = _espn_resultado(away, home, fecha)
            print(f"[ESPN] Respuesta   <- {resultado}")
        logger.info(f"[DEBUG] Resultado para pk={game_pk} ({liga}): {resultado}")

        if not resultado:
            logger.info(f"Sin resultado aún: {away} @ {home} ({liga})")
            continue

        ganador = resultado["winner"]

        # ── POSPUESTO — eliminar del JSON y del CSV ───────────────────────
        if ganador == "POSTPONED":
            logger.info(f"Partido POSPUESTO — eliminando: {away} @ {home} ({fecha})")
            dm.eliminar_partido(game_pk, away_team=away, home_team=home, fecha=fecha)
            bot.enviar_mensaje(
                f"🚫 <b>Partido pospuesto</b>\n"
                f"⚾ {away} @ {home}\n"
                f"📅 {fecha}\n"
                f"🗑️ Eliminado del seguimiento."
            )
            continue
        marcador = (f"{resultado['away_name']} {resultado['away_runs']}"
                    f" - {resultado['home_runs']} {resultado['home_name']}")

        def _match(a: str, b: str) -> bool:
            a, b = a.strip().lower(), b.strip().lower()
            return a == b or a in b or b in a

        acertado = _match(ganador, p["favorito"])

        print(f"[CSV] Actualizando game_pk={game_pk} → {ganador} | {marcador}")
        dm.actualizar_resultado(game_pk, ganador, marcador)
        dm.actualizar_estado_resultado(
            game_pk,
            "acertado" if acertado else "fallido",
            ganador,
        )
        print(f"[CSV] ✅ Guardado")

        analysis = _buscar_analysis(game_pk)
        if analysis:
            bot.enviar_resultado(analysis, ganador, marcador)
        else:
            emoji = "✅" if acertado else "❌"
            fuente = "StatsAPI" if liga == "LMB" else "ESPN"
            bot.enviar_mensaje(
                f"{emoji} <b>{'ACERTADO' if acertado else 'FALLIDO'}</b>\n"
                f"⚾ {away} @ {home}\n"
                f"🏆 Bot: {p['favorito']} ({p['prob_favorito']:.1f}%)\n"
                f"🏁 Ganador: {ganador}\n"
                f"📊 {marcador}\n"
                f"📡 {fuente}"
            )
        logger.info(f"Resultado: {marcador} → {'acertado' if acertado else 'fallido'}")

    # ── Publicar Mini App si hay token ────────────────────────────────────
    if config.GITHUB_TOKEN:
        try:
            from miniapp_publisher import publicar
            ok = publicar()
            if ok:
                logger.info("Mini App publicada tras actualizar resultados")
        except Exception as e:
            logger.error(f"Mini App publish error: {e}")

    # ── Sync live_data.json a GitHub Pages ──────────────────────────────────
    try:
        from miniapp_publisher import publicar_live_data
        ok = publicar_live_data()
        if ok:
            logger.info("Sync GitHub Pages: live_data.json actualizado")
        else:
            logger.warning("Sync GitHub Pages: falló publicar live_data.json")
    except Exception as e:
        logger.warning(f"Sync GitHub Pages falló: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# ESPN — con debug de HTTP
# ─────────────────────────────────────────────────────────────────────────────
def _espn_resultado(away_team: str, home_team: str, game_date: str) -> Optional[dict]:
    import requests as _req

    def _match(a: str, b: str) -> bool:
        a, b = a.strip().lower(), b.strip().lower()
        return a == b or a in b or b in a

    try:
        date_str = game_date.replace("-", "")
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
            f"?dates={date_str}"
        )
        print(f"  [HTTP] GET {url}")
        r = _req.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        print(f"  [HTTP] Status: {r.status_code}")

        if r.status_code != 200:
            logger.warning(f"ESPN HTTP {r.status_code}")
            # ── FALLBACK: MLB Stats API
            return _mlb_stats_resultado(away_team, home_team, game_date)

        events = r.json().get("events", [])
        print(f"  [ESPN] Eventos encontrados: {len(events)}")

        for event in events:
            comp        = (event.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue

            h_name = home.get("team", {}).get("displayName", "")
            a_name = away.get("team", {}).get("displayName", "")
            completed = comp.get("status", {}).get("type", {}).get("completed", False)
            detail    = comp.get("status", {}).get("type", {}).get("detail", "?")
            print(f"  [ESPN] {'OK' if completed else '...'} {a_name} @ {h_name} | {detail}")

            if not (_match(away_team, a_name) and _match(home_team, h_name)):
                continue

            # Pospuesto/cancelado — detectar por detail antes del check completed
            POSTPONED_KEYS = {"postponed", "cancelled", "canceled", "suspended", "ppd"}
            if any(k in detail.lower() for k in POSTPONED_KEYS):
                print(f"  [ESPN] Partido POSPUESTO: {detail}")
                return {"winner": "POSTPONED", "status": detail,
                        "away_name": a_name, "home_name": h_name,
                        "away_runs": 0, "home_runs": 0}

            if not completed:
                print(f"  [ESPN] Partido encontrado pero NO finalizado: {detail}")
                return None

            a_runs = int(away.get("score", 0) or 0)
            h_runs = int(home.get("score", 0) or 0)
            winner = a_name if a_runs > h_runs else h_name
            return {"away_name": a_name, "home_name": h_name,
                    "away_runs": a_runs, "home_runs": h_runs, "winner": winner}

    except Exception as e:
        logger.warning(f"ESPN error: {e}")
        err_icon = "X"
        print(f"  [ESPN] {err_icon} Excepci�n: {e}")

    return None


def _mlb_stats_resultado(away_team: str, home_team: str, game_date: str) -> Optional[dict]:
    """Fallback: MLB Stats API para resultados cuando ESPN falla."""
    import requests as _req

    def _match(a: str, b: str) -> bool:
        a, b = a.strip().lower(), b.strip().lower()
        return a == b or a in b or b in a

    try:
        url = "https://statsapi.mlb.com/api/v1/schedule"
        params = {"sportId": 1, "date": game_date, "hydrate": "linescore"}
        print(f"  [FALLBACK MLB] GET {url} date={game_date}")
        r = _req.get(url, params=params, timeout=15,
                     headers={"User-Agent": "Mozilla/5.0"})
        print(f"  [FALLBACK MLB] Status: {r.status_code}")

        if r.status_code != 200:
            return None

        for date_block in r.json().get("dates", []):
            for g in date_block.get("games", []):
                a_name = g.get("teams", {}).get("away", {}).get("team", {}).get("name", "")
                h_name = g.get("teams", {}).get("home", {}).get("team", {}).get("name", "")
                state  = g.get("status", {}).get("detailedState", "")
                print(f"  [FALLBACK MLB] {a_name} @ {h_name} | {state}")

                if not (_match(away_team, a_name) and _match(home_team, h_name)):
                    continue

                if state not in ("Final", "Game Over", "Completed Early"):
                    print(f"  [FALLBACK MLB] No finalizado: {state}")
                    return None

                ls     = g.get("linescore", {}).get("teams", {})
                a_runs = int(ls.get("away", {}).get("runs", 0) or 0)
                h_runs = int(ls.get("home", {}).get("runs", 0) or 0)
                winner = a_name if a_runs > h_runs else h_name
                return {"away_name": a_name, "home_name": h_name,
                        "away_runs": a_runs, "home_runs": h_runs, "winner": winner}
    except Exception as e:
        print(f"  [FALLBACK MLB] Error: {e}")
    return None


def _lmb_stats_resultado(away_team: str, home_team: str, game_date: str, allow_in_progress: bool = False) -> Optional[dict]:
    """Verifica resultado LMB via MLB StatsAPI sportId=23."""
    import requests as _req

    def _match(a: str, b: str) -> bool:
        a, b = a.strip().lower(), b.strip().lower()
        return a == b or a in b or b in a

    try:
        parts = game_date.split("-")
        api_date = f"{parts[1]}/{parts[2]}/{parts[0]}" if len(parts) == 3 else game_date
        url = (
            "https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=23&date={api_date}&hydrate=linescore"
        )
        print(f"  [LMB] GET {url}")
        r = _req.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        print(f"  [LMB] Status: {r.status_code}")

        if r.status_code != 200:
            return None

        for date_block in r.json().get("dates", []):
            for g in date_block.get("games", []):
                a_name = g.get("teams", {}).get("away", {}).get("team", {}).get("name", "")
                h_name = g.get("teams", {}).get("home", {}).get("team", {}).get("name", "")
                state  = g.get("status", {}).get("detailedState", "")
                print(f"  [LMB] {a_name} @ {h_name} | {state}")

                if not (_match(away_team, a_name) and _match(home_team, h_name)):
                    continue

                is_final = state in ("Final", "Game Over", "Completed Early")
                if not is_final and not allow_in_progress:
                    print(f"  [LMB] No finalizado: {state}")
                    return None

                ls     = g.get("linescore", {}).get("teams", {})
                a_runs = int(ls.get("away", {}).get("runs", 0) or 0)
                h_runs = int(ls.get("home", {}).get("runs", 0) or 0)
                winner = a_name if a_runs > h_runs else h_name
                return {
                    "away_name": a_name, "home_name": h_name,
                    "away_runs": a_runs, "home_runs": h_runs,
                    "winner": winner, "status": state, "is_final": is_final,
                }
    except Exception as e:
        print(f"  [LMB] Error: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _buscar_analysis(game_pk: int) -> Optional[GameAnalysis]:
    for a in _analyses_hoy:
        if a.game_pk == game_pk:
            return a
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TAREA 3 — RESUMEN SEMANAL
# ─────────────────────────────────────────────────────────────────────────────
def tarea_resumen_semanal():
    logger.info("=== Resumen semanal ===")
    bot.enviar_resumen_semanal()


# ─────────────────────────────────────────────────────────────────────────────
# LISTENER DE ERRORES
# ─────────────────────────────────────────────────────────────────────────────
def _listener_errores(event):
    if event.exception:
        logger.error(f"❌ Job '{event.job_id}' falló: {event.exception}",
                     exc_info=(type(event.exception), event.exception,
                               event.exception.__traceback__))
        bot.enviar_mensaje(
            f"🚨 <b>MLB BOT — Error en tarea</b>\n"
            f"🔧 Job: <code>{event.job_id}</code>\n"
            f"💥 Error: <code>{event.exception}</code>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# INICIAR
# ─────────────────────────────────────────────────────────────────────────────
def iniciar():
    import pytz as _pytz
    from datetime import date as _date

    global _scheduler

    scheduler = BlockingScheduler(timezone=config.TIMEZONE)
    scheduler.add_listener(_listener_errores, EVENT_JOB_ERROR)
    _scheduler = scheduler

    # Tarea 1: Análisis dinámico — 1h antes del primer partido del día
    hora_dinamica = _programar_analisis()

    # Tarea de recálculo diario (madrugada): ajusta la hora según los partidos del día
    rec_h, rec_m = config.HORA_RECALCULO_DIARIO.split(":")
    scheduler.add_job(
        _programar_analisis,
        CronTrigger(hour=int(rec_h), minute=int(rec_m), timezone=config.TIMEZONE),
        id="reprogramar_analisis",
        name="Reprogramación diaria del análisis",
        max_instances=1, coalesce=True, misfire_grace_time=600,
    )

    # Tarea 3: Resumen semanal
    scheduler.add_job(
        tarea_resumen_semanal,
        CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=config.TIMEZONE),
        id="resumen_semanal", name="Resumen Semanal",
    )

    logger.info(f"Scheduler iniciado — zona horaria: {config.TIMEZONE}")
    logger.info(f"Análisis diario: {_hora_analisis_hoy} (dinámico); Re-análisis MLB: {config.REANALISIS_MLB_HORA} LMB: {config.REANALISIS_LMB_HORA}")

    # ── LMB: programación dinámica independiente ────────────────────────
    if getattr(config, "LMB_ACTIVO", False) and analizar_lmb_dia is not None:
        hora_lmb = _programar_analisis_lmb()

        # Recálculo diario LMB (madrugada)
        lmb_rec_h, lmb_rec_m = getattr(config, "LMB_HORA_RECALCULO", "05:30").split(":")
        scheduler.add_job(
            _programar_analisis_lmb,
            CronTrigger(hour=int(lmb_rec_h), minute=int(lmb_rec_m), timezone=config.TIMEZONE),
            id="reprogramar_analisis_lmb",
            name="Reprogramación diaria del análisis LMB",
            max_instances=1, coalesce=True, misfire_grace_time=600,
        )

    # ── Re-análisis fijo MLB ───────────────────────────────────────────────
    ra_h, ra_m = config.REANALISIS_MLB_HORA.split(":")
    scheduler.add_job(
        tarea_reanalisis_mlb,
        CronTrigger(hour=int(ra_h), minute=int(ra_m), timezone=config.TIMEZONE),
        id="reanalisis_mlb", name="Re-análisis MLB (fijo)",
        max_instances=1, coalesce=True, misfire_grace_time=600,
    )
    logger.info(f"Re-análisis MLB programado: {config.REANALISIS_MLB_HORA} ({config.TIMEZONE})")

    # ── Re-análisis fijo LMB ───────────────────────────────────────────────
    if getattr(config, "LMB_ACTIVO", False) and analizar_lmb_dia is not None:
        rl_h, rl_m = config.REANALISIS_LMB_HORA.split(":")
        scheduler.add_job(
            tarea_reanalisis_lmb,
            CronTrigger(hour=int(rl_h), minute=int(rl_m), timezone=config.TIMEZONE),
            id="reanalisis_lmb", name="Re-análisis LMB (fijo)",
            max_instances=1, coalesce=True, misfire_grace_time=600,
        )
        logger.info(f"Re-análisis LMB programado: {config.REANALISIS_LMB_HORA} ({config.TIMEZONE})")

    # ── FÚTBOL: análisis diario + live scores cada 20 min ───────────────
    scheduler.add_job(
        tarea_analisis_futbol,
        CronTrigger(hour=6, minute=0, timezone=config.TIMEZONE),
        id="analisis_futbol", name="Análisis Fútbol (06:00)",
        max_instances=1, coalesce=True, misfire_grace_time=600,
    )
    scheduler.add_job(
        tarea_reanalis_futbol,
        IntervalTrigger(minutes=20, timezone=config.TIMEZONE),
        id="live_futbol", name="Live Scores Fútbol (cada 20min)",
        max_instances=1, coalesce=True,
    )
    logger.info("Fútbol programado: análisis 06:00, live cada 20 min")

    # ── Fix arranque tarde: ejecutar análisis si ya pasó la hora
    partidos_hoy = []
    try:
        tz    = _pytz.timezone(config.TIMEZONE)
        ahora = datetime.now(tz)
        hh, mm = _hora_analisis_hoy.split(":")
        ya_paso = (ahora.hour, ahora.minute) >= (int(hh), int(mm))
        if ya_paso:
            hoy_str      = _date.today().strftime("%Y-%m-%d")
            estado_hoy   = dm.cargar_estado()
            partidos_hoy = [p for p in estado_hoy if p.get("game_date","")[:10] == hoy_str]
            if not partidos_hoy:
                logger.info("Arrancó tarde sin análisis — ejecutando ahora")
                tarea_analisis_manana()
                partidos_hoy = [p for p in dm.cargar_estado()
                                if p.get("game_date","")[:10] == hoy_str]
    except Exception as e:
        logger.warning(f"Verificación de análisis al arrancar: {e}")

    # ── Fix arranque tarde LMB ──────────────────────────────────────────────
    if getattr(config, "LMB_ACTIVO", False) and analizar_lmb_dia is not None:
        try:
            tz    = _pytz.timezone(config.TIMEZONE)
            ahora = datetime.now(tz)
            hh_lmb, mm_lmb = _hora_analisis_lmb.split(":")
            ya_paso_lmb = (ahora.hour, ahora.minute) >= (int(hh_lmb), int(mm_lmb))
            if ya_paso_lmb:
                hoy_str_lmb = _date.today().strftime("%Y-%m-%d")
                estado_lmb  = dm.cargar_estado()
                lmb_hoy = [p for p in estado_lmb if p.get("game_date","")[:10] == hoy_str_lmb and p.get("liga","MLB") == "LMB"]
                if not lmb_hoy:
                    logger.info("Arrancó tarde sin análisis LMB — ejecutando ahora")
                    tarea_analisis_lmb()
        except Exception as e:
            logger.warning(f"Verificación de análisis LMB al arrancar: {e}")

    # ── EJECUCIÓN INMEDIATA de resultados al arrancar
    logger.info("Ejecutando tarea_resultados inmediatamente al arrancar...")
    tarea_resultados()

    # ── Calcular próximo múltiplo de 2h para IntervalTrigger
    import pytz as _pytz2
    tz    = _pytz2.timezone(config.TIMEZONE)
    ahora = datetime.now(tz)
    hora_sig = (math.floor(ahora.hour / 2) + 1) * 2
    if hora_sig >= 24:
        import datetime as _dt
        start_date = (ahora + _dt.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = ahora.replace(hour=hora_sig, minute=0, second=0, microsecond=0)

    logger.info(f"Próxima consulta automática: {start_date.strftime('%H:%M')} (cada 2h)")
    print(f"\n[SCHEDULER] Próxima consulta de resultados: {start_date.strftime('%H:%M')} (luego cada 2h)\n")

    scheduler.add_job(
        tarea_resultados,
        IntervalTrigger(hours=2, start_date=start_date, timezone=config.TIMEZONE),
        id="resultados", name="Resultados ESPN (cada 2h)",
        max_instances=1, coalesce=True,
    )

    # ── Job cada 15 min para mantener Mini App actualizada ────────────
    if config.GITHUB_TOKEN:
        def _publicar_miniapp():
            try:
                from miniapp_publisher import publicar
                if publicar():
                    logger.info("Mini App publicada (cada 15 min)")
            except Exception as e:
                logger.error(f"Mini App 15min error: {e}")
        scheduler.add_job(
            _publicar_miniapp,
            IntervalTrigger(minutes=15, timezone=config.TIMEZONE),
            id="miniapp_15min", name="Mini App publish (15 min)",
            max_instances=1, coalesce=True,
        )
        logger.info("Job Mini App cada 15 min registrado")

    logger.info("Jobs activos:")
    for job in scheduler.get_jobs():
        logger.info(f"  [{job.id}] {job.name}")

    telegram_handler.iniciar()

    bot.enviar_inicio(
        hora_analisis=_hora_analisis_hoy,
        timezone=config.TIMEZONE,
        partidos_hoy=len(partidos_hoy),
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot detenido por el usuario.")
        bot.enviar_mensaje("🛑 <b>MLB BOT detenido.</b>")
