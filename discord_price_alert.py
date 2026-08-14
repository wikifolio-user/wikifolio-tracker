"""
Standalone-Skript fuer GitHub Actions: prueft den LS9VFS-Kurs unabhaengig
von der Streamlit-App und meldet sich per Discord. Wird per Cron alle 5 Min
ausgefuehrt (siehe .github/workflows/price-alert.yml).

State (Cooldown, ob wir gerade unter der Schwelle sind) wird in
price_alert_state.json auf einem separaten Git-Branch persistiert, damit
der Job zwischen den Laeufen "weiss", was beim letzten Mal war.
"""
import datetime
import json
import logging
import os
import sys

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- KONSTANTEN (synchron zur Haupt-App halten) ---
WKN = "LS9VFS"
LS_INSTRUMENT_ID = "3865540"
TAGESVERLUST_SCHWELLE_PCT = -1.0

LS_TC_BASE_URL = "https://www.ls-tc.de/_rpc/json/instrument/chart/dataForInstrument"
LS_TC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": f"https://www.ls-tc.de/de/wikifolio/{LS_INSTRUMENT_ID}",
}

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
STATE_FILE = os.environ.get("PRICE_ALERT_STATE_FILE", "price_alert_state.json")


def get_live_market_data():
    params = {
        "container": "chart1",
        "instrumentId": LS_INSTRUMENT_ID,
        "marketId": "1",
        "quotetype": "mid",
        "series": "intraday,history,flags",
        "type": "",
        "localeId": "2",
    }
    r = requests.get(LS_TC_BASE_URL, params=params, headers=LS_TC_HEADERS, timeout=10)
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


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"unter_schwelle": False}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


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


def main():
    now = datetime.datetime.now()
    try:
        akt, vor = get_live_market_data()
    except Exception as e:
        logging.error(f"Kursabruf fehlgeschlagen: {e}")
        # Bewusst kein Discord-Spam bei jedem einzelnen Fehler - nur loggen.
        sys.exit(1)

    pct_change = ((akt - vor) / vor) * 100

    state = load_state()

    # Routine-Update bei jedem Lauf (Cron-Takt bestimmt die Frequenz, z.B. 5 Min)
    routine_msg = (
        f"📊 **Kurs-Update ({WKN})**\n"
        f"Aktueller Kurs: **{akt:.3f}€**\n"
        f"Tagesveränderung: **{pct_change:+.2f}%**\n"
        f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}"
    )
    routine_ok = send_discord(routine_msg)
    if not routine_ok:
        logging.error("Routine-Update konnte NICHT an Discord gesendet werden (siehe Fehler oben).")

    # Schwellen-Alarm nur beim Ueber-/Unterschreiten (nicht bei jedem Lauf)
    aktuell_unter_schwelle = pct_change <= TAGESVERLUST_SCHWELLE_PCT
    war_unter_schwelle = state.get("unter_schwelle", False)

    if aktuell_unter_schwelle and not war_unter_schwelle:
        send_discord(
            f"🚨 **SCHWELLE UNTERSCHRITTEN ({WKN})** 🚨\n"
            f"Tagesveränderung: **{pct_change:+.2f}%** "
            f"(Schwelle: {TAGESVERLUST_SCHWELLE_PCT:+.1f}%)\n"
            f"Aktueller Kurs: **{akt:.3f}€**"
        )
        state["unter_schwelle"] = True
    elif not aktuell_unter_schwelle and war_unter_schwelle:
        send_discord(
            f"✅ **Entwarnung ({WKN})**\n"
            f"Tagesveränderung wieder über {TAGESVERLUST_SCHWELLE_PCT:+.1f}%: "
            f"**{pct_change:+.2f}%**\n"
            f"Aktueller Kurs: **{akt:.3f}€**"
        )
        state["unter_schwelle"] = False

    save_state(state)
    logging.info(f"OK: Kurs={akt:.3f} Veraenderung={pct_change:+.2f}% unter_schwelle={state['unter_schwelle']}")


if __name__ == "__main__":
    main()

