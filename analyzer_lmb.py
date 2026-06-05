"""
LMB Analyzer — Metodologia 5 Bloques (sin Statcast)
B1: Pitcheo (25%) — ERA, WHIP, SO/BB, HR/9
B2: Ofensiva (25%) — AVG, OPS, HR, R, SB
B3: Bullpen (15%) — estimado
B4: Eficiencia (10%) — Run differential
B5: Forma + H2H (25%) — ultimos 10, enfrentamientos directos
Usa calendario REAL de MLB StatsAPI (sportId=23) + stats BR Register.
"""

import logging
from datetime import date, datetime, timezone, timedelta

import config
from api_client_lmb import LMBClientBR

logger = logging.getLogger(__name__)

lmb_client = LMBClientBR()

API_TO_BR_TEAM = {
    "Tecos de los Dos Laredos": "Tecolotes de los Dos Laredos",
    "Algodoneros Union Laguna": "Algodoneros de Union Laguna",
    "Acereros del Norte": "Acereros de Monclova",
}

MT_TZ = timezone(timedelta(hours=-6))


def _normalize_team(api_name: str) -> str:
    return API_TO_BR_TEAM.get(api_name, api_name)


def _parse_utc_to_mt(utc_str: str) -> str:
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        mt = dt.astimezone(MT_TZ)
        return mt.strftime("%H:%M")
    except Exception:
        return "?"


def _score_era(era_str: str) -> float:
    try:
        era = float(era_str)
    except (ValueError, TypeError):
        return 50.0
    if era <= 2.50:
        return 95
    if era <= 3.00:
        return 85
    if era <= 3.50:
        return 75
    if era <= 4.00:
        return 65
    if era <= 4.50:
        return 55
    if era <= 5.00:
        return 45
    if era <= 5.50:
        return 35
    if era <= 6.00:
        return 25
    return 15


def _score_whip(whip_str: str) -> float:
    try:
        whip = float(whip_str)
    except (ValueError, TypeError):
        return 50.0
    if whip <= 1.10:
        return 95
    if whip <= 1.20:
        return 85
    if whip <= 1.30:
        return 75
    if whip <= 1.40:
        return 65
    if whip <= 1.50:
        return 55
    if whip <= 1.60:
        return 45
    if whip <= 1.70:
        return 35
    if whip <= 1.80:
        return 25
    return 15


def _score_so_bb(so_str: str, bb_str: str) -> float:
    try:
        so = float(so_str) if so_str else 0
        bb = float(bb_str) if bb_str else 1
        ratio = so / max(bb, 0.1)
    except (ValueError, TypeError):
        return 50.0
    if ratio >= 3.0:
        return 95
    if ratio >= 2.5:
        return 85
    if ratio >= 2.0:
        return 75
    if ratio >= 1.5:
        return 60
    if ratio >= 1.0:
        return 45
    return 25


def _score_hr9(hr_str: str, ip_str: str) -> float:
    try:
        hr = float(hr_str) if hr_str else 0
        ip = float(ip_str) if ip_str else 1
        hr9 = hr / max(ip, 1.0) * 9
    except (ValueError, TypeError):
        return 50.0
    if hr9 <= 0.5:
        return 95
    if hr9 <= 0.8:
        return 85
    if hr9 <= 1.0:
        return 75
    if hr9 <= 1.2:
        return 65
    if hr9 <= 1.5:
        return 50
    if hr9 <= 2.0:
        return 35
    return 20


def _score_avg(avg_str: str) -> float:
    try:
        avg = float(avg_str)
    except (ValueError, TypeError):
        return 50.0
    if avg >= 0.320:
        return 95
    if avg >= 0.300:
        return 85
    if avg >= 0.280:
        return 75
    if avg >= 0.260:
        return 65
    if avg >= 0.250:
        return 55
    if avg >= 0.240:
        return 45
    if avg >= 0.230:
        return 35
    return 20


def _score_ops(ops_str: str) -> float:
    try:
        ops = float(ops_str)
    except (ValueError, TypeError):
        return 50.0
    if ops >= 0.900:
        return 95
    if ops >= 0.850:
        return 85
    if ops >= 0.800:
        return 75
    if ops >= 0.750:
        return 65
    if ops >= 0.700:
        return 55
    if ops >= 0.650:
        return 45
    if ops >= 0.600:
        return 35
    return 20


def _score_hr(hr_str: str) -> float:
    try:
        hr = float(hr_str)
    except (ValueError, TypeError):
        return 50.0
    if hr >= 30:
        return 95
    if hr >= 25:
        return 85
    if hr >= 20:
        return 75
    if hr >= 15:
        return 65
    if hr >= 10:
        return 55
    if hr >= 5:
        return 40
    return 25


def _score_runs(r_str: str) -> float:
    try:
        r = float(r_str)
    except (ValueError, TypeError):
        return 50.0
    if r >= 400:
        return 95
    if r >= 350:
        return 85
    if r >= 300:
        return 75
    if r >= 250:
        return 65
    if r >= 200:
        return 55
    if r >= 150:
        return 40
    return 25


def _score_sb(sb_str: str) -> float:
    try:
        sb = float(sb_str)
    except (ValueError, TypeError):
        return 50.0
    if sb >= 60:
        return 95
    if sb >= 40:
        return 80
    if sb >= 25:
        return 65
    if sb >= 15:
        return 55
    if sb >= 5:
        return 40
    return 25


def _score_fip(fip: float) -> float:
    if fip <= 3.0:
        return 95
    if fip <= 3.5:
        return 85
    if fip <= 4.0:
        return 75
    if fip <= 4.5:
        return 65
    if fip <= 5.0:
        return 55
    if fip <= 5.5:
        return 45
    if fip <= 6.0:
        return 35
    if fip <= 6.5:
        return 25
    return 15


def _score_kbb(kbb: float) -> float:
    if kbb >= 3.0:
        return 95
    if kbb >= 2.5:
        return 85
    if kbb >= 2.0:
        return 70
    if kbb >= 1.5:
        return 55
    if kbb >= 1.0:
        return 40
    return 25


def _score_wrc(wrc: float) -> float:
    if wrc >= 250:
        return 95
    if wrc >= 200:
        return 80
    if wrc >= 150:
        return 65
    if wrc >= 100:
        return 50
    if wrc >= 75:
        return 35
    return 20


def _calcular_bloque1(pitching: dict) -> float:
    if not pitching:
        return 50.0
    s_era = _score_era(pitching.get("ERA", "0"))
    s_whip = _score_whip(pitching.get("WHIP", "0"))
    s_sobb = _score_so_bb(pitching.get("SO", "0"), pitching.get("BB", "0"))
    s_hr9 = _score_hr9(pitching.get("HR", "0"), pitching.get("IP", "0"))
    return s_era * 0.35 + s_whip * 0.30 + s_sobb * 0.20 + s_hr9 * 0.15


def _calcular_bloque2(batting: dict) -> float:
    if not batting:
        return 50.0
    s_avg = _score_avg(batting.get("BA", batting.get("AVG", "0")))
    s_ops = _score_ops(batting.get("OPS", "0"))
    s_hr = _score_hr(batting.get("HR", "0"))
    s_r = _score_runs(batting.get("R", "0"))
    s_sb = _score_sb(batting.get("SB", "0"))
    return s_avg * 0.25 + s_ops * 0.30 + s_hr * 0.20 + s_r * 0.15 + s_sb * 0.10


def _calcular_bloque3(pitching: dict) -> float:
    if not pitching:
        return 50.0
    s_era = _score_era(pitching.get("ERA", "0"))
    s_whip = _score_whip(pitching.get("WHIP", "0"))
    return s_era * 0.5 + s_whip * 0.5


def _calcular_bloque4(record: dict) -> float:
    if not record:
        return 50.0
    rs = record.get("rs", 0)
    ra = record.get("ra", 0)
    diff = rs - ra
    if diff >= 100:
        return 90
    if diff >= 50:
        return 80
    if diff >= 25:
        return 70
    if diff >= 10:
        return 60
    if diff >= 0:
        return 55
    if diff >= -10:
        return 45
    if diff >= -25:
        return 35
    if diff >= -50:
        return 25
    return 15


def _calcular_bloque5(streak_score: float = 50.0) -> float:
    """B5 Forma: score basado en streak. 0-100."""
    return streak_score


def _form_to_score(wins: int, total: int = 10) -> float:
    """Convierte récord últimos N juegos a score B5 (0-100)."""
    if total <= 0:
        return 50.0
    pct = wins / total
    if pct >= 0.80: return 90
    if pct >= 0.70: return 80
    if pct >= 0.60: return 70
    if pct >= 0.50: return 55
    if pct >= 0.40: return 40
    if pct >= 0.30: return 25
    return 10


def _generar_descripcion_lmb(away: str, home: str, favorito: str, prob: float,
                              s1a: float, s1h: float, s2a: float, s2h: float,
                              s3a: float, s3h: float, s4a: float, s4h: float) -> str:
    lines = [
        f"Fav: {favorito} ({prob:.1f}%)",
        f"B1 Pit: {away}={s1a:.1f} | {home}={s1h:.1f}",
        f"B2 Of: {away}={s2a:.1f} | {home}={s2h:.1f}",
        f"B3 Bp: {away}={s3a:.1f} | {home}={s3h:.1f}",
        f"B4 Ef: {away}={s4a:.1f} | {home}={s4h:.1f}",
    ]
    return " || ".join(lines)


def _get_stats_for_team(br_name: str, all_stats: dict):
    """Busca stats de un equipo en all_stats (con fuzzy match)."""
    best = None
    best_score = 0
    t_lower = br_name.lower()
    for key in all_stats:
        score = 0
        k_lower = key.lower()
        if t_lower == k_lower:
            score = 100
        elif t_lower in k_lower or k_lower in t_lower:
            score = 50
        if score > best_score:
            best_score = score
            best = key

    if not best:
        return {}, {}, {}

    data = all_stats[best]
    batting = data.get("batting", {})
    pitching = data.get("pitching", {})
    record = {}
    if pitching:
        try:
            record["w"] = int(pitching.get("W", 0))
            record["l"] = int(pitching.get("L", 0))
        except (ValueError, TypeError):
            pass
        try:
            record["rs"] = int(batting.get("R", 0)) if batting else 0
            record["ra"] = int(pitching.get("R", 0)) if pitching else 0
        except (ValueError, TypeError):
            pass
    return batting, pitching, record


def _safe_float(val, default=0.0):
    """Convierte a float, devuelve default si falla."""
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    try:
        return int(val) if val else default
    except (ValueError, TypeError):
        return default


def _compute_league_averages(all_stats: dict) -> dict:
    """Calcula promedios de liga desde la fila 'League Totals' (o suma de equipos)."""
    lg = {}
    # Intentar obtener totals directamente
    lt_p = all_stats.get("League Totals", {}).get("pitching", {})
    lt_b = all_stats.get("League Totals", {}).get("batting", {})

    if lt_p:
        so = _safe_int(lt_p.get("SO"))
        bb = _safe_int(lt_p.get("BB"))
        hr = _safe_int(lt_p.get("HR"))
        hbp = _safe_int(lt_p.get("HBP"))
        ip_str = lt_p.get("IP", "0")
        ip = _safe_float(ip_str)
        lg["era"] = _safe_float(lt_p.get("ERA"))
        lg["fip_component"] = (13*hr + 3*(bb + hbp) - 2*so) / ip if ip > 0 else 0
    else:
        # Sumar de todos los equipos
        so = bb = hr = hbp = 0
        ip = 0.0
        era_sum = 0
        count = 0
        for team, data in all_stats.items():
            p = data.get("pitching", {})
            if not p or "League" in team:
                continue
            so += _safe_int(p.get("SO"))
            bb += _safe_int(p.get("BB"))
            hr += _safe_int(p.get("HR"))
            hbp += _safe_int(p.get("HBP"))
            ip += _safe_float(p.get("IP"))
            era_sum += _safe_float(p.get("ERA"))
            count += 1
        lg["era"] = era_sum / count if count else 5.31
        lg["fip_component"] = (13*hr + 3*(bb + hbp) - 2*so) / ip if ip > 0 else 0

    lg["cFIP"] = lg["era"] - lg["fip_component"]

    # wOBA de liga desde batting
    if lt_b:
        lg["pa"] = _safe_int(lt_b.get("PA"))
        lg["r"] = _safe_int(lt_b.get("R"))
        h = _safe_int(lt_b.get("H"))
        d2 = _safe_int(lt_b.get("2B"))
        d3 = _safe_int(lt_b.get("3B"))
        hr_b = _safe_int(lt_b.get("HR"))
        bb_b = _safe_int(lt_b.get("BB"))
        hbp_b = _safe_int(lt_b.get("HBP"))
        ibb = _safe_int(lt_b.get("IBB"))
        s1 = h - d2 - d3 - hr_b
        woba_num = 0.69*(bb_b - ibb) + 0.72*hbp_b + 0.89*s1 + 1.27*d2 + 1.62*d3 + 2.10*hr_b
        woba_den = lg["pa"] - ibb
        lg["woba"] = woba_num / woba_den if woba_den > 0 else 0.350
    else:
        # Sumar de todos los equipos
        pa_tot = r_tot = h_tot = d2_tot = d3_tot = hr_tot = 0
        bb_tot = hbp_tot = ibb_tot = 0
        for team, data in all_stats.items():
            b = data.get("batting", {})
            if not b or "League" in team:
                continue
            pa_tot += _safe_int(b.get("PA"))
            r_tot += _safe_int(b.get("R"))
            h_tot += _safe_int(b.get("H"))
            d2_tot += _safe_int(b.get("2B"))
            d3_tot += _safe_int(b.get("3B"))
            hr_tot += _safe_int(b.get("HR"))
            bb_tot += _safe_int(b.get("BB"))
            hbp_tot += _safe_int(b.get("HBP"))
            ibb_tot += _safe_int(b.get("IBB"))
        lg["pa"] = pa_tot
        lg["r"] = r_tot
        s1 = h_tot - d2_tot - d3_tot - hr_tot
        woba_num = 0.69*(bb_tot - ibb_tot) + 0.72*hbp_tot + 0.89*s1 + 1.27*d2_tot + 1.62*d3_tot + 2.10*hr_tot
        woba_den = pa_tot - ibb_tot
        lg["woba"] = woba_num / woba_den if woba_den > 0 else 0.350

    return lg


def _compute_team_fip(pitching: dict, cFIP: float) -> float:
    """FIP = (13*HR + 3*(BB+HBP) - 2*SO) / IP + cFIP"""
    hr = _safe_int(pitching.get("HR"))
    bb = _safe_int(pitching.get("BB"))
    hbp = _safe_int(pitching.get("HBP"))
    so = _safe_int(pitching.get("SO"))
    ip = _safe_float(pitching.get("IP"))
    if ip <= 0:
        return 0
    return (13*hr + 3*(bb + hbp) - 2*so) / ip + cFIP


def _compute_pitcher_fip(pdata: dict, cFIP: float) -> float:
    """FIP = (13*HR + 3*(BB+HBP) - 2*SO) / IP + cFIP (desde pitcher individual)"""
    hr = pdata.get("hr") or 0
    bb = pdata.get("bb") or 0
    so = pdata.get("so") or 0
    ip = pdata.get("ip") or 0
    hbp = pdata.get("hbp") or 0
    if ip <= 0:
        return 0
    return (13*hr + 3*(bb + hbp) - 2*so) / ip + cFIP


def _compute_team_wrc(batting: dict, lg: dict) -> float:
    """wRC aproximado desde wOBA. wRC = wRAA + (lg_R/lg_PA)*PA"""
    pa = _safe_int(batting.get("PA"))
    if pa <= 0:
        return 0
    h = _safe_int(batting.get("H"))
    d2 = _safe_int(batting.get("2B"))
    d3 = _safe_int(batting.get("3B"))
    hr = _safe_int(batting.get("HR"))
    bb = _safe_int(batting.get("BB"))
    hbp = _safe_int(batting.get("HBP"))
    ibb = _safe_int(batting.get("IBB"))
    s1 = h - d2 - d3 - hr
    woba_num = 0.69*(bb - ibb) + 0.72*hbp + 0.89*s1 + 1.27*d2 + 1.62*d3 + 2.10*hr
    woba_den = pa - ibb
    woba = woba_num / woba_den if woba_den > 0 else 0
    lg_woba = lg.get("woba", 0.350)
    lg_r = lg.get("r", 0)
    lg_pa = lg.get("pa", 1)
    wRAA = ((woba - lg_woba) / 1.15) * pa
    wRC = wRAA + (lg_r / lg_pa) * pa
    return round(wRC, 0)


def analizar_lmb_dia(fecha: str = None) -> list[dict]:
    """
    Ejecuta analisis LMB usando calendario REAL de MLB StatsAPI.
    1. Obtener schedule real (sportId=23)
    2. Obtener stats de equipos via BR Register
    3. Aplicar modelo 5 bloques a cada juego real
    Retorna lista de dicts listos para guardar en CSV.
    """
    if not fecha:
        fecha = date.today().strftime("%Y-%m-%d")

    logger.info("=== Analisis LMB con calendario REAL ===")

    # Convert YYYY-MM-DD -> MM/DD/YYYY para la API
    parts = fecha.split("-")
    api_date = f"{parts[1]}/{parts[2]}/{parts[0]}" if len(parts) == 3 else fecha
    schedule = lmb_client.get_real_schedule(api_date)
    if not schedule:
        logger.warning("No se pudo obtener schedule real LMB")
        return []

    logger.info(f"LMB schedule real: {len(schedule)} juegos")

    all_stats = lmb_client.get_all_team_stats()
    if not all_stats:
        logger.warning("No se pudieron obtener stats BR de equipos LMB")
        return []

    lg_avg = _compute_league_averages(all_stats)
    logger.info(f"LMB lg: ERA={lg_avg['era']:.2f} cFIP={lg_avg['cFIP']:.2f} wOBA={lg_avg['woba']:.3f}")

    # Fetch forma real (últimos 10 juegos) para B5
    form_data = lmb_client.get_team_form(fecha)
    if form_data:
        logger.info(f"Forma LMB: {len(form_data)} equipos")

    # Fetch pitchers individuales para FIP/KBB por abridor
    pitcher_db = lmb_client.get_individual_pitcher_stats()
    if pitcher_db:
        logger.info(f"Pitchers individuales cargados: {len(pitcher_db)}")

    analyses = []
    for game in schedule:
        away_api = game["away_team"]
        home_api = game["home_team"]
        away_br = _normalize_team(away_api)
        home_br = _normalize_team(home_api)

        away_b, away_p, away_r = _get_stats_for_team(away_br, all_stats)
        home_b, home_p, home_r = _get_stats_for_team(home_br, all_stats)

        if not away_p and not away_b:
            logger.warning(f"Sin stats BR para: {away_api} -> '{away_br}' — usando defaults")
        if not home_p and not home_b:
            logger.warning(f"Sin stats BR para: {home_api} -> '{home_br}' — usando defaults")

        s1a = _calcular_bloque1(away_p)
        s1h = _calcular_bloque1(home_p)
        s2a = _calcular_bloque2(away_b)
        s2h = _calcular_bloque2(home_b)
        s3a = _calcular_bloque3(away_p)
        s3h = _calcular_bloque3(home_p)
        s4a = _calcular_bloque4(away_r)
        s4h = _calcular_bloque4(home_r)
        # B5: Forma real (últimos 10 juegos)
        s5a = 50.0
        s5h = 50.0
        fd_a = (form_data or {}).get(away_api, {})
        fd_h = (form_data or {}).get(home_api, {})
        if fd_a and fd_h:
            s5a = _form_to_score(fd_a.get("wins", 0))
            s5h = _form_to_score(fd_h.get("wins", 0))
            s5 = (s5a + s5h) / 2
            form_desc = f"{fd_a['record']} ({fd_a['streak_type'][0].upper()}{fd_a['streak_number']}) / {fd_h['record']} ({fd_h['streak_type'][0].upper()}{fd_h['streak_number']})"
        elif fd_a:
            s5a = _form_to_score(fd_a.get("wins", 0))
            s5 = (s5a + 50.0) / 2
            form_desc = f"{fd_a['record']} ({fd_a['streak_type'][0].upper()}{fd_a['streak_number']}) / N/D"
        elif fd_h:
            s5h = _form_to_score(fd_h.get("wins", 0))
            s5 = (50.0 + s5h) / 2
            form_desc = f"N/D / {fd_h['record']} ({fd_h['streak_type'][0].upper()}{fd_h['streak_number']})"
        else:
            s5 = 50.0
            form_desc = "N/D"

        w1 = config.PESO_LMB_PITCHEO / 100.0
        w2 = config.PESO_LMB_OFENSIVA / 100.0
        w3 = config.PESO_LMB_BULLPEN / 100.0
        w4 = config.PESO_LMB_EFICIENCIA / 100.0
        w5 = config.PESO_LMB_FORMA / 100.0

        total_away_raw = s1a * w1 + s2a * w2 + s3a * w3 + s4a * w4 + s5 * w5
        total_home_raw = s1h * w1 + s2h * w2 + s3h * w3 + s4h * w4 + s5 * w5

        # Metricas avanzadas
        abridor_a = game.get("away_pitcher_name") or "?"
        abridor_h = game.get("home_pitcher_name") or "?"
        pa_data = pitcher_db.get(abridor_a) if abridor_a != "?" else None
        ph_data = pitcher_db.get(abridor_h) if abridor_h != "?" else None
        if pa_data:
            fip_a = _compute_pitcher_fip(pa_data, lg_avg["cFIP"])
            kbb_a = pa_data.get("kbb") or _safe_float((away_p or {}).get("SO/W"))
        elif away_p:
            fip_a = _compute_team_fip(away_p, lg_avg["cFIP"])
            kbb_a = _safe_float(away_p.get("SO/W"))
        else:
            fip_a = lg_avg["cFIP"]
            kbb_a = 0
        if ph_data:
            fip_h = _compute_pitcher_fip(ph_data, lg_avg["cFIP"])
            kbb_h = ph_data.get("kbb") or _safe_float((home_p or {}).get("SO/W"))
        elif home_p:
            fip_h = _compute_team_fip(home_p, lg_avg["cFIP"])
            kbb_h = _safe_float(home_p.get("SO/W"))
        else:
            fip_h = lg_avg["cFIP"]
            kbb_h = 0
        wrc_a = _compute_team_wrc(away_b, lg_avg) if away_b else 100
        wrc_h = _compute_team_wrc(home_b, lg_avg) if home_b else 100

        # Enriquecer bloques con metricas avanzadas
        s_fip_a = _score_fip(fip_a)
        s_fip_h = _score_fip(fip_h)
        s_kbb_a = _score_kbb(kbb_a)
        s_kbb_h = _score_kbb(kbb_h)
        s_wrc_a = _score_wrc(wrc_a)
        s_wrc_h = _score_wrc(wrc_h)

        s1a_enr = s1a * 0.50 + s_fip_a * 0.30 + s_kbb_a * 0.20
        s1h_enr = s1h * 0.50 + s_fip_h * 0.30 + s_kbb_h * 0.20
        s2a_enr = s2a * 0.70 + s_wrc_a * 0.30
        s2h_enr = s2h * 0.70 + s_wrc_h * 0.30

        total_away = s1a_enr * w1 + s2a_enr * w2 + s3a * w3 + s4a * w4 + s5 * w5
        total_home = s1h_enr * w1 + s2h_enr * w2 + s3h * w3 + s4h * w4 + s5 * w5

        favorito = away_api if total_away >= total_home else home_api
        prob_fav = max(total_away, total_home)

        factor = "Alto" if abs(total_away - total_home) < 5 else "Medio"
        factor = "Bajo" if abs(total_away - total_home) > 15 else factor

        game_time_mt = _parse_utc_to_mt(game["game_date_utc"])

        # ── Trigger Moneyline
        senal = "NO APOSTAR"
        nivel_cert = "BAJA"
        try:
            from analyzer import calcular_trigger
            # LMB: sin datos de splits ni pitch_hand por ahora → defaults
            senal, nivel_cert, _ = calcular_trigger(
                fip_a, fip_a, kbb_a,  # xFIP = FIP (LMB no tiene xFIP separado)
                fip_h, fip_h, kbb_h,
                wrc_a, wrc_h,
                liga="LMB",
            )
        except Exception:
            pass

        desc_bloques = _generar_descripcion_lmb(
            away_api, home_api, favorito, prob_fav,
            s1a, s1h, s2a, s2h, s3a, s3h, s4a, s4h,
        )

        desc = (f"{desc_bloques} || P: {abridor_a} vs {abridor_h} "
                f"| FIP: {fip_a:.2f}/{fip_h:.2f} K/BB: {kbb_a:.2f}/{kbb_h:.2f}"
                f" Forma: {form_desc}")

        a = {
            "game_pk": game["game_pk"],
            "game_date": fecha,
            "game_time": game_time_mt,
            "away_team": away_api,
            "home_team": home_api,
            "away_pitcher": abridor_a,
            "home_pitcher": abridor_h,
            "favorito": favorito,
            "prob_favorito": round(prob_fav, 1),
            "odds_mercado": None,
            "es_valor": False,
            "factor_riesgo": factor,
            "score_b1_away": round(s1a, 1),
            "score_b1_home": round(s1h, 1),
            "score_b2_away": round(s2a, 1),
            "score_b2_home": round(s2h, 1),
            "score_b3_away": round(s3a, 1),
            "score_b3_home": round(s3h, 1),
            "score_b4_away": round(s4a, 1),
            "score_b4_home": round(s4h, 1),
            "fip_away": round(fip_a, 2),
            "fip_home": round(fip_h, 2),
            "xfip_away": round(fip_a, 2),
            "xfip_home": round(fip_h, 2),
            "kbb_away": round(kbb_a, 2),
            "kbb_home": round(kbb_h, 2),
            "wrc_away": wrc_a,
            "wrc_home": wrc_h,
            "war_bullpen_away": None,
            "war_bullpen_home": None,
            "senal_moneyline": senal,
            "nivel_certidumbre": nivel_cert,
            "descripcion": desc,
        }
        analyses.append(a)
        logger.info(f"LMB real: {away_api} vs {home_api} -> {favorito} ({prob_fav:.1f}%) [{game_time_mt}]")

    return analyses
