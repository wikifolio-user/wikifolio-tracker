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
import re
import sys
from zoneinfo import ZoneInfo

import requests

import config
import github_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL", "")  # optional, s. Setup-Hinweis
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")  # von Actions automatisch gesetzt
GITHUB_TOKEN = os.environ.get("GH_STATE_TOKEN", "")  # secrets.GITHUB_TOKEN

# --- MELDESCHWELLE FUER DAS ROUTINE-KURS-UPDATE ---
# Betrifft AUSSCHLIESSLICH die regelmaessige "Kurs-Update"-Nachricht: die wird
# nur noch verschickt, wenn sich der Kurs um mindestens diesen Prozentsatz
# gegenueber dem Vortag bewegt hat. Bei ruhigem Markt (z.B. +0,00%) bleibt es
# still, statt alle paar Minuten dieselbe Nicht-Nachricht zu schicken.
#
# WICHTIG: Alle echten Alarme sind davon NICHT betroffen und feuern
# unveraendert - Schwellen-Alarm (config.TAGESVERLUST_SCHWELLE_PCT),
# Entwarnung und Allzeithoch-Meldung.
ROUTINE_MELDESCHWELLE_PCT = 0.50

# Ein neues Allzeithoch wird erst gemeldet, wenn es mindestens so viel Prozent
# ueber dem zuletzt GEMELDETEN Hoch liegt. Der Hoechststand selbst wird immer
# still mitgefuehrt - nur die Benachrichtigung wird gebuendelt.
ATH_MELDESCHWELLE_PCT = 0.50

# --- UEBERWACHTE INSTRUMENTE ---
# Erster Eintrag ist die Hauptposition aus config.py (unveraendertes Verhalten,
# nutzt die bestehenden State-Pfade). Jeder weitere Eintrag bekommt EIGENE
# State-Dateien, damit Cooldowns, Allzeithoch und Kurshistorie sauber getrennt
# bleiben - sonst wuerden sich die Instrumente gegenseitig ueberschreiben.
#
# onvista_url: optionale Zweitquelle fuer den Plausibilitaets-Check. Fehlt sie,
# wird bei einem unplausiblen Sprung ohne Gegenprobe uebersprungen (sicherer
# als ein moeglicher Fehlalarm).
INSTRUMENTE = [
    {
        "wkn": config.WKN,
        "name": "Hauptindizes Global",
        "instrument_id": config.LS_INSTRUMENT_ID,
        "onvista_url": "https://www.onvista.de/derivate/Index-Zertifikate/302671598-LS9VFS-DE000LS9VFS2",
    },
    {
        "wkn": "LS9VSU",
        "name": "FF Inlinetrading",
        # Wird unten automatisch aus config.BENCHMARKS aufgeloest - der Wert
        # ist dort als Vergleichswert bereits mit seiner Instrument-ID
        # hinterlegt. Faellt die Aufloesung aus, hier manuell eintragen.
        "instrument_id": None,
        "onvista_url": None,
    },
]


def _ergaenze_ids_aus_benchmarks():
    """Fuellt fehlende instrument_id-Werte aus config.BENCHMARKS auf. Dort sind
    die Vergleichswerte als {Label: instrument_id} hinterlegt - der Abgleich
    laeuft ueber WKN oder Namensbestandteil im Label, damit dieselbe ID nicht
    an zwei Stellen gepflegt werden muss."""
    benchmarks = getattr(config, "BENCHMARKS", {}) or {}
    for inst in INSTRUMENTE:
        if inst.get("instrument_id"):
            continue
        wkn = (inst.get("wkn") or "").upper()
        name = (inst.get("name") or "").upper()
        for label, inst_id in benchmarks.items():
            label_gross = str(label).upper()
            if (wkn and wkn in label_gross) or (name and name in label_gross):
                inst["instrument_id"] = inst_id
                logging.info(
                    f"{inst['wkn']}: Instrument-ID {inst_id} aus config.BENCHMARKS "
                    f"(Eintrag '{label}') uebernommen."
                )
                break
        else:
            logging.warning(
                f"{inst['wkn']}: keine Instrument-ID gefunden - weder direkt gesetzt "
                f"noch in config.BENCHMARKS. Wird uebersprungen."
            )


_ergaenze_ids_aus_benchmarks()


def state_pfad(basis_pfad, inst):
    """State-Pfad je Instrument. Die Hauptposition behaelt ihre bestehenden
    Pfade (kein Datenverlust beim Update), alle weiteren bekommen die WKN
    ans Ende gehaengt."""
    if inst["wkn"] == config.WKN:
        return basis_pfad
    stamm, punkt, endung = basis_pfad.rpartition(".")
    return f"{stamm}_{inst['wkn']}.{endung}" if punkt else f"{basis_pfad}_{inst['wkn']}"


def get_live_market_data(instrument_id=None):
    """
    Holt den aktuellen Mid-Kurs von ls-tc.de. Vortageskurs: aus
    info.plotlines[id="previousDay"].value (siehe config.extract_previous_close
    - DAS ist der Ort, wo ls-tc.de den echten Vortageswert mitliefert, kein
    top-level 'previousClose'-Feld). Die History-Suche dient nur noch als
    Rueckfalloption.
    """
    params = {
        "container": "chart1",
        "instrumentId": instrument_id or config.LS_INSTRUMENT_ID,
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

    vor = config.extract_previous_close(data)

    if vor is None:
        history = (
            data.get("series", {}).get("history", {}).get("data")
            or data.get("history", {}).get("data")
            or []
        )
        vor = config.pick_previous_close_from_history(history)

    if vor is None:
        vor = float(intraday[0][1])

    if akt <= 0 or vor <= 0:
        raise ValueError("Ungueltige Kurswerte von ls-tc.de erhalten.")
    return akt, vor


def hole_onvista_kontrollkurs(url):
    """Best-effort Kontrollkurs von onvista.de - unabhaengige Zweitquelle
    (Lang & Schwarz Notierung, gleicher Handelsplatz wie ls-tc.de), fuer den
    Plausibilitaets-Check bei verdaechtigen Kurssprüngen. Der Preis steht im
    normal ausgelieferten Seiteninhalt (kein Login, kein JS noetig).
    Gibt None zurueck, wenn's nicht klappt - dann greift nur die feste
    Prozent-Schwelle allein, kein Absturz."""
    if not url:
        return None
    try:
        r = requests.get(
            url,
            headers={"User-Agent": config.LS_TC_HEADERS["User-Agent"]},
            timeout=8,
        )
        r.raise_for_status()
        match = re.search(r"Lang\s*&amp;\s*Schwarz.{0,400}?(\d{1,4},\d{2,3})\s*EUR", r.text, re.DOTALL)
        if not match:
            return None
        return float(match.group(1).replace(",", "."))
    except Exception as e:
        logging.warning(f"onvista-Kontrollkurs nicht abrufbar (kein Problem, nur Zweitquelle): {e}")
        return None


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


def log_price_history(akt, now, inst):
    """Haengt jeden abgerufenen Kurs an eine eigene, monatlich rotierende
    CSV-Datei an - baut so ueber die Zeit eine eigene, von ls-tc.de
    unabhaengige Preis-Zeitreihe auf (Basis fuer spaeteres eigenes
    Backtesting / echte Intraday-Charts)."""
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return
    path = state_pfad(config.price_history_csv_path(now.date()), inst)
    line = f"{now.isoformat()},{akt:.4f}"
    github_store.append_csv_line(
        GITHUB_REPO, config.GITHUB_STATE_BRANCH, path, line, GITHUB_TOKEN,
        header="timestamp,price", message="price history append [skip ci]"
    )


def check_high_watermark(akt, now, inst):
    """Verfolgt das Allzeithoch aus den selbst gesammelten Kursdaten. Ab einem
    neuen Hoch wird bei weiteren Gewinnen Performance Fee
    (config.PERFORMANCE_FEE_PCT) faellig - deshalb ist das meldenswert.

    WICHTIG: Der gespeicherte Hoechststand wird bei JEDEM neuen Hoch still
    aktualisiert, eine Discord-Nachricht gibt es aber erst, wenn das Hoch
    mindestens ATH_MELDESCHWELLE_PCT ueber dem zuletzt GEMELDETEN Hoch liegt.
    Ohne diese Bremse kaeme in einem steigenden Markt alle 5 Minuten eine
    Meldung - schon ein Zehntelcent mehr ist formal ein neues Allzeithoch."""
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return
    hw_pfad = state_pfad(config.STATE_PATH_HIGH_WATERMARK, inst)
    state, _ = github_store.get_json(
        GITHUB_REPO, config.GITHUB_STATE_BRANCH, hw_pfad, GITHUB_TOKEN, default=None
    )
    if state is None or "high_watermark" not in state:
        # Erste Initialisierung: nur speichern, kein Alarm (kein echter
        # Vergleichswert vorhanden - App korrigiert das ggf. noch auf den
        # echten historischen Höchststand, siehe app.py).
        github_store.put_json(
            GITHUB_REPO, config.GITHUB_STATE_BRANCH, hw_pfad,
            {"high_watermark": akt, "erreicht_am": now.isoformat(),
             "zuletzt_gemeldet": akt}, GITHUB_TOKEN,
            message=f"init high watermark {inst['wkn']} [skip ci]"
        )
        return

    bisheriges_hoch = float(state.get("high_watermark", 0))
    if akt <= bisheriges_hoch:
        return

    # Basis fuer die Meldeschwelle ist das zuletzt gemeldete Hoch. Fehlt es
    # (Altbestand vor diesem Update), dient das bisherige Hoch als Basis.
    zuletzt_gemeldet = float(state.get("zuletzt_gemeldet") or bisheriges_hoch)
    anstieg_pct = ((akt - zuletzt_gemeldet) / zuletzt_gemeldet * 100) if zuletzt_gemeldet else 0.0
    melden = anstieg_pct >= ATH_MELDESCHWELLE_PCT

    if melden:
        send_discord(
            f"🏆 **Neues Allzeithoch ({inst['wkn']})** 🏆\n"
            f"{inst['name']}\n"
            f"Aktueller Kurs: **{akt:.3f}€** (zuletzt gemeldet: {zuletzt_gemeldet:.3f}€, "
            f"{anstieg_pct:+.2f}%)\n"
            f"Hinweis: Ab neuen Höchstständen wird bei weiteren Gewinnen "
            f"i.d.R. Performance Fee ({config.PERFORMANCE_FEE_PCT:.1f}%) fällig.\n"
            f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}"
        )
    else:
        logging.info(
            f"{inst['wkn']}: neues Hoch {akt:.3f}€ still gespeichert "
            f"({anstieg_pct:+.2f}% über zuletzt gemeldetem {zuletzt_gemeldet:.3f}€, "
            f"Meldeschwelle {ATH_MELDESCHWELLE_PCT:.2f}%)."
        )

    github_store.put_json(
        GITHUB_REPO, config.GITHUB_STATE_BRANCH, hw_pfad,
        {
            "high_watermark": akt,
            "erreicht_am": now.isoformat(),
            # Nur fortschreiben, wenn wirklich gemeldet wurde - sonst wuerde die
            # Schwelle bei jedem Mini-Hoch neu ansetzen und nie ausloesen.
            "zuletzt_gemeldet": akt if melden else zuletzt_gemeldet,
        },
        GITHUB_TOKEN,
        message=f"update high watermark {inst['wkn']} [skip ci]"
    )


def verarbeite_instrument(inst, now):
    """Kompletter Ablauf fuer EIN Instrument. Gibt True zurueck, wenn der Lauf
    technisch erfolgreich war (auch wenn bewusst keine Nachricht rausging),
    False bei einem echten Fehler.

    Bewusst so gekapselt, dass ein Fehler bei einem Instrument die anderen
    NICHT verhindert - sonst wuerde ein einzelner Ausfall die gesamte
    Ueberwachung lahmlegen."""
    kennung = f"{inst['name']} ({inst['wkn']})"

    if not inst.get("instrument_id"):
        logging.warning(
            f"{kennung}: keine instrument_id hinterlegt - uebersprungen. "
            f"Die ID steht in der ls-tc.de-URL des Produkts."
        )
        return True  # Konfigurationsluecke, kein technischer Fehler

    try:
        akt, vor = get_live_market_data(inst["instrument_id"])
    except Exception as e:
        logging.error(f"{kennung}: Kursabruf fehlgeschlagen: {e}")
        return False

    pct_change = ((akt - vor) / vor) * 100

    # --- PLAUSIBILITAETS-CHECK: unrealistische Kurssprünge verwerfen ---
    # Werte jenseits der Schwelle sind mit hoher Wahrscheinlichkeit ein
    # Uebertragungsfehler von ls-tc.de, keine echte Marktbewegung.
    if abs(pct_change) > config.PLAUSIBILITAETS_SCHWELLE_PCT:
        kontrollkurs = hole_onvista_kontrollkurs(inst.get("onvista_url"))
        onvista_bestaetigt = (
            kontrollkurs is not None and akt > 0
            and abs(kontrollkurs - akt) / akt * 100 <= 5.0
        )
        if onvista_bestaetigt:
            logging.info(
                f"{kennung}: Sprung wirkte unplausibel ({pct_change:+.2f}%), aber onvista.de "
                f"bestaetigt einen aehnlichen Kurs ({kontrollkurs:.3f}€ vs. {akt:.3f}€) - "
                f"scheint echt zu sein, wird normal weiterverarbeitet."
            )
        else:
            logging.error(
                f"{kennung}: Unplausibler Kurssprung verworfen: {vor:.3f}€ -> {akt:.3f}€ "
                f"({pct_change:+.2f}%, Schwelle: ±{config.PLAUSIBILITAETS_SCHWELLE_PCT:.0f}%). "
                f"Kontrollkurs: {kontrollkurs if kontrollkurs else 'nicht verfuegbar'}. "
                f"Ueberspringe dieses Instrument ohne Discord-Nachricht."
            )
            return True  # technisch sauber gelaufen, nur der Wert war unbrauchbar

    log_price_history(akt, now, inst)
    check_high_watermark(akt, now, inst)

    alarm_pfad = state_pfad(config.STATE_PATH_PRICE_ALERT, inst)
    if GITHUB_REPO and GITHUB_TOKEN:
        state, _ = github_store.get_json(
            GITHUB_REPO, config.GITHUB_STATE_BRANCH, alarm_pfad,
            GITHUB_TOKEN, default={"unter_schwelle": False}
        )
    else:
        state = {"unter_schwelle": False}

    # --- ROUTINE-KURS-UPDATE: nur bei nennenswerter NEUER Bewegung ---
    # Zwei Bedingungen muessen zusammenkommen:
    #   1. Die Tagesveraenderung liegt bei mindestens ROUTINE_MELDESCHWELLE_PCT
    #   2. Sie hat sich seit der letzten Meldung um mindestens denselben Betrag
    #      weiterbewegt
    # Ohne (2) wuerde ab dem Ueberschreiten der Schwelle JEDER Lauf melden -
    # bei 5-Minuten-Takt also den ganzen Tag lang. Der Schwellen-Alarm unten
    # ist davon nicht betroffen und feuert unveraendert.
    zuletzt_gemeldet_pct = state.get("zuletzt_gemeldet_pct")
    ueber_schwelle = abs(pct_change) >= ROUTINE_MELDESCHWELLE_PCT
    if zuletzt_gemeldet_pct is None:
        genug_neue_bewegung = True
    else:
        genug_neue_bewegung = (
            abs(pct_change - float(zuletzt_gemeldet_pct)) >= ROUTINE_MELDESCHWELLE_PCT
        )

    if ueber_schwelle and genug_neue_bewegung:
        routine_msg = (
            f"📊 **Kurs-Update ({inst['wkn']})**\n"
            f"{inst['name']}\n"
            f"Aktueller Kurs: **{akt:.3f}€**\n"
            f"Tagesveränderung: **{pct_change:+.2f}%**\n"
            f"Stand: {now.strftime('%d.%m.%Y %H:%M Uhr')}"
        )
        if send_discord(routine_msg):
            state["zuletzt_gemeldet_pct"] = round(pct_change, 2)
        else:
            logging.error(f"{kennung}: Routine-Update konnte NICHT gesendet werden.")
    elif not ueber_schwelle:
        # Zurueck unter die Schwelle: Merker loeschen, damit beim naechsten
        # echten Ausbruch wieder gemeldet wird.
        if zuletzt_gemeldet_pct is not None:
            state["zuletzt_gemeldet_pct"] = None
        logging.info(
            f"{kennung}: Routine-Update uebersprungen ({pct_change:+.2f}% unter "
            f"±{ROUTINE_MELDESCHWELLE_PCT:.2f}%). Alarme bleiben unberuehrt."
        )
    else:
        logging.info(
            f"{kennung}: Routine-Update uebersprungen - {pct_change:+.2f}% liegt zwar "
            f"ueber der Schwelle, aber zu nah an der letzten Meldung "
            f"({zuletzt_gemeldet_pct:+.2f}%)."
        )

    aktuell_unter_schwelle = pct_change <= config.TAGESVERLUST_SCHWELLE_PCT
    war_unter_schwelle = state.get("unter_schwelle", False)

    if aktuell_unter_schwelle and not war_unter_schwelle:
        send_discord(
            f"🚨 **SCHWELLE UNTERSCHRITTEN ({inst['wkn']})** 🚨\n"
            f"{inst['name']}\n"
            f"Tagesveränderung: **{pct_change:+.2f}%** "
            f"(Schwelle: {config.TAGESVERLUST_SCHWELLE_PCT:+.1f}%)\n"
            f"Aktueller Kurs: **{akt:.3f}€**"
        )
        state["unter_schwelle"] = True
    elif not aktuell_unter_schwelle and war_unter_schwelle:
        send_discord(
            f"✅ **Entwarnung ({inst['wkn']})**\n"
            f"{inst['name']}\n"
            f"Tagesveränderung wieder über {config.TAGESVERLUST_SCHWELLE_PCT:+.1f}%: "
            f"**{pct_change:+.2f}%**\n"
            f"Aktueller Kurs: **{akt:.3f}€**"
        )
        state["unter_schwelle"] = False

    # Nur bei echtem Zustandswechsel schreiben - spart unnoetige Commits.
    state_veraendert = (
        state.get("unter_schwelle") != war_unter_schwelle
        or state.get("zuletzt_gemeldet_pct") != zuletzt_gemeldet_pct
    )
    if GITHUB_REPO and GITHUB_TOKEN and state_veraendert:
        github_store.put_json(
            GITHUB_REPO, config.GITHUB_STATE_BRANCH, alarm_pfad,
            state, GITHUB_TOKEN, message=f"update price alert state {inst['wkn']} [skip ci]"
        )

    logging.info(
        f"OK {kennung}: Kurs={akt:.3f} Veraenderung={pct_change:+.2f}% "
        f"unter_schwelle={state['unter_schwelle']}"
    )
    return True


def main():
    now = datetime.datetime.now(ZoneInfo("Europe/Berlin"))

    if not config.ist_handelszeit(now):
        logging.info(
            f"Außerhalb der Handelszeiten ({now.strftime('%a %d.%m.%Y %H:%M')} Europe/Berlin) "
            f"- überspringe Kursabruf und Discord-Nachrichten. Nur Healthcheck-Ping."
        )
        ping_healthcheck()  # Dead-Man's-Switch bleibt auch außerhalb der Handelszeiten "gruen"
        return

    # Jedes Instrument einzeln und unabhaengig abarbeiten. Ein Fehler bei einem
    # Wert darf die Ueberwachung der anderen nicht verhindern.
    ergebnisse = []
    for inst in INSTRUMENTE:
        try:
            ergebnisse.append(verarbeite_instrument(inst, now))
        except Exception as e:
            logging.exception(f"Unerwarteter Fehler bei {inst.get('wkn', '?')}: {e}")
            ergebnisse.append(False)

    # Healthcheck nur pingen, wenn MINDESTENS ein Instrument sauber lief -
    # sonst soll der Watchdog anschlagen. Schlaegt alles fehl, mit Exit-Code 1
    # enden, damit der Actions-Lauf sichtbar rot wird.
    if any(ergebnisse):
        ping_healthcheck()
    if not all(ergebnisse):
        logging.error("Mindestens ein Instrument konnte nicht verarbeitet werden.")
        if not any(ergebnisse):
            sys.exit(1)


if __name__ == "__main__":
    main()
