import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SOCCER_LEAGUES_V1 = {
    "PREMIER_LEAGUE": {
        "understat_league": "EPL",
        "season": 2025,
        "short": "ENG",
        "teams": []
    },
    "LA_LIGA": {
        "understat_league": "La_liga",
        "season": 2025,
        "short": "ESP",
        "teams": []
    },
    "BUNDESLIGA": {
        "understat_league": "Bundesliga",
        "season": 2025,
        "short": "GER",
        "teams": []
    },
    "SERIE_A": {
        "understat_league": "Serie_A",
        "season": 2025,
        "short": "ITA",
        "teams": []
    },
    "LIGUE_1": {
        "understat_league": "Ligue_1",
        "season": 2025,
        "short": "FRA",
        "teams": []
    },
    "LIGA_MX": {
        "source": "espn",
        "espn_slug": "mex.1",
        "season": 2025,
        "short": "MEX",
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

REGRESION_UMBRAL = 1.3

PARTIDOS_RECIENTES = 5
SV_ALTO_UMBRAL  = 3.5
SV_BAJO_UMBRAL  = 2.5
SV_OVER_UMBRAL  = 3.2

CACHE_STATS_PATH  = os.path.join(BASE_DIR, "stats_soccer_equipos.csv")
CSV_SOCCER_PATH   = os.path.join(BASE_DIR, "apuestas_soccer.csv")
LOG_PATH          = os.path.join(BASE_DIR, "futbol_bot.log")
LOG_LEVEL         = "INFO"

TIMEZONE = "America/Ciudad_Juarez"
HORA_ANALISIS_MANANA = "06:00"
MINUTOS_PREVIA_ANALISIS = 60
HORA_RECALCULO_DIARIO = "05:00"

SCRAPE_DELAY = 3

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "8862582497:AAF7o5RX1NH7OI26sG0RyC5hFzNyYSiBjpA")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6099564810")

SCRAPE_DIA_ACTUAL = True
