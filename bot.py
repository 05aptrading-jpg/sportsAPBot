"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MLB BOT — bot.py                                                           ║
║  Construcción y envío de mensajes a Telegram                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
import requests
from datetime import datetime, date
from typing import Optional

import config
from analyzer import GameAnalysis
from data_manager import obtener_estadisticas

logger = logging.getLogger(__name__)

TELEGRAM_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


def _esc(text) -> str:
    """Escapa caracteres especiales de HTML para Telegram parse_mode=HTML."""
    s = str(text) if text is not None else ""
    # Eliminar backslashes y caracteres de control que rompen el parse de Telegram
    s = s.replace("\\", "").replace("\x00", "")
    return (s
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


# ─────────────────────────────────────────────────────────────────────────────
# ENVÍO BASE
# ─────────────────────────────────────────────────────────────────────────────
def _send(text: str, parse_mode: str = "HTML",
          chat_id: str = None) -> bool:
    """Envía un mensaje a Telegram. Retorna True si fue exitoso.
    Si falla con error 400 (HTML inválido), reintenta sin parse_mode."""
    cid = chat_id or config.TELEGRAM_CHAT_ID
    try:
        r = requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            json={
                "chat_id":    cid,
                "text":       text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if r.status_code == 200:
            return True
        # Si Telegram rechaza el HTML, reintentar como texto plano
        if r.status_code == 400 and parse_mode == "HTML":
            logger.warning(f"Telegram HTML parse falló, reintentando sin formato: {r.text[:150]}")
            import re as _re
            plain = _re.sub(r'<[^>]+>', '', text)  # strip HTML tags
            r2 = requests.post(
                f"{TELEGRAM_URL}/sendMessage",
                json={
                    "chat_id": cid,
                    "text":    plain,
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            if r2.status_code == 200:
                logger.info("Mensaje enviado como texto plano (fallback)")
                return True
            logger.error(f"Telegram fallback error {r2.status_code}: {r2.text[:200]}")
            return False
        logger.error(f"Telegram error {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"Error enviando a Telegram: {e}")
        return False


def _chunk(text: str, size: int = 4000) -> list[str]:
    """Divide texto largo en chunks para el límite de Telegram (4096 chars)."""
    return [text[i:i+size] for i in range(0, len(text), size)]


def enviar_mensaje(text: str) -> bool:
    """Envía mensaje largo dividiéndolo si supera el límite."""
    ok = True
    for parte in _chunk(text):
        if not _send(parte):
            ok = False
    # Enviar disclaimer como mensaje separado (solo si el texto no es muy corto)
    if len(text) > 100:
        _send("📚 MLB Analytics — Análisis académico basado en datos públicos. No constituye consejo financiero ni de apuestas.")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# ██  FORMATEADOR — Alerta visual de la Tríada del Valor  ██
# ─────────────────────────────────────────────────────────────────────────────
def formatear_alerta_valor(a: GameAnalysis) -> str:
    """
    Formato visual ultra-legible para señales de valor.
    Diseñado para identificar la Tríada del Valor en un segundo.
    """
    favorito = a.favorito
    if favorito == a.away_team:
        rival = a.home_team
    else:
        rival = a.away_team

    # BaseRuns diff del favorito
    if favorito == a.away_team:
        diff_br = a.away_efficiency.diferencial if a.away_efficiency else 0
    else:
        diff_br = a.home_efficiency.diferencial if a.home_efficiency else 0

    # Bullpen alerts
    bp_alerts = []
    if a.away_bullpen and a.away_bullpen.fatigado:
        bp_alerts.append(f"Bullpen de {a.away_team} con {a.away_bullpen.pitcheos_72h} pitcheos 72h")
    if a.home_bullpen and a.home_bullpen.fatigado:
        bp_alerts.append(f"Bullpen de {a.home_team} con {a.home_bullpen.pitcheos_72h} pitcheos 72h")

    # Mano del abridor rival y wRC+ split
    if favorito == a.away_team:
        mano_rival = a.home_pitcher.pitch_hand if a.home_pitcher else 'R'
    else:
        mano_rival = a.away_pitcher.pitch_hand if a.away_pitcher else 'R'

    edge = a.edge_pct if a.edge_pct else 0
    mercado = a.odds_mercado if a.odds_mercado else 0

    lineas = [
        "🚨 <b>SEÑAL DE VALOR DETECTADA</b> 🚨",
        f"Partido: {_esc(a.away_team)} vs {_esc(a.home_team)}",
        f"Liga: MLB",
        "",
        "📈 <b>Modelo Sabermétrico:</b>",
        f"Favorito: {_esc(favorito)}",
        f"Probabilidad Calculada: <b>{a.prob_favorito:.1f}%</b> (Umbral superado)",
        f"Probabilidad de Mercado: {mercado:.1f}%",
        f"Ventaja (Edge): +{edge:.1f}%",
        "",
        "🛠 <b>Factores de Respaldo (Tríada):</b>",
        f"BaseRuns Diff: {diff_br:.1f} ({_esc(favorito)} con racha de mala suerte, valor oculto)"
        if diff_br < 0 else
        f"BaseRuns Diff: {diff_br:.1f}",
        f"Ajuste del Lineup: wRC+ vs {'Zurdo' if mano_rival == 'L' else 'Derecho'} optimizado",
    ]

    if bp_alerts:
        for ba in bp_alerts:
            lineas.append(f"⚠️ Alerta de Riesgo: {ba}.")
    else:
        lineas.append("✅ Sin alertas de bullpen significativas")

    lineas += [
        "",
        "🔥 <b>Acción: Apuesta sugerida al Favorito (Moneyline).</b>",
    ]

    return "\n".join(lineas)


# ─────────────────────────────────────────────────────────────────────────────
# ██  MENSAJE 1 — ANÁLISIS MATUTINO (8:00 AM)  ██
# ─────────────────────────────────────────────────────────────────────────────
def mensaje_analisis_manana(analyses: list[GameAnalysis]) -> str:
    """
    Genera el mensaje principal de las 8:00 AM con todos los partidos
    analizados ordenados de mayor a menor probabilidad.
    """
    hoy     = date.today().strftime("%A %d de %B, %Y")
    n       = len(analyses)
    valores = [a for a in analyses if a.es_valor]

    lineas = [
        f"⚾ <b>MLB — ANÁLISIS SABERMÉRICO {hoy}</b>",
        f"📊 <b>Metodología v3.0 | {n} partidos analizados</b>",
        "",
        "📡 <b>Fuentes:</b> statsapi.mlb.com · baseballsavant.mlb.com · the-odds-api.com",
        "",
    ]

    # Tríada del Valor
    lineas += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⭐ <b>THE EDGE — TRÍADA DEL VALOR ({len(valores)} partido{'s' if len(valores)!=1 else ''})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if valores:
        for a in valores:
            lineas += ["", formatear_alerta_valor(a)]
    else:
        lineas += [
            "",
            "   ℹ️ Ningún partido cumple la Tríada del Valor hoy.",
            f"   (Prob &gt; {config.PROB_MINIMA_SEÑAL:.0f}% + BaseRuns diff &lt; -{config.BASERUNS_DIFERENCIAL_NUEVO:.1f} + Edge &gt;= {config.EDGE_MINIMO_TRÍADA:.1f}%)",
        ]

    # ── CONFIANZA ALTA — prob ≥ 55% + edge ≥ 3% ────────────────────────
    alta   = [a for a in analyses if a.confianza == "Alta"]
    media  = [a for a in analyses if a.confianza == "Media"]
    debiles = [a for a in analyses if a.confianza == "Baja"]

    if alta:
        lineas += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🔥 <b>CONFIANZA ALTA ({len(alta)} de {n} partidos)</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"<i>Prob ≥ {config.PROB_MINIMA_APUESTA:.0f}% + Edge ≥ {config.EDGE_MINIMO_TRÍADA:.1f}% · mayor a menor</i>",
            "",
        ]
        for idx, a in enumerate(alta, 1):
            edge_str  = (f" | Edge +{a.edge_pct:.1f}%"
                         if a.edge_pct else "")
            mercado_str = (f" | Mercado: {a.odds_mercado:.1f}%"
                           if a.odds_mercado else "")
            valor_str = " ⭐ VALOR" if a.es_valor else ""
            clima_str = (f"   🌬 {_esc(a.weather_desc)}"
                         if getattr(a, "weather_desc", "") else "")
            siera_str = ""
            if a.away_pitcher and a.home_pitcher:
                siera_str = (
                    f"   🎯 xERA: {_esc(a.away_pitcher.name.split()[-1] if a.away_pitcher.name else 'TBD')}"
                    f"={a.away_pitcher.siera:.2f} / "
                    f"{_esc(a.home_pitcher.name.split()[-1] if a.home_pitcher.name else 'TBD')}"
                    f"={a.home_pitcher.siera:.2f}"
                )
            entrada = [
                f"<b>{idx}. {_esc(a.favorito)}</b>{valor_str}",
                f"   ⚾ {_esc(a.away_team)} @ {_esc(a.home_team)}",
                f"   📊 Prob: <b>{a.prob_favorito:.1f}%</b>{mercado_str}{edge_str}",
                f"   {_barra_probabilidad(a.prob_favorito)}",
            ]
            if siera_str:
                entrada.append(siera_str)
            if clima_str:
                entrada.append(clima_str)
            entrada += [
                f"   ⚠️ Riesgo: {_esc(a.factor_riesgo)}",
                "",
            ]
            lineas += entrada

    # ── CONFIANZA MEDIA — prob ≥ 55% sin edge suficiente ───────────────
    if media:
        lineas += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>CONFIANZA MEDIA ({len(media)} partidos)</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"<i>Prob ≥ {config.PROB_MINIMA_APUESTA:.0f}% pero edge &lt; {config.EDGE_MINIMO:.0f}% o sin odds de mercado</i>",
            "",
        ]
        for idx, a in enumerate(media, 1):
            mercado_str = (f" | Mercado: {a.odds_mercado:.1f}%"
                           if a.odds_mercado else "")
            edge_str  = (f" | Edge +{a.edge_pct:.1f}%"
                         if a.edge_pct else "")
            entrada = [
                f"<b>{idx}. {_esc(a.favorito)}</b>",
                f"   ⚾ {_esc(a.away_team)} @ {_esc(a.home_team)}",
                f"   📊 Prob: <b>{a.prob_favorito:.1f}%</b>{mercado_str}{edge_str}",
                f"   {_barra_probabilidad(a.prob_favorito)}",
                f"   ⚠️ Riesgo: {_esc(a.factor_riesgo)}",
                "",
            ]
            lineas += entrada

    if not alta and not media:
        lineas += ["", "   📚 Ningún partido supera el umbral de análisis (prob ≥ 55%) hoy.", ""]

    # ── SOLO INFORMATIVOS — prob < 55% ────────────────────────────────
    if debiles:
        lineas += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📋 <b>SOLO INFORMATIVOS ({len(debiles)} partidos · prob &lt; 55%)</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "<i>⚠️ Señal débil — no se recomienda apostar</i>",
            "",
        ]
        for idx, a in enumerate(debiles, 1):
            mercado_str = (f" | Mercado: {a.odds_mercado:.1f}%"
                           if a.odds_mercado else "")
            lineas += [
                f"{idx}. {_esc(a.favorito)} ({a.prob_favorito:.1f}%{mercado_str})",
                f"   ⚾ {_esc(a.away_team)} @ {_esc(a.home_team)}",
                "",
            ]

    # Estadísticas históricas
    stats = obtener_estadisticas()
    if stats["total"] > 0:
        lineas += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📊 <b>RENDIMIENTO HISTÓRICO DEL BOT</b>",
            f"🌐 Global: {stats['acertados']}✅ {stats['fallidos']}❌ ({stats['total']}) → <b>{stats['win_rate']}%</b>",
        ]
        if stats["alta_total"] > 0:
            rw = stats['alta_win_rate']
            extra = " 🔥" if rw >= 65 else ""
            lineas += [f"🎯 Alta Confianza: {stats['alta_acertados']}✅ {stats['alta_fallidos']}❌ ({stats['alta_total']}) → <b>{rw}%</b>{extra}"]
        if stats["media_total"] > 0:
            lineas += [f"📊 Conf. Media: {stats['media_acertados']}✅ {stats['media_fallidos']}❌ ({stats['media_total']}) → <b>{stats['media_win_rate']}%</b>"]
        if stats["baja_total"] > 0:
            lineas += [f"📋 Solo Inform.: {stats['baja_acertados']}✅ {stats['baja_fallidos']}❌ ({stats['baja_total']}) → <b>{stats['baja_win_rate']}%</b>"]
        lineas += [f"⭐ Señales Valor: {stats['valor_ok']}/{stats['valor_total']} ({stats['valor_rate']}%)"]
        # ── Partidos de hoy con ambas probabilidades — fuente: CSV acumulado
        # (robusto ante caídas de Odds API en el run actual)
        from data_manager import obtener_partidos_hoy_con_mercado
        partidos_filtrados = obtener_partidos_hoy_con_mercado()
        if partidos_filtrados:
            lineas += ["", "   <b>Partidos de hoy (resultados al cierre):</b>"]
            for f in partidos_filtrados:
                fav      = f.get("favorito_sabermetrico", "—")
                prob_i   = f.get("probabilidad_inicial", "—")
                prob_m   = f.get("prob_mercado", "N/D")
                res      = f.get("resultado", "pendiente")
                es_val   = f.get("es_valor", "NO").strip().upper() == "SI"
                res_emoji = {"acertado": "✅", "fallido": "❌"}.get(res, "⏳")
                valor_col = " ⭐" if es_val else ""
                lineas.append(
                    f"   {res_emoji} {_esc(fav)}{valor_col} "
                    f"({_esc(prob_i)} · Mercado: {_esc(prob_m)})"
                )

    lineas += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ <i>Análisis académico. No es asesoría financiera.</i>",
    ]

    return "\n".join(lineas)


# ─────────────────────────────────────────────────────────────────────────────
# ██  MENSAJE 2 — RESULTADO POST-PARTIDO  ██
# ─────────────────────────────────────────────────────────────────────────────
def mensaje_resultado(a: GameAnalysis,
                       ganador: str,
                       marcador: str) -> str:
    """
    Resultado final del partido con comparación vs predicción.
    """
    acertado  = ganador == a.favorito
    emoji     = "✅" if acertado else "❌"
    resultado = "ACERTADO" if acertado else "FALLIDO"
    valor_tag = " ⭐ VALOR" if a.es_valor else ""

    stats = obtener_estadisticas()

    lineas = [
        f"{emoji} <b>RESULTADO{valor_tag} — {resultado}</b>",
        f"⚾ <b>{_esc(a.away_team)} @ {_esc(a.home_team)}</b>",
        f"",
        f"🏆 Favorito bot: <b>{_esc(a.favorito)}</b> ({a.prob_favorito:.1f}%)",
        f"🏁 Ganador real: <b>{_esc(ganador)}</b>",
        f"📊 Marcador: {_esc(marcador)}",
        f"",
        f"📈 Prob. sabermérica: {a.prob_favorito:.1f}%"
        + (f" | Mercado: {a.odds_mercado:.1f}%" if a.odds_mercado else ""),
        f"⚠️ Factor de riesgo: {_esc(a.factor_riesgo)}",
        f"",
        f"📊 <b>Rendimiento acumulado:</b>",
        f"🌐 Global: {stats['acertados']}✅ {stats['fallidos']}❌ → <b>{stats['win_rate']}%</b>",
    ]
    if stats["alta_total"] > 0:
        rw = stats['alta_win_rate']
        extra = " 🔥" if rw >= 65 else ""
        lineas += [f"🎯 Alta Confianza: {stats['alta_acertados']}✅ {stats['alta_fallidos']}❌ → <b>{rw}%</b>{extra}"]
    if stats["media_total"] > 0:
        lineas += [f"📊 Conf. Media: {stats['media_acertados']}✅ {stats['media_fallidos']}❌ → <b>{stats['media_win_rate']}%</b>"]
    if stats["baja_total"] > 0:
        lineas += [f"📋 Solo Inform.: {stats['baja_acertados']}✅ {stats['baja_fallidos']}❌ → <b>{stats['baja_win_rate']}%</b>"]
    lineas += [
        f"⭐ Señales Valor: {stats['valor_ok']}/{stats['valor_total']} ({stats['valor_rate']}%)",
        f"",
        f"📡 Fuente resultado: statsapi.mlb.com",
    ]
    return "\n".join(lineas)


# ─────────────────────────────────────────────────────────────────────────────
# ██  MENSAJE 3 — RESUMEN SEMANAL  ██
# ─────────────────────────────────────────────────────────────────────────────
def mensaje_resumen_semanal() -> str:
    stats = obtener_estadisticas()
    lineas = [
        f"📊 <b>RESUMEN SEMANAL — MLB BOT</b>",
        f"",
        f"📅 {date.today().strftime('%d/%m/%Y')}",
        f"",
        f"🌐 <b>Global:</b> {stats['acertados']}✅ {stats['fallidos']}❌ ({stats['pendientes']}⏳) → <b>{stats['win_rate']}%</b>",
    ]
    if stats["alta_total"] > 0:
        rw = stats['alta_win_rate']
        extra = " 🔥" if rw >= 65 else ""
        lineas += [
            f"🎯 Alta Confianza: {stats['alta_acertados']}✅ {stats['alta_fallidos']}❌ ({stats['alta_total']}) → <b>{rw}%</b>{extra}",
        ]
    if stats["media_total"] > 0:
        lineas += [
            f"📊 Conf. Media: {stats['media_acertados']}✅ {stats['media_fallidos']}❌ ({stats['media_total']}) → <b>{stats['media_win_rate']}%</b>",
        ]
    if stats["baja_total"] > 0:
        lineas += [
            f"📋 Solo Inform.: {stats['baja_acertados']}✅ {stats['baja_fallidos']}❌ ({stats['baja_total']}) → <b>{stats['baja_win_rate']}%</b>",
        ]
    lineas += [
        f"⭐ Señales Valor: {stats['valor_ok']}/{stats['valor_total']} ({stats['valor_rate']}%)",
        f"",
        f"📁 Datos históricos en base de datos local",
    ]
    return "\n".join(lineas)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — BARRA DE PROBABILIDAD
# ─────────────────────────────────────────────────────────────────────────────
def _barra_probabilidad(prob: float, largo: int = 20) -> str:
    """Genera una barra visual de probabilidad."""
    llenos  = int(prob / 100 * largo)
    vacios  = largo - llenos
    color   = "🟢" if prob >= 60 else ("🟡" if prob >= 50 else "🔴")
    return f"   {color} [{'█' * llenos}{'░' * vacios}] {prob:.1f}%"


# ─────────────────────────────────────────────────────────────────────────────
# ENVÍOS COMPLETOS (usados desde scheduler.py)
# ─────────────────────────────────────────────────────────────────────────────
def enviar_analisis_manana(analyses: list[GameAnalysis]) -> bool:
    msg = mensaje_analisis_manana(analyses)
    ok  = enviar_mensaje(msg)
    logger.info(f"Mensaje matutino enviado: {ok}")
    return ok


def enviar_notificacion_actualizacion(liga: str):
    mini_url = "https://05aptrading-jpg.github.io/sportsAPBot/"
    msg = (
        f"📊 <b>Actualización para toma de decisiones</b>\n"
        f"📡 {liga}: datos actualizados en la Mini App.\n"
        f"📱 <a href='{mini_url}'>Abrir Mini App</a>\n\n"
        f"📚 MLB Analytics — Análisis académico. No constituye consejo financiero ni de apuestas."
    )
    enviar_mensaje(msg)
    logger.info(f"Notificación de actualización enviada ({liga})")


def enviar_resultado(a: GameAnalysis,
                      ganador: str, marcador: str) -> bool:
    msg = mensaje_resultado(a, ganador, marcador)
    ok  = enviar_mensaje(msg)
    logger.info(f"Resultado enviado [{a.away_team} @ {a.home_team}]: {ok}")
    return ok


def enviar_resumen_semanal() -> bool:
    msg = mensaje_resumen_semanal()
    ok  = enviar_mensaje(msg)
    logger.info(f"Resumen semanal enviado: {ok}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# ██  MENSAJE 4 — INICIO DEL BOT  ██
# ─────────────────────────────────────────────────────────────────────────────
def mensaje_inicio(hora_analisis: str, timezone: str,
                   partidos_hoy: int = 0) -> str:
    """
    Mensaje de arranque del bot. Incluye estadísticas históricas
    para tener contexto del rendimiento acumulado desde el primer momento.
    """
    stats = obtener_estadisticas()
    stats_lmb = obtener_estadisticas(liga="LMB")

    # Obtener hora LMB
    hora_lmb = getattr(config, "LMB_HORA_MANANA", "10:00")
    try:
        from scheduler import obtener_hora_analisis_lmb
        hora_lmb = obtener_hora_analisis_lmb()
    except Exception:
        pass

    lineas = [
        "🚀 <b>MLB BOT iniciado</b>",
        "",
        f"📡 MLB: <b>{hora_analisis}</b> | 🇲🇽 LMB: <b>{hora_lmb}</b> ({timezone})",
    ]

    if partidos_hoy > 0:
        lineas += [
            "",
            f"📋 Estado de hoy: <b>{partidos_hoy} partidos</b> en seguimiento",
        ]

    if stats["total"] > 0:
        resueltos = stats["acertados"] + stats["fallidos"]
        lineas += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📈 <b>RENDIMIENTO HISTÓRICO</b>",
        ]
        if stats["pendientes"] > 0:
            lineas.append(f"📦 {stats['total']} registros ({stats['pendientes']} pendientes)")
        else:
            lineas.append(f"📦 {stats['total']} registros")
        wr = stats['win_rate']
        extra = " 🔥" if wr >= 60 else (" ⚠️" if wr < 50 else "")
        lineas += [f"🌐 Global: {stats['acertados']}✅ {stats['fallidos']}❌ → <b>{wr}%</b>{extra}"]
        if stats["alta_total"] > 0:
            rw = stats['alta_win_rate']
            extra = " 🔥" if rw >= 65 else ""
            lineas += [f"🎯 Alta Confianza: {stats['alta_acertados']}✅ {stats['alta_fallidos']}❌ → <b>{rw}%</b>{extra}"]
        if stats["media_total"] > 0:
            lineas += [f"📊 Conf. Media: {stats['media_acertados']}✅ {stats['media_fallidos']}❌ → <b>{stats['media_win_rate']}%</b>"]
        if stats["baja_total"] > 0:
            lineas += [f"📋 Solo Inform.: {stats['baja_acertados']}✅ {stats['baja_fallidos']}❌ → <b>{stats['baja_win_rate']}%</b>"]
        lineas += [f"⭐ Señales Valor: {stats['valor_ok']}/{stats['valor_total']} ({stats['valor_rate']}%)"]
        if resueltos > 0:
            lineas.append(f"📁 Basado en {resueltos} predicciones resueltas")

        # LMB Stats
        if stats_lmb and stats_lmb["total"] > 0:
            lineas += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                       "🇲🇽 <b>RENDIMIENTO LMB</b>"]
            lineas += [f"🌐 LMB: {stats_lmb['acertados']}✅ {stats_lmb['fallidos']}❌ → <b>{stats_lmb['win_rate']}%</b>"]
    else:
        lineas += ["", "📋 Sin historial aún — primera ejecución."]

    return "\n".join(lineas)


def enviar_inicio(hora_analisis: str, timezone: str,
                  partidos_hoy: int = 0) -> bool:
    msg = mensaje_inicio(hora_analisis, timezone, partidos_hoy)
    ok  = enviar_mensaje(msg)
    logger.info(f"Mensaje de inicio enviado: {ok}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# ██  MENSAJE 5 — OPCIONES DE APUESTAS (prob > 55% y odds_mercado > 1)  ██
# ─────────────────────────────────────────────────────────────────────────────
def mensaje_analisis_destacados(partidos: list[dict]) -> str:
    """
    Genera el mensaje "Análisis destacados" filtrando partidos del JSON
    donde prob_favorito > 55 y odds_mercado no es null y > 1.
    `partidos` es la lista cruda de partidos_seguimiento.json (dicts).
    """
    hoy = date.today().strftime("%d/%m/%Y")

    candidatos = [
        p for p in partidos
        if (p.get("prob_favorito") or 0) > 55
        and p.get("odds_mercado") is not None
        and (p.get("odds_mercado") or 0) > 1
    ]

    # Ordenar de mayor a menor prob_favorito
    candidatos.sort(key=lambda p: p.get("prob_favorito", 0), reverse=True)

    lineas = [
        f"🎰 <b>OPCIONES DE APUESTAS — {hoy}</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 Filtro: Prob &gt; 55% + Cuota mercado disponible",
        f"📊 {len(candidatos)} partido{'s' if len(candidatos) != 1 else ''} encontrado{'s' if len(candidatos) != 1 else ''}",
        "",
    ]

    if not candidatos:
        lineas += [
            "ℹ️ Ningún partido cumple los criterios hoy.",
            "   (prob_favorito &gt; 55% y odds_mercado &gt; 1)",
        ]
    else:
        for idx, p in enumerate(candidatos, 1):
            prob     = p.get("prob_favorito", 0)
            mercado  = p.get("odds_mercado", 0)
            favorito = _esc(p.get("favorito", "—"))
            away     = _esc(p.get("away_team", "—"))
            home     = _esc(p.get("home_team", "—"))
            edge     = prob - mercado
            edge_str = f"+{edge:.1f}%" if edge >= 0 else f"{edge:.1f}%"
            hora_raw = p.get("game_datetime", "")
            hora_str = ""
            if hora_raw and "T" in hora_raw:
                hora_str = f"   🕐 {hora_raw[11:16]} UTC"

            color = "🟢" if prob >= 60 else "🟡"
            lineas += [
                f"<b>{idx}. {favorito}</b>",
                f"   ⚾ {away} @ {home}",
                f"   {color} Prob: <b>{prob:.1f}%</b> | Mercado: {mercado:.1f}% | Edge: {edge_str}",
                f"   {_barra_probabilidad(prob)}",
            ]
            if hora_str:
                lineas.append(hora_str)
            lineas.append("")

    lineas += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ <i>Análisis académico. No es asesoría financiera.</i>",
    ]

    return "\n".join(lineas)


def enviar_analisis_destacados(partidos: list[dict]) -> bool:
    """Construye y envía el mensaje de análisis destacados a Telegram."""
    msg = mensaje_analisis_destacados(partidos)
    if len(msg) > 4000:
        msg = msg[:3997] + "..."
    ok = enviar_mensaje(msg)
    logger.info(f"Análisis destacados enviados: {ok}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# ██  MENSAJE 6 — ANÁLISIS SABERMÉRICO LMB  ██
# ─────────────────────────────────────────────────────────────────────────────
def mensaje_analisis_lmb(analyses: list[dict]) -> str:
    """
    Genera el mensaje de análisis LMB con todos los partidos
    ordenados de mayor a menor probabilidad.
    `analyses` es la lista de dicts que devuelve analizar_lmb_dia().
    """
    from datetime import date as _date
    hoy = _date.today().strftime("%d/%m/%Y")
    n = len(analyses)

    lineas = [
        f"🇲🇽 <b>LMB — ANÁLISIS SABERMÉRICO {hoy}</b>",
        f"📊 <b>Metodología 5 Bloques | {n} partidos analizados</b>",
        "",
        "📡 <b>Fuentes:</b> statsapi.mlb.com (sportId=23) · Baseball Reference",
        "",
    ]

    # Ordenar de mayor a menor probabilidad
    sorted_a = sorted(analyses, key=lambda x: x.get("prob_favorito", 0), reverse=True)

    alta = [a for a in sorted_a if a.get("prob_favorito", 0) >= config.LMB_PROB_MINIMA]
    debiles = [a for a in sorted_a if a.get("prob_favorito", 0) < config.LMB_PROB_MINIMA]

    if alta:
        lineas += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🔥 <b>CONFIANZA ALTA ({len(alta)} de {n} partidos)</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"<i>Prob ≥ {config.LMB_PROB_MINIMA:.0f}% · mayor a menor</i>",
            "",
        ]
        for idx, a in enumerate(alta, 1):
            prob = a.get("prob_favorito", 0)
            favorito = _esc(a.get("favorito", "—"))
            away = _esc(a.get("away_team", "—"))
            home = _esc(a.get("home_team", "—"))
            abridor_a = _esc(a.get("away_pitcher", "N/D"))
            abridor_h = _esc(a.get("home_pitcher", "N/D"))
            fip_a = a.get("fip_away", 0)
            fip_h = a.get("fip_home", 0)
            kbb_a = a.get("kbb_away", 0)
            kbb_h = a.get("kbb_home", 0)
            wrc_a = a.get("wrc_away", 100)
            wrc_h = a.get("wrc_home", 100)
            factor = a.get("factor_riesgo", "N/D")
            hora = a.get("game_time", "")
            senal = a.get("senal_moneyline", "")

            lineas += [
                f"<b>{idx}. {favorito}</b>",
                f"   ⚾ {away} @ {home}",
                f"   📊 Prob: <b>{prob:.1f}%</b>",
                f"   {_barra_probabilidad(prob)}",
                f"   🎯 Abridor: {abridor_a} (FIP {fip_a:.2f}) vs {abridor_h} (FIP {fip_h:.2f})",
                f"   📈 K/BB: {kbb_a:.2f} vs {kbb_h:.2f} | wRC+: {wrc_a:.0f} vs {wrc_h:.0f}",
                f"   ⚠️ Riesgo: {_esc(factor)}",
            ]
            if senal and senal != "NO APOSTAR":
                lineas.append(f"   💰 Señal: {senal}")
            if hora:
                lineas.append(f"   🕐 {hora}")
            lineas.append("")

    if debiles:
        lineas += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📋 <b>SOLO INFORMATIVOS ({len(debiles)} partidos · prob &lt; {config.LMB_PROB_MINIMA:.0f}%)</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for idx, a in enumerate(debiles, 1):
            prob = a.get("prob_favorito", 0)
            favorito = _esc(a.get("favorito", "—"))
            away = _esc(a.get("away_team", "—"))
            home = _esc(a.get("home_team", "—"))
            lineas.append(
                f"  {idx}. {favorito} ({prob:.1f}%) — {away} @ {home}"
            )
        lineas.append("")

    # Stats LMB
    from data_manager import obtener_estadisticas
    stats = obtener_estadisticas(liga="LMB")
    if stats["total"] > 0:
        lineas += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🇲🇽 <b>RENDIMIENTO LMB ACUMULADO</b>",
            f"🌐 Global: {stats['acertados']}✅ {stats['fallidos']}❌ ({stats['total']}) → <b>{stats['win_rate']}%</b>",
        ]

    lineas += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ <i>Análisis académico. No es asesoría financiera.</i>",
    ]

    return "\n".join(lineas)


def enviar_analisis_lmb(analyses: list[dict]) -> bool:
    """Construye y envía el mensaje de análisis LMB a Telegram."""
    msg = mensaje_analisis_lmb(analyses)
    if len(msg) > 4000:
        msg = msg[:3997] + "..."
    ok = enviar_mensaje(msg)
    logger.info(f"Análisis LMB enviado: {ok}")
    return ok
