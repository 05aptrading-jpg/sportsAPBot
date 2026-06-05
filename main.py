"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MLB BOT — main.py                                                          ║
║  Punto de entrada — ejecutar con: python main.py                           ║
║                                                                              ║
║  Opciones:                                                                  ║
║    python main.py           → Arranca el bot en modo continuo              ║
║    python main.py --ahora   → Ejecuta el análisis de hoy inmediatamente    ║
║    python main.py --test    → Verifica APIs y envía mensaje de prueba      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import io
import logging
from datetime import date

# Forzar UTF-8 en stdout/stderr para emojis en Windows (cp1252 falla sin esto)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import config
import data_manager as dm
import bot
import scheduler as sch
from analyzer import analizar_dia

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = getattr(logging, config.LOG_LEVEL, logging.INFO),
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_PATH, encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# MODO --test
# ─────────────────────────────────────────────────────────────────────────────
def modo_test():
    print("\n🔍 MLB BOT — MODO TEST\n" + "="*40)

    # 1. Verificar Telegram
    print("1. Probando Telegram...", end=" ", flush=True)
    ok = bot.enviar_mensaje(
        "🧪 <b>MLB BOT — Mensaje de prueba</b>\n"
        "✅ Conexión con Telegram verificada.\n"
        f"📅 {date.today().strftime('%Y-%m-%d')}"
    )
    print("✅ OK" if ok else "❌ FALLA — verifica TELEGRAM_TOKEN y TELEGRAM_CHAT_ID")

    # 2. Verificar MLB Stats API
    print("2. Probando MLB Stats API...", end=" ", flush=True)
    from api_client import mlb
    schedule = mlb.get_schedule()
    if schedule:
        games = schedule.get("dates", [{}])[0].get("games", [])
        print(f"✅ OK — {len(games)} partidos hoy")
    else:
        print("❌ FALLA — sin conexión a statsapi.mlb.com")

    # 3. Verificar The Odds API
    print("3. Probando The Odds API...", end=" ", flush=True)
    from api_client import odds as odds_client
    if config.ODDS_API_KEY and config.ODDS_API_KEY != "TU_ODDS_API_KEY":
        odds_data = odds_client.get_mlb_odds()
        if odds_data:
            print(f"✅ OK — {len(odds_data)} partidos con odds")
        else:
            print("⚠️ ODDS_API_KEY configurada pero sin datos (¿fuera de temporada?)")
    else:
        print("⚠️ ODDS_API_KEY no configurada — módulo de valor desactivado")

    # 4. Verificar Baseball Savant — leaderboard lanzadores
    print("4. Probando Baseball Savant (leaderboard)...", end=" ", flush=True)
    from api_client import savant
    pitchers = savant.get_pitcher_leaderboard()
    if pitchers and pitchers.get("data"):
        n = len(pitchers["data"])
        print(f"✅ OK — {n} lanzadores con K%, BB%, xFIP, xwOBA")
    else:
        print(
            "⚠️ Savant leaderboard sin respuesta.\n"
            "   → El bot usa MLB Stats API como fallback automático.\n"
            "   → Datos mínimos (ERA/WHIP/IP) siempre disponibles vía statsapi.mlb.com"
        )

    print("\n" + "="*40)
    print("✅ Test completado. Revisa los resultados arriba.")
    print("Si todas las APIs están OK, ejecuta: python main.py")
    print("="*40 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# MODO --ahora
# ─────────────────────────────────────────────────────────────────────────────
def modo_ahora():
    """Ejecuta el análisis MLB del día inmediatamente."""
    print("\n⚾ MLB BOT — ANÁLISIS MLB\n" + "="*40)
    logger.info("Modo --ahora: ejecutando análisis MLB")

    dm.inicializar_csv()

    analyses = analizar_dia()
    if analyses:
        dm.guardar_analisis(analyses)
        dm.guardar_estado(analyses)
        bot.enviar_analisis_manana(analyses)
        print(f"✅ MLB: {len(analyses)} partidos analizados.")
        for a in analyses:
            fav_str = f"{a.favorito} ({a.prob_favorito:.1f}%)"
            valor   = " ⭐ VALOR" if a.es_valor else ""
            print(f"  {a.away_team} @ {a.home_team} → {fav_str}{valor}")
    else:
        msg = "ℹ️ Sin partidos MLB programados para hoy."
        print(msg)
        bot.enviar_mensaje(f"⚾ <b>MLB BOT</b>\n{msg}")


def modo_ahora_lmb():
    """Ejecuta el análisis LMB del día inmediatamente (independiente de MLB)."""
    print("\n⚾ LMB BOT — ANÁLISIS INMEDIATO\n" + "="*40)
    logger.info("Modo --ahora-lmb: ejecutando análisis LMB")

    if not getattr(config, "LMB_ACTIVO", False):
        print("LMB no está activo en config.py")
        return

    dm.inicializar_csv()
    from analyzer_lmb import analizar_lmb_dia
    lmb_results = analizar_lmb_dia()
    if lmb_results:
        dm.guardar_analisis_lmb(lmb_results)
        dm.guardar_estado_lmb(lmb_results)
        print(f"✅ LMB: {len(lmb_results)} partidos analizados.")
        for a in lmb_results:
            print(f"  {a['away_team']} @ {a['home_team']} → {a['favorito']} ({a['prob_favorito']:.1f}%)")
    else:
        print("ℹ️ Sin partidos LMB para hoy.")


# ─────────────────────────────────────────────────────────────────────────────
# MODO NORMAL (scheduler continuo)
# ─────────────────────────────────────────────────────────────────────────────
def modo_normal():
    print("\n⚾ MLB BOT v3.0 — Iniciando...\n" + "="*40)
    print(f"Zona horaria:   {config.TIMEZONE}")
    print(f"Análisis:       {config.HORA_ANALISIS_MANANA} (ajuste dinámico 1h antes del 1er partido)")
    print(f"Prob. mínima:   {config.PROB_MINIMA_SEÑAL}%")
    print(f"CSV:            {config.CSV_PATH}")
    print(f"Log:            {config.LOG_PATH}")
    print("="*40)
    print("Ctrl+C para detener.\n")

    dm.inicializar_csv()
    sch.iniciar()   # bloqueante


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test" in args:
        modo_test()
    elif "--ahora" in args:
        modo_ahora()
    elif "--ahora-lmb" in args:
        modo_ahora_lmb()
    elif "--resultados" in args:
        modo_resultados()
    else:
        modo_normal()


# ─────────────────────────────────────────────────────────────────────────────
# MODO --resultados  (AGREGADO)
# ─────────────────────────────────────────────────────────────────────────────
def modo_resultados():
    """Consulta ESPN/MLB API y actualiza resultados pendientes ahora mismo."""
    print("\n🔍 MLB BOT — ACTUALIZACIÓN DE RESULTADOS\n" + "="*45)
    logger.info("Modo --resultados: ejecutando actualización inmediata")
    import scheduler as sch
    sch.tarea_resultados()
    print("\n✅ Actualización completada.")
