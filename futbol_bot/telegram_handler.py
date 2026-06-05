import csv
import json
import logging
import os

import requests

import config
import bot

logger = logging.getLogger(__name__)

_last_update_id = 0
TELEGRAM_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"
SUSCRIPTORES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mlb_bot", "suscriptores.json")


def _eliminar_usuario(chat_id: int) -> bool:
    elim = str(chat_id)
    try:
        with open(SUSCRIPTORES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    suscripciones = data.get("suscripciones", {})
    admin = str(data.get("admin_id", 0))
    if elim in suscripciones and elim != admin:
        del suscripciones[elim]
        data["suscripciones"] = suscripciones
        with open(SUSCRIPTORES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Usuario {chat_id} eliminado por solicitud (futbol_bot)")
        return True
    return False


def procesar_comandos():
    global _last_update_id
    if not config.TELEGRAM_TOKEN:
        return
    try:
        r = requests.get(
            f"{TELEGRAM_URL}/getUpdates",
            params={"offset": _last_update_id + 1, "timeout": 10},
            timeout=15,
        )
        if r.status_code != 200:
            return
        data = r.json()
        for update in data.get("result", []):
            _last_update_id = update["update_id"]
            msg = update.get("message", {})
            text = (msg.get("text") or "").strip()
            chat_id = msg.get("chat", {}).get("id", "")
            if not chat_id:
                continue
            if text == "/futbol":
                _responder_futbol(chat_id)
            elif text in ("/borrar", "/delete"):
                if _eliminar_usuario(chat_id):
                    bot.enviar_mensaje(
                        "🗑️ <b>Datos eliminados</b>\n\n"
                        "Tus datos han sido eliminados del sistema.\n"
                        "Gracias por usar el servicio.",
                        chat_id=str(chat_id),
                    )
                else:
                    bot.enviar_mensaje(
                        "ℹ️ No se encontraron datos asociados.",
                        chat_id=str(chat_id),
                    )
    except Exception as e:
        logger.error(f"Error en updates: {e}")


def _responder_futbol(chat_id: str):
    if not os.path.exists(config.CSV_SOCCER_PATH):
        bot.enviar_mensaje("⚠️ No hay análisis de fútbol disponibles aún.", chat_id=chat_id)
        return
    try:
        with open(config.CSV_SOCCER_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        pendientes = [r for r in rows if r.get("resultado") == "pendiente"]
        if not pendientes:
            bot.enviar_mensaje("⚽ No hay partidos pendientes de análisis.", chat_id=chat_id)
            return
        lineas = [f"⚽ <b>Análisis Fútbol</b> — {len(pendientes)} partidos"]
        lineas.append("═" * 30)
        for r in pendientes:
            lineas.append(
                f"\n{r['local']} vs {r['visitante']}"
            )
            lineas.append(f"📊 {r['xg_local']} - {r['xg_visit']} | diff: {r['diff_xg']}")
            if r["senal_ah0"] != "NO_APOSTAR":
                lineas.append(f"🎯 {r['senal_ah0']} ({r['confianza_ah0']})")
            if r["senal_ou25"] != "NO_APOSTAR":
                lineas.append(f"📈 {r['senal_ou25']} ({r['confianza_ou25']})")
            if r.get("senal_corners", "NO_APOSTAR") != "NO_APOSTAR":
                lineas.append(f"🚩 {r['senal_corners']} ({r['confianza_corners']})")
        bot.enviar_mensaje("\n".join(lineas), chat_id=chat_id)
    except Exception as e:
        logger.error(f"Error respondiendo /futbol: {e}")
        bot.enviar_mensaje("⚠️ Error al leer análisis.", chat_id=chat_id)
