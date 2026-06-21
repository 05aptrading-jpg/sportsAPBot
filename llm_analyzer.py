"""
LLM Analyzer for sports matchups via OpenRouter or Gemini.
Analiza favorito vs rival usando modelos de lenguaje con datos reales.
"""
import json
import logging
import requests

import config

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _call_gemini(prompt: str, user_msg: str, model: str = None) -> str | None:
    """Call Gemini API directly. Returns response text or None on error."""
    api_key = config.GEMINI_API_KEY
    if not api_key:
        return None
    model = model or config.GEMINI_MODEL
    url = f"{GEMINI_BASE}/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": f"{prompt}\n\n{user_msg}"}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096,
        },
    }
    try:
        r = requests.post(url, json=payload, timeout=60)
        if r.status_code != 200:
            logger.warning(f"Gemini API error {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "")
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
    return None

PROMPTS = {
    "baseball": (
        "Eres un analista experto en apuestas de béisbol (MLB/LMB) con conocimiento profundo de métricas avanzadas.\n\n"
        "Recibes enfrentamientos con este formato: Local vs Visitante (Fecha).\n"
        "IMPORTANTE: El PRIMER equipo es el LOCAL (juega en casa), el SEGUNDO es el VISITANTE.\n"
        "La fecha te sirve para calcular días de descanso, calendario reciente, etc.\n\n"
        "PARA CADA PARTIDO, ANALIZA:\n\n"
        "1. FAVORITO: ¿Quién es el favorito real? Cruza:\n"
        "   - Posición en división y récord de cada equipo\n"
        "   - Racha reciente (últimos 10 juegos)\n"
        "   - Historial de enfrentamientos directos\n"
        "   - Lesiones de jugadores clave\n\n"
        "1b. POSICIÓN EN TABLA: Para cada equipo indica su división y puesto exacto:\n"
        "   - Ejemplo: 'AL Este: 1º (42-28, Dif +85)' o 'LMB Zona Sur: 3º (25-20)'\n\n"
        "2. CARRERAS ESTIMADAS: Predice el marcador final (ej: 5-3) basado en:\n"
        "   - Promedio de carreras anotadas/recibidas por cada equipo\n"
        "   - Calidad del abridor (ERA, WHIP, K/BB)\n"
        "   - Efectividad del bullpen\n\n"
        "2b. LÍNEAS DE CARRERAS: Para el total de carreras del partido, estima probabilidades para:\n"
        "   - Over/Under 7.5, 8.5, 9.5\n"
        "   - Basado en el potencial ofensivo/defensivo y contexto\n"
        "   - Las probabilidades deben ser realistas (no todos 80%)\n\n"
        "3. ABRIDORES: Evalúa el duelo de lanzadores abridores:\n"
        "   - Nombre, ERA, récord, ponches\n"
        "   - Mano (zurdo/diestro) y cómo afecta a la alineación rival\n\n"
        "4. BATEADORES CLAVE: Identifica 4-6 bateadores clave del partido (2-3 por equipo):\n"
         "   - Bateador estrella de cada equipo\n"
         "   - Estima probabilidad de HR y remolcadas\n"
         "   - Incluye confianza_bateo (0-100%) que refleje tu nivel de certeza en la estimación\n\n"
        "5. RELEVO: Evalúa el bullpen de cada equipo:\n"
        "   - Efectividad general (ERA del bullpen)\n"
        "   - Confianza en situaciones de presión\n\n"
        "6. VEREDICTO: ¿Vale la pena apostar al favorito? Responde SÍ solo si hay ventaja clara.\n\n"
        "Responde EXACTAMENTE con este JSON, sin texto extra, sin markdown, solo el objeto crudo:\n\n"
        '{"partidos": [{"partido": "Local vs Visitante (Fecha)", '
        '"equipo_local": "Nombre exacto del equipo local", '
        '"equipo_visitante": "Nombre exacto del equipo visitante", '
        '"fecha": "YYYY-MM-DD", '
        '"favorito": "Nombre exacto del equipo favorito", '
        '"ir_con_favorito": "SÍ" o "NO", '
        '"porque": "Razón ultra-resumida de máximo 25 palabras.", '
        '"factores": ["Factor clave 1", "Factor clave 2", "Factor clave 3"], '
        '"ranking_local": "División y puesto del local, ej: NL Oeste: 1º (42-28)", '
        '"ranking_visitante": "División y puesto del visitante, ej: NL Oeste: 3º (30-35)", '
        '"carreras_esperadas": "X-Y", '
        '"carreras_lineas": {"over_7.5": probabilidad%, "over_8.5": probabilidad%, "over_9.5": probabilidad%}, '
        '"abridor_local": "Nombre (ERA, récord, Ks)", '
        '"abridor_visitante": "Nombre (ERA, récord, Ks)", '
        '"bateadores_clave": ['
        '{"jugador": "Nombre", "equipo": "Equipo", "hrs_estimados": número, "remolcadas_estimadas": número, "confianza_bateo": porcentaje}, '
        '{"jugador": "Nombre", "equipo": "Equipo", "hrs_estimados": número, "remolcadas_estimadas": número, "confianza_bateo": porcentaje}, '
        '{"jugador": "Nombre", "equipo": "Equipo", "hrs_estimados": número, "remolcadas_estimadas": número, "confianza_bateo": porcentaje}, '
        '{"jugador": "Nombre", "equipo": "Equipo", "hrs_estimados": número, "remolcadas_estimadas": número, "confianza_bateo": porcentaje}, '
        '{"jugador": "Nombre", "equipo": "Equipo", "hrs_estimados": número, "remolcadas_estimadas": número, "confianza_bateo": porcentaje}'
        '], '
        '"relevo_local": "Texto sobre bullpen local", '
        '"relevo_visitante": "Texto sobre bullpen visitante"'
        '}]}\n\n'
        'CRÍTICO: Si no tienes información suficiente, sé honesto y pon "ir_con_favorito": "NO". '
        "Sin introducciones. Solo JSON."
    ),
    "soccer": (
        "Eres un analista de apuestas de fútbol de élite. Analiza el siguiente partido usando tu conocimiento.\n\n"
        "PARA CADA PARTIDO, ANALIZA:\n\n"
        "1. FAVORITO: ¿Quién es el favorito real? No asumas por localía. Cruza:\n"
        "   - Ranking FIFA actual de cada selección o posición en tabla de liga\n"
        "   - Racha reciente (últimos 5 partidos)\n"
        "   - Historial de enfrentamientos directos\n"
        "   - Lesiones de jugadores clave\n"
        "   - Contexto del torneo (necesidad de puntos, presión, etc.)\n\n"
         "1b. RANKING/POSICIÓN EN TABLA: Para cada equipo indica su posición exacta en la tabla de su liga o ranking FIFA:\n"
         "   - Ejemplo: 'Liga MX: 3º puesto' o 'FIFA: #12' o 'Premier League: 1º'\n"
         "   - Si es selección, usa ranking FIFA. Si es club, usa posición en liga.\n\n"
         "2. MARCADOR ESTIMADO: Predice el resultado final más probable basado en:\n"
         "   - Promedio de goles anotados/recibidos por cada equipo\n"
         "   - Estilo de juego (ofensivo vs defensivo)\n"
         "   - Histórico de goles en partidos similares\n\n"
         "2b. LÍNEAS DE GOLES: Para el total de goles del partido, estima probabilidades para:\n"
         "   - Over/Under 0.5, 1.5, 2.5, 3.5\n"
         "   - Basado en el estilo de juego, potencial ofensivo/defensivo y contexto\n"
         "   - Las probabilidades deben ser realistas (no todos 80%)\n\n"
         "3. CORNERS ESTIMADOS: Estima el total de corners basado en:\n"
         "   - Estilo de juego de ambos equipos (posesión vs contraataque)\n"
         "   - Tendencia de corners en el torneo o liga\n\n"
         "3b. LÍNEAS DE CORNERS: Para el total de corners del partido, estima probabilidades para:\n"
         "   - Over/Under 8.5, 9.5, 10.5\n"
         "   - Basado en tendencias ofensivas y defensivas de cada equipo\n\n"
         "4. TIROS A PORTERÍA: Identifica los 3 jugadores más probables de tener tiros a porteria:\n"
         "   - Delanteros principales de cada equipo\n"
         "   - Mediocampistas ofensivos con tendencia a disparar\n"
         "   - Estima cantidad de tiros a porteria por jugador\n\n"
         "5. VEREDICTO: ¿Vale la pena apostar al favorito? Responde SÍ solo si hay ventaja clara.\n\n"
        "Responde EXACTAMENTE con este JSON, sin texto extra, sin markdown ```json ```, solo el objeto crudo:\n\n"
        '{"partidos": [{"partido": "Equipo A vs Equipo B", '
        '"favorito": "Nombre exacto del equipo favorito", '
        '"ir_con_favorito": "SÍ" o "NO", '
        '"porque": "Razón ultra-resumida de máximo 25 palabras.", '
        '"factores": ["Factor clave 1", "Factor clave 2", "Factor clave 3"], '
        '"ranking_local": "Posición en tabla/ranking del equipo local, ej: Liga MX 3º", '
        '"ranking_visitante": "Posición en tabla/ranking del equipo visitante, ej: FIFA #45", '
        '"goles_esperados": "X-Y", '
         '"corners_esperados": número_entero, '
         '"goles_lineas": {"over_0.5": probabilidad%, "over_1.5": probabilidad%, "over_2.5": probabilidad%, "over_3.5": probabilidad%}, '
         '"corners_lineas": {"over_8.5": probabilidad%, "over_9.5": probabilidad%, "over_10.5": probabilidad%}, '
         '"tiros_porteria": ['
         '{"jugador": "Nombre", "equipo": "Equipo", "tiros_estimados": número}, '
         '{"jugador": "Nombre", "equipo": "Equipo", "tiros_estimados": número}, '
         '{"jugador": "Nombre", "equipo": "Equipo", "tiros_estimados": número}'
         ']}]}\n\n'
        'CRÍTICO: Si no tienes información suficiente, sé honesto y pon "ir_con_favorito": "NO". '
        'Si los datos incluyen estadísticas (xG, señales, confianza), úsalas como contexto adicional pero no dependas exclusivamente de ellas.'
    ),
    "nba": (
        "Eres un analista experto en apuestas de la NBA/WNBA con conocimiento profundo de métricas avanzadas.\n\n"
        "Recibes enfrentamientos donde el PRIMER equipo es el local.\n\n"
        "Se te proporcionan DATOS REALES de temporada para cada equipo: récord, estadísticas ofensivas/de equipo y líderes. "
        "USA ESOS DATOS para tu análisis — no inventes estadísticas.\n\n"
        "PARA CADA PARTIDO, ANALIZA:\n\n"
        "1. FAVORITO: ¿Quién es el favorito real? Basado en los récords, estadísticas ofensivas/defensivas, localía y datos proporcionados.\n"
        "2. PUNTOS ESTIMADOS: Predice el marcador final basado en los PPG reales y eficiencia de cada equipo.\n"
        "3. SPREAD ESTIMADO: ¿Cuál sería la diferencia de puntos? Basado en los datos reales.\n"
        "4. CONFIANZA OVER/UNDER: ¿El total de puntos superará la línea esperada? Usa el PPG combinado real.\n"
        "5. FACTORES CLAVE: Usa los datos proporcionados (eficiencia ofensiva/defensiva, ritmo implícito, etc.).\n"
        "   - Back-to-Back: Si algún equipo jugó anoche, penaliza severamente\n"
        "   - Lesiones: Baja de estrella = cambiar pronóstico\n"
        "   - Localía: ventaja real en cancha propia\n\n"
        "6. JUGADORES POR ROL: Identifica 2-3 jugadores por cada rol (usa los LÍDERES proporcionados como referencia). "
        "Debe haber jugadores de AMBOS equipos en cada categoría, mezclando Local y Visitante:\n"
        "   - anotadores: máximo anotador de cada equipo. pts_estimados (float), confianza_pts (0-100%)\n"
        "   - defensores: especialistas en rebotes/robos/bloqueos. reb_estimados (float), robos_estimados (float), bloqueos_estimados (float), confianza_def (0-100%)\n"
        "   - armadores: directores de juego. ast_estimadas (float), confianza_ast (0-100%)\n\n"
        "7. RANKING: Para cada equipo, indica su récord y posición en la conferencia. Ej: 'Este: 1° (11-5)'.\n"
        "8. STATS COMPARISON: Proporciona un objeto con datos clave de comparación:\n"
        "   - ppg_local: puntos anotados por el local en temporada\n"
        "   - ppg_visitante: puntos anotados por el visitante\n"
        "   - opp_ppg_local: puntos recibidos por el local\n"
        "   - opp_ppg_visitante: puntos recibidos por el visitante\n"
        "   - fg_pct_local: % de field goals del local\n"
        "   - fg_pct_visitante: % de field goals del visitante\n"
        "   - pace_analysis: breve texto sobre ritmo de juego\n\n"
        "9. LINEAS O/U: Proporciona un objeto con confianza para diferentes líneas de over/under:\n"
        '   Ej: {"over_140": 75, "over_150": 60, "over_160": 40}\n\n'
        "Responde EXACTAMENTE con este JSON, sin texto extra, sin markdown, solo el objeto crudo:\n\n"
        '{"partidos": [{"partido": "Local vs Visitante", '
        '"favorito": "Nombre del equipo favorito", '
        '"ir_con_favorito": "SÍ" o "NO", '
        '"porque": "Razón ultra-resumida de máximo 20 palabras.", '
        '"factores": ["Factor 1", "Factor 2"], '
        '"puntos_local": número_entero, '
        '"puntos_visitante": número_entero, '
        '"spread_estimado": número_flotante, '
        '"confianza_over_under": porcentaje_0_100, '
        '"linea_over_under": número_flotante, '
        '"b2b_impacto": "Texto sobre impacto B2B o vacío", '
        '"lesion_clave": "Jugador clave y su estado o vacío", '
        '"anotadores": ['
        '{"nombre": "Jugador A", "equipo": "Local", "pts_estimados": 28.5, "confianza_pts": 75}, '
        '{"nombre": "Jugador B", "equipo": "Visitante", "pts_estimados": 32.1, "confianza_pts": 70}'
        '], '
        '"defensores": ['
        '{"nombre": "Jugador C", "equipo": "Local", "reb_estimados": 10.1, "robos_estimados": 1.5, "bloqueos_estimados": 0.8, "confianza_def": 80}, '
        '{"nombre": "Jugador D", "equipo": "Visitante", "reb_estimados": 7.5, "robos_estimados": 2.1, "bloqueos_estimados": 0.3, "confianza_def": 75}'
        '], '
        '"armadores": ['
        '{"nombre": "Jugador E", "equipo": "Local", "ast_estimadas": 7.2, "confianza_ast": 72}, '
        '{"nombre": "Jugador F", "equipo": "Visitante", "ast_estimadas": 6.5, "confianza_ast": 68}'
        '], '
        '"ranking_local": "Conferencia: posición (récord)", '
        '"ranking_visitante": "Conferencia: posición (récord)", '
        '"stats_comparison": {'
        '"ppg_local": 98.5, "ppg_visitante": 102.1, '
        '"opp_ppg_local": 95.2, "opp_ppg_visitante": 99.8, '
        '"fg_pct_local": 46.2, "fg_pct_visitante": 44.1, '
        '"pace_analysis": "Ritmo alto, ambos equipos transicionan rápido"'
        "}, "
        '"lineas_ou": {"over_140": 75, "over_150": 60, "over_160": 40}'
        '}]}\n\n'
        'CRÍTICO: USA LOS DATOS PROPORCIONADOS para tu análisis. '
        'No inventes estadísticas. Si no tienes datos suficientes, sé conservador. '
        'Si el favorito tiene B2B o una lesión de estrella, tu respuesta DEBE ser "ir_con_favorito": "NO".'
    ),
    "nfl": (
        "Eres un analista experto en apuestas de la NFL (fútbol americano) con conocimiento profundo.\n\n"
        "Recibes enfrentamientos donde el PRIMER equipo es el local.\n\n"
        "PARA CADA PARTIDO, ANALIZA:\n\n"
        "1. FAVORITO: ¿Quién es el favorito real? Basado en:\n"
        "   - Récord de temporada y posición en división/conferencia\n"
        "   - Racha reciente (últimos 5 partidos)\n"
        "   - Historial de enfrentamientos directos\n"
        "   - Lesiones de jugadores clave (especialmente QB)\n"
        "   - Ventaja de localía\n\n"
        "2. PUNTOS ESTIMADOS: Predice el marcador final basado en:\n"
        "   - Puntos por juego (PPG) ofensivo y defensivo de cada equipo\n"
        "   - Yardas por juego (YPG) y eficiencia\n"
        "   - Calidad del QB y del coaching staff\n\n"
        "3. SPREAD ESTIMADO: ¿Cuál sería la diferencia de puntos?\n"
        "   - Usa el spread de DraftKings como referencia\n"
        "   - Ajusta por factores como lesiones, viaje, descanso\n\n"
        "4. OVER/UNDER: ¿El total de puntos superará la línea?\n"
        "   - Analiza la velocidad del juego (pace) de ambos equipos\n"
        "   - Defensas vs ofensivas: ¿juegan rápido o lento?\n"
        "   - Clima si es outdoor stadium\n\n"
        "5. MATCHUP DE QBS: Evalúa el duelo de mariscales de campo:\n"
        "   - Nombre, TD/INT ratio, passer rating, yardas por intento\n"
        "   - Experiencia en situaciones de presión\n\n"
        "6. JUGADORES CLAVE: Identifica 3-4 jugadores impactantes:\n"
        "   - QB de cada equipo\n"
        "   - RB o WR principal\n"
        "   - Jugador defensivo estrella\n\n"
        "7. RANKING: Para cada equipo, indica su conferencia, división y posición. Ej: 'AFC Oeste: 1º (12-4)'.\n"
        "8. STATS COMPARISON: Proporciona un objeto con datos clave:\n"
        "   - ppg_local: puntos anotados por juego del local\n"
        "   - ppg_visitante: puntos anotados por juego del visitante\n"
        "   - ypg_local: yardas totales por juego del local\n"
        "   - ypg_visitante: yardas totales por juego del visitante\n"
        "   - def_ppg_local: puntos recibidos por juego del local\n"
        "   - def_ppg_visitante: puntos recibidos por juego del visitante\n\n"
        "Responde EXACTAMENTE con este JSON, sin texto extra, sin markdown, solo el objeto crudo:\n\n"
        '{"partidos": [{"partido": "Local vs Visitante", '
        '"favorito": "Nombre del equipo favorito", '
        '"ir_con_favorito": "SÍ" o "NO", '
        '"porque": "Razón ultra-resumida de máximo 20 palabras.", '
        '"factores": ["Factor 1", "Factor 2", "Factor 3"], '
        '"puntos_local": número_entero, '
        '"puntos_visitante": número_entero, '
        '"spread_estimado": número_flotante, '
        '"confianza_spread": porcentaje_0_100, '
        '"over_under": número_flotante, '
        '"confianza_ou": porcentaje_0_100, '
        '"ranking_local": "Conferencia División: posición (récord)", '
        '"ranking_visitante": "Conferencia División: posición (récord)", '
        '"stats_comparison": {'
        '"ppg_local": 28.5, "ppg_visitante": 24.2, '
        '"ypg_local": 380.5, "ypg_visitante": 345.2, '
        '"def_ppg_local": 19.2, "def_ppg_visitante": 21.5'
        "}, "
        '"jugadores_clave": ['
        '{"nombre": "QB Local", "equipo": "Local", "pos": "QB", "stat_key": "QB Rating: 105.2"}, '
        '{"nombre": "QB Visitante", "equipo": "Visitante", "pos": "QB", "stat_key": "QB Rating: 98.7"}, '
        '{"nombre": "RB/WR Local", "equipo": "Local", "pos": "RB/WR", "stat_key": "Yards: 1200, TDs: 10"}, '
        '{"nombre": "RB/WR Visitante", "equipo": "Visitante", "pos": "RB/WR", "stat_key": "Yards: 1050, TDs: 8"}'
        ']'
        '}]}\n\n'
        'CRÍTICO: USA LOS DATOS PROPORCIONADOS para tu análisis. '
        'No inventes estadísticas. Si no tienes datos suficientes, sé conservador.'
    ),
    "hits": (
        "Eres un analista experto en bateo de b\u00e9isbol (MLB) y sabermetr\u00eda ofensiva.\n\n"
        "Recibes enfrentamientos de equipo con los TOP 5 jugadores con mejor probabilidad de conectar al menos 1 hit.\n\n"
        "Formato:\n"
        "'Equipo A vs Equipo B'\n"
        "Jugador: [nombre] - Prob: [XX.X]% - vs Mano: [Z/D]\n\n"
        "Para CADA equipo, analiza:\n"
        "- \u00bfLas probabilidades tienen sentido contra el abridor de hoy?\n"
        "- \u00bfEl jugador est\u00e1 en el lineup titular o es suplente?\n"
        "- \u00bfEl perfil del lanzador (zurdo/diestro) favorece a estos bateadores?\n"
        "- Si la mayor\u00eda de los top 5 son del mismo lado (ej: todos derechos contra zurdo), se\u00f1\u00e1lalo.\n\n"
        "Responde EXACTAMENTE con este JSON:\n\n"
        '{"hits": [{"equipo": "Nombre del equipo",\n'
        '"confianza": "ALTA" si las probabilidades son confiables, "BAJA" si no,\n'
        '"porque": "raz\u00f3n en m\u00e1x. 25 palabras",\n'
        '"top_jugador": "nombre del jugador con mejor proyecci\u00f3n del equipo",\n'
        '"factores": ["factor1", "factor2"]}]}\n\n'
        'IMPORTANTE: Si un equipo tiene menos de 3 jugadores listados, pon "confianza": "BAJA".\n'
        "Sin introducciones. Solo JSON."
    ),
}


def _detect_sport(partido: str, liga: str = "") -> str:
    """Detecta el deporte basado en el nombre del partido o la liga."""
    liga_upper = liga.upper()
    if liga_upper in ("MLB", "LMB"):
        return "baseball"
    if any(x in liga_upper for x in ("FUTBOL", "FIFA", "PREMIER", "LA LIGA", "SERIE A", "BUNDESLIGA", "LIGUE 1", "MLS", "CHAMPIONS", "MUNDIAL")):
        return "soccer"
    if "NBA" in liga_upper:
        return "nba"
    if any(x in liga_upper for x in ("NFL", "FUTBOL AMERICANO", "AMERICAN FOOTBALL")):
        return "nfl"
    # Detección por nombre
    baseball_teams = ["yankees", "red sox", "dodgers", "braves", "astros", "phillies", "cardinals", "mets",
                      "giants", "cubs", "brewers", "padres", "marlins", "rockies", "diamondbacks",
                      "twins", "guardians", "orioles", "rays", "blue jays", "royals", "tigers",
                      "angels", "rangers", "mariners", "athletics", "reds", "pirates", "nationals",
                      "bravos", "toros", "sultanes", "olmecas", "diablos", "pericos", "piratas",
                      "algodoneros", "charros", "leones", "acereros", "dorados", "rieleros", "tecos"]
    nba_teams = ["lakers", "celtics", "warriors", "heat", "nets", "bucks", "76ers", "nuggets",
                 "mavericks", "suns", "clippers", "kings", "hawks", "bulls", "cavaliers",
                 "pistons", "pacers", "knicks", "magic", "raptors", "wizards", "hornets",
                 "pelicans", "spurs", "thunder", "jazz", "blazers", "rockets", "wolves", "grizzlies",
                 "liberty", "sun", "mercury", "lynx", "fever", "sky",
                 "wings", "aces", "storm", "sparks", "mystics", "dream"]
    nfl_teams = ["chiefs", "bills", "ravens", "bengals", "browns", "steelers", "texans",
                 "colts", "jaguars", "titans", "broncos", "raiders", "chargers", "cowboys",
                 "eagles", "commanders", "giants", "49ers", "seahawks", "rams", "cardinals",
                 "packers", "vikings", "lions", "bears", "buccaneers", "saints", "falcons",
                 "panthers", "patriots", "jets", "dolphins"]
    partido_lower = partido.lower()
    if any(t in partido_lower for t in baseball_teams):
        return "baseball"
    if any(t in partido_lower for t in nba_teams):
        return "nba"
    if any(t in partido_lower for t in nfl_teams):
        return "nfl"
    return "baseball"


def _parse_llm_response(content: str) -> list[dict]:
    """Parse LLM JSON response, handling markdown wrappers and truncation."""
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        content = content.rsplit("```", 1)[0].strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # Try to fix truncated JSON by finding last complete object
        last_brace = content.rfind("}")
        if last_brace > 0:
            attempt = content[:last_brace + 1]
            # Try closing open arrays
            open_brackets = attempt.count("[") - attempt.count("]")
            open_braces = attempt.count("{") - attempt.count("}")
            attempt += "]" * open_brackets + "}" * open_braces
            try:
                result = json.loads(attempt)
            except json.JSONDecodeError:
                logger.warning(f"JSON LLM irreparable (long={len(content)})")
                return []
        else:
            return []
    if isinstance(result, list):
        return result
    if "partidos" in result:
        return result["partidos"]
    if "analisis" in result:
        return result["analisis"]
    if "partido" in result:
        return [result]
    return []


def _ensure_soccer_fields(results: list[dict]):
    """Ensure soccer-specific fields have defaults."""
    for r in results:
        r.setdefault("goles_esperados", "")
        r.setdefault("corners_esperados", 0)
        r.setdefault("tiros_porteria", [])
        r.setdefault("goles_lineas", {})
        r.setdefault("corners_lineas", {})
        r.setdefault("favorito", "")
        r.setdefault("factores", [])
        r.setdefault("ranking_local", "")
        r.setdefault("ranking_visitante", "")


def _ensure_baseball_fields(results: list[dict]):
    """Ensure baseball-specific fields have defaults."""
    for r in results:
        r.setdefault("carreras_esperadas", "")
        r.setdefault("carreras_lineas", {})
        r.setdefault("ranking_local", "")
        r.setdefault("ranking_visitante", "")
        r.setdefault("abridor_local", "")
        r.setdefault("abridor_visitante", "")
        r.setdefault("bateadores_clave", [])
        r.setdefault("relevo_local", "")
        r.setdefault("relevo_visitante", "")
        r.setdefault("favorito", "")
        r.setdefault("factores", [])


def _ensure_nba_fields(results: list[dict]):
    """Ensure NBA-specific fields have defaults."""
    for r in results:
        r.setdefault("puntos_local", 0)
        r.setdefault("puntos_visitante", 0)
        r.setdefault("spread_estimado", 0.0)
        r.setdefault("confianza_over_under", 0)
        r.setdefault("linea_over_under", 0.0)
        r.setdefault("b2b_impacto", "")
        r.setdefault("lesion_clave", "")
        r.setdefault("jugadores_clave", [])
        r.setdefault("anotadores", [])
        r.setdefault("defensores", [])
        r.setdefault("armadores", [])
        r.setdefault("ranking_local", "")
        r.setdefault("ranking_visitante", "")
        r.setdefault("stats_comparison", {})
        r.setdefault("lineas_ou", {})
        r.setdefault("favorito", "")
        r.setdefault("factores", [])


def analizar_partidos(
    partidos: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    Analiza una lista de partidos usando Gemini (primario) u OpenRouter (fallback).

    Args:
        partidos: Lista de dicts con clave 'partido' y opcionalmente 'liga', 'datos'

    Returns:
        Lista de dicts con 'partido', 'ir_con_favorito', 'porque', 'factores'
    """
    if not partidos:
        return []

    # Agrupar por deporte para usar prompt específico
    by_sport = {}
    for p in partidos:
        sport = _detect_sport(p.get("partido", ""), p.get("liga", ""))
        by_sport.setdefault(sport, []).append(p)

    # ── Try Gemini first ────────────────────────────────────────────
    if config.GEMINI_API_KEY:
        logger.info("Intentando Gemini como proveedor LLM...")
        results = _analizar_con_gemini(by_sport, partidos)
        # Check if Gemini actually returned results (not all fallbacks)
        real_results = [r for r in results if r.get("ir_con_favorito") != "N/D"]
        if real_results:
            logger.info(f"Gemini exitoso: {len(real_results)} partidos reales")
            return results
        logger.warning("Gemini sin resultados reales, intentando OpenRouter...")

    # ── Fallback: OpenRouter ────────────────────────────────────────
    if config.OPENROUTER_API_KEY:
        logger.info("Usando OpenRouter como proveedor LLM")
        return _analizar_con_openrouter(by_sport, partidos)

    logger.warning("Sin API key configurada — saltando análisis LLM")
    return _fallback(partidos)


def _analizar_con_gemini(by_sport: dict, all_partidos: list) -> list[dict]:
    """Analiza partidos usando Gemini API."""
    all_results = []
    for sport, sport_partidos in by_sport.items():
        prompt = PROMPTS[sport]
        batch_size = 10 if sport == "baseball" else (3 if sport == "nba" else len(sport_partidos))
        batches = [sport_partidos[i:i+batch_size] for i in range(0, len(sport_partidos), batch_size)]

        for batch in batches:
            lines = []
            for p in batch:
                line = p["partido"]
                if p.get("datos"):
                    line += f" | Datos: {p['datos']}"
                lines.append(line)

            user_prompt = "Analiza los siguientes enfrentamientos:\n" + "\n".join(lines)

            try:
                content = _call_gemini(prompt, user_prompt)
                if not content:
                    logger.warning(f"Gemini devolvió vacío para {sport}")
                    all_results.extend(_fallback(batch))
                    continue

                parsed = _parse_llm_response(content)
                all_results.extend(parsed)

                if sport == "soccer":
                    _ensure_soccer_fields(all_results[-len(batch):])
                elif sport == "baseball":
                    _ensure_baseball_fields(all_results[-len(batch):])
                elif sport == "nba":
                    _ensure_nba_fields(all_results[-len(batch):])

                logger.info(f"Gemini {sport}: {len(batch)} partidos analizados")

            except Exception as e:
                logger.error(f"Error Gemini para {sport}: {e}")
                all_results.extend(_fallback(batch))

    return all_results


def _analizar_con_openrouter(by_sport: dict, all_partidos: list) -> list[dict]:
    """Analiza partidos usando OpenRouter API."""
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai no instalado — pip install openai")
        return _fallback(all_partidos)

    api_key = config.OPENROUTER_API_KEY
    all_results = []
    client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE)

    for sport, sport_partidos in by_sport.items():
        prompt = PROMPTS[sport]
        batch_size = 5
        if sport == "nba":
            batch_size = 3
        if sport == "baseball":
            batch_size = 3
        batches = [sport_partidos[i:i+batch_size] for i in range(0, len(sport_partidos), batch_size)]

        for batch in batches:
            lines = []
            for p in batch:
                line = p["partido"]
                if p.get("datos"):
                    line += f" | Datos: {p['datos']}"
                lines.append(line)

            user_prompt = "Analiza los siguientes enfrentamientos:\n" + "\n".join(lines)

            try:
                response = client.chat.completions.create(
                    model=config.OPENROUTER_MODEL,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=4096 if sport in ("nba", "baseball") else 2048,
                    extra_headers={"HTTP-Referer": "https://github.com/mlb-bot"},
                )

                content = response.choices[0].message.content
                parsed = _parse_llm_response(content)
                all_results.extend(parsed)

                if sport == "soccer":
                    _ensure_soccer_fields(all_results[-len(batch):])
                elif sport == "baseball":
                    _ensure_baseball_fields(all_results[-len(batch):])
                elif sport == "nba":
                    _ensure_nba_fields(all_results[-len(batch):])

                logger.info(f"OpenRouter {sport}: lote de {len(batch)} ok ({len(parsed)} resultados)")

            except Exception as e:
                logger.error(f"Error OpenRouter para {sport}: {e}")
                all_results.extend(_fallback(batch))

    return all_results


def _fallback(partidos: list[dict]) -> list[dict]:
    """Retorna valores vacíos cuando el LLM no está disponible."""
    return [
        {
            "partido": p["partido"],
            "ir_con_favorito": "N/D",
            "porque": "LLM no disponible",
            "factores": [],
            "goles_esperados": "",
            "corners_esperados": 0,
            "tiros_porteria": [],
            "favorito": "",
        }
        for p in partidos
    ]


def analizar_hits(team_groups: list[dict]) -> list[dict]:
    """
    Analiza predicciones de hits por equipo usando OpenRouter.

    Args:
        team_groups: Lista de dicts, cada uno con:
            - "partido": "TeamA vs TeamB"
            - "equipo": nombre del equipo
            - "jugadores": lista de {"nombre": str, "prob": float, "mano": str}
            - "rival": nombre del equipo rival

    Returns:
        Lista de dicts con 'equipo', 'confianza', 'porque', 'top_jugador', 'factores'
    """
    if not team_groups:
        return []

    api_key = config.OPENROUTER_API_KEY
    if not api_key:
        logger.warning("OPENROUTER_API_KEY no configurada — saltando análisis hits LLM")
        return [{"equipo": t["equipo"], "confianza": "N/D", "porque": "LLM no disponible", "top_jugador": "", "factores": []} for t in team_groups]

    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai no instalado — pip install openai")
        return [{"equipo": t["equipo"], "confianza": "N/D", "porque": "LLM no disponible", "top_jugador": "", "factores": []} for t in team_groups]

    prompt = PROMPTS["hits"]
    client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE)

    # Build input: group by partido
    by_game = {}
    for tg in team_groups:
        key = tg["partido"]
        by_game.setdefault(key, {"partido": key, "equipos": []})
        by_game[key]["equipos"].append(tg)

    all_results = []

    for game_key, game_data in by_game.items():
        lines = [f"Partido: {game_key}"]
        for tg in game_data["equipos"]:
            lines.append(f"\nEquipo: {tg['equipo']}")
            for j in tg.get("jugadores", []):
                mano = j.get("mano", "?")
                lines.append(f"  Jugador: {j['nombre']} - Prob: {j['prob']:.1f}% - vs Mano: {mano}")
        lines.append("")
        lines.append(f"Rival: {tg.get('rival', '?')}")

        user_prompt = "Analiza las predicciones de hits para los siguientes equipos:\n" + "\n".join(lines)

        try:
            response = client.chat.completions.create(
                model=config.OPENROUTER_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                extra_headers={"HTTP-Referer": "https://github.com/mlb-bot"},
            )

            content = response.choices[0].message.content
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0].strip()

            result = json.loads(content)

            if isinstance(result, list):
                all_results.extend(result)
            elif "hits" in result:
                all_results.extend(result["hits"])
            elif "equipo" in result:
                all_results.append(result)
            else:
                logger.warning(f"Formato LLM inesperado para hits: {list(result.keys())}")

        except Exception as e:
            logger.error(f"Error llamando OpenRouter para hits ({game_key}): {e}")
            for tg in game_data["equipos"]:
                all_results.append({
                    "equipo": tg["equipo"],
                    "confianza": "N/D",
                    "porque": "Error LLM",
                    "top_jugador": "",
                    "factores": [],
                })

    return all_results


def analizar_desde_csv(today: str = None) -> int:
    """Lee el CSV de baseball, analiza juegos sin LLM y escribe resultados.
    Si today es None, analiza TODOS los juegos sin LLM (histórico).
    Si today es una fecha YYYY-MM-DD, solo analiza juegos de esa fecha.
    Retorna cantidad de juegos analizados."""
    import data_manager as dm
    from datetime import datetime as _dt

    filas = dm._leer_todas()
    need_llm = []
    for f in filas:
        ir = (f.get("llm_ir_favorito") or "").strip()
        if ir:
            continue
        raw_fecha = (f.get("fecha_hora") or "").strip()[:10]
        try:
            fecha = _dt.strptime(raw_fecha, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            try:
                fecha = _dt.strptime(raw_fecha, "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                continue
        if today is not None and fecha != today:
            continue
        liga = (f.get("liga") or "MLB").strip().upper()
        away = (f.get("equipo_visitante") or "").strip()
        home = (f.get("equipo_local") or "").strip()
        fav  = (f.get("favorito_sabermetrico") or "").strip()
        if not away or not home:
            continue
        need_llm.append({
            "partido": f"{fav} vs {away if fav == home else home} ({fecha})",
            "match_key": f"{fav} vs {away if fav == home else home}",
            "liga": liga,
            "fecha": fecha,
            "away": away,
            "home": home,
            "favorito": fav,
            "id_partido": (f.get("id_partido") or "").strip(),
        })

    if not need_llm:
        logger.info("No hay juegos MLB/LMB pendientes de análisis LLM")
        return 0

    logger.info(f"Analizando LLM para {len(need_llm)} juegos MLB/LMB desde CSV")
    results = analizar_partidos(need_llm)

    if not results:
        logger.warning("LLM no retornó resultados")
        return 0

    # Mapear resultados por match_key
    result_map = {}
    for r in results:
        partido_str = r.get("partido", "")
        ir = r.get("ir_con_favorito", "N/D")
        porque = r.get("porque", "")
        factores = r.get("factores", [])
        result_map[partido_str] = {"ir": ir, "porque": porque, "factores": factores}

    # Escribir al CSV
    count = 0
    for entry in need_llm:
        res = result_map.get(entry["partido"]) or result_map.get(entry["match_key"])
        if not res:
            continue
        ir = res["ir"]
        porque = res["porque"]
        factores = json.dumps(res["factores"], ensure_ascii=False)
        idp = entry["id_partido"]
        if idp:
            dm.actualizar_celda(idp, "llm_ir_favorito", ir)
            dm.actualizar_celda(idp, "llm_porque", porque)
            dm.actualizar_celda(idp, "llm_factores", factores)
            # Compute resultado_llm from current CSV state
            _res_actual = dm._leer_fila(idp, "resultado")
            dm.actualizar_celda(idp, "resultado_llm", dm._computar_resultado_llm(ir, _res_actual))
        else:
            dm.actualizar_celda_por_equipos(entry["fecha"], entry["away"], entry["home"], "llm_ir_favorito", ir)
            dm.actualizar_celda_por_equipos(entry["fecha"], entry["away"], entry["home"], "llm_porque", porque)
            dm.actualizar_celda_por_equipos(entry["fecha"], entry["away"], entry["home"], "llm_factores", factores)
            _res_actual = dm._leer_celda_por_equipos(entry["fecha"], entry["away"], entry["home"], "resultado")
            dm.actualizar_celda_por_equipos(entry["fecha"], entry["away"], entry["home"], "resultado_llm",
                                            dm._computar_resultado_llm(ir, _res_actual))

        # Guardar también en cache persistente
        from miniapp_publisher import _save_llm_to_file
        _save_llm_to_file(
            f"{entry['liga']}_{entry['fecha']}_{entry['favorito']}_{entry['away'] if entry['favorito'] == entry['home'] else entry['home']}",
            ir, porque, res["factores"], entry["favorito"], "baseball"
        )
        count += 1

    logger.info(f"LLM escritos en CSV: {count} juegos")
    return count



