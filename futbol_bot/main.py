import sys
import io
import logging
from datetime import date

import pandas as pd

import config
import data_manager as dm
import bot
import scheduler as sch
from generate_data_json import generar_soccer_data_json
from scraper_fbref import actualizar_base_datos_soccer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def modo_normal():
    print("\n⚽ FUTBOL BOT — Iniciando scheduler continuo...\n" + "="*40)
    print(f"Zona horaria:   America/Mexico_City")
    print(f"Scrape:         04:00 diario (ESPN + Understat)")
    print(f"Análisis:       06:00 diario")
    print(f"Live scores:    cada 20 min (si hay partidos)")
    print(f"Telegram poll:  cada 5 min")
    print(f"CSV:            {config.CSV_SOCCER_PATH}")
    print(f"Log:            {config.LOG_PATH}")
    print("="*40)
    print("Ctrl+C para detener.\n")
    dm.inicializar_csv()
    sch.iniciar()


def modo_scrape():
    print("\n⚽ FUTBOL BOT — SCRAPEANDO DATOS\n" + "="*40)
    from scraper_fbref import actualizar_base_datos_soccer
    df = actualizar_base_datos_soccer()
    if df.empty:
        print("❌ No se pudieron obtener datos")
        return

    print(f"\n  Caché: {len(df)} equipos en {df['liga'].nunique()} ligas")

    print("\n📊 Scraping corners...")
    from scraper_corners import scrape_all_corners, curar_datos_para_corners
    from config import CORNER_LEAGUE_AVG
    for liga in df["liga"].unique():
        liga_teams = df[df["liga"] == liga]["equipo"].tolist()
        if liga_teams:
            corners_data = scrape_all_corners(liga, liga_teams)
            if corners_data:
                promedios = CORNER_LEAGUE_AVG.get(liga, CORNER_LEAGUE_AVG["DEFAULT"])
                for team in corners_data:
                    corners_data[team] = curar_datos_para_corners(corners_data[team], promedios)
                dm.actualizar_stats_con_corners(corners_data, liga)
                print(f"  ✅ {liga}: {len(corners_data)} equipos con corners")
    generar_soccer_data_json()
    print("\n✅ Scrape completo")
    print("="*40)


def modo_ahora():
    print("\n⚽ FUTBOL BOT — ANÁLISIS DEL DÍA\n" + "="*40)
    logger.info("Modo --ahora: ejecutando análisis")

    df_stats = dm.cargar_stats_cache()
    if df_stats.empty:
        print("⚠️ No hay cache de stats. Ejecuta primero: python main.py --scrape")
        return

    dm.inicializar_csv()
    from analyzer import generar_partidos_desde_cache, analizar_partido_soccer
    partidos = generar_partidos_desde_cache(df_stats)
    analyses = []
    for match in partidos:
        a = analizar_partido_soccer(match)
        analyses.append(a)
        conf_ah0 = f"{a.confianza_ah0:>5}" if a.senal_ah0 != "NO_APOSTAR" else " —  "
        conf_ou25 = f"{a.confianza_ou25:>5}" if a.senal_ou25 != "NO_APOSTAR" else " —  "
        conf_corners = f"{a.confianza_corners:>5}" if a.senal_corners != "NO_APOSTAR" else " —  "
        print(f"  {a.equipo_local} vs {a.equipo_visitante}")
        print(f"     xG: {a.proyeccion_local} - {a.proyeccion_visitante} | diff: {a.diff_xg:+.2f}")
        print(f"     AH0: {a.senal_ah0} ({conf_ah0})")
        print(f"     O/U: {a.senal_ou25} ({conf_ou25})")
        print(f"     Corners: {a.senal_corners} ({conf_corners})")
        print()
    if analyses:
        dm.guardar_analisis(analyses)
        generar_soccer_data_json()
        bot.enviar_analisis_dia(analyses)
        print(f"✅ {len(analyses)} partidos analizados y enviados")
    else:
        print("ℹ️ Sin partidos para analizar hoy")
    print("="*40)


def modo_test():
    print("\n⚽ FUTBOL BOT — MODO TEST\n" + "="*40)
    print("1. Cache de stats...", end=" ", flush=True)
    df = dm.cargar_stats_cache()
    if not df.empty:
        print(f"✅ OK — {len(df)} equipos, ligas: {df['liga'].unique().tolist()}")
    else:
        print("⚠️ Cache vacío — ejecuta --scrape primero")

    print("2. Telegram...", end=" ", flush=True)
    ok = bot.enviar_mensaje(
        f"⚽ <b>Fútbol Bot — Mensaje de prueba</b>\n"
        f"✅ Conexión verificada.\n"
        f"📅 {date.today().isoformat()}"
    )
    print("✅ OK" if ok else "❌ FALLA — verificar TELEGRAM_TOKEN")

    print("3. Análisis de prueba...", end=" ", flush=True)
    df = dm.cargar_stats_cache()
    if not df.empty:
        from analyzer import generar_partidos_desde_cache, analizar_partido_soccer
        partidos = generar_partidos_desde_cache(df)
        if partidos:
            a = analizar_partido_soccer(partidos[0])
            print(f"✅ OK — {a.equipo_local} vs {a.equipo_visitante}: xG {a.proyeccion_local}-{a.proyeccion_visitante}")
        else:
            print("⚠️ No se generaron partidos de prueba")
    else:
        print("⚠️ Sin cache")
    print("="*40)


def modo_live():
    print("\n⚽ FUTBOL BOT — LIVE SCORES TEST\n" + "="*40)
    logger.info("Modo --live: ejecutando live scores updater")
    from live_scores import actualizar_resultados, hay_partidos_pendientes_hoy
    if hay_partidos_pendientes_hoy():
        print("Hay partidos pendientes hoy. Ejecutando actualización...")
        stats = actualizar_resultados()
        print(f"  Actualizados: {stats.get('updated', 0)}")
        print(f"  Pendientes:   {stats.get('pending', 0)}")
        if stats.get("updated", 0) > 0:
            from generate_data_json import generar_soccer_data_json
            generar_soccer_data_json()
            print("  soccer_data.json regenerado")
    else:
        print("No hay partidos pendientes hoy.")
    print("="*40)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--scrape" in args:
        modo_scrape()
    elif "--ahora" in args:
        modo_ahora()
    elif "--live" in args:
        modo_live()
    elif "--test" in args:
        modo_test()
    else:
        modo_normal()
