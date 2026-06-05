"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MLB BOT — scheduler.py                                                     ║
║  Gestión de todas las tareas programadas con APScheduler                   ║
║                                                                              ║
║  Tareas:                                                                    ║
║    08:00 AM   → Análisis completo del día (todos los partidos)             ║
║    Cada 2h    → Consulta resultados vía ESPN API pública (12:00 - 00:00)  ║
║    Domingo    → Resumen semanal de rendimiento                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

import config
import bot
import data_manager as dm
from analyzer import analizar_dia, GameAnalysis
import requests as _requests

logger = logging.getLogger(__name__)

# Estado global del día
_analyses_hoy: list[GameAnalysis] = []


# ─────────────────────────────────────────────────────────────────────────────
# ██  TAREA 1 — ANÁLISIS MATUTINO (08:00 AM)  ██
# ─────────────────────────────────────────────────────────────────────────────
def tarea_analisis_manana():
    """
    08:00 AM — Descarga y analiza todos los partidos del día.
    Envía el mensaje principal a Telegram y programa las alertas dinámicas.
    """
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
        bot.enviar_mensaje(
            "⚾ <b>MLB BOT</b>\n"
            "ℹ️ Sin partidos de MLB programados para hoy."
        )
        logger.info("Sin partidos hoy — tarea finalizada")
        return

    # Guardar en CSV y estado JSON
    dm.guardar_analisis(_analyses_hoy)
    dm.guardar_estado(_analyses_hoy)

    # Enviar mensaje principal
    bot.enviar_analisis_manana(_analyses_hoy)

    logger.info(f"Análisis completado: {len(_analyses_hoy)} partidos")


# ─────────────────────────────────────────────────────────────────────────────
# ██  TAREA 2 — RESULTADOS VÍA ESPN (cada 2 horas, 12:00 - 00:00)  ██
# ─────────────────────────────────────────────────────────────────────────────
def tarea_resultados():
    """
    Consulta ESPN scoreboard por cada partido pendiente del día.
    Sin API key. Una sola fuente, sin fallbacks complejos.
    """
    global _analyses_hoy

    estado = dm.cargar_estado()
    pendientes = [p for p in estado if p.get("resultado") == "pendiente"]

    if not pendientes:
        logger.info("Resultados: sin partidos pendientes")
        return

    logger.info(f"Resultados: revisando {len(pendientes)} partidos pendientes")

    for p in pendientes:
        game_pk  = p["game_pk"]
        resultado = _espn_resultado(
            p.get("away_team", ""),
            p.get("home_team", ""),
            p.get("game_date", "")[:10],
        )

        if not resultado:
            logger.debug(f"ESPN: {p.get('away_team')} @ {p.get('home_team')} — aún no finalizado o no encontrado")
            continue

        ganador  = resultado["winner"]
        marcador = (f"{resultado['away_name']} {resultado['away_runs']}"
                    f" — {resultado['home_runs']} {resultado['home_name']}")

        def _match(a: str, b: str) -> bool:
            a, b = a.strip().lower(), b.strip().lower()
            return a == b or a in b or b in a

        acertado = _match(ganador, p["favorito"])

        dm.actualizar_resultado(game_pk, ganador, marcador)
        dm.actualizar_estado_resultado(
            game_pk,
            "acertado" if acertado else "fallido",
            ganador,
        )

        analysis = _buscar_analysis(game_pk)
        if analysis:
            bot.enviar_resultado(analysis, ganador, marcador)
        else:
            emoji = "✅" if acertado else "❌"
            bot.enviar_mensaje(
                f"{emoji} <b>{'ACERTADO' if acertado else 'FALLIDO'}</b>\n"
                f"⚾ {p.get('away_team')} @ {p.get('home_team')}\n"
                f"🏆 Bot: {p['favorito']} ({p['prob_favorito']:.1f}%)\n"
                f"🏁 Ganador: {ganador}\n"
                f"📊 {marcador}\n"
                f"📡 ESPN"
            )

        logger.info(f"Resultado: {marcador} → {'acertado' if acertado else 'fallido'}")


def _espn_resultado(away_team: str, home_team: str, game_date: str) -> Optional[dict]:
    """
    Consulta ESPN scoreboard público por fecha y devuelve el resultado
    si el partido ya terminó. Sin API key.
    """
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
        r = _req.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            logger.warning(f"ESPN HTTP {r.status_code}")
            return None

        for event in r.json().get("events", []):
            comp = (event.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue

            h_name = home.get("team", {}).get("displayName", "")
            a_name = away.get("team", {}).get("displayName", "")

            if not (_match(away_team, a_name) and _match(home_team, h_name)):
                continue

            if not comp.get("status", {}).get("type", {}).get("completed", False):
                return None

            a_runs = int(away.get("score", 0) or 0)
            h_runs = int(home.get("score", 0) or 0)
            winner = a_name if a_runs > h_runs else h_name

            return {
                "away_name": a_name,
                "home_name": h_name,
                "away_runs": a_runs,
                "home_runs": h_runs,
                "winner":    winner,
            }

    except Exception as e:
        logger.warning(f"ESPN error: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _buscar_analysis(game_pk: int) -> Optional[GameAnalysis]:
    """Busca un análisis en la lista global del día."""
    for a in _analyses_hoy:
        if a.game_pk == game_pk:
            return a
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ██  TAREA 3 — RESUMEN SEMANAL (Domingo 20:00)  ██
# ─────────────────────────────────────────────────────────────────────────────
def tarea_resumen_semanal():
    logger.info("=== Resumen semanal ===")
    bot.enviar_resumen_semanal()
# ─────────────────────────────────────────────────────────────────────────────
# ██  LISTENER DE ERRORES  ██
# ─────────────────────────────────────────────────────────────────────────────
def _listener_errores(event):
    """Captura errores de jobs y los registra en el log."""
    if event.exception:
        logger.error(
            f"❌ Job '{event.job_id}' falló con excepción: {event.exception}",
            exc_info=(type(event.exception), event.exception, event.exception.__traceback__)
        )
        bot.enviar_mensaje(
            f"🚨 <b>MLB BOT — Error en tarea</b>\n"
            f"🔧 Job: <code>{event.job_id}</code>\n"
            f"💥 Error: <code>{event.exception}</code>\n"
            f"📋 Revisa mlb_bot.log para más detalles."
        )


# ─────────────────────────────────────────────────────────────────────────────
def iniciar():
    """
    Crea y arranca el scheduler con todas las tareas programadas.
    Bloquea el hilo principal hasta recibir Ctrl+C.
    """
    hora_h, hora_m = config.HORA_ANALISIS_MANANA.split(":")

    scheduler = BlockingScheduler(timezone=config.TIMEZONE)
    scheduler.add_listener(_listener_errores, EVENT_JOB_ERROR)

    # ── Tarea 1: Análisis matutino (08:00 AM, todos los días)
    scheduler.add_job(
        tarea_analisis_manana,
        CronTrigger(hour=int(hora_h), minute=int(hora_m),
                    timezone=config.TIMEZONE),
        id          = "analisis_manana",
        name        = "Análisis Matutino MLB",
        max_instances = 1,
        coalesce    = True,
        misfire_grace_time = 600,   # 10 min de gracia si se perdió
    )


    # ── Tarea 2: Resultados — se registra dinámicamente más abajo,
    #    con IntervalTrigger(hours=2) arrancando desde el próximo múltiplo de 2h.

    # ── Tarea 3: Resumen semanal (domingos a las 20:00)
    scheduler.add_job(
        tarea_resumen_semanal,
        CronTrigger(day_of_week="sun", hour=20, minute=0,
                    timezone=config.TIMEZONE),
        id   = "resumen_semanal",
        name = "Resumen Semanal",
    )

    logger.info(f"Scheduler iniciado — zona horaria: {config.TIMEZONE}")
    logger.info(f"Análisis diario: {config.HORA_ANALISIS_MANANA}")
    logger.info("Jobs activos:")
    for job in scheduler.get_jobs():
        logger.info(f"  [{job.id}] {job.name}")

    # ── Fix: Si el bot arrancó tarde (después de la hora de análisis),
    #    verificar si ya existe estado para HOY. Si no, ejecutar análisis ahora.
    partidos_hoy = []  # siempre definida para el mensaje de inicio
    try:
        from datetime import date as _date
        import pytz
        tz     = pytz.timezone(config.TIMEZONE)
        ahora  = datetime.now(tz)
        hora_h_int, hora_m_int = int(hora_h), int(hora_m)
        ya_paso_hora = (ahora.hour, ahora.minute) >= (hora_h_int, hora_m_int)

        if ya_paso_hora:
            estado_hoy = dm.cargar_estado()
            hoy_str    = _date.today().strftime("%Y-%m-%d")
            partidos_hoy = [p for p in estado_hoy
                            if p.get("game_date", "")[:10] == hoy_str]
            if not partidos_hoy:
                logger.info(
                    "Bot arrancó tarde y sin análisis de hoy — "
                    "ejecutando análisis inmediato antes de iniciar scheduler"
                )
                tarea_analisis_manana()
                # Recargar después del análisis
                partidos_hoy = [p for p in dm.cargar_estado()
                                if p.get("game_date", "")[:10] == hoy_str]
    except Exception as e:
        logger.warning(f"No se pudo verificar análisis de hoy al arrancar: {e}")

    # ── Ejecutar resultados inmediatamente al arrancar
    logger.info("Ejecutando tarea_resultados al arrancar...")
    tarea_resultados()

    # ── Calcular próximo múltiplo de 2 horas desde ahora para el IntervalTrigger
    import pytz as _pytz, math as _math
    from apscheduler.triggers.interval import IntervalTrigger as _IntervalTrigger
    import datetime as _dt

    tz    = _pytz.timezone(config.TIMEZONE)
    ahora = datetime.now(tz)
    hora_siguiente = (_math.floor(ahora.hour / 2) + 1) * 2
    if hora_siguiente >= 24:
        start_date = (ahora + _dt.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = ahora.replace(
            hour=hora_siguiente, minute=0, second=0, microsecond=0)

    logger.info(f"Próxima consulta automática de resultados: {start_date.strftime('%H:%M')} (luego cada 2h)")

    # Reemplazar el CronTrigger fijo por IntervalTrigger dinámico
    try:
        scheduler.remove_job("resultados")
    except Exception:
        pass
    scheduler.add_job(
        tarea_resultados,
        _IntervalTrigger(hours=2, start_date=start_date, timezone=config.TIMEZONE),
        id            = "resultados",
        name          = "Resultados ESPN (cada 2h)",
        max_instances = 1,
        coalesce      = True,
    )

    bot.enviar_inicio(
        hora_analisis = config.HORA_ANALISIS_MANANA,
        timezone      = config.TIMEZONE,
        partidos_hoy  = len(partidos_hoy),
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot detenido por el usuario.")
        bot.enviar_mensaje("🛑 <b>MLB BOT detenido.</b>")
