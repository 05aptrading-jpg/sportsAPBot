import logging
from datetime import date

import requests

import config

logger = logging.getLogger(__name__)

TELEGRAM_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


def _esc(text) -> str:
    s = str(text) if text is not None else ""
    s = s.replace("\\", "").replace("\x00", "")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def enviar_mensaje(text: str, parse_mode: str = "HTML") -> bool:
    cid = config.TELEGRAM_CHAT_ID
    if not cid:
        logger.warning("TELEGRAM_CHAT_ID no configurado")
        return False
    try:
        r = requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            json={
                "chat_id": cid,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if r.status_code == 200:
            return True
        if r.status_code == 400 and parse_mode == "HTML":
            import re
            plain = re.sub(r"<[^>]+>", "", text)
            r2 = requests.post(
                f"{TELEGRAM_URL}/sendMessage",
                json={"chat_id": cid, "text": plain, "disable_web_page_preview": True},
                timeout=15,
            )
            return r2.status_code == 200
        logger.error(f"Telegram error {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"Error enviando a Telegram: {e}")
        return False


def enviar_analisis_dia(analyses):
    from analyzer import MatchAnalysis
    if not analyses:
        return
    lineas = [
        f"⚽ <b>Análisis Fútbol — {date.today().isoformat()}</b>",
        "═" * 35,
    ]
    ligas = {}
    for a in analyses:
        ligas.setdefault(a.liga, []).append(a)

    liga_emoji = {
        "PREMIER_LEAGUE": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "LA_LIGA": "🇪🇸",
        "BUNDESLIGA": "🇩🇪",
        "SERIE_A": "🇮🇹",
        "LIGUE_1": "🇫🇷",
        "LIGA_MX": "🇲🇽",
    }

    for liga_name, parts in ligas.items():
        emoji = liga_emoji.get(liga_name, "⚽")
        lineas.append(f"\n{emoji} <b>{liga_name}</b>")
        for a in parts:
            conf_ah0 = f"({a.confianza_ah0})" if a.senal_ah0 != "NO_APOSTAR" else ""
            conf_ou25 = f"({a.confianza_ou25})" if a.senal_ou25 != "NO_APOSTAR" else ""
            lineas.append(
                f"\n{_esc(a.equipo_local)} vs {_esc(a.equipo_visitante)}"
            )
            lineas.append(f"📊 {a.proyeccion_local} - {a.proyeccion_visitante} | diff: {a.diff_xg:+.2f}")
            if a.senal_ah0 != "NO_APOSTAR":
                lineas.append(f"🎯 AH0: {a.senal_ah0} {conf_ah0}")
            if a.senal_ou25 != "NO_APOSTAR":
                lineas.append(f"📈 O/U: {a.senal_ou25} {conf_ou25}")
            if a.senal_corners != "NO_APOSTAR":
                conf_corners = f"({a.confianza_corners})" if a.confianza_corners != "BAJA" else ""
                lineas.append(f"🚩 Corners: {a.senal_corners} {conf_corners}")

    lineas.append(f"\n═" * 35)
    lineas.append("📚 Análisis académico basado en datos públicos.")

    mensaje = "\n".join(lineas)
    enviar_mensaje(mensaje)
