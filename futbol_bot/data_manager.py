import csv
import hashlib
import json
import logging
import os
from datetime import datetime

import pandas as pd

import config

logger = logging.getLogger(__name__)

CSV_COLUMNAS = [
    "id_partido", "liga", "fecha_hora",
    "local", "visitante",
    "xg_local", "xg_visit", "xg_total", "diff_xg",
    "senal_ah0", "confianza_ah0",
    "senal_ou25", "confianza_ou25",
    "xcorner_local", "xcorner_visitante", "xcorner_total",
    "senal_corners", "confianza_corners",
    "resultado", "resultado_ah0", "resultado_ou25",
    "marcador_final", "fecha_actualizacion",
    "fecha_partido", "hora_partido",
]


def inicializar_csv():
    if not os.path.exists(config.CSV_SOCCER_PATH):
        with open(config.CSV_SOCCER_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNAS)
        logger.info(f"CSV creado: {config.CSV_SOCCER_PATH}")


def game_pk(liga: str, local: str, visitante: str, fecha: str) -> int:
    raw = hashlib.md5("|".join([liga, local, visitante, fecha]).encode()).hexdigest()
    return int(raw[:16], 16)


def guardar_analisis(analisis: list):
    from analyzer import MatchAnalysis
    inicializar_csv()
    now = datetime.now().isoformat()
    ids_nuevos = set(str(a.id_partido) for a in analisis)
    analisis_map = {str(a.id_partido): a for a in analisis}
    ids_existentes = set()
    rows = []

    try:
        with open(config.CSV_SOCCER_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or CSV_COLUMNAS
            for row in reader:
                rid = row["id_partido"]
                resultado = row.get("resultado", "pendiente")
                if resultado == "pendiente" and rid not in ids_nuevos:
                    continue
                if rid in ids_nuevos and resultado == "pendiente" and rid in analisis_map:
                    a = analisis_map[rid]
                    row["xg_local"] = a.proyeccion_local
                    row["xg_visit"] = a.proyeccion_visitante
                    row["xg_total"] = a.xg_total
                    row["diff_xg"] = a.diff_xg
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
                    row.setdefault("fecha_partido", "")
                    row.setdefault("hora_partido", "")
                    row.setdefault("resultado_ah0", row.get("resultado", "pendiente"))
                    row.setdefault("resultado_ou25", row.get("resultado", "pendiente"))
                    rows.append(row)
    except Exception:
        fieldnames = CSV_COLUMNAS

    for a in analisis:
        sid = str(a.id_partido)
        if sid in ids_existentes:
            continue
        ids_existentes.add(sid)
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
            "senal_ah0": a.senal_ah0,
            "confianza_ah0": a.confianza_ah0,
            "senal_ou25": a.senal_ou25,
            "confianza_ou25": a.confianza_ou25,
            "xcorner_local": a.xcorner_local,
            "xcorner_visitante": a.xcorner_visitante,
            "xcorner_total": a.xcorner_total,
            "senal_corners": a.senal_corners,
            "confianza_corners": a.confianza_corners,
            "resultado": "pendiente",
            "resultado_ah0": "pendiente",
            "resultado_ou25": "pendiente",
            "marcador_final": "",
            "fecha_actualizacion": now,
            "fecha_partido": a.fecha_partido,
            "hora_partido": a.hora_partido,
        })
    with open(config.CSV_SOCCER_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNAS)
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"{len(analisis)} análisis guardados (limpiados pendientes viejos)")


def guardar_mundial_csv(mundial_games: list):
    """Agrega o actualiza partidos del Mundial en el CSV."""
    if not mundial_games:
        return
    inicializar_csv()
    now = datetime.now().isoformat()
    existentes = {}
    rows = []
    fieldnames = CSV_COLUMNAS
    try:
        with open(config.CSV_SOCCER_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or CSV_COLUMNAS
            for row in reader:
                existentes[row.get("id_partido", "")] = len(rows)
                rows.append(row)
    except Exception:
        pass

    added = 0
    updated = 0
    for g in mundial_games:
        pk = str(game_pk("MUNDIAL", g["local"], g["visitante"], g["fecha_partido"]))
        if pk in existentes:
            idx = existentes[pk]
            if rows[idx].get("xg_local") == "1.3" or rows[idx].get("xg_total") == "2.6":
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
        with open(config.CSV_SOCCER_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Mundial: {added} nuevos, {updated} actualizados en CSV")


def actualizar_resultados(id_partido: str, marcador: str, resultado_ah0: str, resultado_ou25: str) -> bool:
    """Actualiza resultado_ah0, resultado_ou25 y marcador de un partido en el CSV."""
    if not os.path.exists(config.CSV_SOCCER_PATH):
        return False
    rows = []
    changed = False
    with open(config.CSV_SOCCER_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["id_partido"] == id_partido:
                if row.get("resultado_ah0", "pendiente") == "pendiente" or row.get("resultado_ou25", "pendiente") == "pendiente":
                    row["resultado_ah0"] = resultado_ah0
                    row["resultado_ou25"] = resultado_ou25
                    row["marcador_final"] = marcador
                    row["fecha_actualizacion"] = datetime.now().isoformat()
                    changed = True
            rows.append(row)
    if changed:
        with open(config.CSV_SOCCER_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Partido {id_partido} actualizado: AH0={resultado_ah0} O/U={resultado_ou25} {marcador}")
    return changed


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

    if not os.path.exists(config.CSV_SOCCER_PATH):
        return stats
    try:
        with open(config.CSV_SOCCER_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
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

    for l in ligas:
        for m in ["ah0", "ou25", "corners"]:
            ok = stats[f"{l}_{m}_acertados"]
            fail = stats[f"{l}_{m}_fallidos"]
            stats[f"{l}_{m}_win_rate"] = _calcular_win_rate(ok, ok + fail)

    return stats
