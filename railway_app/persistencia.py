import json
import logging
import os
import sys

import requests

logger = logging.getLogger(__name__)

REPO_OWNER = "05aptrading-jpg"
REPO_NAME  = "sportsAPBot"
API_BASE   = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

ARCHIVOS = [
    "apuestas.csv",
    "partidos_seguimiento.json",
    "suscriptores.json",
    "soccer_data.json",
    "futbol_bot/apuestas_soccer.csv",
    "futbol_bot/stats_soccer_equipos.csv",
]

def _get_github_token():
    return os.environ.get("GITHUB_TOKEN", "").strip()

def _headers():
    token = _get_github_token()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        logger.warning("GITHUB_TOKEN no configurado — usando acceso anónimo (rate limit 60 req/h)")
    return headers

def descargar_archivo(ruta_repo: str, ruta_local: str) -> bool:
    headers = _headers()
    if not headers:
        return False
    try:
        r = requests.get(f"{API_BASE}/contents/{ruta_repo}", headers=headers, timeout=15)
        if r.status_code != 200:
            logger.warning(f"No se pudo descargar {ruta_repo}: HTTP {r.status_code}")
            return False
        import base64
        contenido = base64.b64decode(r.json()["content"]).decode("utf-8")
        with open(ruta_local, "w", encoding="utf-8") as f:
            f.write(contenido)
        logger.info(f"Descargado: {ruta_repo} → {ruta_local}")
        return True
    except Exception as e:
        logger.warning(f"Error descargando {ruta_repo}: {e}")
        return False

def subir_archivo(ruta_repo: str, ruta_local: str, mensaje: str = None) -> bool:
    token = _get_github_token()
    if not token:
        logger.warning("GITHUB_TOKEN no configurado — no se puede subir a GitHub")
        return False
    headers = _headers()
    if not os.path.exists(ruta_local):
        logger.warning(f"No existe local: {ruta_local}")
        return False
    try:
        with open(ruta_local, "r", encoding="utf-8") as f:
            contenido = f.read()
        sha = None
        r = requests.get(f"{API_BASE}/contents/{ruta_repo}", headers=headers, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
        elif r.status_code != 404:
            logger.error(f"GitHub API error checking {ruta_repo}: {r.status_code}")
            return False
        import base64
        payload = {
            "message": mensaje or f"Actualizar {ruta_repo}",
            "content": base64.b64encode(contenido.encode("utf-8")).decode("ascii"),
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha
        r = requests.put(f"{API_BASE}/contents/{ruta_repo}", json=payload, headers=headers, timeout=15)
        if r.status_code in (200, 201):
            logger.info(f"Subido: {ruta_repo}")
            return True
        logger.error(f"GitHub push error ({ruta_repo}): {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"Error subiendo {ruta_repo}: {e}")
        return False

def restaurar_desde_github(base_dir: str):
    """Descarga todos los archivos de datos desde GitHub."""
    for archivo in ARCHIVOS:
        ruta_local = os.path.join(base_dir, archivo)
        descargar_archivo(archivo, ruta_local)

def respaldar_a_github(base_dir: str):
    """Sube todos los archivos de datos a GitHub."""
    for archivo in ARCHIVOS:
        ruta_local = os.path.join(base_dir, archivo)
        subir_archivo(archivo, ruta_local)

def sincronizar_csv_desde_github(base_dir: str) -> bool:
    """Descarga apuestas.csv desde GitHub (útil en startup)."""
    ruta_local = os.path.join(base_dir, "apuestas.csv")
    return descargar_archivo("apuestas.csv", ruta_local)
