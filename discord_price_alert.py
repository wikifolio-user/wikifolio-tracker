"""
Standalone-Skript fuer GitHub Actions: prueft den LS9VFS-Kurs unabhaengig
von der Streamlit-App und meldet sich per Discord. Laeuft nur Mo-Fr waehrend
der Handelszeiten (siehe .github/workflows/price-alert.yml).

State liegt jetzt auf dem GitHub-Branch config.GITHUB_STATE_BRANCH und wird
ueber die Contents API gelesen/geschrieben (github_store.py) - kein
Branch-Checkout/-Push mehr noetig.

Dieser Job ist der EINZIGE Absender von Kurs-Alarmen und der einzige Schreiber
des Alarm-States (die App zeigt den State nur an). Grundregeln:
- State (unter_schwelle, zuletzt_gemeldet, ...) wird nur fortgeschrieben, wenn
  die Discord-Nachricht nachweislich angekommen ist (HTTP 2xx) - sonst
  versucht es der naechste Lauf erneut (ALM-01).
- Kein Kurs, unlesbarer State oder unplausible Daten -> kein Alarm, kein
  State-Schreiben (DEP-04).
- Logs enthalten nie URLs/Tokens, nur Fehlertyp und HTTP-Status (SEC-08).
"""
import copy
import datetime
import logging
import os
import re
import sys
import time
import traceback
from zoneinfo import ZoneInfo

import requests

import config
import github_store
import chronik

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

# Hysterese fuer die Entwarnung (Prozentpunkte): Nach einem Schwellen-Alarm
# kommt die Entwarnung erst, wenn der Kurs mindestens so viel UEBER der
# Schwelle liegt. Ohne Hysterese erzeugt ein Kurs, der um die Schwelle pendelt
# (-3,01 / -2,99 / -3,01 ...), bei jedem Lauf Alarm + Entwarnung.
# Ueberschreibbar per config.ALARM_HYSTERESE_PP.
HYSTERESE_PP = 0.5

# Discord-Rate-Limit (HTTP 429): hoechstens EIN kurzer Wiederholversuch, und
# nur wenn Discord hoechstens so lange warten laesst - der Job soll nie haengen.
DISCORD_429_MAX_WARTEN_S = 5.0


def hysterese_pp():
    wert = getattr(config, "ALARM_HYSTERESE_PP", None)
    try:
        return float(wert) if wert is not None else HYSTERESE_PP
    except (TypeError, ValueError):
        return HYSTERESE_PP


class VeralteteDaten(ValueError):
    """Die Intraday-Serie enthaelt (noch) keine Kurse von heute - z. B. vor dem
    ersten Tick oder an einem Feiertag ohne Handel. Kein technischer Fehler,
    aber auch keine Grundlage fuer Alarme."""

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
    {
        "wkn": "LS9VVK",
        "name": "Interesting_Leverage",
        "instrument_id": None,   # wird ebenfalls aus config.BENCHMARKS aufgeloest
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

    Gibt zusaetzlich tageshoch zurueck: den hoechsten Wert der GESAMTEN
    Intraday-Tickserie (nicht nur den letzten Tick). Wichtig fuer die
    Allzeithoch-Erkennung: bei 5-Minuten-Takt kann ein kurzer Spike auf ein
    neues Hoch laengst wieder abgeklungen sein, bis der naechste Lauf
    stattfindet - der letzte Tick allein wuerde diesen Spike verpassen. Die
    Intraday-Serie enthaelt aber alle Ticks des Tages, der Spike bleibt also
    sichtbar, auch wenn der Kurs beim Abruf schon wieder gefallen ist.
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

    # Letzter Tick muss von HEUTE sein - sonst wuerde z. B. die gestrige
    # Tagesbewegung als heutige gemeldet (falscher Alarm mit heutigem Datum).
    heute = datetime.datetime.now(ZoneInfo("Europe/Berlin")).date()
    try:
        tick_datum = datetime.datetime.fromtimestamp(
            float(intraday[-1][0]) / 1000, tz=ZoneInfo("Europe/Berlin")).date()
    except (TypeError, ValueError, OverflowError, OSError, IndexError):
        tick_datum = None  # Zeitstempel nicht auswertbar -> keine Pruefung moeglich
    if tick_datum is not None and tick_datum.year < 2000:
        tick_datum = None  # offenbar kein Millisekunden-Zeitstempel -> nicht pruefbar
    if tick_datum is not None and tick_datum < heute:
        raise VeralteteDaten(f"Letzter Tick vom {tick_datum.isoformat()}, noch kein Kurs von heute.")

    vor = config.extract_previous_close(data)

    if vor is None:
        history = (
            data.get("series", {}).get("history", {}).get("data")
            or data.get("history", {}).get("data")
            or []
        )
        vor = config.pick_previous_close_from_history(history)

    # KEIN Ersatzwert mehr (frueher: erster Intraday-Tick als "Vortageskurs").
    # Damit war die Tagesveraenderung frei erfunden und konnte Alarme ausloesen.
    if vor is None:
        raise ValueError("Kein Vortageskurs ermittelbar - Lauf fuer dieses Instrument uebersprungen.")

    if akt <= 0 or vor <= 0:
        raise ValueError("Ungueltige Kurswerte von ls-tc.de erhalten.")

    # Tageshoch nur aus plausiblen Ticks (ALM-04): ein einzelner Fehltick
    # (z. B. Kommafehler 990 statt 99) darf kein Allzeithoch erzeugen.
    tageshoch = akt
    for punkt in intraday:
        try:
            wert = float(punkt[1])
        except (TypeError, ValueError, IndexError):
            continue
        if wert > tageshoch and _plausibel(wert, vor):
            tageshoch = wert
    return akt, vor, tageshoch


def _plausibel(wert, basis):
    """True, wenn wert hoechstens PLAUSIBILITAETS_SCHWELLE_PCT von basis abweicht."""
    try:
        wert, basis = float(wert), float(basis)
    except (TypeError, ValueError):
        return False
    if wert <= 0 or basis <= 0:
        return False
    return abs(wert - basis) / basis * 100 <= float(config.PLAUSIBILITAETS_SCHWELLE_PCT)


def plausibles_tageshoch(akt, vor, tageshoch):
    """Uebernimmt das Tick-Maximum nur, wenn es gegenueber Vortageskurs ODER
    aktuellem Kurs innerhalb der Plausibilitaetsschwelle liegt - sonst gilt der
    aktuelle Kurs. Zweite Absicherung zusaetzlich zur Tick-Filterung oben."""
    if tageshoch is None:
        return akt
    if _plausibel(tageshoch, vor) or _plausibel(tageshoch, akt):
        return max(akt, float(tageshoch))
    logging.warning(
        f"Tageshoch {float(tageshoch):.3f} unplausibel (Kurs {akt:.3f}, Vortag {vor:.3f}) - "
        f"verwende aktuellen Kurs fuer die Allzeithoch-Pruefung."
    )
    return akt


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
        logging.warning(f"onvista-Kontrollkurs nicht abrufbar (kein Problem, nur Zweitquelle): "
                        f"{type(e).__name__}")
        return None


def _fehlertext(e):
    """Fehler fuers Log OHNE Nachrichtentext - requests-Meldungen enthalten die
    volle URL (beim Discord-Webhook inkl. Token). Nur Typ und ggf. HTTP-Status."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    return f"{type(e).__name__}" + (f" (HTTP {status})" if status else "")


def chronik_eintrag(titel, inhalt, schluessel, now):
    """Alarm zusaetzlich in die Chronik der App schreiben (Depot -> Chronik).
    schluessel ist ereignisbezogen (nicht minutengenau) - ein Wiederholungslauf
    nach einem Teilfehler erzeugt deshalb keinen doppelten Eintrag."""
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return False
    pfad = getattr(config, "STATE_PATH_TRADES_DB", None)
    if not pfad:
        return False
    try:
        ok = chronik.eintragen_github(
            github_store, GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, GITHUB_TOKEN,
            chronik.neuer_eintrag("alarm", titel, inhalt, schluessel=schluessel, zeitpunkt=now))
    except Exception as e:  # Chronik darf nie einen Alarm verhindern
        logging.error(f"Chronik-Eintrag '{schluessel}' fehlgeschlagen: {_fehlertext(e)}")
        return False
    if not ok:
        logging.info(f"Chronik-Eintrag '{schluessel}' nicht neu geschrieben (bereits vorhanden oder Schreibfehler).")
    return bool(ok)


def _retry_after_s(r):
    """Wartezeit aus einer 429-Antwort (Header Retry-After oder JSON retry_after), sonst None."""
    werte = []
    try:
        werte.append((r.headers or {}).get("Retry-After"))
    except Exception:
        pass
    try:
        body = r.json()
        if isinstance(body, dict):
            werte.append(body.get("retry_after"))
    except Exception:
        pass
    for w in werte:
        try:
            if w is not None:
                return max(0.0, float(w))
        except (TypeError, ValueError):
            continue
    return None


def send_discord(msg=None, embed=None):
    """Sendet entweder reinen Text (msg) oder ein Discord-Embed (embed) - ein
    Embed rendert als sauber formatierte Karte mit farbiger Randleiste,
    Titel und ausgerichteten Feldern statt als Fliesstext-Block.

    -> True NUR bei HTTP 2xx. Bei 429 (Rate-Limit) genau ein Wiederholversuch,
    falls Discord hoechstens DISCORD_429_MAX_WARTEN_S Sekunden warten laesst.
    Ins Log kommen nur Fehlertyp/Status, nie die Webhook-URL."""
    if not DISCORD_WEBHOOK_URL:
        logging.warning("Kein DISCORD_WEBHOOK_URL gesetzt, ueberspringe Versand.")
        return False
    payload = {"embeds": [embed]} if embed else {"content": msg}
    for versuch in (1, 2):
        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Discord-Versand fehlgeschlagen: {_fehlertext(e)}")
            return False
        status = getattr(r, "status_code", None)
        if isinstance(status, int) and 200 <= status < 300:
            return True
        if status == 429 and versuch == 1:
            warten = _retry_after_s(r)
            if warten is not None and warten <= DISCORD_429_MAX_WARTEN_S:
                logging.warning(f"Discord Rate-Limit (HTTP 429) - neuer Versuch in {warten:.1f} s.")
                time.sleep(warten)
                continue
        logging.error(f"Discord antwortete mit HTTP {status} - Nachricht nicht zugestellt.")
        return False
    return False


# Farbcodes als Dezimalwerte, wie Discord-Embeds sie erwarten (kein Hex-String)
FARBE_AUF = 0x16C784      # gruen - passend zur App-Akzentfarbe
FARBE_AB = 0xEA3943       # rot
FARBE_ALARM = 0xEA3943    # rot, kraeftiger Fall
FARBE_ATH = 0xF5B700      # gold - Allzeithoch
FARBE_NEUTRAL = 0x7C8493  # grau - Entwarnung/Info


def baue_embed(titel, farbe, felder, fusszeile, now, emoji=""):
    """Baut ein einheitlich gestaltetes Embed fuer alle vier Meldungstypen.

    felder: Liste von (name, wert, inline) Tupeln - erscheinen als
    ausgerichtete Spalten statt als durchlaufender Text.
    """
    return {
        "title": f"{emoji} {titel}".strip(),
        "color": farbe,
        "fields": [
            {"name": n, "value": v, "inline": inline} for n, v, inline in felder
        ],
        "footer": {"text": fusszeile},
        "timestamp": now.astimezone(datetime.timezone.utc).isoformat(),
    }


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
        logging.error(f"Healthcheck-Ping fehlgeschlagen: {_fehlertext(e)}")


def _lese_state(pfad, default):
    """Liest einen State-Datensatz. -> (daten, True) oder (None, False) bei
    Lesefehler. WICHTIG: Ein Lesefehler darf NICHT wie "noch kein State"
    behandelt werden - sonst gaelte z. B. unter_schwelle wieder als False und
    der Alarm wuerde erneut verschickt bzw. das Allzeithoch neu initialisiert."""
    lese_json = getattr(github_store, "lese_json", None)
    if callable(lese_json):
        try:
            daten, _ = lese_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, GITHUB_TOKEN,
                                 default=copy.deepcopy(default))
        except Exception as e:
            logging.error(f"State {pfad} nicht lesbar ({type(e).__name__}) - keine Alarme, kein Schreiben.")
            return None, False
        return daten, True
    daten, _ = github_store.get_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, GITHUB_TOKEN,
                                     default=copy.deepcopy(default))
    lesefehler = getattr(github_store, "lesefehler", None)
    if callable(lesefehler) and lesefehler(pfad):
        logging.error(f"State {pfad} nicht lesbar - keine Alarme, kein Schreiben.")
        return None, False
    return daten, True


def _schreibe_state(pfad, daten, message):
    """put_json mit geprueftem Rueckgabewert. -> True/False"""
    try:
        ok = github_store.put_json(GITHUB_REPO, config.GITHUB_STATE_BRANCH, pfad, daten,
                                   GITHUB_TOKEN, message=message)
    except Exception as e:
        logging.error(f"State {pfad} nicht geschrieben: {_fehlertext(e)}")
        return False
    if not ok:
        logging.error(f"State {pfad} nicht geschrieben (put_json lieferte False) - "
                      f"naechster Lauf arbeitet mit dem alten State weiter.")
    return bool(ok)


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


def hole_historischen_hoechststand(instrument_id, tage=1825):
    """Ermittelt den hoechsten Schlusskurs der letzten `tage` Tage direkt von
    ls-tc.de - dient dazu, das Allzeithoch bei der ERSTEN Initialisierung eines
    Instruments korrekt zu setzen, statt blind den gerade aktuellen Kurs als
    Hoch zu nehmen (das fuehrte sonst zu falschen "Neues Allzeithoch"-Meldungen,
    obwohl der Kurs vorher schon hoeher stand - die App korrigiert das fuer die
    Hauptposition bereits so, hier die gleiche Logik fuer Zusatzwerte).

    Gibt (hoechststand, datum_iso) zurueck, oder (None, None) bei Fehler/leerer
    Historie - der Aufrufer faellt dann auf den aktuellen Kurs zurueck."""
    params = {
        "container": "chart1", "instrumentId": instrument_id, "marketId": "1",
        "quotetype": "mid", "series": "history", "type": "", "localeId": "2",
    }
    try:
        r = requests.get(config.LS_TC_BASE_URL, params=params,
                         headers=config.LS_TC_HEADERS, timeout=10)
        r.raise_for_status()
        raw = r.json()
        history = (raw.get("series", {}).get("history", {}).get("data")
                   or raw.get("history", {}).get("data") or [])
        if not history:
            return None, None
        grenze = datetime.datetime.now(ZoneInfo("Europe/Berlin")) - datetime.timedelta(days=tage)
        beste_ts, bester_wert = None, 0.0
        for ts_ms, close in history:
            close = float(close)
            if close <= 0:
                continue
            ts = datetime.datetime.fromtimestamp(ts_ms / 1000, tz=ZoneInfo("Europe/Berlin"))
            if ts < grenze:
                continue
            if close > bester_wert:
                bester_wert, beste_ts = close, ts
        if beste_ts is None:
            return None, None
        return bester_wert, beste_ts.isoformat()
    except Exception as e:
        logging.warning(f"Historischer Höchststand für Instrument {instrument_id} nicht ladbar: "
                        f"{_fehlertext(e)}")
        return None, None


def check_high_watermark(now, inst, live_kurs, tageshoch):
    """Verfolgt das Allzeithoch aus den selbst gesammelten Kursdaten. Ab einem
    neuen Hoch wird bei weiteren Gewinnen Performance Fee
    (config.PERFORMANCE_FEE_PCT) faellig - deshalb ist das meldenswert.

    tageshoch (hoechster Wert der komplette Intraday-Tickserie) entscheidet
    ueber ein neues Hoch, NICHT nur live_kurs (der letzte Tick) - ein kurzer
    Spike kann bis zum naechsten 5-Minuten-Lauf schon wieder abgeklungen sein.
    live_kurs dient nur der Anzeige in der Meldung, damit klar ist: der
    gemeldete Hoechststand und der GERADE aktuelle Kurs koennen auseinander-
    fallen (Spike bereits vorbei).

    WICHTIG: Der gespeicherte Hoechststand wird bei JEDEM neuen Hoch still
    aktualisiert, eine Discord-Nachricht gibt es aber erst, wenn das Hoch
    mindestens ATH_MELDESCHWELLE_PCT ueber dem zuletzt GEMELDETEN Hoch liegt.
    Ohne diese Bremse kaeme in einem steigenden Markt alle 5 Minuten eine
    Meldung - schon ein Zehntelcent mehr ist formal ein neues Allzeithoch."""
    akt = tageshoch  # fuer die Vergleichslogik unten (bisheriger Variablenname)
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return
    hw_pfad = state_pfad(config.STATE_PATH_HIGH_WATERMARK, inst)
    state, lesbar = _lese_state(hw_pfad, default=None)
    if not lesbar:
        return  # Lesefehler: NICHT neu initialisieren, nichts melden
    if not isinstance(state, dict) or "high_watermark" not in state:
        # ERSTE Initialisierung: NICHT blind den aktuellen Kurs als Hoch nehmen -
        # stattdessen die Kurshistorie pruefen. Reicht sie weiter zurueck und
        # zeigt einen hoeheren Wert, gilt DIESER als Startbasis. So wird kein
        # falsches "Allzeithoch" gemeldet, nur weil die Ueberwachung spaeter
        # gestartet wurde als der Wert tatsaechlich existiert.
        hist_hoch, hist_datum = hole_historischen_hoechststand(inst["instrument_id"])
        if hist_hoch and hist_hoch > akt:
            start_hoch, start_datum = hist_hoch, hist_datum
            logging.info(
                f"{inst['wkn']}: Initialisiere Allzeithoch aus Historie: "
                f"{start_hoch:.3f}€ (statt aktuellem Kurs {akt:.3f}€)."
            )
        else:
            start_hoch, start_datum = akt, now.isoformat()
        neu = dict(state) if isinstance(state, dict) else {}
        # historie_geprueft gleich mitsetzen: die Historie wurde ja gerade geprueft.
        neu.update({"high_watermark": start_hoch, "erreicht_am": start_datum,
                    "zuletzt_gemeldet": start_hoch, "historie_geprueft": True})
        _schreibe_state(hw_pfad, neu, f"init high watermark {inst['wkn']} [skip ci]")
        return

    # SELBSTHEILUNG fuer bereits bestehende States: wurde ein Instrument VOR
    # diesem Fix hinzugefuegt, steckt dort ggf. noch ein falscher Startwert
    # (Kurs zum Zeitpunkt der Ersteinrichtung statt echtem historischen Hoch).
    # Einmalig nachpruefen und still korrigieren (kein Alarm - das ist eine
    # Korrektur der Vergangenheit, keine neue Kursbewegung). "historie_geprueft"
    # verhindert, dass dieser (teurere) Historien-Abruf bei jedem Lauf
    # erneut passiert.
    if not state.get("historie_geprueft"):
        hist_hoch, hist_datum = hole_historischen_hoechststand(inst["instrument_id"])
        aktuelles_hoch_vor_korrektur = float(state.get("high_watermark", 0))
        if hist_hoch and hist_hoch > aktuelles_hoch_vor_korrektur:
            logging.info(
                f"{inst['wkn']}: Selbstheilung - korrigiere Allzeithoch von "
                f"{aktuelles_hoch_vor_korrektur:.3f}€ auf historisch echtes "
                f"Hoch {hist_hoch:.3f}€."
            )
            state["high_watermark"] = hist_hoch
            state["erreicht_am"] = hist_datum
            # zuletzt_gemeldet ebenfalls anheben: dieses Niveau wurde in der
            # Vergangenheit bereits erreicht, ein erneutes Erreichen jetzt ist
            # kein NEUES Hoch und soll keinen Alarm ausloesen.
            state["zuletzt_gemeldet"] = hist_hoch
        state["historie_geprueft"] = True
        if not _schreibe_state(hw_pfad, state, f"selbstheilung high watermark {inst['wkn']} [skip ci]"):
            return  # sonst wuerde unten auf einem nicht gespeicherten Stand weitergearbeitet

    bisheriges_hoch = float(state.get("high_watermark", 0))
    # Basis fuer die Meldeschwelle ist das zuletzt GEMELDETE Hoch. Fehlt es
    # (Altbestand vor diesem Update), dient das bisherige Hoch als Basis.
    zuletzt_gemeldet = float(state.get("zuletzt_gemeldet") or bisheriges_hoch)

    neues_hoch = akt > bisheriges_hoch
    # Gemeldet wird das hoechste bekannte Niveau. Ist eine fruehere Meldung
    # gescheitert (Discord-Fehler), liegt high_watermark bereits ueber
    # zuletzt_gemeldet + Schwelle -> dieser Lauf holt die Meldung nach, auch
    # wenn der Kurs inzwischen wieder etwas gefallen ist (ALM-01).
    kandidat = max(akt, bisheriges_hoch)
    anstieg_pct = ((kandidat - zuletzt_gemeldet) / zuletzt_gemeldet * 100) if zuletzt_gemeldet else 0.0
    melden = anstieg_pct >= ATH_MELDESCHWELLE_PCT

    if not neues_hoch and not melden:
        return

    gemeldet = False
    if melden:
        # Weicht der Live-Kurs vom gemeldeten Hoch ab (Spike bereits abgeklungen),
        # wird das transparent mit ausgewiesen statt den veralteten Eindruck zu
        # erwecken, der Kurs stuende JETZT auf dem Hoch.
        spike_vorbei = abs(live_kurs - kandidat) > 0.0005
        felder = [
            ("Neues Hoch (Tagesverlauf)" if spike_vorbei else "Aktueller Kurs",
             f"**{kandidat:.3f} €**", True),
            ("Zuletzt gemeldet", f"{zuletzt_gemeldet:.3f} € ({anstieg_pct:+.2f} %)", True),
        ]
        if spike_vorbei:
            felder.append(("Kurs jetzt", f"{live_kurs:.3f} €", True))
        felder.append(
            ("Performance Fee", f"Ab hier {config.PERFORMANCE_FEE_PCT:.1f} % auf weitere Gewinne", False)
        )
        gemeldet = send_discord(embed=baue_embed(
            titel=f"Neues Allzeithoch ({inst['wkn']})",
            farbe=FARBE_ATH, emoji="🏆", now=now,
            felder=felder,
            fusszeile=f"{inst['name']} · {now.strftime('%d.%m.%Y %H:%M Uhr')}",
        ))
        if gemeldet:
            chronik_eintrag(f"🏆 Neues Allzeithoch {inst['name']} ({inst['wkn']})",
                            f"{kandidat:.3f} € · {anstieg_pct:+.2f} % über dem zuletzt gemeldeten Hoch "
                            f"({zuletzt_gemeldet:.3f} €)".replace(".", ","),
                            f"ath-{inst['wkn']}-{kandidat:.2f}", now)
        else:
            logging.error(f"{inst['wkn']}: Allzeithoch-Meldung NICHT zugestellt - "
                          f"wird beim naechsten Lauf erneut versucht.")
    else:
        logging.info(
            f"{inst['wkn']}: neues Hoch {akt:.3f}€ still gespeichert "
            f"({anstieg_pct:+.2f}% über zuletzt gemeldetem {zuletzt_gemeldet:.3f}€, "
            f"Meldeschwelle {ATH_MELDESCHWELLE_PCT:.2f}%)."
        )

    aenderung = {}
    if neues_hoch:
        aenderung.update({"high_watermark": akt, "erreicht_am": now.isoformat()})
    if gemeldet:
        # Nur fortschreiben, wenn wirklich zugestellt - sonst wuerde die Meldung
        # verloren gehen bzw. die Schwelle bei jedem Mini-Hoch neu ansetzen.
        aenderung["zuletzt_gemeldet"] = kandidat
    if not aenderung:
        return
    # state.update statt neuem dict: weitere Felder (historie_geprueft, ...)
    # bleiben erhalten (ALM-05).
    state.update(aenderung)
    _schreibe_state(hw_pfad, state, f"update high watermark {inst['wkn']} [skip ci]")


def _alarm_schluessel(art, wkn, now, nr):
    """Ereignisbezogener Chronik-Schluessel: schwelle-{wkn}-{YYYYMMDD}. Bei einem
    zweiten Alarm am selben Tag (nach Entwarnung) mit Zaehler -2, -3 ..."""
    basis = f"{art}-{wkn}-{now.strftime('%Y%m%d')}"
    return basis if nr <= 1 else f"{basis}-{nr}"


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

    # Kein Kurs -> kein Alarm, kein State-Schreiben, kein Allzeithoch (DEP-04).
    try:
        akt, vor, tageshoch = get_live_market_data(inst["instrument_id"])
    except VeralteteDaten as e:
        logging.warning(f"{kennung}: {e} Lauf ohne Alarm/State-Aenderung beendet.")
        return True
    except Exception as e:
        logging.error(f"{kennung}: Kursabruf fehlgeschlagen ({_fehlertext(e)}) - "
                      f"kein Alarm, kein State-Schreiben in diesem Lauf.")
        return False
    try:
        akt, vor = float(akt), float(vor)
    except (TypeError, ValueError):
        logging.error(f"{kennung}: Kursabruf lieferte keine Zahlen - uebersprungen.")
        return False
    if akt <= 0 or vor <= 0:
        logging.error(f"{kennung}: Ungueltige Kurswerte - uebersprungen.")
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
    # Tageshoch statt akt fuer die ATH-Pruefung (erfasst kurze Spikes) - aber
    # nur, wenn es plausibel ist (ALM-04).
    check_high_watermark(now, inst, live_kurs=akt, tageshoch=plausibles_tageshoch(akt, vor, tageshoch))

    alarm_pfad = state_pfad(config.STATE_PATH_PRICE_ALERT, inst)
    if GITHUB_REPO and GITHUB_TOKEN:
        state, lesbar = _lese_state(alarm_pfad, default={"unter_schwelle": False})
        if not lesbar:
            return False
        if not isinstance(state, dict):
            state = {"unter_schwelle": False}
    else:
        state = {"unter_schwelle": False}
    state_vorher = copy.deepcopy(state)

    # --- NEUER HANDELSTAG: Tageszustand zuruecksetzen (ALM-03) ---
    # pct_change bezieht sich immer auf den Vortag. Ein "unter_schwelle" von
    # gestern darf den Alarm von heute nicht unterdruecken.
    heute = now.date().isoformat()
    if state.get("handelstag") != heute:
        if state.get("handelstag") is not None:
            logging.info(f"{kennung}: neuer Handelstag - Alarm-Zustand zurueckgesetzt.")
        state["handelstag"] = heute
        state["unter_schwelle"] = False
        state["zuletzt_gemeldet_pct"] = None
        state["alarme_heute"] = 0

    # --- ROUTINE-KURS-UPDATE: nur bei nennenswerter NEUER Bewegung ---
    # Zwei Bedingungen muessen zusammenkommen:
    #   1. Die Tagesveraenderung liegt bei mindestens ROUTINE_MELDESCHWELLE_PCT
    #   2. Sie hat sich seit der letzten Meldung um mindestens denselben Betrag
    #      weiterbewegt
    # Ohne (2) wuerde ab dem Ueberschreiten der Schwelle JEDER Lauf melden.
    # Der Schwellen-Alarm unten ist davon nicht betroffen.
    zuletzt_gemeldet_pct = state.get("zuletzt_gemeldet_pct")
    ueber_schwelle = abs(pct_change) >= ROUTINE_MELDESCHWELLE_PCT
    if zuletzt_gemeldet_pct is None:
        genug_neue_bewegung = True
    else:
        genug_neue_bewegung = (
            abs(pct_change - float(zuletzt_gemeldet_pct)) >= ROUTINE_MELDESCHWELLE_PCT
        )

    if ueber_schwelle and genug_neue_bewegung:
        pfeil_farbe = FARBE_AUF if pct_change >= 0 else FARBE_AB
        pfeil = "📈" if pct_change >= 0 else "📉"
        erfolg = send_discord(embed=baue_embed(
            titel=f"Kurs-Update ({inst['wkn']})",
            farbe=pfeil_farbe, emoji=pfeil, now=now,
            felder=[
                ("Aktueller Kurs", f"**{akt:.3f} €**", True),
                ("Tagesveränderung", f"**{pct_change:+.2f} %**", True),
            ],
            fusszeile=f"{inst['name']} · {now.strftime('%d.%m.%Y %H:%M Uhr')}",
        ))
        if erfolg:
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
            f"({float(zuletzt_gemeldet_pct):+.2f}%)."
        )

    # --- SCHWELLEN-ALARM / ENTWARNUNG mit Hysterese (ALM-01, ALM-03) ---
    schwelle = float(config.TAGESVERLUST_SCHWELLE_PCT)
    entwarn_grenze = schwelle + hysterese_pp()
    war_unter_schwelle = bool(state.get("unter_schwelle", False))
    alarme_heute = int(state.get("alarme_heute") or 0)

    if pct_change <= schwelle and not war_unter_schwelle:
        gesendet = send_discord(embed=baue_embed(
            titel=f"SCHWELLE UNTERSCHRITTEN ({inst['wkn']})",
            farbe=FARBE_ALARM, emoji="🚨", now=now,
            felder=[
                ("Aktueller Kurs", f"**{akt:.3f} €**", True),
                ("Tagesveränderung", f"**{pct_change:+.2f} %**", True),
                ("Schwelle", f"{schwelle:+.1f} %", True),
            ],
            fusszeile=f"{inst['name']} · {now.strftime('%d.%m.%Y %H:%M Uhr')}",
        ))
        if gesendet:
            state["unter_schwelle"] = True
            state["alarme_heute"] = alarme_heute + 1
            chronik_eintrag(f"🚨 Schwelle unterschritten {inst['name']} ({inst['wkn']})",
                            f"Kurs {akt:.3f} € · Tag {pct_change:+.2f} % · Schwelle "
                            f"{schwelle:+.1f} %".replace(".", ","),
                            _alarm_schluessel("schwelle", inst["wkn"], now, alarme_heute + 1), now)
        else:
            logging.error(f"{kennung}: Schwellen-Alarm NICHT zugestellt - State bleibt, "
                          f"naechster Lauf versucht es erneut.")
    elif war_unter_schwelle and pct_change >= entwarn_grenze:
        gesendet = send_discord(embed=baue_embed(
            titel=f"Entwarnung ({inst['wkn']})",
            farbe=FARBE_NEUTRAL, emoji="✅", now=now,
            felder=[
                ("Aktueller Kurs", f"**{akt:.3f} €**", True),
                ("Tagesveränderung", f"**{pct_change:+.2f} %**", True),
                ("Wieder über", f"{entwarn_grenze:+.1f} %", True),
            ],
            fusszeile=f"{inst['name']} · {now.strftime('%d.%m.%Y %H:%M Uhr')}",
        ))
        if gesendet:
            state["unter_schwelle"] = False
            chronik_eintrag(f"✅ Entwarnung {inst['name']} ({inst['wkn']})",
                            f"Kurs {akt:.3f} € · Tag {pct_change:+.2f} % · wieder über "
                            f"{entwarn_grenze:+.1f} %".replace(".", ","),
                            _alarm_schluessel("entwarnung", inst["wkn"], now, max(alarme_heute, 1)), now)
        else:
            logging.error(f"{kennung}: Entwarnung NICHT zugestellt - naechster Lauf versucht es erneut.")

    # Nur bei echter Aenderung schreiben - spart unnoetige Commits.
    if GITHUB_REPO and GITHUB_TOKEN and state != state_vorher:
        _schreibe_state(alarm_pfad, state, f"update price alert state {inst['wkn']} [skip ci]")

    logging.info(
        f"OK {kennung}: Kurs={akt:.3f} Veraenderung={pct_change:+.2f}% "
        f"unter_schwelle={state.get('unter_schwelle')}"
    )
    return True


def main(now=None):
    now = now or datetime.datetime.now(ZoneInfo("Europe/Berlin"))

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
            # Nur Typ + Stack (Dateien/Zeilen), nicht die Fehlermeldung selbst -
            # die kann bei requests-Fehlern URLs enthalten (SEC-08).
            stack = "".join(traceback.format_tb(e.__traceback__))
            logging.error(f"Unerwarteter Fehler bei {inst.get('wkn', '?')}: {_fehlertext(e)}\n{stack}")
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
