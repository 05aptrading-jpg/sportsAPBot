import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import config
import bot
import data_manager as dm
from generate_data_json import generar_soccer_data_json
from scraper_fbref import actualizar_base_datos_soccer
from live_scores import actualizar_resultados, hay_partidos_pendientes_hoy

logger = logging.getLogger(__name__)

_scheduler: Optional[BlockingScheduler] = None
_live_job_id = "live_scores_20min"


def tarea_scrape_completo():
    """Scrape completo: ESPN (fórmula xG) + Understat (ppda) + corners. Corre a las 04:00."""
    logger.info("Ejecutando scrape programado")
    df = actualizar_base_datos_soccer()
    if df.empty:
        logger.warning("Scrape devolvió vacío")
        return

    logger.info(f"Cache: {len(df)} equipos en {df['liga'].nunique()} ligas")
    logger.info("Scraping corners...")
    from scraper_corners import scrape_all_corners, curar_datos_para_corners
    for liga in df["liga"].unique():
        liga_teams = df[df["liga"] == liga]["equipo"].tolist()
        if liga_teams:
            corners_data = scrape_all_corners(liga, liga_teams)
            if corners_data:
                from config import CORNER_LEAGUE_AVG
                promedios = CORNER_LEAGUE_AVG.get(liga, CORNER_LEAGUE_AVG["DEFAULT"])
                for team in corners_data:
                    corners_data[team] = curar_datos_para_corners(corners_data[team], promedios)
                dm.actualizar_stats_con_corners(corners_data, liga)
                logger.info(f"  {liga}: {len(corners_data)} equipos corners actualizados")
    generar_soccer_data_json()


def tarea_analisis():
    logger.info("Ejecutando análisis programado")
    df_stats = dm.cargar_stats_cache()
    if df_stats.empty:
        logger.warning("Cache vacío, ejecutando scrape primero")
        df_stats = actualizar_base_datos_soccer()
        if df_stats.empty:
            return
    dm.inicializar_csv()

    from analyzer import generar_partidos_desde_cache, analizar_partido_soccer
    partidos = generar_partidos_desde_cache(df_stats)
    if not partidos:
        logger.info("Sin partidos para analizar hoy")
        return
    analyses = []
    for match in partidos:
        a = analizar_partido_soccer(match)
        analyses.append(a)
    if analyses:
        dm.guardar_analisis(analyses)
        generar_soccer_data_json()
        bot.enviar_analisis_dia(analyses)
        logger.info(f"{len(analyses)} partidos analizados y enviados")


def tarea_telegram_updates():
    import telegram_handler
    telegram_handler.procesar_comandos()


def tarea_live_scores():
    """Check for live scores every 20 min. Auto-stops when no more pending matches today."""
    if not hay_partidos_pendientes_hoy():
        logger.info("Live scores: sin partidos pendientes hoy, deteniendo updater")
        _detener_live_updater()
        return
    logger.info("Live scores: ejecutando actualización...")
    stats = actualizar_resultados()
    if stats.get("updated", 0) > 0:
        logger.info(f"Live scores: {stats['updated']} partidos actualizados")
        generar_soccer_data_json()
    else:
        logger.info(f"Live scores: sin cambios (pendientes: {stats.get('pending', 0)})")


def _detener_live_updater():
    """Remove the live scores job from the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        try:
            _scheduler.remove_job(_live_job_id)
            logger.info("Live scores updater detenido (no hay más partidos hoy)")
        except Exception:
            pass


def _iniciar_live_updater():
    """Add the live scores job to the scheduler if not already running."""
    global _scheduler
    if not _scheduler:
        return
    try:
        existing = _scheduler.get_job(_live_job_id)
        if existing:
            return
    except Exception:
        pass
    _scheduler.add_job(
        tarea_live_scores,
        IntervalTrigger(minutes=20),
        id=_live_job_id,
        name="Live scores cada 20 min",
    )
    logger.info("Live scores updater iniciado (cada 20 min)")


def iniciar():
    global _scheduler
    _scheduler = BlockingScheduler()

    _scheduler.add_job(
        tarea_scrape_completo,
        CronTrigger(hour=4, minute=0),
        id="scrape_completo",
        name="Scrape completo (ESPN + Understat)",
    )
    _scheduler.add_job(
        tarea_analisis,
        CronTrigger(hour=config.HORA_ANALISIS_MANANA.split(":")[0],
                    minute=config.HORA_ANALISIS_MANANA.split(":")[1]),
        id="analisis_matutino",
        name="Análisis matutino",
    )

    if hay_partidos_pendientes_hoy():
        _iniciar_live_updater()
        logger.info("Live scores: hay partidos pendientes hoy, updater activo")
    else:
        logger.info("Live scores: sin partidos pendientes hoy, updater inactivo")

    logger.info("Scheduler iniciado")
    print(f"⚽ Futbol Bot — Scheduler iniciado")
    print(f"  Scrape:       04:00 diario (ESPN fórmula xG + Understat ppda)")
    print(f"  Análisis:     {config.HORA_ANALISIS_MANANA} diario")
    print(f"  Live scores:  cada 20 min (si hay partidos)")
    print("  Ctrl+C para detener.\n")

    try:
        _scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler detenido por usuario")
    finally:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown()
