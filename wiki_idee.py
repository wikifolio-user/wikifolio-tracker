"""Wiki-Idee: Modelldepot aus den besten 50 Aktien und 20 ETFs des Bewertungssystems - reine Rechenlogik.

Ablauf (nach Bedarf: Knopf "Liste jetzt erstellen" in der Ansicht Wiki-Idee, wiki_idee_ui.py):
  1. Rangliste der Aktien aus vier Bausteinen (fehlt ein Baustein, zaehlt er neutral mit 50 - fehlende Daten
     werden nicht belohnt):
       40 %  Qualitaets-Score aus "Ranglisten & Screener" (Qualitaets-Agent: Wachstum, Rendite auf das
             Kapital, Margen, Bilanz, Bewertung - state/qualitaet/alle_N.json, Feld "gesamt")
       30 %  Investoren-Checks (Buffett, Graham, Lynch, Greenblatt, Piotroski ... - Legenden-Konsens 0-100)
       20 %  Unterbewertung: Abstand fairer Wert (Median der Bewertungsmodelle) zum Kurs, als Rang
       10 %  Qualitaet x Kurs: hohe Qualitaet bei zuletzt schwachem Kurs (6 Monate)
     Ausgeschlossen: Warnsignale (Altman-Gefahrenzone, Beneish-Verdacht, ueberwiegend Bilanz-Warnsignale).
  2. Rangliste der ETFs nach dem ETF-Score aus "Ranglisten & Screener" (klassen_score.py), ohne Hebel-/Short-
     Produkte, mindestens 3 Jahre Historie.
  3. Streuung: hoechstens MAX_JE_SEKTOR Aktien je Branche, hoechstens MAX_JE_ETF_GRUPPE ETFs je Region + Thema.
  4. Zielportfolio mit Puffer: gehaltene Werte bleiben, solange sie in den Top PUFFER_* stehen - kein Tausch
     wegen kleiner Score-Schwankungen; frei werdende Plaetze bekommen die Besten.
  5. Gleichgewichtung: 70 % auf die Aktien, 30 % auf die ETFs, ganze Stueckzahlen, Restkasse wird verteilt.
     Jede Liste setzt alle Positionen auf das Zielgewicht zurueck (im wikifolio ohne Kosten).
Die Liste nennt Kaeufe und Verkaeufe zu den Kursen der Abfrage. Das Modelldepot uebernimmt sie erst, wenn der
Nutzer sie als umgesetzt bestaetigt - es fuehrt keine echten Trades aus.
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
BAUSTEINE = (("score", "Qualitäts-Score", 40), ("investoren", "Investoren-Checks", 30),
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


def eur_kurs(e, eur_kurse=None):
    """Kurs in EUR: aus eur_kurse (WKN/ISIN -> EUR, Katalog bzw. ls-tc), sonst e["kurs"] nur, wenn er in EUR
    ist (der Gesamt-Score fuehrt Aktien teils in Landeswaehrung) - sonst None."""
    for k in (e.get("wkn"), e.get("isin"), e.get("ticker")):
        if k and eur_kurse and _zahl(eur_kurse.get(str(k).upper())):
            return _zahl(eur_kurse[str(k).upper()])
    return _zahl(e.get("kurs")) if str(e.get("waehrung") or "EUR").upper() == "EUR" else None


def gewichtet(teile):
    """Gesamt-Score: gewichteter Durchschnitt der VORHANDENEN Bausteine - fehlt einer (z. B. noch keine
    Investoren-Checks), geht sein Gewicht anteilig auf die uebrigen ueber (kein Deckel durch Neutralwerte)."""
    da = [(g, teile[k]) for k, _, g in BAUSTEINE if teile.get(k) is not None]
    return sum(g * v for g, v in da) / sum(g for g, _ in da) if da else 0.0


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


def aktien_rangliste(eintraege, investoren=None, eur_kurse=None):
    """eintraege: [(e, b)] mit e aus scoring.universum (art "aktie"; Qualitaets-Score in e["info"]["gesamt"]),
    b optional (scoring.bewerten, nur fuer das Fazit).
    investoren: {ticker: Kurzform aus state/investoren/ergebnis_NN.json}. eur_kurse: siehe eur_kurs.
    -> (liste absteigend nach "mix", ausgeschlossen: [{name, grund}])"""
    investoren = investoren or {}
    kand, aus = {}, []
    for e, b in eintraege:
        if e.get("art") != "aktie" or not eur_kurs(e, eur_kurse) or \
                _zahl((e.get("info") or {}).get("gesamt")) is None:
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
        teile = {"score": _zahl(e["info"]["gesamt"]), "investoren": _zahl(inv.get("score")), "unterbewertung": fv.get(i),
                 "qualitaet_kurs": qk}
        mix = gewichtet(teile)
        liste.append({"id": i, "art": "aktie", "name": e["name"], "ticker": e.get("ticker") or "",
                      "wkn": e.get("wkn") or "", "isin": e.get("isin") or "", "gruppe": e.get("sektor") or "–",
                      "kurs": eur_kurs(e, eur_kurse), "mix": round(mix, 1),
                      "teile": {k: (None if v is None else round(v, 1)) for k, v in teile.items()},
                      "note": inv.get("note"), "kaufen": inv.get("kaufen"), "von": inv.get("inv"),
                      "fv": _zahl(inv.get("fv")), "fazit": (b or {}).get("fazit"),
                      "klasse": (e.get("info") or {}).get("klasse"),
                      "detail": {"q": (e.get("info") or {}).get("q") or {}, "fv": _zahl(inv.get("fv")),
                                 "inv": {"note": inv.get("note"), "kaufen": inv.get("kaufen"), "von": inv.get("inv"),
                                         "w": inv.get("w"),
                                         "c": {cid: z[0] for cid, z in (inv.get("c") or {}).items()
                                               if isinstance(z, (list, tuple)) and z and z[0] is not None}}}})
    liste.sort(key=lambda w: (-w["mix"], w["name"].lower()))
    for r, w in enumerate(liste, 1):
        w["rang"], w["von_gesamt"] = r, len(liste)
    return liste, aus


def _etf_score(e, b, etf_score):
    """ETF-Score (klassen_score.je_kennung: {WKN/ISIN: {score, jahre, einordnung}}) - ohne Tabelle (Tests)
    der Score aus b."""
    if etf_score is None:
        return ({"score": (b or {}).get("gesamt"), "jahre": e["k"].get("jahre")}
                if (b or {}).get("gesamt") is not None else None)
    return next((etf_score[str(k).upper()] for k in (e.get("wkn"), e.get("isin"))
                 if k and str(k).upper() in etf_score), None)


def etf_rangliste(eintraege, hebel_muster=None, merkmale=None, eur_kurse=None, etf_score=None):
    """eintraege: [(e, b)] mit art "etf". hebel_muster: Regex fuer Hebel/Short (klassen_score.HEBEL);
    merkmale: Funktion name -> {"region", "themen"} (etf_merkmale.merkmale) fuer die Streuung;
    etf_score: ETF-Score aus "Ranglisten & Screener" je WKN/ISIN (klassen_score.je_kennung(katalog, "etf"))."""
    liste = []
    for e, b in eintraege:
        s_ = _etf_score(e, b, etf_score) if e.get("art") == "etf" else None
        if not s_ or _zahl(s_.get("score")) is None or not eur_kurs(e, eur_kurse):
            continue
        if hebel_muster is not None and hebel_muster.search(e["name"]):
            continue
        if (_zahl(s_.get("jahre")) or _zahl(e["k"].get("jahre")) or 0) < MIN_ETF_JAHRE:
            continue
        mm = merkmale(e["name"]) if merkmale else {}
        # ohne erkennbare Region keine Gruppe (sonst landeten alle unbekannten ETFs in einer)
        gruppe = f'{mm["region"]} · {"/".join(mm.get("themen") or ["–"])}' \
            if mm and mm.get("region") not in (None, "Sonstige") else "–"
        liste.append({"id": e["id"], "art": "etf", "name": e["name"], "ticker": "", "wkn": e.get("wkn") or "",
                      "isin": e.get("isin") or "", "gruppe": gruppe, "kurs": eur_kurs(e, eur_kurse),
                      "mix": round(_zahl(s_["score"]), 1), "teile": {"score": round(_zahl(s_["score"]), 1)},
                      "klasse": s_.get("einordnung"),
                      "detail": {"etf": {k: s_.get(k) for k in ("rendite", "rendite_jahre", "rr", "dd", "vola",
                                                               "jahre", "einordnung") if s_.get(k) is not None},
                                 "mm": {k: mm.get(k) for k in ("region", "themen", "anbieter", "ertrag")} if mm else {}}})
    liste.sort(key=lambda w: (-w["mix"], w["name"].lower()))
    for r, w in enumerate(liste, 1):
        w["rang"], w["von_gesamt"] = r, len(liste)
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

    def nehmen(w, grund):
        w["auswahl"] = grund
        ziel.append(w)
        je_gruppe[w["gruppe"]] = je_gruppe.get(w["gruppe"], 0) + 1

    for w in rangliste[:puffer]:
        if w["id"] in gehalten and len(ziel) < n and passt(w):
            nehmen(w, "gehalten" if w["rang"] <= n else "puffer")
    gewaehlt = {w["id"] for w in ziel}
    for w in rangliste:
        if len(ziel) >= n:
            break
        if w["id"] not in gewaehlt and passt(w):
            nehmen(w, "top" if w["rang"] <= n else "nachgerueckt")
            gewaehlt.add(w["id"])
    # Streuungsregel laesst zu wenige zu: mit den naechstbesten auffuellen (Budget gilt weiter)
    for w in rangliste:
        if len(ziel) >= n:
            break
        if w["id"] not in gewaehlt and (budget is None or w["kurs"] <= budget):
            nehmen(w, "aufgefuellt")
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
                            "ziel": je, "detail": w.get("detail") or {}, "auswahl": w.get("auswahl"),
                            "von_gesamt": w.get("von_gesamt")}
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


def ranglisten(bewertet, investoren=None, hebel_muster=None, merkmale=None, eur_kurse=None, etf_score=None):
    """bewertet: [(e, scoring.bewerten(e, ver))] aller Aktien und ETFs. -> (aktien, ausgeschlossen, etfs)"""
    rang_a, aus = aktien_rangliste([x for x in bewertet if x[0].get("art") == "aktie"], investoren, eur_kurse)
    rang_e = etf_rangliste([x for x in bewertet if x[0].get("art") == "etf"], hebel_muster, merkmale, eur_kurse,
                           etf_score)
    return rang_a, aus, rang_e


def kurs_kandidaten(depot, rang_aktien, rang_etf, n_aktien=100, n_etf=40):
    """Werte, fuer die zum Abfragezeitpunkt der aktuelle Kurs gebraucht wird: gehaltene + die vorderen Plaetze."""
    aus = {}
    for w in list((depot.get("positionen") or {}).values()) + rang_aktien[:n_aktien] + rang_etf[:n_etf]:
        aus.setdefault(w["id"], w)
    return list(aus.values())


def umschichten(depot, rang_aktien, rang_etf, preise, datum, startkapital=STARTKAPITAL, zeitpunkt=None):
    """Eine Umschichtung. depot: bisheriger Stand ({} beim Start). preise: {id: aktueller Kurs EUR}
    (fehlt einer, gilt der Kurs aus den Ranglisten bzw. der letzte bekannte). -> (neues depot, auftraege)"""
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
    laeufe = (list(depot.get("laeufe") or []) + [{"datum": datum, "zeit": zeitpunkt or datum,
                                                   "wert": round(kapital, 2), "auftraege": liste}])[-30:]
    neu = {"start": depot.get("start") or datum, "startkapital": depot.get("startkapital") or startkapital,
           "stand": datum, "wert": round(kapital, 2), "kasse": kasse, "positionen": pos, "historie": historie,
           "laeufe": laeufe}
    return neu, liste


def betraege(liste):
    """Auftraege mit Betrag (Verkauf negativ, Korrektur 0) und Summen. -> (zeilen, {"kauf": €, "verkauf": €})"""
    zeilen, kauf, verkauf = [], 0.0, 0.0
    for a in liste:
        vz = 1 if a["aktion"] in ("Neu", "Kauf") else 0 if a["aktion"] == "Korrektur" else -1
        b = a["stueck"] * a["kurs"] * vz
        zeilen.append(dict(a, betrag=round(b, 2)))
        if b > 0:
            kauf += b
        else:
            verkauf -= b
    return zeilen, {"kauf": round(kauf, 2), "verkauf": round(verkauf, 2)}


def signatur(depot):
    """Kennung eines gespeicherten Stands - eine Liste darf nur auf genau dem Stand uebernommen werden, von dem
    sie berechnet wurde (sonst wurde inzwischen anderswo umgeschichtet)."""
    laeufe = (depot or {}).get("laeufe") or []
    return [len(laeufe), (laeufe[-1].get("zeit") if laeufe else None), (depot or {}).get("wert")]


def uebernehmen(gespeichert, neu, basis):
    """Neuer Stand zum Speichern (mit dem alten als "vorher" fuer Rueckgaengig) oder None, wenn sich der
    gespeicherte Stand seit der Berechnung geaendert hat."""
    if signatur(gespeichert) != basis:
        return None
    vorher = {k: v for k, v in (gespeichert or {}).items() if k != "vorher"}
    return dict(neu, vorher=vorher)


def rueckgaengig(gespeichert):
    """Stand vor der letzten Uebernahme ({} = noch kein Depot) oder None, wenn es keinen gibt."""
    if not gespeichert or "vorher" not in gespeichert:
        return None
    return gespeichert["vorher"] or {}


def ausfuehren(alt, neu, ist):
    """Die Liste so uebernehmen, wie sie im wikifolio tatsaechlich umgesetzt wurde.
    alt: Depot, von dem die Liste berechnet wurde ({} beim Start); neu: Ergebnis von umschichten;
    ist: {id: {"stueck": ausgefuehrte Stueck (0 = nicht ausgefuehrt), "kurs": Ausfuehrungskurs}} - fehlt ein
    Auftrag, gilt er wie geplant. Kasse = alte Kasse (beim Start das Startkapital) + Verkaeufe - Kaeufe.
    -> Depot wie neu, aber mit den tatsaechlichen Stueckzahlen, Kursen und der Kasse."""
    alt_pos = (alt or {}).get("positionen") or {}
    neu_pos = neu.get("positionen") or {}
    pos = {}
    for i, p in alt_pos.items():                       # Ausgangsbestand mit aktuellem Kurs und neuem Rang
        basis = neu_pos.get(i) or p
        pos[i] = dict(basis, stueck=p["stueck"], kurs=basis["kurs"])
    kasse = float(alt.get("kasse") or 0) if alt_pos else float(neu.get("startkapital") or STARTKAPITAL)
    lauf = dict((neu.get("laeufe") or [{}])[-1])
    ausgefuehrt = []
    for a in lauf.get("auftraege") or []:
        x = ist.get(a["id"]) or {}
        stueck = max(int(x.get("stueck", a["stueck"]) or 0), 0)
        kurs = _zahl(x.get("kurs")) or a["kurs"]
        if stueck <= 0:
            continue
        vz = 1 if a["aktion"] in ("Neu", "Kauf") else -1
        if vz < 0:
            stueck = min(stueck, (pos.get(a["id"]) or {}).get("stueck", 0))   # nie mehr verkaufen als da ist
            if not stueck:
                continue
        meta = neu_pos.get(a["id"]) or alt_pos.get(a["id"])
        p = pos.get(a["id"]) or dict(meta, stueck=0)
        p = dict(p, stueck=p["stueck"] + vz * stueck, kurs=kurs if vz > 0 else p["kurs"])
        kasse -= vz * stueck * kurs
        if p["stueck"] > 0:
            pos[a["id"]] = p
        else:
            pos.pop(a["id"], None)
        ausgefuehrt.append(dict(a, stueck=stueck, kurs=round(kurs, 4), nachher=p["stueck"],
                                geplant=a["stueck"], kurs_geplant=a["kurs"]))
    for p in pos.values():
        p["wert"] = round(p["stueck"] * p["kurs"], 2)
    wert = round(sum(p["wert"] for p in pos.values()) + kasse, 2)
    lauf["auftraege"] = ausgefuehrt
    return dict(neu, positionen=pos, kasse=round(kasse, 2), wert=wert,
                laeufe=list(neu.get("laeufe") or [])[:-1] + [lauf])


def korrigieren(depot, zeilen, kasse, datum, zeitpunkt=None):
    """Bestand von Hand an die echte Umsetzung anpassen. zeilen: [{id (None = neu), name, wkn, isin, art, stueck,
    kurs}] - Positionen, die fehlen, werden entfernt; Stueck 0 entfernt ebenfalls. -> neues Depot (mit einem
    Protokolleintrag "Korrektur")"""
    alt = depot.get("positionen") or {}
    pos, aend = {}, []
    for z in zeilen:
        stueck, kurs = int(z.get("stueck") or 0), _zahl(z.get("kurs"))
        kennung = str(z.get("wkn") or z.get("isin") or "").strip().upper()
        i = z.get("id") or (f"H:{kennung}" if kennung else None)
        if not i or stueck <= 0 or not kurs or kurs <= 0:
            continue
        basis = alt.get(i) or {"id": i, "art": z.get("art") or "aktie", "name": str(z.get("name") or kennung),
                                "wkn": str(z.get("wkn") or ""), "isin": str(z.get("isin") or ""), "ticker": "",
                                "gruppe": "–", "rang": 999, "mix": None, "teile": {}}
        p = dict(basis, stueck=stueck, kurs=kurs, wert=round(stueck * kurs, 2),
                 name=str(z.get("name") or basis["name"]))
        pos[i] = p
        vorher = (alt.get(i) or {}).get("stueck", 0)
        if vorher != stueck or abs(((alt.get(i) or {}).get("kurs") or 0) - kurs) > 1e-9:
            aend.append({"aktion": "Korrektur", "id": i, "name": p["name"], "wkn": p["wkn"], "isin": p["isin"],
                         "art": p["art"], "stueck": stueck, "vorher": vorher, "nachher": stueck, "kurs": kurs})
    for i, p in alt.items():
        if i not in pos:
            aend.append({"aktion": "Korrektur", "id": i, "name": p["name"], "wkn": p.get("wkn", ""),
                         "isin": p.get("isin", ""), "art": p["art"], "stueck": 0, "vorher": p["stueck"],
                         "nachher": 0, "kurs": p["kurs"]})
    kasse = round(float(kasse or 0), 2)
    if abs(kasse - float(depot.get("kasse") or 0)) > 0.005:
        aend.append({"aktion": "Korrektur", "id": "_kasse", "name": "Kasse", "wkn": "", "isin": "", "art": "kasse",
                     "stueck": 0, "vorher": depot.get("kasse"), "nachher": kasse, "kurs": 0})
    wert = round(sum(p["wert"] for p in pos.values()) + kasse, 2)
    laeufe = (list(depot.get("laeufe") or []) + [{"datum": datum, "zeit": zeitpunkt or datum, "wert": wert,
                                                   "auftraege": aend, "korrektur": True}])[-30:]
    return dict({k: v for k, v in depot.items() if k != "vorher"}, positionen=pos, kasse=kasse, wert=wert,
                stand=datum, laeufe=laeufe), aend


# ---------------------------------------------------------------------------
# Werte direkt aus "Ranglisten & Screener"
# ---------------------------------------------------------------------------
UNTEREINHEIT = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ILA": ("ILS", 100), "ZAc": ("ZAR", 100),
                "ZAC": ("ZAR", 100), "KWF": ("KWD", 1000)}


def in_eur(kurs, waehrung, fx):
    """Kurs in Landeswaehrung -> EUR. fx: {Waehrung: Einheiten je 1 EUR} (state/top50_fx.json, Feld [1]).
    Ohne Wechselkurs -> None (lieber kein Wert als ein falscher)."""
    k = _zahl(kurs)
    if not k or k <= 0:
        return None
    w = str(waehrung or "EUR")
    w, teiler = UNTEREINHEIT.get(w, (w.upper(), 1))
    if w == "EUR":
        return round(k / teiler, 4)
    rate = _zahl((fx or {}).get(w))
    return round(k / teiler / rate, 4) if rate and rate > 0 else None


# Felder der Rangliste "Qualitaets-Score", die in die Begruendung je Wert eingehen
Q_DETAIL = ("pt", "g_ums", "g_eps", "g_fcf", "roic", "om", "fkgv", "ev_ebit", "fcfy", "moat", "mgmt", "bew", "risiko",
            "mos", "div", "p12", "q_ant", "b_ant")
# Punkte je Bereich (Reihenfolge wie "pt" im Qualitaets-Agenten) mit Hoechstpunktzahl
Q_BEREICHE = (("Qualität", 20), ("Wachstum", 15), ("Cashflow", 15), ("Bilanz", 10), ("Management", 10),
              ("Burggraben", 10), ("Bewertung", 15), ("Chance", 5))


def aktien_aus_qualitaet(alle_teile, yahoo_isin=None, fx=None):
    """Alle Aktien der Rangliste "Qualitaets-Score" (state/qualitaet/alle_N.json) als Eintraege fuer
    aktien_rangliste - Kurs in EUR, ISIN aus state/top50_yahoo.json ({ISIN: Symbol})."""
    isin_je = {str(s): str(i).upper() for i, s in (yahoo_isin or {}).items() if s}
    aus = []
    for d in alle_teile or []:
        felder = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            q = dict(zip(felder, z))
            s = str(q.get("s") or "").strip()
            if not s or _zahl(q.get("gesamt")) is None:
                continue
            aus.append({"id": s, "art": "aktie", "name": str(q.get("name") or s).strip(), "ticker": s, "wkn": "",
                        "isin": isin_je.get(s, ""), "sektor": str(q.get("br") or ""),
                        "kurs": in_eur(q.get("kurs"), q.get("kwae"), fx), "waehrung": "EUR",
                        "k": {"p6": _zahl(q.get("p6"))},
                        "info": {"gesamt": _zahl(q.get("gesamt")), "klasse": q.get("klasse"),
                                 "q": {k: q.get(k) for k in Q_DETAIL if q.get(k) not in (None, "")}}})
    return aus


def etfs_aus_katalog(katalog_teile):
    """Alle ETFs des Katalogs (Grundlage des ETF-Scores) als Eintraege fuer etf_rangliste - Kurs in EUR."""
    aus, gesehen = [], set()
    for d in katalog_teile or []:
        felder = (d or {}).get("felder") or []
        for z in (d or {}).get("zeilen") or []:
            w = dict(zip(felder, z))
            if w.get("typ") != "etf":
                continue
            kenn, isin = str(w.get("kennung") or "").upper(), str(w.get("isin") or "").upper()
            i = isin or kenn
            if not i or i in gesehen:
                continue
            gesehen.add(i)
            aus.append({"id": i, "art": "etf", "name": str(w.get("name") or i), "ticker": "", "wkn": kenn,
                        "isin": isin, "kurs": _zahl(w.get("kurs")), "waehrung": "EUR",
                        "k": {"jahre": _zahl(w.get("jahre"))}, "info": {}})
    return aus


def handelbar(aktien, ids=None, mindestens=2 * N_AKTIEN):
    """Nur Aktien, die man im wikifolio auch findet: mit ISIN; und - wenn davon genug uebrig bleiben - nur
    solche mit bekannter Kurs-ID bei Lang & Schwarz (ids: {WKN/ISIN/Symbol: id}), dem Handelspartner von
    wikifolio. -> (liste, nur_ls: bool)"""
    mit_isin = [e for e in aktien if e.get("isin")]
    if ids:
        bei_ls = [e for e in mit_isin if any(str(k).upper() in ids for k in (e.get("isin"), e.get("ticker"), e.get("wkn"))
                                            if k)]
        if len(bei_ls) >= mindestens:
            return bei_ls, True
    return mit_isin, False


# ---------------------------------------------------------------------------
# Charts (Hitparade): Platzierung der Depotwerte wie in einer Musik-Chartliste
# ---------------------------------------------------------------------------
def plaetze(depot, art):
    """{id: Platz} der Positionen einer Art, nach Score (mix) absteigend - Platz 1 = bester Wert."""
    pos = [p for p in (depot or {}).get("positionen", {}).values() if p.get("art") == art]
    pos.sort(key=lambda p: (-(p.get("mix") if p.get("mix") is not None else -1), p.get("rang") or 999,
                            str(p.get("name") or "").lower()))
    return {p["id"]: i for i, p in enumerate(pos, 1)}


def charts_fortschreiben(alt, neu_depot):
    """Chart-Statistik je Wert {id: {"listen": Anzahl Listen in den Charts, "best": hoechster Platz}} um den
    neuen Stand erweitern (bei jeder Uebernahme)."""
    aus = {k: dict(v) for k, v in (alt or {}).items()}
    for art in ("aktie", "etf"):
        for i, platz in plaetze(neu_depot, art).items():
            e = aus.setdefault(i, {"listen": 0, "best": platz})
            e["listen"] = e.get("listen", 0) + 1
            e["best"] = min(e.get("best") or platz, platz)
    return aus


def hitparade(neu_depot, alt_depot, art, statistik=None):
    """Chartliste der Art: [{platz, vorher, bewegung (neu|wieder|hoch|runter|gleich), delta, listen, best, p}]
    und die aus den Charts gefallenen Werte [{vorher, p}]. statistik: charts_fortschreiben des alten Stands."""
    statistik = statistik or {}
    neu_pl, alt_pl = plaetze(neu_depot, art), plaetze(alt_depot, art)
    pos_neu = (neu_depot or {}).get("positionen") or {}
    zeilen = []
    for i, platz in sorted(neu_pl.items(), key=lambda x: x[1]):
        vorher = alt_pl.get(i)
        st_ = statistik.get(i) or {}
        if vorher is None:
            bewegung, delta = ("wieder" if st_.get("listen") else "neu"), None
        else:
            delta = vorher - platz
            bewegung = "hoch" if delta > 0 else "runter" if delta < 0 else "gleich"
        zeilen.append({"platz": platz, "vorher": vorher, "bewegung": bewegung, "delta": delta,
                       "listen": st_.get("listen", 0) + 1, "best": min(st_.get("best") or platz, platz),
                       "p": pos_neu[i]})
    raus = [{"vorher": pl, "p": ((alt_depot or {}).get("positionen") or {})[i]}
            for i, pl in sorted(alt_pl.items(), key=lambda x: x[1]) if i not in neu_pl]
    return zeilen, raus



# ---------------------------------------------------------------------------
# Begruendung je Wert ("Warum ist dieser Wert im Depot?")
# ---------------------------------------------------------------------------
AUSWAHL_TEXT = {
    "top": "Unter den besten {n} der Rangliste – direkt ausgewählt.",
    "gehalten": "Bereits im Depot und weiter unter den besten {n}.",
    "puffer": "Bereits im Depot und noch unter den Top {p} (Puffer) – bleibt, damit nicht wegen kleiner "
              "Score-Schwankungen getauscht wird.",
    "nachgerueckt": "Nachgerückt: Besser platzierte Werte wurden wegen der Streuung (Branchen- bzw. Regionsgrenze) "
                    "oder weil eine Aktie teurer als das Budget je Position ist, übersprungen.",
    "aufgefuellt": "Aufgefüllt: Die Streuungsregel ließ nicht genug Werte zu – nächstbester verfügbarer Wert.",
}


def _pct(x, vz=True):
    v = _zahl(x)
    if v is None:
        return None
    t = f"{v:+.1f}" if vz else f"{v:.1f}"
    return t.replace(".", ",") + " %"


def begruendung(p, investor_namen=None):
    """-> {"kurz": str, "abschnitte": [(titel, [zeilen])], "staerken": [..], "schwaechen": [..]} fuer eine Position
    (oder einen Ranglisten-Eintrag). investor_namen: {check_id: Name} (investor_checks.REGISTRY)."""
    namen = investor_namen or {}
    d = p.get("detail") or {}
    art = p.get("art")
    n_ = N_AKTIEN if art == "aktie" else N_ETF
    puffer = PUFFER_AKTIEN if art == "aktie" else PUFFER_ETF
    rang, von = p.get("rang"), p.get("von_gesamt")
    abschnitte, staerken, schwaechen, kurz = [], [], [], []
    if rang and von:
        top = rang / von * 100
        kurz.append(f"Platz {rang} von {von:,}".replace(",", "."))
        art_txt = "Aktien" if art == "aktie" else "ETFs"
        abschnitte.append(("Platzierung", [
            f"Platz {rang} von {f'{von:,}'.replace(',', '.')} bewerteten {art_txt} "
            f"(Top {f'{max(top, 0.1):.1f}'.replace('.', ',')} %).",
            ]))
    grund = p.get("auswahl")
    if grund in AUSWAHL_TEXT:
        abschnitte.append(("Warum ausgewählt", [AUSWAHL_TEXT[grund].format(n=n_, p=puffer)]))
    if art == "aktie":
        teile = p.get("teile") or {}
        zeilen = []
        summe_g = sum(g for k, _, g in BAUSTEINE if teile.get(k) is not None) or 1
        for k, t, g in BAUSTEINE:
            v = teile.get(k)
            if v is None:
                zeilen.append(f"{t}: keine Daten – Gewicht {g} % geht anteilig auf die übrigen Bausteine")
            else:
                zeilen.append(f"{t}: {v:.0f} × {g / summe_g * 100:.0f} % = {v * g / summe_g:.1f} Punkte")
        zeilen.append(f"= Gesamt {p.get('mix', 0):.0f} von 100")
        abschnitte.append(("So setzt sich der Score zusammen", [z.replace(".", ",") for z in zeilen]))
        q = d.get("q") or {}
        pt = q.get("pt") or []
        if pt:
            bereiche = []
            for (t, mx), v in zip(Q_BEREICHE, pt):
                v = _zahl(v) or 0
                bereiche.append(f"{t} {v:.0f}/{mx}")
                if v >= 0.75 * mx:
                    staerken.append(f"{t} {v:.0f}/{mx}")
                elif v <= 0.35 * mx:
                    schwaechen.append(f"{t} {v:.0f}/{mx}")
            abschnitte.append(("Qualitäts-Score je Bereich", [" · ".join(bereiche)]))
        kz = []
        for k, t in (("g_ums", "Umsatzwachstum p. a."), ("g_eps", "Gewinnwachstum p. a."),
                     ("g_fcf", "Free-Cashflow-Wachstum p. a."), ("roic", "Rendite aufs Kapital (ROIC)"),
                     ("om", "operative Marge"), ("fcfy", "Free-Cashflow-Rendite"), ("div", "Dividendenrendite")):
            v = _pct(q.get(k), vz=k.startswith("g_"))
            if v:
                kz.append(f"{t} {v}")
        if _zahl(q.get("fkgv")):
            kz.append(f"KGV (erwartet) {_zahl(q['fkgv']):.1f}".replace(".", ","))
        if _zahl(q.get("ev_ebit")):
            kz.append(f"EV/EBIT {_zahl(q['ev_ebit']):.1f}".replace(".", ","))
        txt = [x for x in (q.get("moat") and f"Burggraben {q['moat']}", q.get("mgmt") and f"Management {q['mgmt']}",
                           q.get("bew") and f"Bewertung {q['bew']}", q.get("risiko") and f"Risiko {q['risiko']}") if x]
        if kz or txt:
            abschnitte.append(("Kennzahlen", kz + ([" · ".join(txt)] if txt else [])))
        inv = d.get("inv") or {}
        if inv.get("von"):
            kaeufer = sorted(((namen.get(cid, cid), sc) for cid, sc in (inv.get("c") or {}).items()
                              if sc is not None and sc >= 70 and cid in namen), key=lambda x: -x[1])
            zeile = f"{inv.get('kaufen') or 0} von {inv['von']} Börsenlegenden würden kaufen"
            if inv.get("note"):
                zeile += f" – Gesamtnote {inv['note']}"
            abschnitte.append(("Börsenprofis (Investoren-Checks)",
                               [zeile] + ([", ".join(f"{n} ({sc:.0f})" for n, sc in kaeufer[:8])] if kaeufer else [])
                               + ([f"{inv['w']} Warnsignal(e) beachten"] if inv.get("w") else [])))
            if inv.get("kaufen"):
                kurz.append(f"{inv['kaufen']} Legenden kaufen")
                if inv["kaufen"] >= max(3, inv["von"] / 2):
                    staerken.append(f"{inv['kaufen']} von {inv['von']} Legenden kaufen")
        fv = _zahl(p.get("fv") if p.get("fv") is not None else (d.get("fv")))
        aussicht = []
        if fv is not None:
            aussicht.append(f"Fairer Wert {('über' if fv >= 0 else 'unter')} dem Kurs: {_pct(fv)} "
                            + ("Potenzial" if fv >= 0 else "(Kurs über fairem Wert)"))
            kurz.append(f"{_pct(fv)} zum fairen Wert")
            (staerken if fv >= 15 else schwaechen if fv <= -15 else []).append(f"fairer Wert {_pct(fv)}")
        if pt and len(pt) >= 8:
            aussicht.append(f"Chance-Punkte {(_zahl(pt[7]) or 0):.0f}/5 (Wachstumsaussicht im Qualitäts-Score)")
        if _zahl(q.get("mos")) is not None:
            aussicht.append(f"Sicherheitsmarge {_pct(q['mos'])}")
        if aussicht:
            abschnitte.append(("Zukunftsaussichten", aussicht))
        if staerken[:1]:
            kurz.insert(1, staerken[0])
    else:
        e = d.get("etf") or {}
        z = []
        if e.get("rendite") is not None:
            z.append(f"Rendite {_pct(e['rendite'])} p. a. über {e.get('rendite_jahre') or '–'} Jahre")
            kurz.append(f"{_pct(e['rendite'])} p. a.")
        if e.get("rr") is not None:
            z.append(f"Rendite je Risiko {_zahl(e['rr']):.2f}".replace(".", ","))
        if e.get("dd") is not None:
            z.append(f"größter Rückgang −{abs(_zahl(e['dd'])):.0f} %")
        if e.get("vola") is not None:
            z.append(f"Schwankung {_zahl(e['vola']):.0f} % p. a.")
        if e.get("jahre") is not None:
            z.append(f"Historie {_zahl(e['jahre']):.1f} Jahre".replace(".", ","))
        if e.get("einordnung"):
            z.append({"prio": "ETF-Score: hohe Analysepriorität", "beobachten": "ETF-Score: Beobachtungsliste",
                      "nicht": "ETF-Score: eher nicht"}.get(e["einordnung"], e["einordnung"]))
        abschnitte.append((f"ETF-Score {p.get('mix', 0):.0f}", z))
        mm = d.get("mm") or {}
        if mm:
            abschnitte.append(("Merkmale", [" · ".join(x for x in (mm.get("region"), "/".join(mm.get("themen") or []),
                                                                 mm.get("anbieter"), mm.get("ertrag")) if x)]))
    return {"kurz": " · ".join(kurz[:4]), "abschnitte": abschnitte, "staerken": staerken[:4],
            "schwaechen": schwaechen[:4]}
