"""Wiki-Idee: Modelldepot aus den besten 50 Aktien und 20 ETFs des Bewertungssystems - reine Rechenlogik.

Ablauf (woechentlich freitags, wiki_idee_agent.py):
  1. Rangliste der Aktien aus vier Bausteinen (fehlt ein Baustein, zaehlt er neutral mit 50 - fehlende Daten
     werden nicht belohnt):
       40 %  Gesamt-Score des Bewertungssystems (scoring.py: Bewertung, Qualitaet, Wachstum, Stabilitaet,
             Dividende, Momentum)
       30 %  Investoren-Checks (Buffett, Graham, Lynch, Greenblatt, Piotroski ... - Legenden-Konsens 0-100)
       20 %  Unterbewertung: Abstand fairer Wert (Median der Bewertungsmodelle) zum Kurs, als Rang
       10 %  Qualitaet x Kurs: hohe Qualitaet bei zuletzt schwachem Kurs (6 Monate)
     Ausgeschlossen: Warnsignale (Altman-Gefahrenzone, Beneish-Verdacht, ueberwiegend Bilanz-Warnsignale).
  2. Rangliste der ETFs nach Gesamt-Score (scoring.py), ohne Hebel-/Short-Produkte, mindestens 3 Jahre Historie.
  3. Streuung: hoechstens MAX_JE_SEKTOR Aktien je Branche, hoechstens MAX_JE_ETF_GRUPPE ETFs je Region + Thema.
  4. Zielportfolio mit Puffer: gehaltene Werte bleiben, solange sie in den Top PUFFER_* stehen - kein Tausch
     wegen kleiner Score-Schwankungen; frei werdende Plaetze bekommen die Besten.
  5. Gleichgewichtung: 70 % auf die Aktien, 30 % auf die ETFs, ganze Stueckzahlen, Rest bleibt Kasse.
     Jeden Freitag werden alle Positionen auf das Zielgewicht zurueckgesetzt (im wikifolio ohne Kosten).
Das Modelldepot wird zu den Kursen des Laufs umgeschichtet - es fuehrt keine echten Trades aus.
"""
import bisect
import math

STARTKAPITAL = 100_000.0
ANTEIL_AKTIEN = 0.70
N_AKTIEN, N_ETF = 50, 20
PUFFER_AKTIEN, PUFFER_ETF = 60, 24
MAX_JE_SEKTOR = 10
MAX_JE_ETF_GRUPPE = 2
MIN_ETF_JAHRE = 3.0
UEBER_ZIEL = 0.10            # Restkasse: eine Position darf hoechstens 10 % ueber ihr Zielgewicht wachsen
BAUSTEINE = (("score", "Gesamt-Score", 40), ("investoren", "Investoren-Checks", 30),
             ("unterbewertung", "Unterbewertung", 20), ("qualitaet_kurs", "Qualität × Kurs", 10))
NEUTRAL = 50.0


def _zahl(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _rang(werte):
    """{schluessel: wert} -> {schluessel: 0..100} (Perzentil, 100 = hoechster Wert)"""
    sortiert = sorted(werte.values())
    n = len(sortiert)
    if n < 2:
        return {k: NEUTRAL for k in werte}
    return {k: 100.0 * bisect.bisect_left(sortiert, v) / (n - 1) for k, v in werte.items()}


def warnsignal(inv):
    """Grund fuer den Ausschluss aus den Investoren-Checks oder None.
    c: {check_id: [score 0-100, erfuellt, gesamt]}"""
    c = (inv or {}).get("c") or {}

    def score(cid):
        z = c.get(cid)
        return _zahl(z[0]) if isinstance(z, (list, tuple)) and z else None
    if score("altman") == 0:
        return "Altman Z-Score in der Gefahrenzone"
    if score("beneish") == 0:
        return "Beneish: Verdacht auf Bilanzmanipulation"
    rf = score("red_flags")
    if rf is not None and rf < 50:
        return "überwiegend Bilanz-Warnsignale"
    return None


def aktien_rangliste(eintraege, investoren=None):
    """eintraege: [(e, b)] mit e aus scoring.universum (art "aktie") und b = scoring.bewerten(e, ver).
    investoren: {ticker: Kurzform aus state/investoren/ergebnis_NN.json}.
    -> (liste absteigend nach "mix", ausgeschlossen: [{name, grund}])"""
    investoren = investoren or {}
    kand, aus = {}, []
    for e, b in eintraege:
        if e.get("art") != "aktie" or not _zahl(e.get("kurs")) or (b or {}).get("gesamt") is None:
            continue
        inv = investoren.get(e.get("ticker") or "") or {}
        grund = warnsignal(inv)
        if grund:
            aus.append({"name": e["name"], "grund": grund})
            continue
        kand[e["id"]] = (e, b, inv)
    fv = _rang({i: _zahl(inv.get("fv")) for i, (_, _, inv) in kand.items() if _zahl(inv.get("fv")) is not None})
    qual = _rang({i: _zahl((e.get("info") or {}).get("gesamt")) for i, (e, _, _) in kand.items()
                  if _zahl((e.get("info") or {}).get("gesamt")) is not None})
    kurs6 = _rang({i: _zahl(e["k"].get("p6")) for i, (e, _, _) in kand.items() if _zahl(e["k"].get("p6")) is not None})
    liste = []
    for i, (e, b, inv) in kand.items():
        qk = None
        if i in qual and i in kurs6:
            qk = 0.5 * qual[i] + 0.5 * (100.0 - kurs6[i])          # gute Firma, schwacher Kurs
        teile = {"score": b["gesamt"], "investoren": _zahl(inv.get("score")), "unterbewertung": fv.get(i),
                 "qualitaet_kurs": qk}
        mix = sum(g * (NEUTRAL if teile[k] is None else teile[k]) for k, _, g in BAUSTEINE) / \
            sum(g for _, _, g in BAUSTEINE)
        liste.append({"id": i, "art": "aktie", "name": e["name"], "ticker": e.get("ticker") or "",
                      "wkn": e.get("wkn") or "", "isin": e.get("isin") or "", "gruppe": e.get("sektor") or "–",
                      "kurs": _zahl(e["kurs"]), "mix": round(mix, 1),
                      "teile": {k: (None if v is None else round(v, 1)) for k, v in teile.items()},
                      "note": inv.get("note"), "kaufen": inv.get("kaufen"), "von": inv.get("inv"),
                      "fv": _zahl(inv.get("fv")), "fazit": b.get("fazit")})
    liste.sort(key=lambda w: (-w["mix"], w["name"].lower()))
    for r, w in enumerate(liste, 1):
        w["rang"] = r
    return liste, aus


def etf_rangliste(eintraege, hebel_muster=None, merkmale=None):
    """eintraege: [(e, b)] mit art "etf". hebel_muster: Regex fuer Hebel/Short (klassen_score.HEBEL);
    merkmale: Funktion name -> {"region", "themen"} (etf_merkmale.merkmale) fuer die Streuung."""
    liste = []
    for e, b in eintraege:
        if e.get("art") != "etf" or not _zahl(e.get("kurs")) or (b or {}).get("gesamt") is None:
            continue
        if hebel_muster is not None and hebel_muster.search(e["name"]):
            continue
        if (_zahl(e["k"].get("jahre")) or 0) < MIN_ETF_JAHRE:
            continue
        mm = merkmale(e["name"]) if merkmale else {}
        # ohne erkennbare Region keine Gruppe (sonst landeten alle unbekannten ETFs in einer)
        gruppe = f'{mm["region"]} · {"/".join(mm.get("themen") or ["–"])}' \
            if mm and mm.get("region") not in (None, "Sonstige") else "–"
        liste.append({"id": e["id"], "art": "etf", "name": e["name"], "ticker": "", "wkn": e.get("wkn") or "",
                      "isin": e.get("isin") or "", "gruppe": gruppe, "kurs": _zahl(e["kurs"]),
                      "mix": round(b["gesamt"], 1), "teile": {"score": round(b["gesamt"], 1)}})
    liste.sort(key=lambda w: (-w["mix"], w["name"].lower()))
    for r, w in enumerate(liste, 1):
        w["rang"] = r
    return liste


def auswahl(rangliste, n, puffer, gehalten, max_je_gruppe, budget=None):
    """Zielwerte: gehaltene Werte innerhalb der Top `puffer` bleiben (bessere zuerst), dann die Besten bis n.
    Hoechstens max_je_gruppe je Gruppe (Branche bzw. Region/Thema) - reicht das nicht fuer n Werte, wird mit
    den naechstbesten aufgefuellt; Werte, deren Kurs ueber dem Budget je
    Position liegt (keine ganze Stueckzahl moeglich), werden uebersprungen."""
    gehalten = set(gehalten or ())
    je_gruppe, ziel = {}, []

    def passt(w):
        if budget is not None and w["kurs"] > budget:
            return False
        return je_gruppe.get(w["gruppe"], 0) < max_je_gruppe or w["gruppe"] == "–"

    def nehmen(w):
        ziel.append(w)
        je_gruppe[w["gruppe"]] = je_gruppe.get(w["gruppe"], 0) + 1

    for w in rangliste[:puffer]:
        if w["id"] in gehalten and len(ziel) < n and passt(w):
            nehmen(w)
    gewaehlt = {w["id"] for w in ziel}
    for w in rangliste:
        if len(ziel) >= n:
            break
        if w["id"] not in gewaehlt and passt(w):
            nehmen(w)
            gewaehlt.add(w["id"])
    # Streuungsregel laesst zu wenige zu: mit den naechstbesten auffuellen (Budget gilt weiter)
    for w in rangliste:
        if len(ziel) >= n:
            break
        if w["id"] not in gewaehlt and (budget is None or w["kurs"] <= budget):
            nehmen(w)
            gewaehlt.add(w["id"])
    return sorted(ziel, key=lambda w: w["rang"])


def stueckzahlen(ziel_aktien, ziel_etf, kapital, anteil_aktien=ANTEIL_AKTIEN):
    """Gleichgewichtung je Klasse in ganzen Stueck: erst abgerundet, dann wird die Restkasse Stueck fuer Stueck
    an die Position verteilt, die (relativ) am weitesten unter ihrem Zielwert liegt - so bleibt kaum Kasse
    uebrig, ohne einen Zielwert um mehr als eine Aktie zu ueberschreiten.
    -> (positionen {id: {..., stueck, wert, ziel}}, kasse)"""
    pos = {}
    for liste, topf in ((ziel_aktien, kapital * anteil_aktien), (ziel_etf, kapital * (1 - anteil_aktien))):
        if not liste:
            continue
        je = topf / len(liste)
        for w in liste:
            if not w["kurs"] or w["kurs"] <= 0:
                continue
            pos[w["id"]] = {"id": w["id"], "art": w["art"], "name": w["name"], "wkn": w["wkn"], "isin": w["isin"],
                            "ticker": w.get("ticker", ""), "gruppe": w["gruppe"], "rang": w["rang"], "mix": w["mix"],
                            "teile": w.get("teile") or {}, "stueck": int(je // w["kurs"]), "kurs": w["kurs"],
                            "ziel": je}
    kasse = kapital - sum(p["stueck"] * p["kurs"] for p in pos.values())
    while True:
        # aufstocken nur bis hoechstens 10 % ueber Ziel bzw. eine Aktie ueber Ziel (bei teuren Werten)
        passend = [p for p in pos.values() if p["kurs"] <= kasse + 1e-9 and
                   (p["stueck"] + 1) * p["kurs"] <= max(p["ziel"] * (1 + UEBER_ZIEL), p["ziel"] + p["kurs"])]
        if not passend:
            break
        p = min(passend, key=lambda p: ((p["stueck"] + 1) * p["kurs"] - p["ziel"]) / p["ziel"])
        p["stueck"] += 1
        kasse -= p["kurs"]
    pos = {i: p for i, p in pos.items() if p["stueck"] > 0}
    for p in pos.values():
        p["wert"] = round(p["stueck"] * p["kurs"], 2)
        p["ziel"] = round(p["ziel"], 2)
    return pos, round(kapital - sum(p["stueck"] * p["kurs"] for p in pos.values()), 2)


def bewerten_depot(depot, preise):
    """Aktueller Wert der Positionen (preise: {id: kurs}; fehlt ein Kurs, gilt der letzte bekannte)."""
    wert = float(depot.get("kasse") or 0)
    for p in (depot.get("positionen") or {}).values():
        wert += p["stueck"] * (preise.get(p["id"]) or p["kurs"])
    return round(wert, 2)


def auftraege(alt, neu):
    """Unterschied alter -> neuer Bestand: [{aktion: Kauf|Verkauf|Neu|Raus, id, name, wkn, isin, art, stueck,
    vorher, nachher, kurs}] - Raus/Verkauf zuerst (setzt Kasse frei), dann Neu/Kauf."""
    aus = []
    for i in set(alt) | set(neu):
        a, n = alt.get(i), neu.get(i)
        vorher, nachher = (a or {}).get("stueck", 0), (n or {}).get("stueck", 0)
        if vorher == nachher:
            continue
        p = n or a
        aktion = "Neu" if not vorher else "Raus" if not nachher else "Kauf" if nachher > vorher else "Verkauf"
        aus.append({"aktion": aktion, "id": i, "name": p["name"], "wkn": p.get("wkn", ""), "isin": p.get("isin", ""),
                    "art": p["art"], "stueck": abs(nachher - vorher), "vorher": vorher, "nachher": nachher,
                    "kurs": p["kurs"]})
    folge = {"Raus": 0, "Verkauf": 1, "Neu": 2, "Kauf": 3}
    aus.sort(key=lambda x: (folge[x["aktion"]], x["art"], x["name"].lower()))
    return aus


def umschichten(depot, rang_aktien, rang_etf, preise, datum, startkapital=STARTKAPITAL):
    """Ein Freitagslauf. depot: bisheriger Stand ({} beim Start). preise: {id: aktueller Kurs EUR} fuer die
    gehaltenen Werte (Kurse der Ranglisten gelten fuer neue). -> (neues depot, auftraege)"""
    alt = dict(depot.get("positionen") or {})
    for i, p in alt.items():                                   # aktuelle Kurse fuer die alten Positionen
        if preise.get(i):
            alt[i] = dict(p, kurs=preise[i])
    kapital = bewerten_depot({"positionen": alt, "kasse": depot.get("kasse")}, preise) if alt else startkapital
    for liste in (rang_aktien, rang_etf):
        for w in liste:
            if preise.get(w["id"]):
                w["kurs"] = preise[w["id"]]
    gehalten = set(alt)
    ziel_a = auswahl(rang_aktien, N_AKTIEN, PUFFER_AKTIEN, gehalten, MAX_JE_SEKTOR,
                     budget=kapital * ANTEIL_AKTIEN / N_AKTIEN)
    ziel_e = auswahl(rang_etf, N_ETF, PUFFER_ETF, gehalten, MAX_JE_ETF_GRUPPE,
                     budget=kapital * (1 - ANTEIL_AKTIEN) / N_ETF)
    pos, kasse = stueckzahlen(ziel_a, ziel_e, kapital)
    liste = auftraege(alt, pos)
    historie = list(depot.get("historie") or [])
    if not historie or historie[-1][0] != datum:
        historie.append([datum, round(kapital, 2)])
    else:
        historie[-1] = [datum, round(kapital, 2)]
    laeufe = (list(depot.get("laeufe") or []) + [{"datum": datum, "wert": round(kapital, 2),
                                                   "auftraege": liste}])[-26:]   # ein halbes Jahr Protokoll
    neu = {"start": depot.get("start") or datum, "startkapital": depot.get("startkapital") or startkapital,
           "stand": datum, "wert": round(kapital, 2), "kasse": kasse, "positionen": pos, "historie": historie,
           "laeufe": laeufe}
    return neu, liste


# ---------------------------------------------------------------------------
# Mail
# ---------------------------------------------------------------------------
def _de(x, dez=2):
    return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _h(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def mail_text(depot, liste, app_url=""):
    """(Betreff, Text, HTML) der Freitags-Mail mit den Anpassungen."""
    start, wert = depot["startkapital"], depot["wert"]
    rendite = (wert / start - 1) * 100 if start else 0.0
    betreff = (f"Wiki-Idee {depot['stand']}: {len(liste)} Anpassungen · Depot {_de(wert, 0)} € "
               f"({'+' if rendite >= 0 else ''}{_de(rendite, 1)} %)")
    zeilen = [f"{a['aktion']:8} {a['stueck']:>6} × {a['name'][:40]} ({a['wkn'] or a['isin']}) "
              f"zu ca. {_de(a['kurs'])} €  ({a['vorher']} → {a['nachher']} Stück)" for a in liste]
    text = (f"Wiki-Idee – Umschichtung vom {depot['stand']}\n\n"
            f"Depotwert: {_de(wert)} € (Start {_de(start, 0)} € am {depot['start']}, "
            f"{'+' if rendite >= 0 else ''}{_de(rendite, 1)} %)\n"
            f"Positionen: {sum(1 for p in depot['positionen'].values() if p['art'] == 'aktie')} Aktien, "
            f"{sum(1 for p in depot['positionen'].values() if p['art'] == 'etf')} ETFs · Kasse {_de(depot['kasse'])} €\n\n"
            + ("Anpassungen (erst Verkäufe, dann Käufe):\n" + "\n".join(zeilen) if zeilen
               else "Keine Anpassungen nötig.") +
            ("\n\nDetails im Dashboard: " + app_url if app_url else "") +
            "\n\nModellrechnung aus vergangenen Daten – keine Anlageberatung. Kurse: letzter verfügbarer Kurs "
            "beim Lauf, im wikifolio kann der Ausführungskurs abweichen.")
    farbe = {"Neu": "#16a34a", "Kauf": "#16a34a", "Verkauf": "#dc2626", "Raus": "#dc2626"}
    tz = "".join(f'<tr><td style="color:{farbe[a["aktion"]]};font-weight:600">{a["aktion"]}</td>'
                 f'<td style="text-align:right">{a["stueck"]}</td><td>{_h(a["name"])}<br><small>{_h(a["wkn"] or a["isin"])}'
                 f' · {"Aktie" if a["art"] == "aktie" else "ETF"}</small></td>'
                 f'<td style="text-align:right">{_de(a["kurs"])} €</td>'
                 f'<td style="text-align:right">{a["vorher"]} → {a["nachher"]}</td></tr>' for a in liste)
    html = (f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#111">'
            f'<h2 style="margin:0 0 8px">Wiki-Idee – Umschichtung vom {_h(depot["stand"])}</h2>'
            f'<p>Depotwert <b>{_de(wert)} €</b> · Start {_de(start, 0)} € am {_h(depot["start"])} · '
            f'<b style="color:{"#16a34a" if rendite >= 0 else "#dc2626"}">{"+" if rendite >= 0 else ""}'
            f'{_de(rendite, 1)} %</b> · Kasse {_de(depot["kasse"])} €</p>'
            + (f'<table cellpadding="6" style="border-collapse:collapse;border:1px solid #ddd">'
               f'<tr style="background:#f3f4f6"><th>Aktion</th><th>Stück</th><th>Wert</th><th>Kurs ca.</th>'
               f'<th>Bestand</th></tr>{tz}</table>' if liste else "<p>Keine Anpassungen nötig.</p>")
            + (f'<p><a href="{_h(app_url)}">Details im Dashboard</a></p>' if app_url else "")
            + '<p style="color:#666;font-size:12px">Modellrechnung aus vergangenen Daten – keine Anlageberatung. '
              'Kurse: letzter verfügbarer Kurs beim Lauf, im wikifolio kann der Ausführungskurs abweichen.</p></div>')
    return betreff, text, html

