"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MLB BOT — config.py                                                        ║
║  Configuración centralizada — edita solo este archivo                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

CLAVES API — CÓMO OBTENERLAS:
──────────────────────────────────────────────────────────────────────────────
1. TELEGRAM_TOKEN:
   · Abre Telegram → busca @BotFather → /newbot
   · Sigue las instrucciones → copia el token que te da
   · Ejemplo: "7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

2. TELEGRAM_CHAT_ID:
   · Envía un mensaje a tu bot
   · Visita: https://api.telegram.org/bot<TU_TOKEN>/getUpdates
   · Busca "chat" → "id" en el JSON
   · Ejemplo: "123456789"

3. ODDS_API_KEY:
   · Registro gratuito (500 req/mes):
   · https://the-odds-api.com/#get-access
   · Ejemplo: "abc123def456abc123def456abc12345"
   · Sin esta key el bot funciona pero sin análisis de valor de cuotas.
──────────────────────────────────────────────────────────────────────────────
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────────────────────────────────────
# CREDENCIALES
# ─────────────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "8862582497:AAF7o5RX1NH7OI26sG0RyC5hFzNyYSiBjpA")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6099564810")

ODDS_API_KEY     = os.environ.get("ODDS_API_KEY", "a6466e5654475830ce2a3667dc76bd90")

# ─────────────────────────────────────────────────────────────────────────────
# HORARIOS (formato 24h, zona horaria configurada en TIMEZONE)
# ─────────────────────────────────────────────────────────────────────────────
TIMEZONE = "America/Ciudad_Juarez"      # Cambia a tu zona horaria
HORA_ANALISIS_MANANA  = "08:00"   # Fallback — si no hay partidos o falla la API
HORA_PREVIA_PARTIDO   = 30        # Minutos antes del partido — alerta de cuotas
HORA_RESULTADO        = 4         # Horas después del inicio — buscar resultado

# ── Programación dinámica ─────────────────────────────────────────────────────
MINUTOS_PREVIA_ANALISIS  = 60   # Minutos antes del primer partido para ejecutar el análisis
HORA_RECALCULO_DIARIO    = "05:00"  # Madrugada: recalcular hora del análisis para el día

# ─────────────────────────────────────────────────────────────────────────────
# PARÁMETROS DE ANÁLISIS SABERMÉRICO (Metodología v3.0)
# ─────────────────────────────────────────────────────────────────────────────

# Pesos por bloque (deben sumar 100)
PESO_PITCHEO_ABRIDOR  = 20   # Bloque 1 — FIP, xFIP, K%-BB%
PESO_OFENSIVA         = 50   # Bloque 2 — wRC+ lineup activo
PESO_BULLPEN          = 20   # Bloque 3 — WAR bullpen + fatiga
PESO_EFICIENCIA       = 10   # Bloque 4 — BaseRuns vs récord real

# Peso si el abridor es Opener (se transfiere al bullpen)
PESO_OPENER_REDUCCION = 15   # Abridor → 15%, Bullpen += 15%

# Umbral mínimo de score para considerar señal válida
PROB_MINIMA_SEÑAL     = 57.0  # % — "Tríada del Valor": necesita > 57%
PROB_MINIMA_ANALISIS  = 57.0  # % — Umbral mínimo para análisis accionable
                               # Partidos < 55% se marcan como "señal débil"
PROB_MINIMA_APUESTA   = PROB_MINIMA_ANALISIS  # Alias para retrocompatibilidad
EDGE_MINIMO           = 4.0   # % — Edge mínimo (prob_bot - prob_mercado) para Confianza Alta

# ── Bloque 1: Pitcheo abridor
IP_MINIMAS_TEMPORADA  = 20      # Menos de 20 IP → penalización de volatilidad
PENALIZACION_IP_PCT   = 5       # -5% probabilidad final por abridor debutante
BABIP_SUERTE_BAJO     = 0.260   # BABIP < 0.260 → posible suerte positiva
BABIP_SUERTE_ALTO     = 0.340   # BABIP > 0.340 → posible mala suerte
HARD_HIT_UMBRAL       = 42.0    # Hard-Hit% > 42 → penalizar aunque BABIP bajo
XFIP_PENALIZACION     = 0.50    # Puntos que se añaden al xFIP si Hard-Hit > umbral

# ── Bloque 3: Bullpen / fatiga
PITCHEOS_FATIGA_72H   = 40      # Cerrador + Setup > 40 pitcheos → bullpen agotado
PENALIZACION_BULLPEN  = 35      # % de reducción al WAR del bullpen si fatigado

# ── Bloque 4: BaseRuns
BASERUNS_DIFERENCIAL  = 5       # Diferencia W-L vs BaseRuns W para señal de suerte

# ── Trigger Moneyline (filtro de senal)
TRIGGER_WRC_MIN_LMB    = 15   # Diferencia minima de wRC para validar trigger en LMB
TRIGGER_PROB_MIN       = 35   # % — Probabilidad de mercado minima para evitar volatilidad

# ── Holgura para segmentacion ALTA vs MEDIA ──────────────────────────────
# ALTA = |diff_pitcheo| > HOLGURA_PITCHEO  Y  |diff_wrc| > HOLGURA_WRC
# MEDIA = pasa trigger combinado pero no cumple ambos umbrales
TRIGGER_HOLGURA_PITCHEO = 7.0  # Diferencia absoluta de Score_Pitcheo para ALTA
TRIGGER_HOLGURA_WRC     = 18   # Diferencia absoluta de wRC+ para ALTA
# PF, BP, FIP son estrictamente informativos — no bloquean ni degradan

# ── Cuotas / "Tríada del Valor"
CAMBIO_ODDS_ALERTA    = 5       # % de cambio en prob. implícita para disparar alerta
XWOBA_DESVIACION_7D   = 0.030   # Desviación xwOBA 7 días vs temporada (30 puntos)

# ─────────────────────────────────────────────────────────────────────────────
# ARCHIVOS DE SALIDA
# ─────────────────────────────────────────────────────────────────────────────
CSV_PATH              = os.path.join(BASE_DIR, "apuestas.csv")
LOG_PATH              = os.path.join(BASE_DIR, "mlb_bot.log")
LOG_LEVEL             = "INFO"    # DEBUG | INFO | WARNING | ERROR

# ── Fútbol (CSV y cache) ─────────────────────────────────────────────
FUTBOL_DIR            = os.path.normpath(os.path.join(BASE_DIR, "futbol_bot"))
CSV_SOCCER_PATH       = os.path.join(FUTBOL_DIR, "apuestas_soccer.csv")
SOCCER_DATA_JSON      = os.path.join(BASE_DIR, "soccer_data.json")

# ── Re-análisis diario (horas fijas, después del análisis dinámico) ──────
REANALISIS_MLB_HORA = "08:00"   # Re-análisis MLB (hora fija)
REANALISIS_LMB_HORA = "12:30"   # Re-análisis LMB (hora fija)

# ── Telegram Mini App (GitHub Pages) ──────────────────────────────────────
GITHUB_TOKEN          = os.environ.get("GITHUB_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "MLBAnalyticsRailwayBot")
# La Mini App se publica en:
# https://apuestasmlb-production.up.railway.app/

# ─────────────────────────────────────────────────────────────────────────────
# OTROS
# ─────────────────────────────────────────────────────────────────────────────
MAX_REINTENTOS_API    = 1      # Intentos si una API falla
DELAY_ENTRE_REINTENTOS = 0   # Segundos entre reintentos
SEASON_ACTUAL         = 2025  # Temporada MLB en curso

# ── Administrador ────────────────────────────────────────────────────
ADMIN_USERNAME = "AdrianAdmin"

# ── Railway Deploy API ───────────────────────────────────────────────
RAILWAY_API_TOKEN   = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_PROJECT_ID  = os.environ.get("RAILWAY_PROJECT_ID", "")
RAILWAY_SERVICE_ID  = os.environ.get("RAILWAY_SERVICE_ID", "")
RAILWAY_URL         = os.environ.get("RAILWAY_URL", "")  # https://tu-proyecto.railway.app
HOSTINGER_URL       = os.environ.get("HOSTINGER_URL", "")  # https://tu-dominio.com

# ─────────────────────────────────────────────────────────────────────────────
# LMB (Liga Mexicana de Béisbol)
# ─────────────────────────────────────────────────────────────────────────────
LMB_ACTIVO = True
LMB_LEAGUE_ID = "f6efe3f3"

# Pesos por bloque para LMB (sin Statcast — métricas básicas)
PESO_LMB_PITCHEO   = 25   # B1 — ERA, WHIP, SO/BB, HR/9
PESO_LMB_OFENSIVA  = 25   # B2 — AVG, OPS, HR, R
PESO_LMB_BULLPEN   = 15   # B3 — Bullpen estimado
PESO_LMB_EFICIENCIA = 10  # B4 — Run differential, Pythagorean
PESO_LMB_FORMA     = 25   # B5 — Últimos 10 juegos + H2H

# Umbrales LMB
LMB_PROB_MINIMA   = 55.0  # % umbral mínimo de score
LMB_EDGE_MINIMO   = 3.0   # % edge mínimo para Alta Confianza
LMB_ZONAS         = ["Norte", "Sur"]
LMB_EQUIPOS_NORTE = [
    "Sultanes de Monterrey", "Toros de Tijuana", "Charros de Jalisco",
    "Acereros de Monclova", "Rieleros de Aguascalientes", "Caliente de Durango",
    "Tecolotes de los Dos Laredos", "Algodoneros de Union Laguna",
    "Saraperos de Saltillo", "Dorados de Chihuahua",
]
LMB_EQUIPOS_SUR = [
    "Diablos Rojos del Mexico", "Guerreros de Oaxaca", "Olmecas de Tabasco",
    "Bravos de Leon", "Pericos de Puebla", "Conspiradores de Queretaro",
    "El Aguila de Veracruz", "Piratas de Campeche",
    "Tigres de Quintana Roo", "Leones de Yucatan",
]

# LMB temporada (BR Register)
SEASON_LMB = 2026

# ── Programación dinámica LMB ────────────────────────────────────────────────
LMB_HORA_MANANA          = "12:30"  # Fallback — primer juego LMB ~19:00 MT, análisis 60 min antes
LMB_MINUTOS_PREVIA       = 60       # Minutos antes del primer partido LMB
LMB_HORA_RECALCULO       = "05:30"  # 30 min tras MLB para recalcular hora LMB
