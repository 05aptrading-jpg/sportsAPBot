"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MLB BOT — analyzer.py                                                      ║
║  Motor de análisis sabermérico — Metodología v3.0                          ║
║                                                                              ║
║  Distribución de pesos:                                                     ║
║    Bloque 1 — Pitcheo Abridor   30% (FIP, xFIP, K%-BB%)                   ║
║    Bloque 2 — Ofensiva Activa   35% (wRC+ lineup × Park Factor)            ║
║    Bloque 3 — Bullpen/Fatiga    25% (WAR + log 72h Baseball-Ref)           ║
║    Bloque 4 — Eficiencia        10% (BaseRuns vs récord real)              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional

import config
from api_client import mlb, savant, fg, odds, weather, bref

logger = logging.getLogger(__name__)


def normalizar_kbb_lmb(so_w_ratio):
    """Convierte SO/W ratio (ej: 2.5) a K%-BB% (ej: 4.55) usando regresión.
    Solo se llama cuando liga==LMB, todos los valores son SO/W ratio."""
    try:
        val = float(so_w_ratio)
        kbb_pct = (val - 1.2) * 3.5
        return max(0.5, round(kbb_pct, 4))
    except (ValueError, TypeError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PitcherProfile:
    name:           str
    player_id:      int
    ip:             float = 0.0
    fip:            float = 4.50
    xfip:           float = 4.50
    siera:          float = 4.50   # SIERA — más predictivo que FIP (ajusta por tipo contacto)
    k_pct:          float = 20.0
    bb_pct:         float = 8.0
    babip:          float = 0.300
    xwoba_against:  float = 0.320
    barrel_pct:     float = 8.0
    hard_hit_pct:   float = 36.0
    gb_pct:         float = 44.0   # Ground Ball % — clave para Park Factor ajuste
    pitch_hand:     str   = 'R'    # 'R' o 'L' — mano del lanzador
    is_opener:      bool  = False
    penalizacion:   float = 0.0    # % de penalización acumulada


@dataclass
class TeamOffense:
    name:           str
    wrc_plus:       float = 100.0
    wrc_vs_rhp:     float = 100.0   # wRC+ contra derechos
    wrc_vs_lhp:     float = 100.0   # wRC+ contra zurdos
    xwoba_7d:       float = 0.320
    xwoba_season:   float = 0.320
    park_factor:    float = 100.0


@dataclass
class BullpenStatus:
    team_name:      str
    war_bullpen:    float = 0.0
    pitcheos_72h:   int   = 0     # cerrador + setup man últimas 72h
    fatigado:       bool  = False


@dataclass
class TeamEfficiency:
    team_name:      str
    wins_real:      int   = 0
    losses_real:    int   = 0
    wins_baseruns:  float = 0.0   # victorias esperadas por BaseRuns
    diferencial:    float = 0.0   # wins_real - wins_baseruns


@dataclass
class GameAnalysis:
    game_pk:          int
    game_date:        str            # 'YYYY-MM-DD'
    game_datetime:    str = ''       # ISO 8601 con hora — para monitor pre-partido
    away_team:        str = ''
    home_team:        str = ''
    away_pitcher:     Optional[PitcherProfile] = None
    home_pitcher:     Optional[PitcherProfile] = None
    away_offense:     Optional[TeamOffense]    = None
    home_offense:     Optional[TeamOffense]    = None
    away_bullpen:     Optional[BullpenStatus]  = None
    home_bullpen:     Optional[BullpenStatus]  = None
    away_efficiency:  Optional[TeamEfficiency] = None
    home_efficiency:  Optional[TeamEfficiency] = None

    # Scores por bloque (0-100)
    away_score_b1:    float = 50.0   # Pitcheo abridor
    home_score_b1:    float = 50.0
    away_score_b2:    float = 50.0   # Ofensiva activa
    home_score_b2:    float = 50.0
    away_score_b3:    float = 50.0   # Bullpen
    home_score_b3:    float = 50.0
    away_score_b4:    float = 50.0   # Eficiencia
    home_score_b4:    float = 50.0

    # Trigger Moneyline (filtro de senal)
    senal_moneyline:   str   = "NO APOSTAR"
    nivel_certidumbre: str   = "MEDIA"   # "MEDIA" | "ALTA" — segun filtros avanzados
    usa_splits_reales: bool  = False    # Shadow Mode: True cuando splits B-Ref != fallback

    # Resultado final
    away_prob:        float = 50.0
    home_prob:        float = 50.0
    favorito:         str   = ""
    prob_favorito:    float = 50.0
    factor_riesgo:    str   = ""
    es_valor:         bool  = False   # Tríada del Valor
    odds_mercado:     Optional[float] = None  # prob. implícita mercado
    edge_pct:         Optional[float] = None  # prob_favorito - odds_mercado
    confianza:        str   = ""      # "Alta" | "Media" | "Baja"
    es_top3:          bool  = False   # Una de las 3 mejores selecciones del día
    top3_rank:        int   = 0       # 1, 2 o 3

    # Clima
    weather_desc:     str   = ""    # descripción del impacto del viento
    weather_ajuste:   float = 0.0   # ajuste aplicado al score B2

    # Fuentes consultadas
    fuentes:          list  = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# ██  BLOQUE 1 — PITCHEO ABRIDOR (30%)  ██
# ─────────────────────────────────────────────────────────────────────────────
def score_bloque1(pitcher: PitcherProfile,
                  peso_actual: float,
                  park_factor: float = 100.0) -> tuple[float, list[str]]:
    """
    Calcula el score del Bloque 1 para un equipo.
    Retorna (score 0-100, lista de alertas).

    Pesos internos (suma 1.0):
      SIERA  40% — más predictivo que FIP: ajusta por tipo de contacto (GB/FB/LD)
      xFIP   30% — estabiliza BABIP y HR/FB
      K-BB%  30% — control puro del lanzador

    SIERA es especialmente útil en estadios extremos (Coors, CDMX):
    lanzadores Ground Ball en parques elevados tienen SIERA mejor que FIP
    porque los GBs no se convierten en HR aunque vuelen más lejos.
    """
    alertas = []

    # ── xERA/SIERA (rango típico 2.8 - 5.5 → mapear a 0-100)
    # Usa xERA de Savant como proxy de SIERA (ambas son métricas predictivas
    # basadas en calidad de contacto). Fallback a xFIP si no disponible.
    xera_eff = pitcher.siera if pitcher.siera < 9.0 else pitcher.xfip
    xera_score = max(0, min(100, (5.5 - xera_eff) / 2.7 * 100))

    # ── xFIP (rango 2.5 - 6.0)
    xfip_score = max(0, min(100, (6.0 - pitcher.xfip) / 3.5 * 100))

    # ── K%-BB% diferencial (control puro)
    kbb_diff  = pitcher.k_pct - pitcher.bb_pct
    kbb_score = max(0, min(100, (kbb_diff + 5) / 30 * 100))

    # ── Ponderación base con xERA como métrica principal
    score = xera_score * 0.40 + xfip_score * 0.30 + kbb_score * 0.30

    alertas.append(
        f"📐 xERA={xera_eff:.2f} xFIP={pitcher.xfip:.2f} "
        f"K-BB%={kbb_diff:.1f}% → Score={score:.1f}"
    )

    # ── Ajuste Park Factor para lanzadores GB en parques elevados
    # Si park_factor > 105 (ej. Coors 113, CDMX ~110) y el lanzador
    # es Ground Ball (gb_pct > 50%), SIERA ya lo captura, pero añadimos
    # un bonus explícito para que el score no se penalice por park.
    if park_factor > 105 and pitcher.gb_pct > 50:
        bonus = min(5.0, (park_factor - 105) * 0.3)
        score = min(100, score + bonus)
        alertas.append(
            f"⛰️ GB pitcher ({pitcher.gb_pct:.0f}%) en parque elevado "
            f"(PF={park_factor:.0f}) → bonus +{bonus:.1f}"
        )
    elif park_factor > 105 and pitcher.gb_pct < 38:
        # Fly ball pitcher en parque elevado: penalizar
        penalidad = min(8.0, (park_factor - 105) * 0.5)
        score = max(0, score - penalidad)
        alertas.append(
            f"⚠️ FB pitcher ({pitcher.gb_pct:.0f}% GB) en parque elevado "
            f"(PF={park_factor:.0f}) → penalización -{penalidad:.1f}"
        )

    # ── Modulador BABIP / Savant
    if pitcher.babip < config.BABIP_SUERTE_BAJO:
        if pitcher.barrel_pct <= 8.0 and pitcher.xwoba_against <= 0.300:
            alertas.append("✅ BABIP bajo sustentado por Savant (baja regresión)")
        elif pitcher.hard_hit_pct > config.HARD_HIT_UMBRAL:
            pitcher.xfip += config.XFIP_PENALIZACION
            xfip_adj = max(0, min(100, (6.0 - pitcher.xfip) / 3.5 * 100))
            score = xera_score * 0.40 + xfip_adj * 0.30 + kbb_score * 0.30
            alertas.append(
                f"⚠️ Hard-Hit% {pitcher.hard_hit_pct:.1f}% > {config.HARD_HIT_UMBRAL}% "
                f"con BABIP bajo → xFIP penalizado +{config.XFIP_PENALIZACION}"
            )
    elif pitcher.babip > config.BABIP_SUERTE_ALTO:
        score = min(100, score * 1.05)
        alertas.append(f"📈 BABIP alto ({pitcher.babip:.3f}) → posible regresión positiva")

    # ── Penalización IP < 20
    if pitcher.ip < config.IP_MINIMAS_TEMPORADA:
        pitcher.penalizacion += config.PENALIZACION_IP_PCT
        alertas.append(
            f"🚨 Abridor con {pitcher.ip:.1f} IP (< {config.IP_MINIMAS_TEMPORADA}) "
            f"→ penalización -{config.PENALIZACION_IP_PCT}% probabilidad final"
        )

    # ── Opener
    if pitcher.is_opener:
        score *= 0.5
        alertas.append("📋 Opener detectado → peso bloque pitcheo reducido al 15%")

    return round(score, 2), alertas


# ─────────────────────────────────────────────────────────────────────────────
# ██  BLOQUE 2 — OFENSIVA ACTIVA (35%)  ██
# ─────────────────────────────────────────────────────────────────────────────
def score_bloque2(offense: TeamOffense) -> tuple[float, list[str]]:
    """
    wRC+ colectivo ajustado por Park Factor y tendencia xwOBA 7 días.
    wRC+ 100 = liga. Mejor equipo ~140, peor ~70.
    """
    alertas = []

    # Ajustar wRC+ por Park Factor (PF 100 = neutro)
    wrc_adj = offense.wrc_plus * (offense.park_factor / 100.0)

    # Normalizar: rango 70-140 → 0-100
    score = max(0, min(100, (wrc_adj - 70) / 70 * 100))

    # ── Modulador xwOBA 7 días (enracha / fría)
    desviacion = offense.xwoba_7d - offense.xwoba_season
    if abs(desviacion) > config.XWOBA_DESVIACION_7D:
        ajuste = (desviacion / config.XWOBA_DESVIACION_7D) * 10
        score  = max(0, min(100, score + ajuste))
        if desviacion > 0:
            alertas.append(
                f"🔥 Ofensiva enrachada — xwOBA 7d supera temporada "
                f"en +{desviacion:.3f} (>{config.XWOBA_DESVIACION_7D:.3f})"
            )
        else:
            alertas.append(
                f"❄️ Ofensiva fría — xwOBA 7d por debajo de temporada "
                f"en {desviacion:.3f}"
            )

    return round(score, 2), alertas


# ─────────────────────────────────────────────────────────────────────────────
# ██  BLOQUE 3 — BULLPEN / FATIGA (25%)  ██
# ─────────────────────────────────────────────────────────────────────────────
def score_bloque3(bullpen: BullpenStatus,
                  peso_extra: float = 0.0) -> tuple[float, list[str]]:
    """
    WAR del bullpen ajustado por fatiga de los últimos 3 días.
    peso_extra: si hay Opener, recibe los 15% adicionales.
    """
    alertas = []

    # WAR bullpen rango típico: -2.0 a +6.0 → normalizar a 0-100
    war_score = max(0, min(100, (bullpen.war_bullpen + 2.0) / 8.0 * 100))

    # ── Fatiga: cerrador + setup > 40 pitcheos en 72h
    if bullpen.pitcheos_72h > config.PITCHEOS_FATIGA_72H:
        reduccion = config.PENALIZACION_BULLPEN / 100.0
        war_score *= (1.0 - reduccion)
        bullpen.fatigado = True
        alertas.append(
            f"🆘 Bullpen FATIGADO — {bullpen.pitcheos_72h} pitcheos "
            f"(cerrador+setup) en 72h → WAR reducido {config.PENALIZACION_BULLPEN}%"
        )
    else:
        alertas.append(
            f"✅ Bullpen descansado — {bullpen.pitcheos_72h} pitcheos en 72h"
        )

    return round(war_score, 2), alertas


# ─────────────────────────────────────────────────────────────────────────────
# ██  BLOQUE 4 — EFICIENCIA DE VICTORIAS (10%)  ██
# ─────────────────────────────────────────────────────────────────────────────
def score_bloque4(efficiency: TeamEfficiency) -> tuple[float, list[str]]:
    """
    Compara récord real vs BaseRuns.
    Equipos que pierden más de lo esperado → candidatos a regresión positiva.
    """
    alertas = []
    diff = efficiency.wins_real - efficiency.wins_baseruns

    # Normalizar diferencial -15 a +15 → 0-100
    # Mayor diferencial negativo = más "suerte pendiente" = mejor candidato
    score = max(0, min(100, (-diff + 15) / 30 * 100))

    if diff < -config.BASERUNS_DIFERENCIAL:
        alertas.append(
            f"🎯 Equipo con mala suerte — {abs(diff):.1f} victorias "
            f"por debajo de BaseRuns esperado → candidato a regresión"
        )
    elif diff > config.BASERUNS_DIFERENCIAL:
        alertas.append(
            f"⚠️ Equipo 'afortunado' — {diff:.1f} victorias "
            f"sobre BaseRuns esperado → posible regresión negativa"
        )
    else:
        alertas.append("→ Récord real alineado con BaseRuns (sin sesgo significativo)")

    return round(score, 2), alertas


# ─────────────────────────────────────────────────────────────────────────────
# ██  MOTOR PRINCIPAL  ██
# ─────────────────────────────────────────────────────────────────────────────
def calcular_probabilidad(score_b1: float, score_b2: float,
                           score_b3: float, score_b4: float,
                           opener: bool = False) -> tuple[float, dict]:
    """
    Combina los 4 bloques con sus pesos y retorna la probabilidad 0-100.
    Si hay Opener: bloque 1 baja a 15% y bullpen sube a 40%.
    """
    if opener:
        w1 = config.PESO_PITCHEO_ABRIDOR - config.PESO_OPENER_REDUCCION  # 15
        w3 = config.PESO_BULLPEN + config.PESO_OPENER_REDUCCION           # 40
    else:
        w1 = config.PESO_PITCHEO_ABRIDOR   # 30
        w3 = config.PESO_BULLPEN           # 25

    w2 = config.PESO_OFENSIVA    # 35
    w4 = config.PESO_EFICIENCIA  # 10

    total = (score_b1 * w1 +
             score_b2 * w2 +
             score_b3 * w3 +
             score_b4 * w4) / 100.0

    pesos = {"B1_pitcheo": w1, "B2_ofensiva": w2,
             "B3_bullpen": w3, "B4_eficiencia": w4}
    return round(total, 2), pesos


# ─────────────────────────────────────────────────────────────────────────────
# ██  TRIGGER MONEYLINE — filtro de senal  ██
# ─────────────────────────────────────────────────────────────────────────────
def calcular_trigger(
    fip_a: float, xfip_a: float, kbb_a: float,
    fip_h: float, xfip_h: float, kbb_h: float,
    wrc_a: float, wrc_h: float,
    liga: str = "MLB",
    # Shadow Mode Fase 2 — splits por mano del abridor rival
    wrc_rhp_a: float = None, wrc_lhp_a: float = None,
    wrc_rhp_h: float = None, wrc_lhp_h: float = None,
    abridor_mano_a: str = None, abridor_mano_h: str = None,
) -> tuple[str, str, bool]:
    """
    Segmenta triggers por HOLGURA del score.

    Score_Pitcheo = (10 - FIP) + (10 - xFIP) + (K/BB * 2)

    Retorna (senal, nivel_certidumbre, usa_splits_reales):
      senal:   "APRETA TRIGGER VISITANTE" | "APRETA TRIGGER LOCAL" | "NO APOSTAR"
      nivel:   "ALTA" | "MEDIA" | ""

    ALTA si |diff_pitcheo| > TRIGGER_HOLGURA_PITCHEO (6.0)
          Y |diff_wrc| > TRIGGER_HOLGURA_WRC (15).
    MEDIA si pasa el trigger combinado pero holgura insuficiente.

    Shadow Mode Fase 2: si se pasan wrc_rhp/lhp y abridor_mano, selecciona
    el split ofensivo según la mano del abridor rival. Solo activo cuando
    los splits son datos reales (diferentes del wrc_plus genérico).

    PF, BP, FIP son estrictamente INFORMATIVOS (en descripcion_analisis).
    """
    # ── Normalizacion LMB: SO/W ratio → K%-BB% y xFIP = FIP ─────
    if liga == "LMB":
        kbb_a = normalizar_kbb_lmb(kbb_a)
        kbb_h = normalizar_kbb_lmb(kbb_h)
        xfip_a = fip_a
        xfip_h = fip_h

    # ── Shadow Mode: split dinámico según mano del abridor rival ────────────
    usa_splits_reales = False
    if liga == "MLB" and all(v is not None for v in
        [wrc_rhp_a, wrc_lhp_a, wrc_rhp_h, wrc_lhp_h, abridor_mano_a, abridor_mano_h]):
        # Heurística: splits reales cuando NO todos son 100.0 (fallback de B-Ref)
        todos_cien = (wrc_rhp_a == 100.0 and wrc_lhp_a == 100.0
                      and wrc_rhp_h == 100.0 and wrc_lhp_h == 100.0)
        usa_splits_reales = not todos_cien
        if usa_splits_reales:
            wrc_a = wrc_lhp_a if abridor_mano_h == 'L' else wrc_rhp_a
            wrc_h = wrc_lhp_h if abridor_mano_a == 'L' else wrc_rhp_h
            logger.debug(f"Shadow Mode splits activo: wrc_a={wrc_a} wrc_h={wrc_h}")

    sa = (10 - fip_a) + (10 - xfip_a) + (kbb_a * 2)
    sh = (10 - fip_h) + (10 - xfip_h) + (kbb_h * 2)
    diff_p = sa - sh
    diff_w = wrc_a - wrc_h

    # ── Trigger base: Score_Pitcheo y wRC+ deben coincidir ──────────────────
    if diff_p > 0 and wrc_a > wrc_h:
        trig = "APRETA TRIGGER VISITANTE"
    elif diff_p < 0 and wrc_h > wrc_a:
        trig = "APRETA TRIGGER LOCAL"
    else:
        return ("NO APOSTAR", "BAJA", usa_splits_reales)

    # Filtro LMB: wRC diff >= 15
    if liga == "LMB" and abs(diff_w) < config.TRIGGER_WRC_MIN_LMB:
        return ("NO APOSTAR", "BAJA", usa_splits_reales)

    # ── Holgura: segmenta ALTA vs MEDIA ─────────────────────────────────────
    if abs(diff_p) > config.TRIGGER_HOLGURA_PITCHEO and abs(diff_w) > config.TRIGGER_HOLGURA_WRC:
        nivel = "ALTA"
    else:
        nivel = "MEDIA"

    return (trig, nivel, usa_splits_reales)


def analizar_partido(game: dict,
                     fg_pitchers: dict,
                     fg_batting: dict,
                     fg_bullpen: dict,
                     pythagorean_records: dict,
                     odds_data: list,
                     weather_cache: dict = None,
                     splits_cache: dict = None) -> GameAnalysis:
    """
    Analiza un partido completo aplicando la metodología sabermérica v3.0.
    Retorna un GameAnalysis con probabilidades, scores y alertas.
    """
    fuentes = [
        "https://statsapi.mlb.com (MLB Stats API oficial)",
        "https://baseballsavant.mlb.com (K%, BB%, xFIP, xwOBA, Barrel%, BABIP)",
        "https://baseballsavant.mlb.com (Statcast: xwOBA, Barrel%, BABIP)",
        "https://the-odds-api.com (Cuotas mercado)",
    ]

    # ── Extraer info básica del partido
    try:
        teams      = game["teams"]
        away_info  = teams["away"]
        home_info  = teams["home"]
        away_name  = away_info["team"]["name"]
        home_name  = home_info["team"]["name"]
        game_pk       = game["gamePk"]
        raw_dt        = game.get("gameDate", "")
        # Convertir UTC a timezone local antes de extraer fecha
        try:
            utc_dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
            local_tz = timezone(timedelta(hours=-6))  # America/Ciudad_Juarez = UTC-6
            local_dt = utc_dt.astimezone(local_tz)
            game_date = local_dt.strftime("%Y-%m-%d")
        except Exception:
            game_date = raw_dt[:10]
        # Conservar ISO completo con hora si MLB lo trae; fallback a fecha sola
        game_datetime = raw_dt if "T" in raw_dt else game_date

        away_pitcher_name = (away_info.get("probablePitcher") or {}).get("fullName", "TBD")
        home_pitcher_name = (home_info.get("probablePitcher") or {}).get("fullName", "TBD")
        away_pitcher_id   = (away_info.get("probablePitcher") or {}).get("id")
        home_pitcher_id   = (home_info.get("probablePitcher") or {}).get("id")
    except (KeyError, TypeError) as e:
        logger.error(f"Error extrayendo info del partido: {e}")
        return None

    analysis = GameAnalysis(
        game_pk       = game_pk,
        game_date     = game_date,
        game_datetime = game_datetime,
        away_team     = away_name,
        home_team     = home_name,
        fuentes       = fuentes,
    )

    alertas_away = []
    alertas_home = []

    def build_pitcher(name, pid) -> PitcherProfile:
        p = PitcherProfile(name=name, player_id=pid or 0)
        if not name or name == "TBD":
            p.penalizacion += config.PENALIZACION_IP_PCT
            return p

        # ── Fuente 1: Savant leaderboard (vía alias fg) ──────────────────
        fg_data = fg.find_pitcher(fg_pitchers, name)
        leaderboard_tiene_statcast = False
        if fg_data:
            p.pitch_hand = str(fg_data.get("p_throws", "R")).upper()
            p.fip       = float(fg_data.get("FIP") or 4.50)
            p.xfip      = float(fg_data.get("xFIP") or 4.50)
            # SIERA — usa xERA como proxy si SIERA no está en el leaderboard
            # Savant no exporta SIERA directamente; xERA es el equivalente moderno
            siera_raw   = fg_data.get("SIERA") or fg_data.get("xERA") or fg_data.get("ERA")
            p.siera     = float(siera_raw or 4.50)
            p.k_pct     = float(fg_data.get("K%") or 20.0)
            p.bb_pct    = float(fg_data.get("BB%") or 8.0)
            p.ip        = float(fg_data.get("IP") or 0.0)
            # Ground Ball % — usado para ajuste de Park Factor en parques elevados
            # NO usar Whiff% como fallback — no tiene relación con Ground Balls
            gb_raw      = fg_data.get("GB%") or fg_data.get("gb_percent")
            if gb_raw:
                # GB% del leaderboard puede venir como 0-100 o 0-1
                gb_val = float(gb_raw)
                p.gb_pct = gb_val if gb_val > 1 else gb_val * 100

            babip_ld = fg_data.get("BABIP")
            if babip_ld is not None and float(babip_ld) > 0:
                p.babip         = float(babip_ld)
                p.xwoba_against = float(fg_data.get("xwOBA_against") or 0.320)
                p.barrel_pct    = float(fg_data.get("Barrel%")       or 8.0)
                p.hard_hit_pct  = float(fg_data.get("HardHit%")      or 36.0)
                leaderboard_tiene_statcast = True

        # ── Fuente 2: MLB Stats API — fallback cuando Savant no responde ──
        # Se activa cuando: el leaderboard falló (fg_data=None) O entregó
        # IP=0 (lanzador no alcanzó el mínimo de 10 IP del filtro Savant).
        # Usa ERA/WHIP/K9/BB9 para estimar FIP, xFIP y K%-BB%.
        if pid and (not fg_data or p.ip == 0.0):
            mlb_stats = mlb.get_pitcher_stats_mlb(pid)
            if mlb_stats and mlb_stats.get("ip", 0.0) > 0:
                p.pitch_hand = str(mlb_stats.get("pitch_hand", "R")).upper()
                p.ip  = mlb_stats["ip"]
                # Estimar K% y BB% desde K/9 y BB/9
                # K/9 promedio liga ~8.5 → K% ~22%; BB/9 ~3 → BB% ~8%
                p.k_pct  = round(mlb_stats.get("so_per9", 8.5) / 38.0 * 100, 1)
                p.bb_pct = round(mlb_stats.get("bb_per9", 3.0) / 38.0 * 100, 1)
                # FIP desde ERA como proxy conservador
                era = mlb_stats.get("era", 4.50)
                p.fip  = round(era * 0.95, 2)   # FIP tiende a ser ~5% mejor que ERA
                p.xfip = round(era * 0.92, 2)
                p.siera = era                   # xERA/SIERA proxy
                p.babip = mlb_stats.get("babip", 0.300)
                logger.info(
                    f"Pitcher [{name}]: Savant sin datos → MLB API fallback "
                    f"(ERA={era} IP={p.ip:.1f} K/9={mlb_stats.get('so_per9',0):.1f})"
                )

        # ── Fuente 3: Statcast individual — solo si el leaderboard no trajo métricas ──
        if pid and not leaderboard_tiene_statcast and p.ip > 0:
            csv_text = savant.get_pitcher_statcast(pid)
            sv_data  = savant.parse_pitcher_metrics(csv_text, pid)
            if sv_data["babip"] is not None:
                p.babip         = sv_data["babip"]
                p.xwoba_against = sv_data["xwoba_against"] or 0.320
                p.barrel_pct    = sv_data["barrel_pct"]    or 8.0
                p.hard_hit_pct  = sv_data["hard_hit_pct"]  or 36.0

        # ── Fuente 4: Rol del lanzador — opener vs SP vs bulk ────────────
        # Analiza los últimos 5 arranques via MLB API gameLog.
        # Solo se llama si tiene pid y suficientes IP para haber arrancado.
        if pid and p.ip > 0:
            role = mlb.get_pitcher_role(pid)
            if role == "opener":
                p.is_opener = True
                logger.info(f"Pitcher [{name}]: OPENER detectado (gameLog MLB API)")
            elif role == "bulk":
                logger.debug(f"Pitcher [{name}]: bulk pitcher (avg IP < 5.0)")

        return p

    away_p = build_pitcher(away_pitcher_name, away_pitcher_id)
    home_p = build_pitcher(home_pitcher_name, home_pitcher_id)
    analysis.away_pitcher = away_p
    analysis.home_pitcher = home_p

    # ─── BLOQUE 2: Ofensiva activa ────────────────────────────────────────
    # Se construye ANTES del Bloque 1 para tener park_factor disponible
    def build_offense(name) -> TeamOffense:
        off = TeamOffense(name=name)
        td  = fg.find_team_batting(fg_batting, name)
        if td:
            off.wrc_plus    = float(td.get("OPS+") or td.get("wRC+") or 100.0)
            off.park_factor = float(td.get("ParkFactor") or td.get("BPF") or 100.0)
            off.wrc_vs_rhp = float(td.get("OPS_vs_RHP") or off.wrc_plus)
            off.wrc_vs_lhp = float(td.get("OPS_vs_LHP") or off.wrc_plus)
        return off

    away_off = build_offense(away_name)
    home_off = build_offense(home_name)

    # Cargar splits reales desde B-Ref (Opción B) si no vienen de FG
    sc = splits_cache if splits_cache is not None else {}
    _splits_encontrados = False
    for off_obj, team_name in [(away_off, away_name), (home_off, home_name)]:
        if off_obj and off_obj.wrc_vs_rhp == off_obj.wrc_plus and off_obj.wrc_vs_lhp == off_obj.wrc_plus:
            if team_name not in sc:
                sc[team_name] = bref.get_team_splits(team_name)
            sp = sc[team_name]
            off_obj.wrc_vs_rhp = sp.get("ops_vs_rhp", off_obj.wrc_plus)
            off_obj.wrc_vs_lhp = sp.get("ops_vs_lhp", off_obj.wrc_plus)
            if sp.get("found"):
                _splits_encontrados = True
    analysis.away_offense = away_off
    analysis.home_offense = home_off

    # ─── BLOQUE 1: Pitcheo abridor ────────────────────────────────────────
    # park_factor del estadio local aplica a ambos lanzadores
    _park_factor = home_off.park_factor if home_off else 100.0
    score_a1, al_a1 = score_bloque1(away_p, config.PESO_PITCHEO_ABRIDOR, _park_factor)
    score_h1, al_h1 = score_bloque1(home_p, config.PESO_PITCHEO_ABRIDOR, _park_factor)
    analysis.away_score_b1 = score_a1
    analysis.home_score_b1 = score_h1
    alertas_away.extend(al_a1)
    alertas_home.extend(al_h1)

    score_a2, al_a2 = score_bloque2(away_off)
    score_h2, al_h2 = score_bloque2(home_off)
    analysis.away_score_b2 = score_a2
    analysis.home_score_b2 = score_h2
    alertas_away.extend(al_a2)
    alertas_home.extend(al_h2)

    # ── Ajuste por clima (Open-Meteo, sin key) ──────────────────────────
    if weather_cache is not None:
        if home_name not in weather_cache:
            weather_cache[home_name] = weather.get_stadium_weather(home_name)
        w        = weather_cache.get(home_name)
        w_ajuste, w_desc = weather.wind_impact(w, home_name)
        if w_ajuste != 0.0:
            # Viento hacia afuera → favorece ofensiva (ajuste negativo baja pitcheo)
            # Viento hacia adentro → suprime ofensiva (ajuste positivo sube pitcheo)
            analysis.away_score_b2 = max(0, min(100, score_a2 - w_ajuste))
            analysis.home_score_b2 = max(0, min(100, score_h2 - w_ajuste))
            analysis.away_score_b1 = max(0, min(100, analysis.away_score_b1 + w_ajuste * 0.5))
            analysis.home_score_b1 = max(0, min(100, analysis.home_score_b1 + w_ajuste * 0.5))
            analysis.weather_desc   = w_desc
            analysis.weather_ajuste = w_ajuste
            alertas_away.append(w_desc)
        elif w and w_desc:
            analysis.weather_desc = w_desc

    # ─── BLOQUE 3: Bullpen / fatiga ───────────────────────────────────────
    def build_bullpen(name) -> BullpenStatus:
        bp  = BullpenStatus(team_name=name)

        # ── WAR del bullpen — dos fuentes ────────────────────────────────
        # 1. WAR del staff completo desde fg_bullpen (tabla teams_value_pitching)
        bpd = fg.find_team_batting(fg_bullpen, name)
        staff_war = float(bpd.get("WAR") or 0.0) if bpd else 0.0

        # 2. WAR específico de relevistas (B-Ref players_value_pitching)
        try:
            reliever_war = bref.get_bullpen_war(name)
            if reliever_war != 0.0:
                bp.war_bullpen = reliever_war
                logger.debug(f"Bullpen [{name}]: WAR={reliever_war:.2f} (B-Ref relevistas)")
            elif staff_war != 0.0:
                # Fallback: ~35% del WAR total del staff es del bullpen
                bp.war_bullpen = round(staff_war * 0.35, 2)
                logger.debug(f"Bullpen [{name}]: WAR≈{bp.war_bullpen:.2f} (35% de staff WAR={staff_war:.2f})")
        except Exception as e:
            logger.debug(f"Bullpen WAR [{name}]: {e}")
            if staff_war != 0.0:
                bp.war_bullpen = round(staff_war * 0.35, 2)

        # ── Pitcheos últimas 72h — MLB Stats API (schedule reciente) ────
        try:
            bp.pitcheos_72h = bref.get_bullpen_pitcheos_72h(name)
            logger.debug(f"Bullpen [{name}]: {bp.pitcheos_72h} pitcheos 72h (MLB API)")
        except Exception as e:
            logger.debug(f"Bullpen pitcheos_72h [{name}]: {e} → 0")
            bp.pitcheos_72h = 0

        return bp

    away_bp = build_bullpen(away_name)
    home_bp = build_bullpen(home_name)
    analysis.away_bullpen = away_bp
    analysis.home_bullpen = home_bp

    score_a3, al_a3 = score_bloque3(away_bp)
    score_h3, al_h3 = score_bloque3(home_bp)
    analysis.away_score_b3 = score_a3
    analysis.home_score_b3 = score_h3
    alertas_away.extend(al_a3)
    alertas_home.extend(al_h3)

    # ─── BLOQUE 4: Eficiencia / BaseRuns ─────────────────────────────────
    def build_efficiency(name, wins, losses) -> TeamEfficiency:
        eff = TeamEfficiency(team_name=name,
                              wins_real=wins, losses_real=losses)
        # Pitagórico desde standings MLB API (R² / (R²+RA²))
        if pythagorean_records:
            rec = pythagorean_records.get(name)
            if rec:
                eff.wins_baseruns = rec["wins_pyt"]
        if eff.wins_baseruns == 0.0:
            eff.wins_baseruns = float(wins)
        eff.diferencial = wins - eff.wins_baseruns
        return eff

    away_w = away_info.get("leagueRecord", {}).get("wins", 0)
    home_w = home_info.get("leagueRecord", {}).get("wins", 0)
    away_l = away_info.get("leagueRecord", {}).get("losses", 0)
    home_l = home_info.get("leagueRecord", {}).get("losses", 0)

    away_eff = build_efficiency(away_name, away_w, away_l)
    home_eff = build_efficiency(home_name, home_w, home_l)
    analysis.away_efficiency = away_eff
    analysis.home_efficiency = home_eff

    score_a4, al_a4 = score_bloque4(away_eff)
    score_h4, al_h4 = score_bloque4(home_eff)
    analysis.away_score_b4 = score_a4
    analysis.home_score_b4 = score_h4
    alertas_away.extend(al_a4)
    alertas_home.extend(al_h4)

    # ─── TRIGGER MONEYLINE ───────────────────────────────────────────────
    # Usa FIP/xFIP/KBB/wRC reales (no scores normalizados) para filtrar
    senal_moneyline, nivel_cert, usa_splits = calcular_trigger(
        away_p.fip, away_p.xfip, away_p.k_pct - away_p.bb_pct,
        home_p.fip, home_p.xfip, home_p.k_pct - home_p.bb_pct,
        away_off.wrc_plus, home_off.wrc_plus,
        liga="MLB",
        wrc_rhp_a=away_off.wrc_vs_rhp, wrc_lhp_a=away_off.wrc_vs_lhp,
        wrc_rhp_h=home_off.wrc_vs_rhp, wrc_lhp_h=home_off.wrc_vs_lhp,
        abridor_mano_a=away_p.pitch_hand, abridor_mano_h=home_p.pitch_hand,
    )
    analysis.senal_moneyline = senal_moneyline
    analysis.nivel_certidumbre = nivel_cert
    analysis.usa_splits_reales = _splits_encontrados

    # ─── PROBABILIDAD FINAL ───────────────────────────────────────────────
    opener_away = away_p.is_opener
    opener_home = home_p.is_opener

    prob_away, _ = calcular_probabilidad(
        score_a1, score_a2, score_a3, score_a4, opener_away)
    prob_home, _ = calcular_probabilidad(
        score_h1, score_h2, score_h3, score_h4, opener_home)

    # Normalizar para que sumen 100
    total = prob_away + prob_home
    if total > 0:
        prob_away = round(prob_away / total * 100, 2)
        prob_home = round(100 - prob_away, 2)

    # Aplicar penalizaciones de IP
    prob_away -= away_p.penalizacion
    prob_home -= home_p.penalizacion
    # Renormalizar
    total = prob_away + prob_home
    if total > 0:
        prob_away = round(prob_away / total * 100, 2)
        prob_home = round(100 - prob_away, 2)

    analysis.away_prob = prob_away
    analysis.home_prob = prob_home

    # ─── FAVORITO Y FACTOR DE RIESGO ─────────────────────────────────────
    if prob_away >= prob_home:
        analysis.favorito      = away_name
        analysis.prob_favorito = prob_away
    else:
        analysis.favorito      = home_name
        analysis.prob_favorito = prob_home

    riesgos = []
    if away_p.ip < config.IP_MINIMAS_TEMPORADA:
        label = "sin datos" if away_p.ip == 0.0 else f"{away_p.ip:.0f} IP"
        riesgos.append(f"Abridor visitante pocas IP ({label})")
    if home_p.ip < config.IP_MINIMAS_TEMPORADA:
        label = "sin datos" if home_p.ip == 0.0 else f"{home_p.ip:.0f} IP"
        riesgos.append(f"Abridor local pocas IP ({label})")
    if away_bp.fatigado:
        riesgos.append("Bullpen visitante fatigado (B-Ref 72h)")
    if home_bp.fatigado:
        riesgos.append("Bullpen local fatigado (B-Ref 72h)")
    if away_p.is_opener:
        riesgos.append("Opener visitante")
    if home_p.is_opener:
        riesgos.append("Opener local")
    # Señal débil: probabilidad demasiado cercana a 50%
    if analysis.prob_favorito < config.PROB_MINIMA_APUESTA:
        riesgos.append(f"⚠️ Señal débil ({analysis.prob_favorito:.1f}% < {config.PROB_MINIMA_APUESTA}%)")
    if not riesgos:
        riesgos.append("Normal")
    analysis.factor_riesgo = " | ".join(riesgos)

    # ─── TRÍADA DEL VALOR ────────────────────────────────────────────────
    # Condición 1: prob > 55%
    cond1 = analysis.prob_favorito > config.PROB_MINIMA_SEÑAL

    # Condición 2: mala suerte en BaseRuns (diferencial < -5)
    if analysis.favorito == away_name:
        eff_fav = away_eff
        off_fav = away_off
    else:
        eff_fav = home_eff
        off_fav = home_off
    cond2 = eff_fav.diferencial < -config.BASERUNS_DIFERENCIAL

    # Condición 3: odds de mercado pagan como underdog (prob < prob sabermérica)
    cond3 = False
    if odds_data:
        for game_odds in odds_data:
            if (analysis.favorito.lower() in
                    game_odds.get("home_team", "").lower() or
                    analysis.favorito.lower() in
                    game_odds.get("away_team", "").lower()):
                market_prob = odds.get_consensus_prob(
                    game_odds, analysis.favorito)
                if market_prob:
                    # SIEMPRE guardar odds_mercado si la API retornó datos,
                    # independientemente de si el mercado subestima o no.
                    analysis.odds_mercado = round(market_prob * 100, 2)
                    # cond3 solo True cuando el mercado SUBestima al favorito
                    if market_prob < (analysis.prob_favorito / 100):
                        cond3 = True
                break

    analysis.es_valor = cond1 and cond2 and cond3

    # ─── EDGE Y CONFIANZA ──────────────────────────────────────────────────
    if analysis.odds_mercado is not None:
        analysis.edge_pct = round(analysis.prob_favorito - analysis.odds_mercado, 2)
    if cond1 and analysis.edge_pct is not None and analysis.edge_pct >= config.EDGE_MINIMO:
        analysis.confianza = "Alta"
    elif cond1:
        analysis.confianza = "Media"
    else:
        analysis.confianza = "Baja"

    # ─── FALLBACK ODDS: si todos los bloques quedaron en defaults (50.0) ──────
    # Ocurre cuando Savant y B-Ref fallan completamente y MLB API tampoco
    # aportó suficiente data. En ese caso la probabilidad 50/50 no dice nada;
    # la probabilidad implícita de mercado es la mejor estimación disponible.
    _DEFAULT = 50.0
    scores_son_default = all(
        abs(v - _DEFAULT) < 0.5 for v in [
            analysis.away_score_b1, analysis.home_score_b1,
            analysis.away_score_b2, analysis.home_score_b2,
            analysis.away_score_b3, analysis.home_score_b3,
            analysis.away_score_b4, analysis.home_score_b4,
        ]
    )
    if scores_son_default and odds_data:
        for game_odds in odds_data:
            h = game_odds.get("home_team", "").lower()
            a = game_odds.get("away_team", "").lower()
            if home_name.lower() in h or h in home_name.lower() or \
               away_name.lower() in a or a in away_name.lower():
                prob_away_mkt = odds.get_consensus_prob(game_odds, away_name)
                prob_home_mkt = odds.get_consensus_prob(game_odds, home_name)
                if prob_away_mkt and prob_home_mkt:
                    # Normalizar para que sumen 100 (el mercado tiene vig)
                    total_mkt = prob_away_mkt + prob_home_mkt
                    away_pct = round(prob_away_mkt / total_mkt * 100, 2)
                    home_pct = round(100 - away_pct, 2)
                    analysis.away_prob     = away_pct
                    analysis.home_prob     = home_pct
                    if away_pct >= home_pct:
                        analysis.favorito      = away_name
                        analysis.prob_favorito = away_pct
                    else:
                        analysis.favorito      = home_name
                        analysis.prob_favorito = home_pct
                    analysis.odds_mercado = round(
                        max(prob_away_mkt, prob_home_mkt) * 100, 2
                    )
                    logger.warning(
                        f"[FALLBACK ODDS] {away_name} @ {home_name} — "
                        f"datos saberméricos insuficientes. "
                        f"Usando probabilidad de mercado: "
                        f"{analysis.favorito} {analysis.prob_favorito:.1f}%"
                    )
                break

    # ── FALLBACK MLB API: si todos los bloques quedaron en defaults ──────
    _DEFAULT = 50.0
    scores_cerca_default = all(
        abs(v - _DEFAULT) < 1.0 for v in [
            analysis.away_score_b1, analysis.home_score_b1,
            analysis.away_score_b2, analysis.home_score_b2,
        ]
    )
    if scores_cerca_default:
        logger.warning(
            f"[MLB API FALLBACK] {away_name} @ {home_name} — "
            f"scores B1/B2 cerca de defaults, enriqueciendo con MLB API"
        )
        analysis = _enriquecer_con_mlb_api(analysis)
        # Recalcular probabilidades después del enriquecimiento
        prob_away2, _ = calcular_probabilidad(
            analysis.away_score_b1, analysis.away_score_b2,
            analysis.away_score_b3, analysis.away_score_b4,
            away_p.is_opener)
        prob_home2, _ = calcular_probabilidad(
            analysis.home_score_b1, analysis.home_score_b2,
            analysis.home_score_b3, analysis.home_score_b4,
            home_p.is_opener)
        total2 = prob_away2 + prob_home2
        if total2 > 0:
            analysis.away_prob = round(prob_away2 / total2 * 100, 2)
            analysis.home_prob = round(100 - analysis.away_prob, 2)
        if analysis.away_prob >= analysis.home_prob:
            analysis.favorito = away_name
            analysis.prob_favorito = analysis.away_prob
        else:
            analysis.favorito = home_name
            analysis.prob_favorito = analysis.home_prob

    return analysis


# ─────────────────────────────────────────────────────────────────────────────
# ANALIZAR TODOS LOS PARTIDOS DEL DÍA
# ─────────────────────────────────────────────────────────────────────────────
def analizar_dia(game_date: str = None) -> list[GameAnalysis]:
    """
    Carga datos globales una sola vez y analiza todos los partidos del día.
    Retorna lista de GameAnalysis ordenada de mayor a menor probabilidad.
    """
    logger.info("Cargando datos globales (Savant, B-Ref, Odds API)...")

    fg_pitchers = fg.get_pitcher_stats()
    fg_batting  = fg.get_team_batting()
    fg_bullpen  = fg.get_bullpen_war()
    odds_data   = odds.get_mlb_odds() or []

    # Clima por estadio (se cachea por home_team para no llamar N veces)
    _weather_cache: dict = {}

    # Splits de B-Ref (se cachea por team_name)
    _splits_cache: dict = {}

    # Pitagórico real desde MLB Stats API standings (reemplaza fg_baseruns)
    _standings = mlb.get_standings()
    pythagorean_records = mlb.parse_pythagorean(_standings) if _standings else {}

    schedule = mlb.get_schedule(game_date)
    if not schedule:
        logger.error("No se pudo obtener el calendario MLB")
        return []

    resultados = []
    dates = schedule.get("dates", [])
    if not dates:
        logger.info("Sin partidos programados para hoy")
        return []

    # Recopilar todos los juegos de todos los dates devueltos (la API a veces
    # agrupa varios días si se pide sin fecha explícita o hay dobleheaders).
    # Filtramos SOLO los de la fecha objetivo para no analizar partidos de mañana.
    if not game_date:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        game_date = _dt.now(_tz(_td(hours=-6))).strftime("%Y-%m-%d")
    fecha_objetivo = game_date
    games_raw = []
    for d in dates:
        for g in d.get("games", []):
            games_raw.append(g)

    # ── Filtro 1: incluir la fecha objetivo y, por diferencia horaria, la fecha siguiente ────────
    from datetime import datetime, timedelta
    # La API devuelve 'gameDate' en UTC. Si el juego comienza después de la medianoche UTC
    # pero aún es el mismo día en la zona horaria local (ej. -6 h), el "YYYY‑MM‑DD" será
    # la fecha siguiente. Por eso aceptamos tanto la fecha objetivo como su día siguiente.
    fecha_dt = datetime.strptime(fecha_objetivo, "%Y-%m-%d")
    fecha_siguiente = (fecha_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    fechas_aceptadas = {fecha_objetivo, fecha_siguiente}
    games_fecha = [
        g for g in games_raw
        if g.get("gameDate", "")[:10] in fechas_aceptadas
    ]
    if len(games_fecha) < len(games_raw):
        omitidos = len(games_raw) - len(games_fecha)
        logger.info(
            f"Filtro fecha: {omitidos} partido(s) de otra/fecha descartados "
            f"(se analizan fechas {fecha_objetivo} y {fecha_siguiente})"
        )

    # ── Filtro 2: descartar pospuestos / cancelados ───────────────────────────
    # MLB API reporta: detailedState = "Postponed" | "Cancelled" | "Suspended"
    ESTADOS_NO_JUGABLES = {"postponed", "cancelled", "canceled", "suspended"}
    games = []
    for g in games_fecha:
        estado = g.get("status", {}).get("detailedState", "").lower()
        if any(s in estado for s in ESTADOS_NO_JUGABLES):
            pk = g.get("gamePk")
            at = g.get("teams", {}).get("away", {}).get("team", {}).get("name", "?")
            ht = g.get("teams", {}).get("home", {}).get("team", {}).get("name", "?")
            logger.warning(
                f"Partido {pk} ({at} @ {ht}) descartado — estado: '{estado}'"
            )
        else:
            games.append(g)

    if not games:
        logger.info(f"Sin partidos jugables para {fecha_objetivo}")
        return []

    logger.info(f"Analizando {len(games)} partidos para {fecha_objetivo}...")

    for game in games:
        try:
            analysis = analizar_partido(
                game, fg_pitchers, fg_batting,
                fg_bullpen, pythagorean_records, odds_data,
                weather_cache=_weather_cache,
                splits_cache=_splits_cache
            )
            if analysis:
                resultados.append(analysis)
            else:
                # Agregar juego sin análisis para que siempre quede en el CSV
                teams = game.get("teams", {})
                away_info = teams.get("away", {}).get("team", {})
                home_info = teams.get("home", {}).get("team", {})
                raw_dt = game.get("gameDate", "")
                try:
                    utc_dt_fb = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                    local_tz_fb = timezone(timedelta(hours=-6))
                    local_dt_fb = utc_dt_fb.astimezone(local_tz_fb)
                    fb_date = local_dt_fb.strftime("%Y-%m-%d")
                except Exception:
                    fb_date = raw_dt[:10]
                fallback = GameAnalysis(
                    game_pk=game.get("gamePk", 0),
                    game_date=fb_date,
                    game_datetime=raw_dt,
                    away_team=away_info.get("name", "TBD"),
                    home_team=home_info.get("name", "TBD"),
                    prob_favorito=50.0,
                    favorito=away_info.get("name", "TBD"),
                    senal_moneyline="NO APOSTAR",
                    nivel_certidumbre="SIN DATOS",
                    fuentes=["Sin datos disponibles"],
                )
                resultados.append(fallback)
                logger.warning(f"Juego sin análisis completo: {fallback.away_team} @ {fallback.home_team} — guardado con valores por defecto")
        except Exception as e:
            logger.error(f"Error analizando partido {game.get('gamePk')}: {e}")
            # Agregar juego con error para que siempre quede en el CSV
            teams = game.get("teams", {})
            away_info = teams.get("away", {}).get("team", {})
            home_info = teams.get("home", {}).get("team", {})
            raw_dt = game.get("gameDate", "")
            fallback = GameAnalysis(
                game_pk=game.get("gamePk", 0),
                game_date=raw_dt[:10],
                game_datetime=raw_dt,
                away_team=away_info.get("name", "TBD"),
                home_team=home_info.get("name", "TBD"),
                prob_favorito=50.0,
                favorito=away_info.get("name", "TBD"),
                senal_moneyline="NO APOSTAR",
                nivel_certidumbre="SIN DATOS",
                fuentes=[f"Error: {e}"],
            )
            resultados.append(fallback)

    # Ordenar por probabilidad del favorito (mayor primero)
    resultados.sort(key=lambda x: x.prob_favorito, reverse=True)

    # ── Marcar Top 3 selecciones del día ──────────────────────────────
    # Criterio de selección (en orden de prioridad):
    #   1. Partidos con es_valor=True (tríada completa)
    #   2. Partidos con odds_mercado disponible (podemos comparar)
    #   3. Mayor prob_favorito
    # Solo se marcan si prob_favorito > PROB_MINIMA_SEÑAL
    candidatos_top = [
        a for a in resultados
        if a.prob_favorito > config.PROB_MINIMA_SEÑAL
    ]
    # Ordenar: valor primero, luego con odds, luego por prob
    candidatos_top.sort(
        key=lambda a: (a.es_valor, a.odds_mercado is not None, a.prob_favorito),
        reverse=True
    )
    for i, a in enumerate(candidatos_top[:3]):
        a.es_top3 = True
        a.top3_rank = i + 1
        logger.info(
            f"TOP {i+1}: {a.favorito} ({a.prob_favorito:.1f}%) "
            f"valor={a.es_valor} odds={'si' if a.odds_mercado else 'no'}"
        )

    return resultados


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN AUXILIAR — usa MLB Stats API como fuente primaria de datos reales
# Se llama desde analizar_partido cuando Savant/B-Ref retornan None
# ─────────────────────────────────────────────────────────────────────────────
def _enriquecer_con_mlb_api(analysis: "GameAnalysis") -> "GameAnalysis":
    """
    Cuando Savant/B-Ref fallan, obtiene ERA/WHIP/IP del lanzador y
    OPS/AVG del equipo directamente desde MLB Stats API.
    Convierte esos valores a scores equivalentes de los 4 bloques.
    """
    from api_client import mlb as mlb_client

    # ── Bloque 1: pitcher stats desde MLB API
    for lado in [("away", analysis.away_pitcher, "away_score_b1"),
                 ("home", analysis.home_pitcher, "home_score_b1")]:
        _, pitcher, score_attr = lado
        if not pitcher or not pitcher.player_id:
            continue
        stats = mlb_client.get_pitcher_stats_mlb(pitcher.player_id)
        if not stats:
            continue
        pitcher.ip = stats["ip"]
        # Convertir ERA a score (ERA 2.0=100, ERA 6.0=0)
        era_score  = max(0, min(100, (6.0 - stats["era"]) / 4.0 * 100))
        # K/9 - BB/9 como proxy de K%-BB%
        kbb_score  = max(0, min(100, (stats["so_per9"] - stats["bb_per9"] + 2) / 12 * 100))
        # BABIP
        babip_adj  = 0
        if stats["babip"] < 0.260:
            babip_adj = 5
        elif stats["babip"] > 0.340:
            babip_adj = -5
        new_score = era_score * 0.6 + kbb_score * 0.4 + babip_adj
        new_score = max(0, min(100, new_score))
        setattr(analysis, score_attr, round(new_score, 2))
        if pitcher.ip < config.IP_MINIMAS_TEMPORADA:
            pitcher.penalizacion += config.PENALIZACION_IP_PCT
        logger.info(f"MLB API pitcher [{pitcher.name}]: ERA={stats['era']} → score={new_score:.1f}")

    # ── Bloque 2: team batting desde MLB API
    games = mlb_client.get_schedule()
    if not games:
        return analysis
    dates = games.get("dates", [])
    if not dates:
        return analysis

    team_ids = {}
    for game in dates[0].get("games", []):
        try:
            pk = game["gamePk"]
            if pk != analysis.game_pk:
                continue
            team_ids["away"] = game["teams"]["away"]["team"]["id"]
            team_ids["home"] = game["teams"]["home"]["team"]["id"]
        except Exception:
            pass

    for lado, attr in [("away", "away_score_b2"), ("home", "home_score_b2")]:
        tid = team_ids.get(lado)
        if not tid:
            continue
        ts = mlb_client.get_team_stats_mlb(tid)
        if not ts:
            continue
        # OPS rango típico 0.600-0.900 → normalizar a 0-100
        ops_score = max(0, min(100, (ts["ops"] - 0.600) / 0.300 * 100))
        setattr(analysis, attr, round(ops_score, 2))
        logger.info(f"MLB API batting [{lado}]: OPS={ts['ops']} → score={ops_score:.1f}")

    # ── Bloque 3: team pitching (proxy bullpen) desde MLB API
    for lado, attr in [("away", "away_score_b3"), ("home", "home_score_b3")]:
        tid = team_ids.get(lado)
        if not tid:
            continue
        tp = mlb_client.get_team_pitching_mlb(tid)
        if not tp:
            continue
        # ERA bullpen proxy: ERA 3.0=100, ERA 6.0=0
        era_score = max(0, min(100, (6.0 - tp["era"]) / 3.0 * 100))
        # Save% como proxy de salud del bullpen
        total_op = tp["saves"] + tp["blownSaves"]
        save_pct  = (tp["saves"] / total_op * 100) if total_op > 0 else 70
        bp_score  = era_score * 0.7 + save_pct * 0.3
        setattr(analysis, attr, round(min(100, bp_score), 2))
        logger.info(f"MLB API bullpen [{lado}]: ERA={tp['era']} → score={bp_score:.1f}")

    return analysis
