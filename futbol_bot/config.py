import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"))

SOCCER_LEAGUES_V1 = {
    # ── Understat (solo ppda/final_third) + ESPN para fórmula xG ─────────
    "PREMIER_LEAGUE": {
        "understat_league": "EPL",
        "espn_slug": "eng.1",
        "season": 2025,
        "short": "ENG",
        "teams": []
    },
    "LA_LIGA": {
        "understat_league": "La_liga",
        "espn_slug": "esp.1",
        "season": 2025,
        "short": "ESP",
        "teams": []
    },
    "BUNDESLIGA": {
        "understat_league": "Bundesliga",
        "espn_slug": "ger.1",
        "season": 2025,
        "short": "GER",
        "teams": []
    },
    "SERIE_A": {
        "understat_league": "Serie_A",
        "espn_slug": "ita.1",
        "season": 2025,
        "short": "ITA",
        "teams": []
    },
    "LIGUE_1": {
        "understat_league": "Ligue_1",
        "espn_slug": "fra.1",
        "season": 2025,
        "short": "FRA",
        "teams": []
    },
    # ── ESPN API (fórmula xG: tiros×0.05 + SOT×0.12) ────────────────────
    "LIGA_MX": {
        "espn_slug": "mex.1",
        "season": 2025,
        "short": "MEX",
        "teams": []
    },
    "MLS": {
        "espn_slug": "usa.1",
        "season": 2025,
        "short": "USA",
        "teams": []
    },
    "BRASILEIRAO": {
        "espn_slug": "bra.1",
        "season": 2025,
        "short": "BRA",
        "teams": []
    },
    "EREDIVISIE": {
        "espn_slug": "ned.1",
        "season": 2025,
        "short": "NED",
        "teams": []
    },
    "CHAMPIONSHIP": {
        "espn_slug": "eng.2",
        "season": 2025,
        "short": "ENG2",
        "teams": []
    },
    "PRIMEIRA_LIGA": {
        "espn_slug": "por.1",
        "season": 2025,
        "short": "POR",
        "teams": []
    },
    "SUPER_LIG": {
        "espn_slug": "tur.1",
        "season": 2025,
        "short": "TUR",
        "teams": []
    },
    "PRIMERA_DIVISION_ARG": {
        "espn_slug": "arg.1",
        "season": 2025,
        "short": "ARG",
        "teams": []
    },
}

UNDERSTAT_API = "https://understat.com/getLeagueData/{league}/{season}"

ESPN_SOCCER_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"

XG_DIFF_MINIMA = 0.40
XG_DIFF_ALTA   = 0.75
FACTOR_LOCALIA = 0.35
PENALIZACION_BAJA = 0.10

PPDA_BAJO = 10.0
PPDA_ALTO = 15.0

UMBRAL_OVER_25   = 2.8
UMBRAL_UNDER_25  = 2.2
UMBRAL_OVER_ALTA  = 3.2
UMBRAL_UNDER_ALTA = 1.8

UMBRAL_PROB_OVER_POISSON = 65.0

CORNER_LEAGUE_AVG = {
    "PREMIER_LEAGUE": {"centros": 15.2, "tiros": 12.4, "bloqueos": 3.1, "despejes": 18.5, "corners_por_equipo": 5.1},
    "LA_LIGA": {"centros": 14.8, "tiros": 11.9, "bloqueos": 3.4, "despejes": 19.2, "corners_por_equipo": 4.9},
    "BUNDESLIGA": {"centros": 15.5, "tiros": 13.1, "bloqueos": 2.9, "despejes": 17.8, "corners_por_equipo": 5.0},
    "SERIE_A": {"centros": 14.1, "tiros": 11.5, "bloqueos": 3.6, "despejes": 20.1, "corners_por_equipo": 4.7},
    "LIGUE_1": {"centros": 14.5, "tiros": 11.8, "bloqueos": 3.3, "despejes": 19.0, "corners_por_equipo": 4.8},
    "LIGA_MX": {"centros": 14.0, "tiros": 11.2, "bloqueos": 3.5, "despejes": 19.5, "corners_por_equipo": 4.6},
    "MLS": {"centros": 14.2, "tiros": 11.0, "bloqueos": 3.2, "despejes": 18.8, "corners_por_equipo": 4.5},
    "BRASILEIRAO": {"centros": 13.8, "tiros": 11.5, "bloqueos": 3.4, "despejes": 19.8, "corners_por_equipo": 4.7},
    "EREDIVISIE": {"centros": 16.0, "tiros": 13.5, "bloqueos": 2.8, "despejes": 17.0, "corners_por_equipo": 5.3},
    "PRIMEIRA_LIGA": {"centros": 14.3, "tiros": 11.8, "bloqueos": 3.3, "despejes": 18.9, "corners_por_equipo": 4.7},
    "SUPER_LIG": {"centros": 13.5, "tiros": 11.0, "bloqueos": 3.5, "despejes": 20.0, "corners_por_equipo": 4.5},
    "CHAMPIONSHIP": {"centros": 15.0, "tiros": 12.0, "bloqueos": 3.2, "despejes": 19.0, "corners_por_equipo": 5.0},
    "PRIMERA_DIVISION_ARG": {"centros": 13.5, "tiros": 10.8, "bloqueos": 3.6, "despejes": 20.2, "corners_por_equipo": 4.4},
    "MUNDIAL": {"centros": 14.5, "tiros": 11.5, "bloqueos": 3.3, "despejes": 19.0, "corners_por_equipo": 4.8},
    "DEFAULT": {"centros": 14.5, "tiros": 11.5, "bloqueos": 3.3, "despejes": 19.0, "corners_por_equipo": 4.8},
}

UMBRAL_OVER_45_CORNERS = 5.5
UMBRAL_OVER_55_CORNERS = 6.2
UMBRAL_CENTROS_ALTO = 18.0
UMBRAL_BLOQUEOS_ALTO = 4.5

REGRESION_UMBRAL = 1.3

PARTIDOS_RECIENTES = 5
SV_ALTO_UMBRAL  = 3.5
SV_BAJO_UMBRAL  = 2.5
SV_OVER_UMBRAL  = 3.2

CACHE_STATS_PATH  = os.path.join(BASE_DIR, "stats_soccer_equipos.csv")
CSV_SOCCER_PATH   = os.path.join(BASE_DIR, "apuestas_soccer.xlsx")
LOG_PATH          = os.path.join(BASE_DIR, "futbol_bot.log")
LOG_LEVEL         = "INFO"

TIMEZONE = "America/Ciudad_Juarez"
HORA_ANALISIS_MANANA = "06:00"
MINUTOS_PREVIA_ANALISIS = 60
HORA_RECALCULO_DIARIO = "05:00"

SCRAPE_DELAY = 3

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6099564810")

SCRAPE_DIA_ACTUAL = True
