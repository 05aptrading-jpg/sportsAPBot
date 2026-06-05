"""
Telegram command handler.
Escucha comandos /actualizar y responde con tabla compacta de resultados.
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime

import requests

import config
import data_manager as dm
from api_client import mlb
import bot

logger = logging.getLogger(__name__)

TELEGRAM_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"
_last_update_id = 0


MINIAPP_URL = "https://05aptrading-jpg.github.io/sportsAPBot/"

DISCLAIMER = "📚 MLB Analytics — Análisis académico basado en datos públicos. No constituye consejo financiero ni de apuestas."

# ── Cargar / guardar suscriptores ─────────────────────────────────────
SUSCRIPTORES_PATH = os.path.join(os.path.dirname(__file__), "suscriptores.json")


def _cargar_suscriptores() -> dict:
    try:
        with open(SUSCRIPTORES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Migrar formato antiguo (autorizados: [ids]) -> nuevo (suscripciones: {})
        if "autorizados" in data and "suscripciones" not in data:
            from datetime import date as _date, timedelta
            expira = (_date.today() + timedelta(days=30)).isoformat()
            suscripciones = {}
            for uid in data.get("autorizados", []):
                uid_str = str(uid)
                if uid_str == str(data.get("admin_id")):
                    suscripciones[uid_str] = None
                else:
                    suscripciones[uid_str] = expira
            data["suscripciones"] = suscripciones
            del data["autorizados"]
            _guardar_suscriptores(data)
        return data
    except Exception:
        return {"admin_id": 0, "suscripciones": {}}


def _guardar_suscriptores(data: dict):
    try:
        with open(SUSCRIPTORES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando suscriptores: {e}")


def _expirar_vencidos(data: dict):
    from datetime import date as _date
    hoy = _date.today().isoformat()
    suscripciones = data.get("suscripciones", {})
    vencidos = [uid for uid, exp in suscripciones.items()
                if exp is not None and exp < hoy]
    for uid in vencidos:
        del suscripciones[uid]
        logger.info(f"Suscripción vencida — usuario {uid} eliminado")
    if vencidos:
        data["suscripciones"] = suscripciones
        _guardar_suscriptores(data)
    return data


def _eliminar_usuario(chat_id: int) -> bool:
    elim = str(chat_id)
    data = _cargar_suscriptores()
    suscripciones = data.get("suscripciones", {})
    admin = str(data.get("admin_id", 0))
    if elim in suscripciones and elim != admin:
        del suscripciones[elim]
        data["suscripciones"] = suscripciones
        _guardar_suscriptores(data)
        logger.info(f"Usuario {chat_id} eliminado por solicitud")
        return True
    return False


def _esta_autorizado(chat_id: int) -> bool:
    if chat_id == int(config.TELEGRAM_CHAT_ID):
        return True
    data = _cargar_suscriptores()
    data = _expirar_vencidos(data)
    admin = data.get("admin_id", 0)
    if chat_id == admin:
        return True
    uid_str = str(chat_id)
    suscripciones = data.get("suscripciones", {})
    if uid_str not in suscripciones:
        return False
    expira = suscripciones[uid_str]
    if expira is None:
        return True
    from datetime import date as _date
    return expira >= _date.today().isoformat()


# ── Envío de mensajes ─────────────────────────────────────────────────
def _send_raw(chat_id: str, text: str, mini_app: bool = False):
    import requests as _r
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if mini_app and config.GITHUB_TOKEN:
        payload["reply_markup"] = {
            "inline_keyboard": [[{
                "text": "📱 Abrir Mini App",
                "web_app": {"url": MINIAPP_URL},
            }]],
        }
    try:
        _r.post(url, json=payload, timeout=10)
    except Exception:
        pass


# ── Comandos ──────────────────────────────────────────────────────────
def _cmd_actualiza(chat_id: str):
    """Ejecuta /actualizar: consulta ESPN y muestra resultados + rendimiento."""
    from datetime import date as _date, timedelta
    hoy = _date.today()
    ayer = hoy - timedelta(days=1)
    lineas = [
        "📊 <b>MLB BOT — ACTUALIZACIÓN</b>",
        f"📅 {hoy.strftime('%d/%m/%Y')}",
        "",
    ]

    # Consultar ESPN para hoy y ayer
    def _espn_scoreboard(fecha: _date) -> list:
        try:
            ds = fecha.strftime("%Y%m%d")
            url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={ds}"
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return []
            games = []
            for ev in r.json().get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                comps = comp.get("competitors", [])
                h = next((c for c in comps if c.get("homeAway") == "home"), None)
                a = next((c for c in comps if c.get("homeAway") == "away"), None)
                if not h or not a:
                    continue
                hn = h.get("team", {}).get("displayName", "")
                an = a.get("team", {}).get("displayName", "")
                detail = comp.get("status", {}).get("type", {}).get("detail", "")
                done = comp.get("status", {}).get("type", {}).get("completed", False)
                ar = int(a.get("score", 0) or 0)
                hr = int(h.get("score", 0) or 0)
                games.append({"a": an, "h": hn, "ar": ar, "hr": hr, "detail": detail, "done": done})
            return games
        except Exception:
            return []

    def _t_sep():
        return "┌─────┬──────────────────────────────────┬──────────┐"

    def _t_row(emoji, equipos, estado):
        e = emoji.ljust(5)
        eq = equipos.ljust(32)
        es = estado.ljust(10)
        return f"│ {e}│ {eq}│ {es}│"

    all_games = _espn_scoreboard(hoy) + _espn_scoreboard(ayer)

    if not all_games:
        lineas.append("ℹ️ Sin partidos disponibles vía ESPN.")
    else:
        hoy_games = [g for g in all_games if "Final" not in g["detail"] or "Aplazado" in g["detail"]]
        ayer_games = [g for g in all_games if g not in hoy_games]
        pendientes = [g for g in hoy_games if not g["done"]]
        finalizados_hoy = [g for g in hoy_games if g["done"]]
        ordenados = pendientes + finalizados_hoy + ayer_games

        for g in ordenados[:15]:
            if g["done"]:
                emoji = "✅" if int(g["ar"]) != int(g["hr"]) else "🤝"
                score = f"{g['ar']}-{g['hr']}"
                state = g["detail"][:10]
            elif "Postp" in g["detail"] or "Aplaz" in g["detail"]:
                emoji = "🚫"
                score = "—"
                state = "Posp."
            elif "progr" in g["detail"].lower() or "sched" in g["detail"].lower():
                emoji = "⏳"
                score = "—"
                state = g["detail"][:10]
            else:
                emoji = "🔴"
                score = f"{g['ar']}-{g['hr']}"
                state = g["detail"][:10]
            lineas.append(f"{emoji} <code>{score:>5}</code> {g['a'][:20]} vs {g['h'][:20]}  <i>{state}</i>")

    # ── Estadísticas históricas ──
    lineas += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    stats = dm.obtener_estadisticas()
    if stats["total"] > 0:
        lineas += [
            "📊 <b>MLB BOT — RENDIMIENTO</b>",
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

    # ── Fútbol stats ──
    try:
        import json as _json
        soccer_json = os.path.join(config.FUTBOL_DIR, "soccer_data.json")
        if os.path.exists(soccer_json):
            with open(soccer_json, encoding="utf-8") as _f:
                _sd = _json.load(_f)
            fut_stats = _sd.get("stats", {})
            if fut_stats.get("total", 0) > 0:
                lineas += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
                lineas.append("⚽ <b>FÚTBOL — RENDIMIENTO</b>")
                lineas.append(f"🌐 Global: {fut_stats.get('acertados',0)}✅ {fut_stats.get('fallidos',0)}❌ ({fut_stats.get('total',0)}) → <b>{fut_stats.get('win_rate',0)}%</b>")
                if fut_stats.get("ah0_total", 0) > 0:
                    lineas.append(f"🎯 AH0: {fut_stats.get('ah0_acertados',0)}✅ {fut_stats.get('ah0_fallidos',0)}❌ ({fut_stats.get('ah0_total',0)}) → <b>{fut_stats.get('ah0_win_rate',0)}%</b>")
                if fut_stats.get("ou25_total", 0) > 0:
                    lineas.append(f"📈 O/U 2.5: {fut_stats.get('ou25_acertados',0)}✅ {fut_stats.get('ou25_fallidos',0)}❌ ({fut_stats.get('ou25_total',0)}) → <b>{fut_stats.get('ou25_win_rate',0)}%</b>")
    except Exception:
        pass

    show_mini = bool(config.GITHUB_TOKEN)
    text = "\n".join(lineas)
    if len(text) <= 4000:
        _send_raw(chat_id, text, mini_app=show_mini)
    else:
        for parte in [text[i:i+4000] for i in range(0, len(text), 4000)]:
            _send_raw(chat_id, parte, mini_app=False)


def _cmd_futbol(chat_id: str):
    """Muestra análisis de fútbol (Premier, La Liga, Liga MX)."""
    import csv as _csv
    from datetime import date as _date
    hoy = _date.today()
    lineas = [
        "⚽ <b>FÚTBOL — ANÁLISIS</b>",
        f"📅 {hoy.strftime('%d/%m/%Y')}",
        "",
    ]

    csv_path = config.CSV_SOCCER_PATH
    if not os.path.exists(csv_path):
        lineas.append("ℹ️ Sin datos de fútbol disponibles.")
        _send_raw(chat_id, "\n".join(lineas), mini_app=True)
        return

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))
    except Exception as e:
        lineas.append(f"⚠️ Error leyendo datos: {e}")
        _send_raw(chat_id, "\n".join(lineas), mini_app=True)
        return

    pendientes = [r for r in rows if r.get("resultado") == "pendiente"]
    if not pendientes:
        lineas.append("ℹ️ Sin partidos pendientes de fútbol.")
        _send_raw(chat_id, "\n".join(lineas), mini_app=True)
        return

    ligas = {}
    for r in pendientes:
        lk = r.get("liga", "FÚTBOL")
        ligas.setdefault(lk, []).append(r)

    liga_emoji = {"PREMIER_LEAGUE": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "LA_LIGA": "🇪🇸", "LIGA_MX": "🇲🇽"}

    for liga, parts in ligas.items():
        emoji = liga_emoji.get(liga, "⚽")
        lineas.append(f"{emoji} <b>{liga}</b> — {len(parts)} partidos")
        for r in parts:
            diff = r.get("diff_xg", "0")
            try:
                diff_val = float(diff)
                diff_str = f"+{diff_val:.2f}" if diff_val > 0 else f"{diff_val:.2f}"
            except (ValueError, TypeError):
                diff_str = str(diff)
            lineas.append(f"  {r['local']} vs {r['visitante']}")
            lineas.append(f"    📊 {r.get('xg_local','?')} - {r.get('xg_visit','?')} | diff: {diff_str}")
            if r.get("senal_ah0", "NO_APOSTAR") != "NO_APOSTAR":
                lineas.append(f"    🎯 AH0: {r['senal_ah0']} ({r.get('confianza_ah0', '')})")
            if r.get("senal_ou25", "NO_APOSTAR") != "NO_APOSTAR":
                lineas.append(f"    📈 O/U 2.5: {r['senal_ou25']} ({r.get('confianza_ou25', '')})")
        lineas.append("")

    # Stats de fútbol
    try:
        import json as _json
        soccer_json = os.path.join(config.FUTBOL_DIR, "soccer_data.json")
        if os.path.exists(soccer_json):
            with open(soccer_json, encoding="utf-8") as _f:
                _sd = _json.load(_f)
            stats = _sd.get("stats", {})
            if stats.get("total", 0) > 0:
                lineas += ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
                lineas.append("📊 <b>FÚTBOL — RENDIMIENTO</b>")
                lineas.append(f"🌐 Global: {stats.get('acertados',0)}✅ {stats.get('fallidos',0)}❌ ({stats.get('total',0)}) → <b>{stats.get('win_rate',0)}%</b>")
                if stats.get("ah0_total", 0) > 0:
                    lineas.append(f"🎯 AH0: {stats.get('ah0_acertados',0)}✅ {stats.get('ah0_fallidos',0)}❌ ({stats.get('ah0_total',0)}) → <b>{stats.get('ah0_win_rate',0)}%</b>")
                if stats.get("ou25_total", 0) > 0:
                    lineas.append(f"📈 O/U 2.5: {stats.get('ou25_acertados',0)}✅ {stats.get('ou25_fallidos',0)}❌ ({stats.get('ou25_total',0)}) → <b>{stats.get('ou25_win_rate',0)}%</b>")
    except Exception:
        pass

    text = "\n".join(lineas)
    if len(text) <= 4000:
        _send_raw(chat_id, text, mini_app=True)
    else:
        for parte in [text[i:i+4000] for i in range(0, len(text), 4000)]:
            _send_raw(chat_id, parte, mini_app=False)





def _cmd_suscriptores(chat_id: int, args: str):
    data = _cargar_suscriptores()
    data = _expirar_vencidos(data)
    admin = data.get("admin_id", 0)
    if chat_id != admin:
        _send_raw(str(chat_id), "⛔ Solo el administrador puede gestionar suscriptores.")
        return

    suscripciones = data.get("suscripciones", {})
    partes = args.strip().split()
    if not partes:
        from datetime import date as _date
        hoy = _date.today()
        lineas = []
        for uid_str, expira in suscripciones.items():
            if expira is None:
                lineas.append(f"  • {uid_str} (permanente)")
            else:
                dias_rest = (_date.fromisoformat(expira) - hoy).days
                lineas.append(f"  • {uid_str} (expira {expira}, restan {dias_rest}d)")
        _send_raw(str(chat_id),
            f"📋 <b>Suscriptores ({len(suscripciones)})</b>\n" + "\n".join(lineas) or "  (vacía)")
        return

    subcmd = partes[0].lower()
    if subcmd == "add" and len(partes) >= 2:
        try:
            uid = int(partes[1])
            uid_str = str(uid)
            from datetime import date as _date, timedelta
            expira = (_date.today() + timedelta(days=30)).isoformat()
            if uid_str in suscripciones and suscripciones[uid_str] is not None:
                suscripciones[uid_str] = expira
                _send_raw(str(chat_id), f"✅ Suscripción de {uid} renovada hasta {expira}.")
            elif uid_str in suscripciones and suscripciones[uid_str] is None:
                _send_raw(str(chat_id), f"ℹ️ {uid} ya tiene acceso permanente.")
                return
            else:
                suscripciones[uid_str] = expira
                _send_raw(str(chat_id), f"✅ Usuario {uid} añadido hasta {expira}.")
            data["suscripciones"] = suscripciones
            _guardar_suscriptores(data)
        except ValueError:
            _send_raw(str(chat_id), "❌ ID inválido. Usa: /suscriptores add <ID>")
        return

    if subcmd == "del" and len(partes) >= 2:
        uid_str = partes[1]
        if uid_str in suscripciones:
            del suscripciones[uid_str]
            data["suscripciones"] = suscripciones
            _guardar_suscriptores(data)
            _send_raw(str(chat_id), f"🗑️ Usuario {uid_str} eliminado.")
        else:
            _send_raw(str(chat_id), f"❌ {uid_str} no está en la lista.")
        return

    _send_raw(str(chat_id), "❌ Usa: /suscriptores add <ID> | del <ID> | (sin args para listar)")


def _cmd_reiniciar(chat_id: int):
    """Re-analiza MLB + LMB en un thread y notifica el resultado."""
    data = _cargar_suscriptores()
    admin = data.get("admin_id", 0)
    if chat_id != admin:
        _send_raw(str(chat_id), "⛔ Solo el administrador puede reiniciar.")
        return

    _send_raw(str(chat_id), "🔄 Ejecutando análisis completo MLB + LMB + Fútbol...")

    def _work():
        try:
            import data_manager as dm
            resultados = []

            dm.inicializar_csv()

            # MLB
            try:
                from railway_app.scheduler_async import tarea_analisis_mlb
                tarea_analisis_mlb()
                resultados.append("✅ MLB completado")
            except Exception as e:
                resultados.append(f"❌ MLB error: {e}")
                logger.error(f"MLB reinicio error: {e}")

            # LMB
            try:
                from railway_app.scheduler_async import tarea_analisis_lmb
                tarea_analisis_lmb()
                resultados.append("✅ LMB completado")
            except Exception as e:
                resultados.append(f"❌ LMB error: {e}")
                logger.error(f"LMB reinicio error: {e}")

            # Fútbol
            try:
                import subprocess
                result = subprocess.run(
                    ["python", "main.py", "--ahora"],
                    cwd=config.FUTBOL_DIR,
                    capture_output=True, text=True, timeout=120, encoding="utf-8"
                )
                if result.returncode == 0:
                    resultados.append(f"✅ Fútbol completado")
                    if result.stdout:
                        for line in result.stdout.strip().split('\n')[-3:]:
                            resultados.append(f"  {line}")
                else:
                    resultados.append(f"❌ Fútbol error: {result.stderr[:200] if result.stderr else 'exit code ' + str(result.returncode)}")
                    logger.error(f"Fútbol error: {result.stderr[:500]}")
            except Exception as e:
                resultados.append(f"❌ Fútbol error: {e}")
                logger.error(f"Fútbol reinicio error: {e}")

            _send_raw(str(chat_id),
                "✅ <b>Análisis completo finalizado</b>\n\n" +
                "\n".join(f"  {r}" for r in resultados))

            # Sync live_data.json to GitHub Pages
            _send_raw(str(chat_id), "🔄 Publicando live_data.json en GitHub Pages...")
            try:
                from miniapp_publisher import publicar_live_data
                ok = publicar_live_data()
                if ok:
                    _send_raw(str(chat_id), "✅ Mini app actualizada en GitHub Pages!")
                else:
                    _send_raw(str(chat_id), "⚠️ Sync falló — mini app puede estar desactualizada.")
            except Exception as e:
                logger.error(f"Publish live_data error: {e}")
                _send_raw(str(chat_id), f"⚠️ Error publicando: {e}")

        except Exception as e:
            logger.error(f"Reinicio error: {e}")
            _send_raw(str(chat_id), f"❌ Error: {e}")

    t = threading.Thread(target=_work, daemon=True)
    t.start()


def _cmd_deploy(chat_id: int):
    """Trigger a Railway deployment via API."""
    data = _cargar_suscriptores()
    admin = data.get("admin_id", 0)
    if chat_id != admin:
        _send_raw(str(chat_id), "⛔ Solo el administrador puede desplegar.")
        return

    token = os.environ.get("RAILWAY_API_TOKEN", "")
    project_id = os.environ.get("RAILWAY_PROJECT_ID", "")
    service_id = os.environ.get("RAILWAY_SERVICE_ID", "")

    if not token or not service_id:
        _send_raw(str(chat_id),
            "⚠️ Variables de Railway no configuradas.\n"
            "Asegúrate de tener RAILWAY_API_TOKEN y RAILWAY_SERVICE_ID en las variables de entorno.")
        return

    _send_raw(str(chat_id), "🚀 Iniciando deploy en Railway...")

    def _work():
        try:
            import requests as _req
            url = "https://backboard.railway.app/graphql/v2"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            query = """
            mutation {
              serviceInstanceDeploy(input: {
                serviceId: "%s"
              }) {
                id
                status
              }
            }
            """ % service_id

            r = _req.post(url, json={"query": query}, headers=headers, timeout=15)
            if r.status_code == 200:
                resp = r.json()
                if resp.get("data", {}).get("serviceInstanceDeploy"):
                    dep = resp["data"]["serviceInstanceDeploy"]
                    _send_raw(str(chat_id),
                        f"✅ Deploy iniciado!\n"
                        f"ID: <code>{dep['id'][:8]}</code>\n"
                        f"Estado: {dep['status']}")
                else:
                    errors = resp.get("errors", [])
                    msg = errors[0].get("message", "Error desconocido") if errors else "Error desconocido"
                    _send_raw(str(chat_id), f"❌ Error de Railway API:\n<code>{msg[:200]}</code>")
            else:
                _send_raw(str(chat_id), f"❌ HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            _send_raw(str(chat_id), f"❌ Error: {e}")

    t = threading.Thread(target=_work, daemon=True)
    t.start()


def _cmd_reload(chat_id: int):
    """Recarga módulos principales sin reiniciar el proceso."""
    data = _cargar_suscriptores()
    admin = data.get("admin_id", 0)
    if chat_id != admin:
        _send_raw(str(chat_id), "⛔ Solo el administrador puede recargar.")
        return

    _send_raw(str(chat_id), "🔄 Recargando módulos...")

    import importlib
    modulos = ["config", "data_manager", "scheduler", "miniapp_publisher", "telegram_handler"]
    resultados = []

    for nombre in modulos:
        try:
            mod = importlib.import_module(nombre)
            importlib.reload(mod)
            resultados.append(f"✅ {nombre}")
        except Exception as e:
            resultados.append(f"❌ {nombre}: {e}")
            logger.error(f"Reload error ({nombre}): {e}")

    # Re-apuntar las referencias locales en este handler
    import config as _cfg
    import data_manager as _dm
    global config, dm
    config = _cfg
    dm = _dm

    _send_raw(str(chat_id),
        "✅ <b>Módulos recargados</b>\n\n" +
        "\n".join(f"  {r}" for r in resultados) +
        "\n\nEjecuta /reiniciar para refrescar datos."
    )


# ── Procesador de updates ─────────────────────────────────────────────
def procesar_comando(chat_id, text: str):
    """Procesa un comando de Telegram. Usado por polling y webhook."""
    if not chat_id or not text:
        return

    # /start
    if text.startswith("/start"):
        if _esta_autorizado(chat_id):
            data = _cargar_suscriptores()
            es_admin = chat_id == data.get("admin_id", 0)
            cmds = (
                "📊 <b>Comandos disponibles:</b>\n"
                "  /actualizar — Ver resultados del día (MLB + LMB + Fútbol)\n"
                "  /futbol — Ver análisis de fútbol\n"
                "  /suscribirse — Abrir Mini App\n"
                "  /borrar — Eliminar mis datos del sistema"
            )
            if es_admin:
                cmds += "\n  /suscriptores — Gestionar suscriptores"
                cmds += "\n  /reiniciar — Reiniciar bot (MLB+LMB+Fútbol)"
                cmds += "\n  /deploy — Desplegar en Railway"
                cmds += "\n  /reload — Recargar código sin reiniciar"
            _send_raw(str(chat_id),
                "⚾ <b>MLB Analytics</b>\n\n"
                "Bienvenido al sistema de análisis MLB.\n\n"
                + cmds,
                mini_app=True
            )
        else:
            _send_raw(str(chat_id),
                "⚾ <b>MLB Analytics</b>\n\n"
                "Bienvenido.\n\n"
                "🔒 Acceso exclusivo para suscriptores.\n"
                f"Contacta a @{config.ADMIN_USERNAME} para obtener acceso.",
                mini_app=True
            )
        return

    # /actualizar
    if text.startswith("/actualizar"):
        if _esta_autorizado(chat_id):
            _cmd_actualiza(str(chat_id))
        else:
            _send_raw(str(chat_id),
                "🔒 Acceso restringido.\n"
                f"Contacta a @{config.ADMIN_USERNAME} para obtener acceso.",
                mini_app=True
            )
        return

    # /futbol
    if text.startswith("/futbol"):
        if _esta_autorizado(chat_id):
            _cmd_futbol(str(chat_id))
        else:
            _send_raw(str(chat_id),
                "🔒 Acceso restringido.\n"
                f"Contacta a @{config.ADMIN_USERNAME} para obtener acceso.",
                mini_app=True
            )
        return

    # /borrar o /delete
    if text.startswith("/borrar") or text.startswith("/delete"):
        if _eliminar_usuario(chat_id):
            _send_raw(str(chat_id),
                "🗑️ <b>Datos eliminados</b>\n\n"
                "Tus datos han sido eliminados del sistema.\n"
                "Gracias por usar el servicio.",
                mini_app=True
            )
        else:
            _send_raw(str(chat_id),
                "ℹ️ No se encontraron datos asociados a tu cuenta.\n"
                "Si eres el administrador, no puedes eliminarte desde aquí.",
                mini_app=True
            )
        return

    # /suscribirse
    if text.startswith("/suscribirse"):
        if chat_id:
            _send_raw(str(chat_id),
                "📱 <b>Abrir Mini App</b>\nToca el botón de abajo para ver el análisis en vivo.",
                mini_app=True)
        return

    # /suscriptores — solo admin
    if text.startswith("/suscriptores"):
        if chat_id:
            _cmd_suscriptores(chat_id, text[len("/suscriptores"):].strip())
        return

    # /reiniciar — solo admin
    if text.startswith("/reiniciar"):
        _cmd_reiniciar(chat_id)
        return

    # /deploy — solo admin
    if text.startswith("/deploy"):
        _cmd_deploy(chat_id)
        return

    # /reload — solo admin
    if text.startswith("/reload"):
        _cmd_reload(chat_id)
        return


def handle_updates():
    global _last_update_id
    logger.info("Telegram handler: polling iniciado")
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"

    while True:
        try:
            r = requests.get(url, params={
                "offset": _last_update_id,
                "timeout": 10,
                "allowed_updates": json.dumps(["message"]),
            }, timeout=15)
            if r.status_code != 200:
                time.sleep(5)
                continue
            updates = r.json().get("result", [])
            for upd in updates:
                _last_update_id = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat_id = msg.get("chat", {}).get("id")
                if not chat_id:
                    continue

                text = (msg.get("text") or "").strip()
                if not text:
                    continue

                procesar_comando(chat_id, text)

        except Exception as e:
            logger.error(f"Telegram handler error: {e}")
            time.sleep(5)


def iniciar():
    """Arranca el handler en un thread daemon. Configura el Menu Button de Mini App."""
    # Botón permanente de Mini App en la barra de input del chat
    try:
        requests.post(
            f"{TELEGRAM_URL}/setChatMenuButton",
            json={
                "menu_button": {
                    "type": "web_app",
                    "text": "📱 Mini App",
                    "web_app": {"url": MINIAPP_URL},
                }
            },
            timeout=5,
        )
    except Exception as e:
        logger.warning(f"No se pudo configurar Menu Button: {e}")

    # Registrar comandos en el menú de Telegram
    try:
        requests.post(
            f"{TELEGRAM_URL}/setMyCommands",
            json={
                "commands": [
                    {"command": "start", "description": "Ver comandos disponibles"},
                    {"command": "actualizar", "description": "Ver resultados del día (MLB+LMB+Fútbol)"},
                    {"command": "futbol", "description": "Ver análisis de fútbol"},
                    {"command": "suscribirse", "description": "Abrir Mini App"},
                    {"command": "borrar", "description": "Eliminar mis datos del sistema"},
                ]
            },
            timeout=5,
        )
    except Exception as e:
        logger.warning(f"No se pudieron registrar comandos: {e}")

    hilo = threading.Thread(target=handle_updates, daemon=True, name="telegram-cmd")
    hilo.start()
    logger.info("Telegram handler: thread iniciado")
