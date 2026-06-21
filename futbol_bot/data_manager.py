import hashlib
import json
import logging
import os
from datetime import datetime

import pandas as pd

import config

logger = logging.getLogger(__name__)

COLUMNAS = [
    "id_partido", "liga", "fecha_hora",
    "local", "visitante",
    "xg_local", "xg_visit", "xg_total", "diff_xg",
    "senal_ah0", "confianza_ah0",
    "senal_ou25", "confianza_ou25",
    "xcorner_local", "xcorner_visitante", "xcorner_total",
    "senal_corners", "confianza_corners",
    "resultado", "resultado_ah0", "resultado_ou25", "resultado_corners",
    "marcador_final", "fecha_actualizacion",
    "fecha_partido", "hora_partido",
    "llm_ah0", "llm_ou25", "llm_corners", "llm_porque",
    "llm_favorito", "llm_ir_favorito", "llm_goles", "llm_corners_est",
    "llm_tiros_porteria", "llm_lineas", "llm_resultado",
]


def cargar_partidos_xlsx() -> list[dict]:
    """Lee el xlsx de apuestas y retorna lista de dicts (público)."""
    return _leer_xlsx()


def _leer_xlsx() -> list[dict]:
    """Lee el xlsx y retorna lista de dicts (vacíos si no existe)."""
    if not os.path.exists(config.CSV_SOCCER_PATH):
        return []
    try:
        df = pd.read_excel(config.CSV_SOCCER_PATH, dtype=str)
        return df.to_dict("records")
    except Exception:
        return []


def _escribir_xlsx(rows: list[dict]):
    """Escribe lista de dicts a xlsx, siempre usando COLUMNAS completas."""
    df = pd.DataFrame(rows, columns=COLUMNAS).fillna("")
    df.to_excel(config.CSV_SOCCER_PATH, index=False, engine='openpyxl')


def inicializar_csv():
    path = config.CSV_SOCCER_PATH
    if not os.path.exists(path):
        df = pd.DataFrame(columns=COLUMNAS)
        df.to_excel(path, index=False, engine='openpyxl')
        logger.info(f"xlsx creado: {path}")
    else:
        try:
            existing = pd.read_excel(path, dtype=str, engine='openpyxl')
            existing_cols = set(existing.columns)
            missing = [c for c in COLUMNAS if c not in existing_cols]
            if missing:
                for c in missing:
                    existing[c] = ""
                existing.to_excel(path, index=False, engine='openpyxl')
                logger.info(f"Columnas LLM agregadas al xlsx: {missing}")
        except Exception as e:
            logger.warning(f"Error migrando xlsx: {e}")


def game_pk(liga: str, local: str, visitante: str, fecha: str = "") -> int:
    raw = hashlib.md5("|".join([liga, local, visitante]).encode()).hexdigest()
    return int(raw[:16], 16)


def guardar_analisis(analisis: list):
    from analyzer import MatchAnalysis
    from datetime import date
    inicializar_csv()
    now = datetime.now().isoformat()
    hoy = date.today()
    ids_nuevos = set(str(a.id_partido) for a in analisis)
    analisis_map = {str(a.id_partido): a for a in analisis}
    ids_existentes = set()
    rows = _leer_xlsx()

    # Merge existing rows (keep finished matches, update pending)
    nuevos = []
    existentes_map = {}
    for row in rows:
        rid = row["id_partido"]
        resultado = row.get("resultado", "pendiente")
        resultado_ah0 = row.get("resultado_ah0", "pendiente")
        resultado_ou25 = row.get("resultado_ou25", "pendiente")
        tiene_resultado = (resultado != "pendiente" or resultado_ah0 != "pendiente" or resultado_ou25 != "pendiente")
        if tiene_resultado and rid not in ids_nuevos:
            nuevos.append(row)
            ids_existentes.add(rid)
            continue
        if rid in ids_nuevos and resultado == "pendiente" and rid in analisis_map:
            a = analisis_map[rid]
            row["xg_local"] = a.proyeccion_local
            row["xg_visit"] = a.proyeccion_visitante
            row["xg_total"] = a.xg_total
            row["diff_xg"] = a.diff_xg
            es_futuro = False
            try:
                fd = date.fromisoformat(a.fecha_partido) if a.fecha_partido else hoy
                es_futuro = fd > hoy
            except Exception:
                pass
            if es_futuro:
                row["senal_ah0"] = "pendiente"
                row["confianza_ah0"] = "—  "
                row["senal_ou25"] = "pendiente"
                row["confianza_ou25"] = "—  "
            else:
                row["senal_ah0"] = a.senal_ah0
                row["confianza_ah0"] = a.confianza_ah0
                row["senal_ou25"] = a.senal_ou25
                row["confianza_ou25"] = a.confianza_ou25
            row["xcorner_local"] = a.xcorner_local
            row["xcorner_visitante"] = a.xcorner_visitante
            row["xcorner_total"] = a.xcorner_total
            row["senal_corners"] = a.senal_corners
            row["confianza_corners"] = a.confianza_corners
            row["fecha_actualizacion"] = now
        if rid not in ids_existentes:
            ids_existentes.add(rid)
            nuevos.append(row)
    rows = nuevos

    for a in analisis:
        sid = str(a.id_partido)
        if sid in ids_existentes:
            continue
        ids_existentes.add(sid)
        es_futuro = False
        try:
            fd = date.fromisoformat(a.fecha_partido) if a.fecha_partido else hoy
            es_futuro = fd > hoy
        except Exception:
            pass
        senal_ah0_final = "pendiente" if es_futuro else a.senal_ah0
        conf_ah0_final = "—  " if es_futuro else a.confianza_ah0
        senal_ou25_final = "pendiente" if es_futuro else a.senal_ou25
        conf_ou25_final = "—  " if es_futuro else a.confianza_ou25
        rows.append({
            "id_partido": sid,
            "liga": a.liga,
            "fecha_hora": now,
            "local": a.equipo_local,
            "visitante": a.equipo_visitante,
            "xg_local": a.proyeccion_local,
            "xg_visit": a.proyeccion_visitante,
            "xg_total": a.xg_total,
            "diff_xg": a.diff_xg,
            "senal_ah0": senal_ah0_final,
            "confianza_ah0": conf_ah0_final,
            "senal_ou25": senal_ou25_final,
            "confianza_ou25": conf_ou25_final,
            "xcorner_local": a.xcorner_local,
            "xcorner_visitante": a.xcorner_visitante,
            "xcorner_total": a.xcorner_total,
            "senal_corners": a.senal_corners,
            "confianza_corners": a.confianza_corners,
            "resultado": "pendiente",
            "resultado_ah0": "pendiente",
            "resultado_ou25": "pendiente",
            "resultado_corners": "pendiente",
            "marcador_final": "",
            "fecha_actualizacion": now,
            "fecha_partido": a.fecha_partido,
            "hora_partido": a.hora_partido,
        })
    _escribir_xlsx(rows)
    logger.info(f"{len(analisis)} análisis guardados (limpiados pendientes viejos)")


def guardar_mundial_csv(mundial_games: list):
    if not mundial_games:
        return
    inicializar_csv()
    now = datetime.now().isoformat()
    rows = _leer_xlsx()
    existentes = {row.get("id_partido", ""): i for i, row in enumerate(rows)}

    added = 0
    updated = 0
    for g in mundial_games:
        pk = str(game_pk("MUNDIAL", g["local"], g["visitante"], g["fecha_partido"]))
        if pk in existentes:
            idx = existentes[pk]
            if rows[idx].get("xg_local") in ("1.3", "2.6"):
                rows[idx]["xg_local"] = g.get("xg_local", 0.0)
                rows[idx]["xg_visit"] = g.get("xg_visit", 0.0)
                rows[idx]["xg_total"] = g.get("xg_total", 0.0)
                rows[idx]["diff_xg"] = g.get("diff_xg", 0.0)
                rows[idx]["fecha_actualizacion"] = now
                updated += 1
            continue
        rows.append({
            "id_partido": pk,
            "liga": "MUNDIAL",
            "fecha_hora": now,
            "local": g["local"],
            "visitante": g["visitante"],
            "xg_local": g.get("xg_local", 0.0),
            "xg_visit": g.get("xg_visit", 0.0),
            "xg_total": g.get("xg_total", 0.0),
            "diff_xg": g.get("diff_xg", 0.0),
            "senal_ah0": g.get("senal_ah0", "NO_APOSTAR"),
            "confianza_ah0": g.get("confianza_ah0", "BAJA"),
            "senal_ou25": g.get("senal_ou25", "NO_APOSTAR"),
            "confianza_ou25": g.get("confianza_ou25", "BAJA"),
            "resultado": "pendiente",
            "resultado_ah0": g.get("resultado_ah0", "pendiente"),
            "resultado_ou25": g.get("resultado_ou25", "pendiente"),
            "marcador_final": g.get("marcador_final", ""),
            "fecha_actualizacion": now,
            "fecha_partido": g["fecha_partido"],
            "hora_partido": g.get("hora_partido", ""),
        })
        added += 1

    if added or updated:
        _escribir_xlsx(rows)
        logger.info(f"Mundial: {added} nuevos, {updated} actualizados en xlsx")


def actualizar_resultados(id_partido: str, marcador: str, resultado_ah0: str, resultado_ou25: str, resultado_corners: str = "pendiente") -> bool:
    if not os.path.exists(config.CSV_SOCCER_PATH):
        return False
    rows = _leer_xlsx()
    changed = False
    for row in rows:
        if row["id_partido"] == id_partido:
            if row.get("resultado_ah0", "pendiente") == "pendiente":
                row["resultado_ah0"] = resultado_ah0
                changed = True
            if row.get("resultado_ou25", "pendiente") == "pendiente":
                row["resultado_ou25"] = resultado_ou25
                changed = True
            if row.get("resultado_corners", "pendiente") == "pendiente" and resultado_corners != "pendiente":
                row["resultado_corners"] = resultado_corners
                changed = True
            if changed:
                row["marcador_final"] = marcador
                row["fecha_actualizacion"] = datetime.now().isoformat()
                if resultado_ah0 in ("acertado", "fallido", "devuelto"):
                    row["resultado"] = resultado_ah0
            if not changed and row.get("resultado", "pendiente") == "pendiente" and resultado_ah0 == "no_apostar":
                row["resultado"] = "no_apostar"
                row["marcador_final"] = marcador
                row["fecha_actualizacion"] = datetime.now().isoformat()
                changed = True
            break
    if changed:
        _escribir_xlsx(rows)
        logger.info(f"Partido {id_partido} actualizado: AH0={resultado_ah0} O/U={resultado_ou25} Corners={resultado_corners} {marcador}")
    return changed


def guardar_llm_soccer(id_partido: str, favorito: str, ir: str, goles: str, corners, tiros_porteria: list, porque: str = "", factores: list = None, lineas: dict = None, ranking_local: str = "", ranking_visitante: str = ""):
    """Guarda los resultados del análisis LLM en el XLSX de fútbol."""
    if not os.path.exists(config.CSV_SOCCER_PATH):
        return
    rows = _leer_xlsx()
    changed = False
    tiros_json = json.dumps(tiros_porteria, ensure_ascii=False) if tiros_porteria else "[]"
    factores_json = json.dumps(factores or [], ensure_ascii=False)
    lineas_json = json.dumps(lineas or {}, ensure_ascii=False)
    for row in rows:
        if row["id_partido"] == id_partido:
            row["llm_favorito"] = favorito or ""
            row["llm_ir_favorito"] = ir or ""
            row["llm_goles"] = goles or ""
            row["llm_corners_est"] = str(corners) if corners else ""
            row["llm_tiros_porteria"] = tiros_json
            row["llm_lineas"] = lineas_json
            row["llm_porque"] = porque or ""
            row["llm_ah0"] = factores_json
            row["llm_ranking_local"] = ranking_local or ""
            row["llm_ranking_visitante"] = ranking_visitante or ""
            row["fecha_actualizacion"] = datetime.now().isoformat()
            changed = True
            break
    if changed:
        _escribir_xlsx(rows)
        logger.info(f"LLM soccer escrito en XLSX: {id_partido} → {favorito} ({ir})")


def _computar_resultado_llm_soccer(ir: str, resultado_real: str) -> str:
    """Calcula si el LLM acertó: SÍ + acertado = acertado, NO + fallido = acertado."""
    if ir not in ("SÍ", "NO") or resultado_real in ("pendiente", "no_apostar", ""):
        return "pendiente"
    if (ir == "SÍ" and resultado_real == "acertado") or (ir == "NO" and resultado_real == "fallido"):
        return "acertado"
    return "fallido"


def actualizar_llm_resultado_soccer(id_partido: str) -> bool:
    """Calcula y escribe el resultado del LLM después de que se resuelve el partido."""
    if not os.path.exists(config.CSV_SOCCER_PATH):
        return False
    rows = _leer_xlsx()
    changed = False
    for row in rows:
        if row["id_partido"] == id_partido:
            ir = row.get("llm_ir_favorito", "")
            if not ir or ir in ("N/D", ""):
                break
            # Calcular resultado del LLM basado en AH0 (la predicción principal)
            res_ah0 = row.get("resultado_ah0", "pendiente")
            res_llm = _computar_resultado_llm_soccer(ir, res_ah0)
            if row.get("llm_resultado", "pendiente") == "pendiente" and res_llm != "pendiente":
                row["llm_resultado"] = res_llm
                changed = True
            break
    if changed:
        _escribir_xlsx(rows)
    return changed


def obtener_stats_llm_soccer() -> dict:
    """Retorna estadísticas de accuracy del LLM para fútbol."""
    stats = {"total": 0, "acertados": 0, "fallidos": 0, "win_rate": 0}
    rows = _leer_xlsx()
    for row in rows:
        res = row.get("llm_resultado", "pendiente")
        if res in ("acertado", "fallido"):
            stats["total"] += 1
            if res == "acertado":
                stats["acertados"] += 1
            else:
                stats["fallidos"] += 1
    if stats["total"] > 0:
        stats["win_rate"] = round(stats["acertados"] / stats["total"] * 100)
    return stats


def cargar_stats_cache() -> pd.DataFrame:
    if not os.path.exists(config.CACHE_STATS_PATH):
        return pd.DataFrame()
    df = pd.read_csv(config.CACHE_STATS_PATH)
    for col in ("xg_last5", "xga_last5", "ppda_last5", "corners_last5"):
        if col in df.columns:
            df[col] = df[col].apply(_parse_json_list)
        else:
            df[col] = [[] for _ in range(len(df))]
    for col in ("centros_por_juego", "tiros_por_juego", "bloqueos_por_juego", "despejes_por_juego"):
        if col not in df.columns:
            df[col] = 0.0
    return df


def _parse_json_list(val):
    if isinstance(val, list):
        return val
    if pd.isna(val) or not val:
        return []
    try:
        parsed = json.loads(val)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def actualizar_stats_con_corners(corners_data: dict, liga: str):
    if not os.path.exists(config.CACHE_STATS_PATH):
        return
    df = pd.read_csv(config.CACHE_STATS_PATH)
    updated = 0
    for team_name, stats in corners_data.items():
        mask = (df["equipo"].str.lower() == team_name.lower()) & (df["liga"] == liga)
        if not mask.any():
            mask = df["equipo"].str.contains(team_name, case=False)
        if mask.any():
            idx = mask.idxmax()
            df.at[idx, "centros_por_juego"] = stats.get("centros", 0.0)
            df.at[idx, "tiros_por_juego"] = stats.get("tiros", 0.0)
            df.at[idx, "bloqueos_por_juego"] = stats.get("bloqueos", 0.0)
            df.at[idx, "despejes_por_juego"] = stats.get("despejes", 0.0)
            if "corners_per_90" in stats:
                existing = df.at[idx, "corners_last5"] if "corners_last5" in df.columns else "[]"
                corners_list = _parse_json_list(existing) if isinstance(existing, str) else (existing if isinstance(existing, list) else [])
                corners_list.append(stats["corners_per_90"])
                corners_list = corners_list[-5:]
                df.at[idx, "corners_last5"] = json.dumps(corners_list)
            updated += 1
    if updated > 0:
        df.to_csv(config.CACHE_STATS_PATH, index=False)
        logger.info(f"Stats cache: {updated} equipos actualizados con corners para {liga}")


def obtener_stats_equipo(df: pd.DataFrame, nombre_equipo: str, liga: str) -> dict:
    row = df[(df["equipo"].str.lower() == nombre_equipo.lower()) & (df["liga"] == liga)]
    if row.empty:
        row = df[df["equipo"].str.contains(nombre_equipo, case=False)]
    if row.empty:
        logger.warning(f"Equipo no encontrado en cache: {nombre_equipo} ({liga})")
        return {}
    return row.iloc[0].to_dict()


def _calcular_win_rate(acertados: int, total: int) -> int:
    if total == 0:
        return 0
    return round(acertados / total * 100)


def obtener_estadisticas_soccer() -> dict:
    stats = {
        "total": 0, "acertados": 0, "fallidos": 0, "win_rate": 0,
        "ah0_total": 0, "ah0_acertados": 0, "ah0_fallidos": 0, "ah0_devueltos": 0, "ah0_win_rate": 0,
        "ou25_total": 0, "ou25_acertados": 0, "ou25_fallidos": 0, "ou25_devueltos": 0, "ou25_win_rate": 0,
        "corners_total": 0, "corners_acertados": 0, "corners_fallidos": 0, "corners_win_rate": 0,
        "llm_total": 0, "llm_acertados": 0, "llm_fallidos": 0, "llm_win_rate": 0,
    }
    ligas = ["premier", "laliga", "bundesliga", "seriea", "ligue1", "ligamx"]
    liga_map = {"PREMIER_LEAGUE": "premier", "LA_LIGA": "laliga", "BUNDESLIGA": "bundesliga",
                "SERIE_A": "seriea", "LIGUE_1": "ligue1", "LIGA_MX": "ligamx"}
    for l in ligas:
        for m in ["ah0", "ou25", "corners"]:
            stats[f"{l}_{m}_total"] = 0
            stats[f"{l}_{m}_acertados"] = 0
            stats[f"{l}_{m}_fallidos"] = 0
            stats[f"{l}_{m}_devueltos"] = 0
            stats[f"{l}_{m}_win_rate"] = 0

    rows = _leer_xlsx()
    if not rows:
        return stats

    for row in rows:
        res_ah0 = row.get("resultado_ah0", "pendiente")
        res_ou25 = row.get("resultado_ou25", "pendiente")
        liga = row.get("liga", "")
        liga_key = liga_map.get(liga, "")

        if res_ah0 != "pendiente" and res_ah0 != "no_apostar":
            stats["ah0_total"] += 1
            if res_ah0 == "acertado":
                stats["ah0_acertados"] += 1
            elif res_ah0 == "fallido":
                stats["ah0_fallidos"] += 1
            elif res_ah0 == "devuelto":
                stats["ah0_devueltos"] += 1
            if liga_key:
                stats[f"{liga_key}_ah0_total"] += 1
                if res_ah0 == "acertado":
                    stats[f"{liga_key}_ah0_acertados"] += 1
                elif res_ah0 == "fallido":
                    stats[f"{liga_key}_ah0_fallidos"] += 1
                elif res_ah0 == "devuelto":
                    stats[f"{liga_key}_ah0_devueltos"] += 1

        if res_ou25 != "pendiente" and res_ou25 != "no_apostar":
            stats["ou25_total"] += 1
            if res_ou25 == "acertado":
                stats["ou25_acertados"] += 1
            elif res_ou25 == "fallido":
                stats["ou25_fallidos"] += 1
            elif res_ou25 == "devuelto":
                stats["ou25_devueltos"] += 1
            if liga_key:
                stats[f"{liga_key}_ou25_total"] += 1
                if res_ou25 == "acertado":
                    stats[f"{liga_key}_ou25_acertados"] += 1
                elif res_ou25 == "fallido":
                    stats[f"{liga_key}_ou25_fallidos"] += 1
                elif res_ou25 == "devuelto":
                    stats[f"{liga_key}_ou25_devueltos"] += 1

        res_corners = row.get("resultado_corners", "pendiente")
        if res_corners != "pendiente" and res_corners != "no_apostar":
            stats["corners_total"] += 1
            if res_corners == "acertado":
                stats["corners_acertados"] += 1
            elif res_corners == "fallido":
                stats["corners_fallidos"] += 1
            if liga_key:
                stats[f"{liga_key}_corners_total"] += 1
                if res_corners == "acertado":
                    stats[f"{liga_key}_corners_acertados"] += 1
                elif res_corners == "fallido":
                    stats[f"{liga_key}_corners_fallidos"] += 1

    stats["total"] = stats["ah0_total"] + stats["ou25_total"] + stats["corners_total"]
    stats["acertados"] = stats["ah0_acertados"] + stats["ou25_acertados"] + stats["corners_acertados"]
    stats["fallidos"] = stats["ah0_fallidos"] + stats["ou25_fallidos"] + stats["corners_fallidos"]

    stats["win_rate"] = _calcular_win_rate(stats["acertados"], stats["total"])
    stats["ah0_win_rate"] = _calcular_win_rate(stats["ah0_acertados"], stats["ah0_acertados"] + stats["ah0_fallidos"])
    stats["ou25_win_rate"] = _calcular_win_rate(stats["ou25_acertados"], stats["ou25_acertados"] + stats["ou25_fallidos"])
    stats["corners_win_rate"] = _calcular_win_rate(stats["corners_acertados"], stats["corners_acertados"] + stats["corners_fallidos"])

    llm = obtener_stats_llm_soccer()
    stats["llm_total"] = llm["total"]
    stats["llm_acertados"] = llm["acertados"]
    stats["llm_fallidos"] = llm["fallidos"]
    stats["llm_win_rate"] = llm["win_rate"]

    for l in ligas:
        for m in ["ah0", "ou25", "corners"]:
            ok = stats[f"{l}_{m}_acertados"]
            fail = stats[f"{l}_{m}_fallidos"]
            stats[f"{l}_{m}_win_rate"] = _calcular_win_rate(ok, ok + fail)

    return stats
