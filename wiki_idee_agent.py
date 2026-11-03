"""Wiki-Idee: woechentliche Umschichtung des Modelldepots (freitags, GitHub Action wiki_idee.yml).

Liest nur die vorhandenen Agenten-Dateien (Katalog, Qualitaet, Investoren-Checks), holt fuer die betroffenen
Werte den aktuellen Kurs von ls-tc.de und schreibt nur state/wiki_idee/... auf den State-Branch:
  state/wiki_idee/depot.json       Modelldepot (Positionen, Stueckzahlen, Kasse, Wertverlauf, Protokoll)
  state/wiki_idee/rangliste.json   aktuelle Ranglisten (Top 100 Aktien, Top 40 ETFs) fuer das Dashboard
Danach optional eine Mail mit den Anpassungen (Gmail mit App-Passwort; Secrets MAIL_ABSENDER,
MAIL_APP_PASSWORT, MAIL_EMPFAENGER - fehlen sie, wird nur gespeichert).

Ein erneuter Lauf am selben Tag rechnet vom Stand vor dem ersten Lauf dieses Tages - nie doppelt umgeschichtet.
"""
import datetime
import os
import smtplib
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import etf_merkmale as EM
import investoren_agent as IA
import klassen_score as KS
import kurs_agent as KA
import kurs_vorrat as KV
import scoring as SC
import top50_agent as T
import wiki_idee as WI

log = T.log
STATE_DEPOT = "state/wiki_idee/depot.json"
STATE_RANG = "state/wiki_idee/rangliste.json"
APP_URL = os.environ.get("APP_URL", "https://zzvuvqwe6.streamlit.app")
KURS_KANDIDATEN = (100, 40)          # fuer so viele Aktien/ETFs der Rangliste wird der aktuelle Kurs geholt


def live_kurse(eintraege, ids):
    """Aktueller ls-tc-Kurs (EUR) je Wert-ID, sofern die Kurs-ID bekannt ist. -> {id: kurs}"""
    jobs = []
    for w in eintraege:
        iid = next((ids[k.upper()] for k in (w.get("wkn"), w.get("isin")) if k and k.upper() in ids), None)
        if iid:
            jobs.append((w["id"], iid))
    jetzt = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def holen(job):
        try:
            live, _ = KA.auswerten(KA.abrufen(job[1], "intraday"), jetzt)
            kurs = float(live["i"][-1][1]) if live else None
            return job[0], (kurs if kurs and kurs > 0 else None)
        except Exception:
            return job[0], None
    with ThreadPoolExecutor(8) as pool:
        return {i: k for i, k in pool.map(holen, jobs) if k}


def mail_senden(betreff, text, html):
    absender, passwort = os.environ.get("MAIL_ABSENDER"), os.environ.get("MAIL_APP_PASSWORT")
    empfaenger = os.environ.get("MAIL_EMPFAENGER") or absender
    if not (absender and passwort and empfaenger):
        log.info("Keine Mail-Zugangsdaten hinterlegt - Mail entfaellt.")
        return False
    m = MIMEMultipart("alternative")
    m["Subject"], m["From"], m["To"] = betreff, absender, empfaenger
    m.attach(MIMEText(text, "plain", "utf-8"))
    m.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL(os.environ.get("MAIL_SERVER", "smtp.gmail.com"), 465,
                          context=ssl.create_default_context(), timeout=30) as s:
        s.login(absender, passwort)
        s.sendmail(absender, [a.strip() for a in empfaenger.split(",") if a.strip()], m.as_string())
    log.info("Mail mit den Anpassungen verschickt.")
    return True


def main():
    heute = datetime.date.today().isoformat()
    depot, status = T.lade_state_geprueft(STATE_DEPOT, {})
    if status == "fehler":
        log.error("Modelldepot nicht lesbar - Lauf abgebrochen, nichts ueberschrieben.")
        return 1
    if depot.get("stand") == heute and depot.get("vorher") is not None:
        log.info("Heute schon umgeschichtet - rechne vom Stand vor dem ersten Lauf heute.")
        depot = depot["vorher"]

    u, _ = IA.universum_laden()
    if not u:
        log.error("Keine Bewertungsdaten - Lauf abgebrochen.")
        return 1
    ver = SC.verteilungen(u)
    bewertet = [(e, SC.bewerten(e, ver)) for e in u if e["art"] in ("aktie", "etf")]
    investoren, _ = IA.lade_teile()
    rang_a, ausgeschlossen = WI.aktien_rangliste([x for x in bewertet if x[0]["art"] == "aktie"], investoren)
    rang_e = WI.etf_rangliste([x for x in bewertet if x[0]["art"] == "etf"], KS.HEBEL, EM.merkmale)
    log.info(f"Rangliste: {len(rang_a)} Aktien ({len(ausgeschlossen)} wegen Warnsignalen ausgeschlossen), "
             f"{len(rang_e)} ETFs")
    if len(rang_a) < WI.N_AKTIEN or len(rang_e) < WI.N_ETF:
        log.error("Zu wenige bewertete Werte - Lauf abgebrochen.")
        return 1

    ids = KV.kennung_ids(T.lade_state("state/top50_ids.json", {}), T.lade_state("state/top50_wikifolios.json", {}))
    gehalten = list((depot.get("positionen") or {}).values())
    kandidaten = {w["id"]: w for w in gehalten + rang_a[:KURS_KANDIDATEN[0]] + rang_e[:KURS_KANDIDATEN[1]]}
    preise = live_kurse(list(kandidaten.values()), ids)
    log.info(f"Aktuelle Kurse: {len(preise)} von {len(kandidaten)} Werten (Rest: letzter Tagesschluss)")

    vorher = {k: v for k, v in depot.items() if k != "vorher"}
    neu, liste = WI.umschichten(vorher, rang_a, rang_e, preise, heute)
    neu["vorher"] = vorher or {}
    neu["ausgeschlossen"] = ausgeschlossen[:200]
    if not T.speichere_state(STATE_DEPOT, neu, "wiki-idee: umschichtung [skip ci]"):
        log.error("Modelldepot nicht gespeichert - keine Mail.")
        return 1
    T.speichere_state(STATE_RANG, {"stand": heute, "aktien": rang_a[:100], "etf": rang_e[:40],
                                   "bausteine": [[k, t, g] for k, t, g in WI.BAUSTEINE]},
                      "wiki-idee: rangliste [skip ci]")
    log.info(f"Depot {neu['wert']:.2f} EUR, {len(liste)} Anpassungen")
    try:
        mail_senden(*WI.mail_text(neu, liste, APP_URL))
    except Exception as e:                       # Mail-Fehler darf den gespeicherten Lauf nicht kippen
        log.error(f"Mail nicht verschickt: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
