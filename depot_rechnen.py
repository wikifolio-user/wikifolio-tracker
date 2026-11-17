"""Depot-Rechenfunktionen ohne Streamlit (aus app.py ausgelagert, Audit ARCH-01): Sparplan- und Entnahme-Termine,
Depotkennzahlen, Renditen (seit Kauf, p. a., geldgewichtet/XIRR), Zeitraeume, robuste CAGR, Bandbreiten-Simulation,
Wikifolio-Kennzahlen sowie die deutschen Zahlenformate fuer die Anzeige. app.py importiert alle Namen zurueck; die
Tests (test_app_rechner, test_referenz_360, test_nutzerdaten) importieren dieses Modul direkt.
"""
import bisect
import datetime
import html

import pandas as pd

import formate as FMT


# --- ZAHLENFORMATIERUNG (Punkt = Tausender, Komma = Dezimal) ---
def _kaufm(val, dec=2):
    """Kaufmaennisch runden (360°-Pruefung F-07) - zentral in formate.runden. -> float"""
    return FMT.runden(val, dec)


def fmt(val, dec=2):
    """Euro-Betrag: '1.234,56 €' (zentral: formate.eur)."""
    return FMT.eur(val, max(dec, 0))


def fmt_vz(val, dec=2):
    """Wie fmt, aber immer mit Vorzeichen: '+1.234,00 €' / '−500,00 €' (Audit DEP-13).
    Werte, die auf 0 runden, erscheinen als '+0,00 €' (kein '−0,00 €')."""
    return FMT.eur(val, dec, vz=True)


def vz_zahl(wert, nachkomma=2):
    """Deutsche Zahl mit Vorzeichen ohne Einheit: '+1.234,56' / '−0,50' (Audit DEP-13)."""
    return FMT.zahl(wert, nachkomma, vz=True)


def wikifolio_werte(kat, lang):
    """Alle wikifolios der Ranglisten (Top 50 je Zeitraum + Top-500-Langliste) zu einer Tabelle:
    -> {wkn: {"name", "wkn", "perf": {zeitraum: Entwicklung %}}}. Ein Zeitraum fehlt, wenn der Wert
    dort nicht unter den Top 500 ist."""
    werte = {}

    def dazu(name, wkn, zr, perf):
        if not wkn or not isinstance(perf, (int, float)):
            return
        w = werte.setdefault(wkn, {"name": str(name or wkn), "wkn": wkn, "perf": {}})
        w["perf"].setdefault(zr, float(perf))

    for zr, liste in ((kat or {}).get("top") or {}).items():
        for e in liste or []:
            dazu(e.get("name"), e.get("wkn"), zr, e.get("perf"))
    for zr, liste in ((lang or {}).get("top") or {}).items():
        for r in liste or []:
            if len(r) >= 3:
                dazu(r[0], r[1], zr, r[2])
    return werte


def wikifolio_rangliste(werte, zeitraum, begriff="", n=500):
    """Rangliste nach einem Zeitraum (die besten n), danach optional nach Name/WKN gefiltert -
    der Rang bleibt der in der vollen Liste."""
    liste = sorted((w for w in werte.values() if w["perf"].get(zeitraum) is not None),
                   key=lambda w: (-w["perf"][zeitraum], w["name"].lower()))[:n]
    liste = [dict(w, rang=i) for i, w in enumerate(liste, 1)]
    b = str(begriff or "").strip().lower()
    return [w for w in liste if b in (w["name"] + " " + w["wkn"]).lower()] if b else liste


def _h(text):
    """HTML-Escaping fuer Nutzer-/Fremdtexte in unsafe_allow_html-Bausteinen (Audit SEC-04)."""
    return html.escape("" if text is None else str(text), quote=True)


# --- SPARPLAN / ENTNAHME: EIN gemeinsamer Monatsplan (Audit DEP-03/DEP-11) ---
def monats_termine(start, bis, ab_k=0):
    """Alle Termine start + k Monate (k >= ab_k), die am oder vor 'bis' liegen.
    Monatsenden werden von pandas gekappt (31.01. + 1 Monat = 28./29.02.)."""
    if start is None or bis is None:
        return []
    start_ts = pd.Timestamp(start).normalize()
    bis_ts = pd.Timestamp(bis).normalize()
    termine = []
    k = ab_k
    while True:
        t = start_ts + pd.DateOffset(months=k)
        if t > bis_ts:
            break
        termine.append(t)
        k += 1
    return termine


def sparplan_termine(start, heute):
    """Sparplan-Kaeufe: der erste am Starttag (k=0), dann monatlich."""
    return monats_termine(start, heute, ab_k=0)


def entnahme_termine(kaufdatum, heute):
    """Entnahmen: erstmals einen Monat nach dem Kauf (k=1), dann monatlich."""
    return monats_termine(kaufdatum, heute, ab_k=1)


def kumulierte_entnahme(index, termine, rate):
    """Je Zeitpunkt des Index: Summe aller Entnahmen bis einschliesslich dieses Tages."""
    sortiert = sorted(pd.Timestamp(t) for t in termine)
    return [rate * bisect.bisect_right(sortiert, pd.Timestamp(ts).normalize()) for ts in index]


def sparplan_phasen(state):
    """Gespeicherter Sparplan (Audit DEP-02) -> (start_datum | None, [(ab_datum, rate), ...]).
    Format: {"start_datum": "YYYY-MM-DD", "rate": 500.0, "phasen": [{"ab": ..., "rate": ...}]}.
    Altbestand nur mit start_datum (Rate wurde frueher nicht gespeichert) -> leere Phasen."""
    if not isinstance(state, dict) or not state.get("start_datum"):
        return None, []
    try:
        start = datetime.date.fromisoformat(str(state["start_datum"]))
    except ValueError:
        return None, []
    phasen = []
    for ph in state.get("phasen") or []:
        try:
            phasen.append((datetime.date.fromisoformat(str(ph["ab"])), float(ph["rate"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not phasen and state.get("rate") is not None:
        try:
            phasen = [(start, float(state["rate"]))]
        except (TypeError, ValueError):
            phasen = []
    return start, sorted(phasen)


def sparrate_am(phasen, tag):
    """Sparrate, die an 'tag' gilt (letzte Phase mit ab <= tag), sonst 0."""
    t = pd.Timestamp(tag).normalize()
    rate = 0.0
    for ab, r in phasen:
        if pd.Timestamp(ab) <= t:
            rate = r
        else:
            break
    return rate


def sparplan_state_neu(state, rate, heute):
    """Zustand nach dem AUSDRUECKLICHEN Speichern einer Sparrate > 0 (Audit DEP-02).
    Neuer Plan startet heute; eine geaenderte Rate gilt ab heute (fruehere Kaeufe
    behalten ihre Rate). Altbestand ohne gespeicherte Rate: Rate gilt ab Start.
    -> neuer Zustand oder None (nichts zu aendern)."""
    rate = float(rate)
    start, phasen = sparplan_phasen(state)
    if start is None:
        h = heute.isoformat()
        return {"start_datum": h, "rate": rate, "phasen": [{"ab": h, "rate": rate}]}
    if phasen and abs(phasen[-1][1] - rate) < 1e-9:
        return None
    if not phasen:
        phasen = [(start, rate)]
    else:
        phasen = [p for p in phasen if p[0] < heute] + [(heute, rate)]
    return {"start_datum": start.isoformat(), "rate": rate,
            "phasen": [{"ab": ab.isoformat(), "rate": r} for ab, r in phasen]}


def sparplan_einzelkaeufe(termine, kursreihe, rate, ersatzkurs=None, max_verzug_tage=7):
    """Jeder ausgefuehrte Sparplan-Kauf als (kauftag, betrag, stueck).
    Ausfuehrung wie beim Broker am ersten Handelstag am/nach dem Termin (Audit A-27,
    gleiche Regel wie die Verkaeufe in berechne_reale_stueckzahl); gibt es dafuer noch
    keinen Kurs (Termin heute/am Wochenende), gilt der Ersatzkurs (Live-Kurs), sonst
    bleibt der Kauf offen. Liegt der naechste Kurs mehr als max_verzug_tage nach dem
    Termin (Termin vor Beginn der Kursdaten), wird nicht zu einem spaeteren Kurs gekauft.
    rate: Zahl oder Funktion termin -> Rate (Phasen)."""
    if not callable(rate) and (not rate or rate <= 0):
        return []
    rate_fn = rate if callable(rate) else (lambda _t, _r=rate: _r)
    kaeufe = []
    for t in termine:
        t = pd.Timestamp(t).normalize()
        r_t = rate_fn(t) or 0.0
        if r_t <= 0:
            continue
        tag, preis = None, None
        if kursreihe is not None and len(kursreihe):
            danach = kursreihe[(kursreihe.index >= t) & (kursreihe.index <= t + pd.Timedelta(days=max_verzug_tage))]
            if len(danach):
                tag, preis = pd.Timestamp(danach.index[0]).normalize(), float(danach.iloc[0])
        nach_datenende = kursreihe is None or not len(kursreihe) or t > pd.Timestamp(kursreihe.index[-1])
        if preis is None and ersatzkurs and nach_datenende:
            tag, preis = t, float(ersatzkurs)
        if preis and preis > 0:
            kaeufe.append((tag, float(r_t), r_t / preis))
    return kaeufe


def sparplan_kaeufe(termine, kursreihe, rate, ersatzkurs=None):
    """-> (eingezahlt, stueck) aller ausgefuehrten Kaeufe (sparplan_einzelkaeufe).
    Nur tatsaechlich ausgefuehrte Kaeufe (mit Kurs) zaehlen zum Einstand."""
    kaeufe = sparplan_einzelkaeufe(termine, kursreihe, rate, ersatzkurs)
    return sum(k[1] for k in kaeufe), sum(k[2] for k in kaeufe)


def sparplan_verlauf(index, kaeufe):
    """Kumulierte (stueck, eingezahlt) je Zeitpunkt des Index (Audit A-09: Chart und
    Tabelle enthalten die Sparplan-Anteile ab ihrem Kauftag)."""
    stueck, geld = [], []
    if not len(index):
        return stueck, geld
    # Kaeufe nach dem letzten Punkt (vorgemerkt zum Live-Kurs, z. B. Termin am Wochenende)
    # zaehlen am letzten Punkt mit - sonst fehlten sie im Chart, waehrend die Kachel sie zeigt.
    ende = pd.Timestamp(index[-1]).normalize()
    kaeufe = [(min(k[0], ende), k[1], k[2]) for k in kaeufe]
    for ts in index:
        tag = pd.Timestamp(ts).normalize()
        stueck.append(sum(k[2] for k in kaeufe if k[0] <= tag))
        geld.append(sum(k[1] for k in kaeufe if k[0] <= tag))
    return stueck, geld


def entnahme_rate_aus_state(state, standard):
    """Monatliche Entnahme (Audit DEP-03): gespeicherter Wert, sonst Standard (config.ENTNAHME_PM)."""
    try:
        if isinstance(state, dict) and state.get("rate") is not None:
            return max(0.0, float(state["rate"]))
    except (TypeError, ValueError):
        pass
    return max(0.0, float(standard or 0.0))


def hochgerechnete_rendite_pa(kurs, kaufkurs, tage, min_tage=30):
    """Prognose-Hochrechnung bei Historie unter 1 Jahr (Nutzerentscheid zu DEP-08):
    geometrische Ø-Monatsrendite r_m = (1+gesamt)^(1/monate) - 1 mit
    monate = tage / 30,4375, hochgerechnet auf r_pa = (1+r_m)^12 - 1.
    Unter min_tage (1 Monat) bzw. bei ungueltigen Kursen -> None.
    -> (rate_pa_pct, monate, rate_mo_pct) | None"""
    if not kaufkurs or kaufkurs <= 0 or not kurs or kurs <= 0 or tage < min_tage:
        return None
    monate = tage / 30.4375          # 365,25 / 12
    r_m = (kurs / kaufkurs) ** (1 / monate) - 1
    return ((1 + r_m) ** 12 - 1) * 100, monate, r_m * 100


def prognose_rate_rueckfall(kurs, kaufkurs, tage, min_tage=30):
    """Ersatz-Prognoserate, wenn die Produkt-Historie keine Rate liefert (Audit DEP-08):
    ab 365 Tagen realisierte Rendite p.a. (unveraendert); von min_tage (1 Monat) bis
    unter 1 Jahr die auf ein Jahr hochgerechnete Ø-Monatsrendite (mit Hinweis);
    darunter 0 % (bewusst neutral, manuell ueberschreibbar).
    -> (rate_pa, hinweis | None)"""
    if tage >= 365:
        r = realisierte_rendite_pa(kurs, kaufkurs, tage, 365)
        if r is not None:
            return r, None
    else:
        h = hochgerechnete_rendite_pa(kurs, kaufkurs, tage, min_tage)
        if h is not None:
            r, monate, r_m = h
            return r, (f"Hochgerechnet aus {monate:.1f} Monaten (Ø Monatsrendite {r_m:+.2f} %) – "
                       "vorläufig, bis 1 Jahr Historie vorliegt")
    return 0.0, "Zu kurze Historie (< 1 Monat) – 0 % p.a. angenommen, bitte bei Bedarf anpassen"


def depot_kennzahlen(stueck_basis, stueck_sparplan, kurs, startkapital, sparplan_eingezahlt,
                     entnahme_rate, anzahl_entnahmen):
    """Kennzahlen 'seit Kauf' (Audit DEP-01/DEP-03): Einstand = Startkapital + tatsaechlich
    eingezahlte Sparraten; Netto = Brutto - Rate x Anzahl Entnahmen seit Kauf."""
    brutto = (stueck_basis + stueck_sparplan) * kurs
    einstand = startkapital + sparplan_eingezahlt
    gewinn = brutto - einstand
    entnommen = entnahme_rate * anzahl_entnahmen
    return {
        "brutto": brutto, "einstand": einstand, "gewinn": gewinn,
        "rendite_pct": (gewinn / einstand * 100) if einstand else 0.0,
        "entnommen": entnommen, "netto": brutto - entnommen,
    }


def depot_kennzahlen_real(stueck_real, stueck_sparplan, kurs, einstand, ausgezahlt):
    """Kennzahlen bei ECHTEN Entnahmen (Audit A-12): Depotwert = verbliebene Anteile x Kurs;
    das bereits ausgezahlte Geld gehoert zum Ergebnis: Gewinn = Depotwert + ausgezahlt - Einstand.
    Ohne Entnahmen identisch mit depot_kennzahlen (brutto/gewinn/rendite_pct)."""
    wert = (stueck_real + stueck_sparplan) * kurs
    gewinn = wert + ausgezahlt - einstand
    return {"wert": wert, "gewinn": gewinn, "ausgezahlt": ausgezahlt,
            "rendite_pct": (gewinn / einstand * 100) if einstand else 0.0}


def rendite_pa_geldgewichtet(zahlungen, endwert, heute):
    """Interner Zinsfuss (XIRR) in % p. a.: zahlungen = [(datum, betrag)] mit Einzahlungen positiv
    (Startkapital, Sparraten) und Auszahlungen negativ (Entnahmen); endwert = Depotwert am Tag heute.
    Jede Zahlung zaehlt ab ihrem eigenen Datum - eine Sparrate von gestern hatte keine Zeit zu wachsen.
    -> Rate oder None (keine Loesung / keine Einzahlung)."""
    fluss = [(pd.Timestamp(d).normalize(), float(b)) for d, b in zahlungen or [] if b]
    if not fluss or sum(b for _, b in fluss if b > 0) <= 0 or endwert is None or endwert < 0:
        return None
    t_end = pd.Timestamp(heute).normalize()
    jahre = [max((t_end - d).days, 0) / 365.25 for d, _ in fluss]

    def wert_am_ende(r):          # Endwert der Zahlungen bei Rate r minus tatsaechlicher Endwert
        return sum(b * (1 + r) ** j for (_, b), j in zip(fluss, jahre)) - endwert

    lo, hi = -0.9999, 10.0
    if wert_am_ende(lo) > 0 or wert_am_ende(hi) < 0:
        return None
    for _ in range(200):
        mitte = (lo + hi) / 2
        if wert_am_ende(mitte) > 0:
            hi = mitte
        else:
            lo = mitte
    return (lo + hi) / 2 * 100


def rendite_pa_seit_kauf(einstand, ergebnis_wert, kaufdatum, heute, zahlungen=None, depotwert=None):
    """Ø-Rendite p.a. seit Kauf fuer Kachel UND Vergleichstabelle (Audit A-08, eine Quelle).
    ergebnis_wert = Depotwert + bereits ausgezahlte Entnahmen. Ab 1 Jahr jaehrlich, darunter
    ab 30 Tagen aus der Ø-Monatsrendite hochgerechnet (Nutzerentscheid DEP-08), sonst None.
    Mit zahlungen (Sparraten/Entnahmen mit Datum, siehe rendite_pa_geldgewichtet) und depotwert:
    geldgewichtet (XIRR) - sonst wuerde jede Sparrate so gerechnet, als laege sie seit dem Kauf im
    Depot, und die Rendite fiele viel zu niedrig aus (360°-Pruefung F-01).
    -> (rate_pa | None, hochgerechnet: bool)"""
    if not einstand or einstand <= 0 or ergebnis_wert is None or ergebnis_wert <= 0:
        return None, False
    if zahlungen and depotwert is not None:
        erste = min(pd.Timestamp(d) for d, _ in zahlungen).date()
        tage = (heute - erste).days
        if tage < 30:
            return None, False
        r = rendite_pa_geldgewichtet(zahlungen, depotwert, heute)
        return (r, tage < 365) if r is not None else (None, False)
    _, monatlich, jaehrlich, _ = berechne_performance_kennzahlen(einstand, ergebnis_wert, kaufdatum, heute)
    if jaehrlich is not None:
        return jaehrlich, False
    if monatlich is not None:
        return ((1 + monatlich / 100) ** 12 - 1) * 100, True
    return None, False


def berechne_reale_stueckzahl(df, start_stueckzahl, entnahme_pm, termine, spread_pct):
    """REAL: zu jedem Entnahmetermin werden tatsaechlich Anteile zum Geldkurs (Mid minus
    Spread) verkauft - am ersten Handelstag am/nach dem Termin. Gleicher Plan und gleiche
    Rate wie die Netto-Simulation (Audit DEP-03). -> Stueckzahl je Zeile von df."""
    stueckzahl = start_stueckzahl
    offen = sorted(pd.Timestamp(t) for t in termine)
    i = 0
    verlauf = []
    for ts, row in df.iterrows():
        tag = pd.Timestamp(ts).normalize()
        while i < len(offen) and offen[i] <= tag:
            geld_preis = float(row["Close"]) * (1 - spread_pct / 100.0)
            if entnahme_pm and geld_preis > 0:
                stueckzahl = max(0.0, stueckzahl - entnahme_pm / geld_preis)
            i += 1
        verlauf.append(stueckzahl)
    return verlauf


def berechne_performance_kennzahlen(erste_werte, letzter_wert, start_datum, end_datum):
    """Gesamt-%, Ø-monatliche % und Ø-jährliche % sowie Gewinn/Verlust in €.
    Keine Hochrechnung kurzer Zeitraeume (Audit DEP-08): Ø/Jahr erst ab 365 Tagen,
    Ø/Monat erst ab 30 Tagen - sonst None ('n. a.', angezeigt wird die Gesamtrendite)."""
    if not erste_werte or erste_werte <= 0:
        return None, None, None, letzter_wert - (erste_werte or 0.0)
    gesamt_pct = (letzter_wert / erste_werte - 1) * 100
    tage = max(1, (end_datum - start_datum).days)
    monate = tage / 30.44
    monatliche_pct = (((letzter_wert / erste_werte) ** (1 / monate)) - 1) * 100 if tage >= 30 else None
    jaehrliche_pct = (((letzter_wert / erste_werte) ** (365.25 / tage)) - 1) * 100 if tage >= 365 else None
    gewinn_verlust_euro = letzter_wert - erste_werte
    return gesamt_pct, monatliche_pct, jaehrliche_pct, gewinn_verlust_euro


def perf_sortierwert(e):
    """Sortierung der Vergleichstabellen: erst Eintraege mit Ø/Jahr (danach), sonst Gesamt."""
    j = e.get("_jaehrlich")
    return (1, j) if j is not None else (0, e.get("_perf") or 0.0)


def realisierte_rendite_pa(kurs, kaufkurs, tage, min_tage=180):
    """Realisierte Rendite p.a. seit Kauf - nur ab min_tage (Audit DEP-08), sonst None."""
    if not kaufkurs or kaufkurs <= 0 or not kurs or kurs <= 0 or tage < min_tage:
        return None
    return ((kurs / kaufkurs) ** (365.25 / tage) - 1) * 100


def gesamt_perioden_berechnen(beitraege, labels):
    """Depot-Gesamtsumme je Zeitraum (Audit DEP-07). beitraege: [(aktueller_wert,
    {label: betrag})] je Position. Basis je Zeitraum = nur die Positionen, die fuer
    diesen Zeitraum einen Wert liefern. -> [(label, betrag, pct, teilweise)]"""
    erg = []
    for lbl in labels:
        mit = [(w, z[lbl]) for w, z in beitraege if lbl in z]
        if not mit:
            continue
        betrag = sum(b for _, b in mit)
        basis = sum(w for w, _ in mit) - betrag
        pct = (betrag / basis * 100) if basis else 0.0
        erg.append((lbl, betrag, pct, len(mit) < len(beitraege)))
    return erg


def haenge_live_punkt_an(df, heute, kurs):
    """Live-Kurs als Punkt fuer HEUTE (Audit DEP-10): gibt es die Zeile schon, wird sie
    aktualisiert, sonst wird der Index um heute verlaengert - statt den gestrigen
    Schlusskurs zu ueberschreiben. Gleiches Vorgehen wie bei den Vergleichswerten."""
    if df is None or df.empty or not kurs:
        return df
    heute_ts = pd.Timestamp(heute).normalize()
    letzter = pd.Timestamp(df.index[-1]).normalize()
    if letzter > heute_ts:
        return df
    df = df.copy()
    if letzter == heute_ts:
        ts = df.index[-1]
        df.loc[ts, "Close"] = kurs
        if "High" in df.columns:
            df.loc[ts, "High"] = max(float(df.loc[ts, "High"]), kurs)
        if "Low" in df.columns:
            df.loc[ts, "Low"] = min(float(df.loc[ts, "Low"]), kurs)
    else:
        df.loc[heute_ts] = [kurs] * len(df.columns)
        df = df.sort_index()
    return df


def _berlin_tage(ts_ms):
    """ls-tc-Zeitstempel (ms, UTC) -> Kalendertag in Europe/Berlin als naive Mitternacht
    (Audit DEP-09) - wie der Workflow; passt so auf bdate_range-Indizes."""
    s = pd.to_datetime(pd.Series(ts_ms), unit="ms", utc=True)
    return s.dt.tz_convert("Europe/Berlin").dt.normalize().dt.tz_localize(None)


def referenzkurs_vor_tagen(historie, tage, heute):
    # Hinweis: der AKTUELLE Wert kommt immer live von get_live_kurs() herein,
    # hier wird ausschliesslich der historische Referenzpunkt gesucht.
    """Letzter Schlusskurs am oder vor dem Stichtag (heute - tage). Nimmt
    bewusst den naechstfrueheren Handelstag, wenn der Stichtag auf ein
    Wochenende/Feiertag faellt. None, wenn die Historie nicht weit genug
    zurueckreicht - dann entfaellt die Zeile in der Anzeige."""
    if historie is None or historie.empty:
        return None
    stichtag = pd.Timestamp(heute) - pd.Timedelta(days=tage)
    passend = historie[historie.index <= stichtag]
    if passend.empty:
        return None
    # Nur nutzen, wenn die Historie wirklich bis in die Naehe des Stichtags
    # reicht (sonst waere "1 Jahr" bei 3 Monaten Historie schlicht falsch).
    if (stichtag - passend.index[-1]).days > 10:
        return None
    return float(passend.iloc[-1])


def berechne_zeitraeume(aktueller_kurs, vortag_kurs, historie, heute):
    """Liefert [(Label, Kursdifferenz, Prozent), ...] fuer Tag/Woche/Monat/Jahr.

    Reicht die Historie fuer einen Zeitraum nicht aus, wird die Zeile
    weggelassen - AUSSER beim Jahr: dort wird ersatzweise der aelteste
    verfuegbare Kurs herangezogen und das Label entsprechend umbenannt
    ("seit 28.01.2026"). So bleibt bei jung aufgelegten Produkten die
    Langfrist-Zeile sichtbar, ohne einen Jahreswert vorzutaeuschen, den
    die Daten gar nicht hergeben."""
    zeilen = []
    if vortag_kurs:
        d = aktueller_kurs - vortag_kurs
        zeilen.append(("Tag", d, d / vortag_kurs * 100))

    for label, tage in [("Woche", 7), ("Monat", 30), ("3 Monate", 91),
                        ("6 Monate", 182), ("9 Monate", 273)]:
        ref = referenzkurs_vor_tagen(historie, tage, heute)
        if ref:
            d = aktueller_kurs - ref
            zeilen.append((label, d, d / ref * 100))

    # Laufendes Jahr (YTD) - bewusst nach den festen Zeitraeumen, da es je nach
    # Kalenderlage kuerzer oder laenger als 6 Monate sein kann.
    jahresanfang = datetime.date(heute.year, 1, 1)
    if historie is not None and not historie.empty:
        vor_jahresstart = historie[historie.index <= pd.Timestamp(jahresanfang)]
        if not vor_jahresstart.empty:
            ytd_ref = float(vor_jahresstart.iloc[-1])
            if ytd_ref:
                d = aktueller_kurs - ytd_ref
                zeilen.append(("Lfd. Jahr", d, d / ytd_ref * 100))

    jahr_ref = referenzkurs_vor_tagen(historie, 365, heute)
    if jahr_ref:
        d = aktueller_kurs - jahr_ref
        zeilen.append(("Jahr", d, d / jahr_ref * 100))
    elif historie is not None and not historie.empty:
        # Kein Jahreswert vorhanden - aeltesten Kurs nehmen und ehrlich
        # beschriften. Nur sinnvoll, wenn dieser Zeitraum laenger ist als der
        # bereits gezeigte Monat, sonst waere es eine Dopplung.
        aeltester_ts = historie.index[0]
        if (pd.Timestamp(heute) - aeltester_ts).days > 182:
            ref = float(historie.iloc[0])
            if ref:
                d = aktueller_kurs - ref
                zeilen.append((f"seit {aeltester_ts.strftime('%d.%m.%Y')}", d, d / ref * 100))
    return zeilen


def mc_einsatz(startwert, tage, sparrate_monat=0.0, entnahme_monat=0.0):
    """Eingesetztes Geld in der Simulation: Startwert + Zahlungen an jedem 21. Handelstag
    (genau wie in simuliere_bandbreite) - Bezugsgroesse der Verlustwahrscheinlichkeit."""
    monate = int(tage) // 21
    return float(startwert) + monate * (float(sparrate_monat or 0) - float(entnahme_monat or 0))


def simuliere_bandbreite(startwert, kursreihe, jahre, sparrate_monat=0.0,
                         entnahme_monat=0.0, shrinkage=True, pfade=4000):
    """Monte-Carlo-Simulation moeglicher Wertentwicklungen statt einer
    einzelnen Punktprognose.

    Warum ueberhaupt: Eine einzelne Zahl ("in 5 Jahren sind es X €")
    suggeriert eine Praezision, die es nicht gibt. Bei kurzer Historie ist
    der Standardfehler einer annualisierten Rendite riesig - bei ~7 Monaten
    Daten und hoher Volatilitaet liegt er schnell bei +/- 60 Prozentpunkten.
    Eine Bandbreite ist ehrlicher als eine Kommastelle.

    Methode: Aus den taeglichen Log-Renditen der echten Kursreihe werden
    Drift (mu) und Volatilitaet (sigma) geschaetzt, dann werden `pfade`
    moegliche Verlaeufe gewuerfelt (geometrische Brownsche Bewegung).

    shrinkage: Bei kurzer Historie ist der geschaetzte Drift extrem
    unzuverlaessig - ein siebenmonatiger Boom wuerde sonst ungebremst ueber
    Jahre fortgeschrieben (die naive Rechnung ergab dann z.B. 0% Verlust-
    wahrscheinlichkeit, was offensichtlich unrealistisch ist). Deshalb wird
    der Drift Richtung eines konservativen Ankers (8% p.a., grobe langfristige
    Aktienmarktrendite) zusammengezogen. Das Gewicht haengt an der Datenmenge:
    wenig Historie -> mehr Anker, viel Historie -> mehr eigene Daten.

    Gibt (perzentile_dict, kennzahlen_dict) zurueck oder (None, None), wenn
    die Kursreihe zu duenn fuer eine sinnvolle Schaetzung ist.
    """
    import numpy as np

    if kursreihe is None or len(kursreihe) < 30:
        return None, None

    reihe = kursreihe.dropna()
    reihe = reihe[reihe > 0]
    if len(reihe) < 30:
        return None, None

    log_renditen = np.diff(np.log(reihe.values))
    if len(log_renditen) < 20:
        return None, None

    mu_tag = float(np.mean(log_renditen))
    sigma_tag = float(np.std(log_renditen, ddof=1))
    if sigma_tag <= 0:
        return None, None

    jahre_historie = len(log_renditen) / 252.0
    mu_roh_pa = (np.exp(mu_tag * 252) - 1) * 100

    if shrinkage:
        ANKER_PA = 0.08          # grobe langfristige Marktrendite als Rueckfallanker
        HALBES_VERTRAUEN = 3.0   # ab 3 Jahren Historie: 50% Gewicht auf eigene Daten
        mu_anker_tag = np.log(1 + ANKER_PA) / 252
        gewicht = jahre_historie / (jahre_historie + HALBES_VERTRAUEN)
        mu_verwendet = gewicht * mu_tag + (1 - gewicht) * mu_anker_tag
    else:
        gewicht = 1.0
        mu_verwendet = mu_tag

    tage = max(1, int(jahre * 252))
    rng = np.random.default_rng(12345)   # fester Seed: gleiche Eingabe -> gleiches Bild
    z = rng.standard_normal((pfade, tage))
    # Audit DEP-05: mu_tag ist bereits der Mittelwert der LOG-Renditen (enthaelt -sigma^2/2),
    # der Anker ln(1,08)/252 ebenfalls eine Log-Rate - KEIN zweiter Abzug. Median der
    # Endwerte (ohne Ein-/Auszahlungen) = startwert * exp(mu_verwendet * tage).
    schritte = mu_verwendet + sigma_tag * z

    # Sparrate/Entnahme monatlich einrechnen: Pfade schrittweise aufbauen,
    # damit Ein-/Auszahlungen zum jeweils simulierten Kurs wirken.
    if sparrate_monat or entnahme_monat:
        werte = np.full(pfade, float(startwert))
        netto_monat = sparrate_monat - entnahme_monat
        for t in range(tage):
            werte = werte * np.exp(schritte[:, t])
            if (t + 1) % 21 == 0:          # ~1 Handelsmonat
                werte = np.maximum(0.0, werte + netto_monat)
        endwerte = werte
    else:
        endwerte = startwert * np.exp(schritte.sum(axis=1))

    perzentile = {p: float(np.percentile(endwerte, p)) for p in (5, 25, 50, 75, 95)}
    # Audit DEP-06: Verlust = Endwert unter dem insgesamt eingesetzten Geld
    # (Startwert + Einzahlungen - Entnahmen), nicht nur unter dem Startwert.
    eingesetzt = mc_einsatz(startwert, tage, sparrate_monat, entnahme_monat)
    kennzahlen = {
        "verlust_wahrscheinlichkeit": float((endwerte < eingesetzt).mean() * 100),
        "eingesetzt": float(eingesetzt),
        "vola_pa": float(sigma_tag * np.sqrt(252) * 100),
        "mu_roh_pa": float(mu_roh_pa),
        "mu_verwendet_pa": float((np.exp(mu_verwendet * 252) - 1) * 100),
        "jahre_historie": float(jahre_historie),
        "gewicht_eigene_daten": float(gewicht * 100),
        "pfade": pfade,
    }
    return perzentile, kennzahlen


def berechne_robuste_cagr(aktueller_kurs, historie, heute, daempfung=False,
                          auflage_datum=None, auflage_kurs=None):
    """Schaetzt eine annualisierte Wachstumsrate (CAGR), die ueber den Tag
    KONSTANT bleibt und nicht an einem einzelnen Kurspunkt haengt.

    Warum nicht einfach "aeltester Kurs vs. heute": beide Endpunkte sind
    Zufallspunkte. Und Achtung - der Mittelwert der taeglichen Log-Renditen
    ist KEINE Verbesserung: er teleskopiert sich exakt zu demselben
    Zwei-Punkte-Vergleich. Deshalb hier:

    1. TREND PER REGRESSION (Hauptwert): Kleinste-Quadrate-Gerade durch
       ln(Kurs) ueber die Zeit. Nutzt JEDEN Kurspunkt der Historie, nicht nur
       Anfang und Ende - ein einzelner Ausreisser am Rand verschiebt sie kaum.
    2. LANGE ZEITFENSTER als Quervergleich (ab 6 Monaten). Fenster unter 6
       Monaten werden bewusst NICHT verwendet: ein Monat hochgerechnet
       multipliziert das Zufallsrauschen mit 12 und ergibt Fantasiewerte
       (getestet: +1.480 % p.a. bei einem Produkt, das real ~150 % lief).
    3. MEDIAN aus Regression + Fenstern - unempfindlich gegen einen einzelnen
       Ausreisser darin.
    4. DAEMPFUNG bei kurzer Historie: aus 7 Monaten laesst sich keine
       Jahresrate ablesen (Standardfehler ueber 60 Prozentpunkte). Das
       Ergebnis wird deshalb Richtung einer konservativen Marktrendite
       (8 % p.a.) gezogen, gewichtet nach Datenmenge - dieselbe Regel wie in
       der Bandbreiten-Simulation. Ueber `daempfung=False` abschaltbar.

    Als "heutiger" Kurs dient bewusst der letzte SCHLUSSKURS der Historie,
    nicht der Live-Tick: sonst aenderte sich die Vorgabe mit jedem
    Kurs-Update um mehrere Prozentpunkte (getestet: +-2 % Kursbewegung
    verschob die Rate um +-5 Prozentpunkte).

    Gibt (cagr, details) zurueck; details ist eine Liste (Label, Wert) fuer
    die Transparenz-Anzeige. Reicht die Historie nicht (unter ~90
    Handelstagen), kommt (None, []) zurueck.
    """
    import numpy as np

    if historie is None or len(historie) < 90:
        return None, []
    reihe = historie.dropna()
    reihe = reihe[reihe > 0]
    if len(reihe) < 90:
        return None, []

    schlusskurs = float(reihe.iloc[-1])
    jahre_hist = max(1e-6, (reihe.index[-1] - reihe.index[0]).days / 365.25)

    # 1) Trend per Regression auf ln(Kurs)
    t = np.array([(ts - reihe.index[0]).days for ts in reihe.index], dtype=float) / 365.25
    y = np.log(reihe.values.astype(float))
    steigung = float(np.polyfit(t, y, 1)[0])          # ln-Einheiten pro Jahr
    cagr_trend = (float(np.exp(steigung)) - 1) * 100
    details = [(f"Trend über {jahre_hist:.1f} Jahre (Regression)", cagr_trend)]

    # 2) Lange Zeitfenster als Quervergleich
    for label, tage in [("6 Monate", 182), ("9 Monate", 273), ("1 Jahr", 365),
                        ("2 Jahre", 730), ("3 Jahre", 1095), ("5 Jahre", 1826)]:
        ref = referenzkurs_vor_tagen(reihe, tage, heute)
        if ref and ref > 0:
            details.append((label, ((schlusskurs / ref) ** (365.25 / tage) - 1) * 100))

    # SEIT BEGINN DER DATEN: gesamte Entwicklung vom ersten verfuegbaren Kurs.
    start_kurs = float(reihe.iloc[0])
    if start_kurs > 0 and jahre_hist >= 0.5:
        details.append((
            f"Seit Datenbeginn {reihe.index[0].strftime('%d.%m.%Y')} "
            f"({start_kurs:.2f} € → {schlusskurs:.2f} €)",
            ((schlusskurs / start_kurs) ** (1 / jahre_hist) - 1) * 100,
        ))

    # SEIT AUFLEGUNG: ls-tc.de liefert die Historie erst ab Listing - bei
    # LS9VFS z.B. erst ab 09.07.2025 bei 128,80 €, obwohl das Zertifikat am
    # 24.06.2025 bei 100 € startete. Dieser Teil der Entwicklung fehlt in den
    # Daten komplett. Deshalb laesst sich der Auflegungspunkt hier von Hand
    # setzen; er geht dann als eigenes Fenster in den Median ein.
    if auflage_datum is not None and auflage_kurs and auflage_kurs > 0:
        jahre_auflage = (pd.Timestamp(heute) - pd.Timestamp(auflage_datum)).days / 365.25
        if jahre_auflage >= 0.5:
            details.append((
                f"Seit Auflegung {pd.Timestamp(auflage_datum).strftime('%d.%m.%Y')} "
                f"({auflage_kurs:.2f} € → {schlusskurs:.2f} €)",
                ((schlusskurs / auflage_kurs) ** (1 / jahre_auflage) - 1) * 100,
            ))

    # 3) Median daraus
    werte = sorted(w for _, w in details)
    n = len(werte)
    roh = werte[n // 2] if n % 2 else (werte[n // 2 - 1] + werte[n // 2]) / 2

    # 4) Daempfung bei kurzer Historie (im Log-Raum, damit aus zwei
    #    Wachstumsraten wieder eine saubere Wachstumsrate wird)
    ergebnis = roh
    if daempfung:
        ANKER_PA = 8.0
        HALBES_VERTRAUEN = 3.0
        gewicht = jahre_hist / (jahre_hist + HALBES_VERTRAUEN)
        log_roh = np.log(max(1 + roh / 100, 1e-6))
        log_anker = np.log(1 + ANKER_PA / 100)
        ergebnis = (float(np.exp(gewicht * log_roh + (1 - gewicht) * log_anker)) - 1) * 100
        details.append((f"Median der Verfahren oben", roh))
        details.append((f"Nach Dämpfung ({gewicht * 100:.0f} % eigene Daten, "
                        f"Rest Richtung {ANKER_PA:.0f} % Marktrendite)", ergebnis))

    return ergebnis, details
