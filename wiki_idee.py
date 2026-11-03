"""Wiki-Idee: Modelldepot aus den besten 50 Aktien und 20 ETFs des Bewertungssystems - reine Rechenlogik.

Ablauf (nach Bedarf: Knopf "Liste jetzt erstellen" in der Ansicht Wiki-Idee, wiki_idee_ui.py):
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


def eur_kurs(e, eur_kurse=None):
    """Kurs in EUR: aus eur_kurse (WKN/ISIN -> EUR, Katalog bzw. ls-tc), sonst e["kurs"] nur, wenn er in EUR
    ist (der Gesamt-Score fuehrt Aktien teils in Landeswaehrung) - sonst None."""
    for k in (e.get("wkn"), e.get("isin"), e.get("ticker")):
        if k and eur_kurse and _zahl(eur_kurse.get(str(k).upper())):
            return _zahl(eur_kurse[str(k).upper()])
    return _zahl(e.get("kurs")) if str(e.get("waehrung") or "EUR").upper() == "EUR" else None


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
    """eintraege: [(e, b)] mit e aus scoring.universum (art "aktie") und b = scoring.bewerten(e, ver).
    investoren: {ticker: Kurzform aus state/investoren/ergebnis_NN.json}. eur_kurse: siehe eur_kurs.
    -> (liste absteigend nach "mix", ausgeschlossen: [{name, grund}])"""
    investoren = investoren or {}
    kand, aus = {}, []
    for e, b in eintraege:
        if e.get("art") != "aktie" or not eur_kurs(e, eur_kurse) or (b or {}).get("gesamt") is None:
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
                      "kurs": eur_kurs(e, eur_kurse), "mix": round(mix, 1),
                      "teile": {k: (None if v is None else round(v, 1)) for k, v in teile.items()},
                      "note": inv.get("note"), "kaufen": inv.get("kaufen"), "von": inv.get("inv"),
                      "fv": _zahl(inv.get("fv")), "fazit": b.get("fazit")})
    liste.sort(key=lambda w: (-w["mix"], w["name"].lower()))
    for r, w in enumerate(liste, 1):
        w["rang"] = r
    return liste, aus


def etf_rangliste(eintraege, hebel_muster=None, merkmale=None, eur_kurse=None):
    """eintraege: [(e, b)] mit art "etf". hebel_muster: Regex fuer Hebel/Short (klassen_score.HEBEL);
    merkmale: Funktion name -> {"region", "themen"} (etf_merkmale.merkmale) fuer die Streuung."""
    liste = []
    for e, b in eintraege:
        if e.get("art") != "etf" or not eur_kurs(e, eur_kurse) or (b or {}).get("gesamt") is None:
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
                      "isin": e.get("isin") or "", "gruppe": gruppe, "kurs": eur_kurs(e, eur_kurse),
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


def ranglisten(bewertet, investoren=None, hebel_muster=None, merkmale=None, eur_kurse=None):
    """bewertet: [(e, scoring.bewerten(e, ver))] aller Aktien und ETFs. -> (aktien, ausgeschlossen, etfs)"""
    rang_a, aus = aktien_rangliste([x for x in bewertet if x[0].get("art") == "aktie"], investoren, eur_kurse)
    rang_e = etf_rangliste([x for x in bewertet if x[0].get("art") == "etf"], hebel_muster, merkmale, eur_kurse)
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
