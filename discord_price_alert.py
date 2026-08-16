"""
Standalone-Skript fuer GitHub Actions: prueft den LS9VFS-Kurs unabhaengig
von der Streamlit-App und meldet sich per Discord. Wird per Cron alle 5 Min
ausgefuehrt (siehe .github/workflows/price-alert.yml).

State liegt jetzt auf dem GitHub-Branch config.GITHUB_STATE_BRANCH und wird
ueber die Contents API gelesen/geschrieben (github_store.py) - kein
Branch-Checkout/-Push mehr noetig.
"""
import datetime
import logging
import os
import sys

import requests

import config
import github_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL", "")  # optional, s. Setup-Hinweis
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")  # von Actions automatisch gesetzt
GITHUB_TOKEN = os.environ.get("GH_STATE_TOKEN", "")  # secrets.GITHUB_TOKEN


def get_live_market_data():
    params = {
        "container": "chart1",
        "instrumentId": config.LS_INSTRUMENT_ID,
        "marketId": "1",
        "quotetype": "mid",
        "series": "intraday,history,flags",
        "type": "",
        "localeId": "2",
    }
    r = requests.get(config.LS_TC_BASE_URL, params=params, headers=config.LS_TC_HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()

    intraday = (
        data.get("series", {}).get("intraday", {}).get("data")
        or data.get("intraday", {}).get("data")
        or []
    )
    if not intraday:
        raise ValueError("Keine Intraday-Daten in der ls-tc.de Antwort gefunden.")

    akt = float(intraday[-1][1])

    history = (
        data.get("series", {}).get("history", {}).get("data")
        or data.get("history", {}).get("data")
        or []
    )
    if len(history) >= 2:
        vor = float(history[-2][1])
    else:
        vor = float(data.get("previousClose", intraday[0][1]))

    if akt <= 0 or vor <= 0:
        raise ValueError("Ungueltige Kurswerte von ls-tc.de erhalten.")
    return akt, vor


def send_discord(msg):
    if not DISCORD_WEBHOOK_URL:
        logging.warning("Kein DISCORD_WEBHOOK_URL gesetzt, ueberspringe Versand.")
        return False
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=10)
        if r.status_code not in (200, 204):
            logging.error(f"Discord antwortete mit Status {r.status_code}: {r.text[:300]}")
            return False
        return True
    except Exception as e:
        logging.error(f"Discord-Versand fehlgeschlagen: {e}")
        return False


def ping_healthcheck():
    """Dead-Man's-Switch: bestaetigt einem externen Watchdog (z.B.
    healthchecks.io), dass dieser Lauf erfolgreich durchgelaufen ist. Bleibt
    dieser Ping laenger als erwartet aus, meldet der Watchdog-Dienst SELBST
    (unabhaengig von diesem Skript!) einen Ausfall - z.B. per E-Mail."""
    if not HEALTHCHECK_URL:
        return
    try:
        requests.get(HEALTHCHECK_URL, timeout=10)
    except Exception as e:
        logging.error(f"Healthcheck-Ping fehlgeschlagen: {e}")


def log_price_history(akt, now):
    """Haengt jeden abgerufenen Kurs an eine eigene, monatlich rotierende
    CSV-Datei an - baut so ueber die Zeit eine eigene, von ls-tc.de
    unabhaengige Preis-Zeitreihe auf (Basis fuer spaeteres eigenes
    Backtesting / echte Intraday-Charts)."""
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return
    path = config.price_history_csv_path(now.date())
    line = f"{now.isoformat()},{akt:.4f}"
    github_store.append_csv_line(
        GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, line, GITHUB_TOKEN,
        header="timestamp,price", message="price history append [skip ci]"
    )


def check_high_watermark(akt, now):
    """Ersetzt das nicht funktionierende 'Last Login'-Signal: eigene,
    zuverlaessige Berechnung des Allzeithochs aus den selbst gesammelten
    Kursdaten. Neues Hoch = finanziell relevanter als ein Login-Zeitstempel,
    da ab hier bei weiteren Gewinnen Performance Fee (config.PERFORMANCE_FEE_PCT)
    faellig wird."""
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return
    state, _ = github_store.get_json(
        GITHUB_REPO, config.GITHUB_STATE_BRANCH, config.STATE_PATH_HIGH_WATERMARK,
        GITHUB_TOKEN, default=None
    )
    if state is None or "high_watermark" not in state:
        # Erste Initialisierung: nur speichern, kein Alarm (kein echter
        # Vergleichswert vorhanden - App korrigiert das ggf. noch auf den
        # echten historischen Höchststand, siehe app.py).
        github_store.put_json(
            GITHUB_REPO, config.GITHUB_STATE_BRANCH, config.STATE_PATH_HIGH_WATERMARK,
            {"high_watermark": akt, "erreicht_am": now.isoformat()}, GITHUB_TOKEN,
            message="init high watermark [skip ci]"
        )
        return

    bisheriges_hoch = float(state.get("high_watermark", 0))
    if akt > bisheriges_hoch:
        send_discord(
            f"🏆 **Neues Allzeithoch ({config.WKN})** 🏆\n"
            f"Aktueller Kurs: **{akt:.3f}€** (bisher: {bisheriges_hoch:.3f}€)\n"
            f"Hinweis: Ab neuen Höchstständen wird bei weiteren Gewinnen "
            f"i.d.R. Performance Fee ({config.PERFORMANCE_FEE_PCT:.1f}%) fällig.\n"
            f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}"
        )
        github_store.put_json(
            GITHUB_REPO, config.GITHUB_STATE_BRANCH, config.STATE_PATH_HIGH_WATERMARK,
            {"high_watermark": akt, "erreicht_am": now.isoformat()}, GITHUB_TOKEN,
            message="update high watermark [skip ci]"
        )


def main():
    now = datetime.datetime.now()

    try:
        akt, vor = get_live_market_data()
    except Exception as e:
        logging.error(f"Kursabruf fehlgeschlagen: {e}")
        # Bewusst kein Discord-Spam bei jedem einzelnen Fehler; der
        # Healthcheck-Ping bleibt in diesem Fall ebenfalls aus, sodass der
        # Watchdog nach Ausbleiben mehrerer Pings selbst Alarm schlaegt.
        sys.exit(1)

    pct_change = ((akt - vor) / vor) * 100

    log_price_history(akt, now)
    check_high_watermark(akt, now)

    if GITHUB_REPO and GITHUB_TOKEN:
        state, _ = github_store.get_json(
            GITHUB_REPO, config.GITHUB_STATE_BRANCH, config.STATE_PATH_PRICE_ALERT,
            GITHUB_TOKEN, default={"unter_schwelle": False}
        )
    else:
        state = {"unter_schwelle": False}

    routine_msg = (
        f"📊 **Kurs-Update ({config.WKN})**\n"
        f"Aktueller Kurs: **{akt:.3f}€**\n"
        f"Tagesveränderung: **{pct_change:+.2f}%**\n"
        f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}"
    )
    if not send_discord(routine_msg):
        logging.error("Routine-Update konnte NICHT an Discord gesendet werden (siehe Fehler oben).")

    aktuell_unter_schwelle = pct_change <= config.TAGESVERLUST_SCHWELLE_PCT
    war_unter_schwelle = state.get("unter_schwelle", False)

    if aktuell_unter_schwelle and not war_unter_schwelle:
        send_discord(
            f"🚨 **SCHWELLE UNTERSCHRITTEN ({config.WKN})** 🚨\n"
            f"Tagesveränderung: **{pct_change:+.2f}%** "
            f"(Schwelle: {config.TAGESVERLUST_SCHWELLE_PCT:+.1f}%)\n"
            f"Aktueller Kurs: **{akt:.3f}€**"
        )
        state["unter_schwelle"] = True
    elif not aktuell_unter_schwelle and war_unter_schwelle:
        send_discord(
            f"✅ **Entwarnung ({config.WKN})**\n"
            f"Tagesveränderung wieder über {config.TAGESVERLUST_SCHWELLE_PCT:+.1f}%: "
            f"**{pct_change:+.2f}%**\n"
            f"Aktueller Kurs: **{akt:.3f}€**"
        )
        state["unter_schwelle"] = False

    if GITHUB_REPO and GITHUB_TOKEN:
        github_store.put_json(
            GITHUB_REPO, config.GITHUB_STATE_BRANCH, config.STATE_PATH_PRICE_ALERT,
            state, GITHUB_TOKEN, message="update price alert state [skip ci]"
        )

    ping_healthcheck()
    logging.info(f"OK: Kurs={akt:.3f} Veraenderung={pct_change:+.2f}% unter_schwelle={state['unter_schwelle']}")


if __name__ == "__main__":
    main()
