"""Datenbasierte Investment-Analyse je Wert (Aktie, ETF, Wikifolio).

Ergaenzt den transparenten Score (bewertung.py) um eine Einschaetzung im Stil
eines Analysten - aber regelbasiert und nur aus Daten, die wirklich vorliegen:

- Fakten (Kurshistorie, Fundamentaldaten) sind als "Fakt" gekennzeichnet,
- Analystenschaetzungen (Yahoo earningsTrend) als "Externe Prognose",
- Szenarien und Ableitungen als "Modell/Annahme",
- das Urteil als "Einschätzung".
Was die Datenquelle nicht liefert (Branchenstudien, Zinsprognosen, TER ...),
wird ausdruecklich als nicht bewertet genannt statt erfunden. Vergangene
Renditen werden nicht fortgeschrieben: die Szenarien daempfen sie je nach
Datenbasis Richtung 8 % p.a. (wie der Portfolio-Planer, planer_daten.VORSCHLAG).

Reine Rechenlogik ohne Streamlit - getestet in test_analyse.py.
"""
import math
import statistics

import bewertung as BW

FAKT, PROGNOSE, MODELL, EINSCHAETZUNG = "Fakt", "Externe Prognose", "Modell/Annahme", "Einschätzung"

URTEILE = {
    "attraktiv": ("🟢", "Besonders attraktiv"),
    "eingeschraenkt": ("🟡", "Interessant mit Einschränkungen"),
    "unattraktiv": ("🔴", "Eher unattraktiv"),
}
ANKER = 0.08                 # langfristiger Renditeanker (wie planer_daten.VORSCHLAG)
BEAR_ABSCHLAG, BULL_ZUSCHLAG = 0.5, 0.2
STARTBETRAG = 10_000


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
def _z(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _de(x, dec=1, vz=False):
    if x is None:
        return "–"
    t = f"{x:+,.{dec}f}" if vz else f"{x:,.{dec}f}"
    return t.replace(",", "§").replace(".", ",").replace("§", ".").replace("-", "−")


def _p(x, dec=1, vz=True):
    return "–" if x is None else f"{_de(x, dec, vz)} %"


def _eur(x):
    return "–" if x is None else f"{_de(x, 0)} €"


def _klasse_mehrzahl(typ):
    return BW.KLASSE_EINZAHL.get(typ, "Werte")


def _q(z, feld, detail=None):
    if detail and detail.get(feld) is not None:
        return detail.get(feld)
    return (z.get("qd") or {}).get(feld)


# ---------------------------------------------------------------------------
# Kontext: Vergleichsgruppe und Benchmark
# ---------------------------------------------------------------------------
def kontext(basis):
    """Mediane je Anlageklasse und ein breiter Welt-ETF als Benchmark (falls in der Liste)."""
    med = {}
    for typ in BW.KLASSEN:
        zeilen = [z for z in basis if z.get("typ") == typ]
        for feld in ("r1", "r3", "r5", "r10", "vola", "maxdd", "div"):
            werte = [_z(z.get(feld)) for z in zeilen]
            werte = [w for w in werte if w is not None]
            med[(typ, feld)] = statistics.median(werte) if len(werte) >= 5 else None
        for feld in ("g_ums", "g_eps", "roic", "fkgv", "fcfy"):
            werte = [_z((z.get("qd") or {}).get(feld)) for z in zeilen]
            werte = [w for w in werte if w is not None]
            med[(typ, feld)] = statistics.median(werte) if len(werte) >= 5 else None
    bench = None
    kandidaten = [z for z in basis if z.get("typ") == "etf" and _z(z.get("r5")) is not None
                  and BW.streuung_geschaetzt(z.get("name"))[0] == 90]
    if kandidaten:
        def vorrang(z):
            n = (z.get("name") or "").lower()
            return (("all-world" in n or "all world" in n or "msci world" in n or "acwi" in n),
                    _z(z.get("jahre")) or 0)
        bench = max(kandidaten, key=vorrang)
    return {"median": med, "benchmark": bench}


# ---------------------------------------------------------------------------
# Szenarien
# ---------------------------------------------------------------------------
MAX_GEWICHT_HISTORIE = 0.5    # Vergangenheit zaehlt hoechstens zur Haelfte (Renditen sind wenig persistent)


def vertrauen(jahre, typ):
    """Gewicht der eigenen Historie 0-0,5: waechst mit der Laenge, bleibt aber bewusst
    unter dem Planer-Wert, weil hohe Vergangenheitsrenditen selten anhalten."""
    if not jahre or jahre <= 0:
        return 0.05
    faktor = {"aktie": 0.9, "wikifolio": 0.8, "etf": 1.0}.get(typ, 1.0)
    return max(0.0, min(MAX_GEWICHT_HISTORIE, MAX_GEWICHT_HISTORIE * (1 - math.exp(-jahre / 5.0)) * faktor))


def renditeszenarien(z):
    """Bear/Base/Bull p.a. aus der Historie, gedaempft Richtung 8 % - keine Prognose."""
    hist, quelle = None, None
    for feld, q in (("r5", "5 J. p.a."), ("r3", "3 J. p.a."), ("r10", "10 J. p.a.")):
        if _z(z.get(feld)) is not None:
            hist, quelle = _z(z[feld]) / 100, q
            break
    if hist is None:
        return None
    conf = vertrauen(_z(z.get("jahre")), z.get("typ"))
    if z.get("typ") == "etf" and BW.streuung_geschaetzt(z.get("name"))[0] <= 20:
        conf *= 0.5                                   # Hebel/Krypto/Rohstoff: Historie kaum uebertragbar
    base = conf * hist + (1 - conf) * ANKER
    vola = _z(z.get("vola"))
    v = vola / 100 if vola else None
    # Spanne: mindestens -50 % / +20 % der Basis, bei schwankenden Werten die typische
    # Unsicherheit einer 5-Jahres-Durchschnittsrendite (Vola / Wurzel 5), nach unten staerker
    unsicher = v / math.sqrt(5) if v else 0.0
    bear = base - max(BEAR_ABSCHLAG * abs(base), unsicher)
    bull = base + max(BULL_ZUSCHLAG * abs(base), 0.6 * unsicher)
    return {"base": base, "bear": bear, "bull": bull, "hist": hist, "quelle": quelle, "vertrauen": conf,
            "vola": v, "unsicher": unsicher}


def _endwert(r, jahre):
    if r is None or r <= -1:
        return None
    return STARTBETRAG * (1 + r) ** jahre


# ---------------------------------------------------------------------------
# Bausteine der Analyse
# ---------------------------------------------------------------------------
def _vergleichstext(wert, median, einheit="% p.a.", besser_hoch=True):
    if wert is None or median is None:
        return ""
    diff = wert - median
    if abs(diff) < 0.5:
        return f"etwa Median ({_de(median)} {einheit})"
    gut = (diff > 0) == besser_hoch
    return f"{'über' if diff > 0 else 'unter'} Median {_de(median)} {einheit}" + (" ✓" if gut else "")


def _vergangenheit(z, b, ctx, detail):
    typ = z.get("typ")
    med = ctx["median"]
    bench = ctx.get("benchmark")
    kz, texte = [], []
    for feld, label in (("r1", "1 Jahr"), ("r3", "3 J. p.a."), ("r5", "5 J. p.a."), ("r10", "10 J. p.a.")):
        w = _z(z.get(feld))
        bw = _z(bench.get(feld)) if bench and bench is not z else None
        kz.append((f"Kursrendite {label}", _p(w), _vergleichstext(w, med.get((typ, feld)))
                   + (f" · Benchmark {_p(bw)}" if bw is not None else "")))
    vola, dd, div, jahre = _z(z.get("vola")), _z(z.get("maxdd")), _z(z.get("div")), _z(z.get("jahre"))
    kz.append(("Schwankung (Vola 1 J.)", _p(vola, vz=False),
               _vergleichstext(vola, med.get((typ, "vola")), "%", besser_hoch=False)))
    kz.append(("Größter Rückgang seit Beginn", _p(dd, vz=False),
               _vergleichstext(dd, med.get((typ, "maxdd")), "%", besser_hoch=True)))
    if div is not None:
        kz.append(("Dividendenrendite (aktuell)", _p(div, 2, vz=False), _vergleichstext(div, med.get((typ, "div")), "%")))
    kz.append(("Historie", f"{_de(jahre)} Jahre" if jahre else "–", ""))

    # Gesamtrendite inkl. Ausschuettungen (Naeherung)
    r5 = _z(z.get("r5")) if _z(z.get("r5")) is not None else _z(z.get("r3"))
    if div and r5 is not None and typ == "aktie":
        texte.append((MODELL, f"Gesamtrendite inkl. Dividende grob {_p(r5 + div)} p.a. (Kursrendite + aktuelle "
                              "Dividendenrendite; Näherung, da frühere Ausschüttungen nicht einzeln vorliegen)."))
    elif typ == "etf":
        texte.append((FAKT, "Bei thesaurierenden ETFs sind Ausschüttungen im Kurs enthalten; bei ausschüttenden "
                            "kommt die Dividende zur Kursrendite hinzu (Ertragsart nicht in der Datenquelle)."))
    elif typ == "wikifolio":
        texte.append((FAKT, "Wikifolio-Kurse sind nach Gebühren und enthalten Dividenden der Positionen."))

    # Bestaendigkeit
    reihe = [(l, _z(z.get(f))) for f, l in (("r1", "1 J."), ("r3", "3 J."), ("r5", "5 J."), ("r10", "10 J."))]
    vorhanden = [(l, w) for l, w in reihe if w is not None]
    if len(vorhanden) >= 2:
        negativ = [l for l, w in vorhanden if w < 0]
        spanne = max(w for _, w in vorhanden) - min(w for _, w in vorhanden)
        if not negativ and spanne < 10:
            texte.append((FAKT, f"Sehr beständig: alle Zeiträume positiv, Spanne nur {_de(spanne)} %-Punkte."))
        elif not negativ:
            texte.append((FAKT, f"Alle Zeiträume positiv, aber ungleichmäßig (Spanne {_de(spanne)} %-Punkte)."))
        else:
            texte.append((FAKT, f"Negativ über {', '.join(negativ)} – die Entwicklung war nicht durchgehend stark."))
    # Schwierige Marktphasen
    if dd is not None:
        erholung = 1 / (1 + dd / 100) - 1 if dd > -99 else None
        texte.append((FAKT, f"Schwierige Phasen: größter Rückgang {_p(dd, vz=False)} seit Beginn der Historie"
                            + (f" – zum Aufholen waren danach {_p(erholung * 100, 0, vz=True)} nötig." if erholung else ".")
                            + " Einzelne Krisenjahre lassen sich aus den gespeicherten Kennzahlen nicht getrennt zeigen."))
    # Aktien: Fundamentalentwicklung
    if typ == "aktie":
        f = lambda k: _z(_q(z, k, detail))        # noqa: E731
        teile = []
        for k, l in (("g_ums", "Umsatz"), ("g_eps", "Gewinn je Aktie"), ("g_fcfps", "FCF je Aktie")):
            if f(k) is not None:
                teile.append(f"{l} {_p(f(k))} p.a.")
        if teile:
            n = _q(z, "n", detail)
            texte.append((FAKT, "Geschäftsentwicklung" + (f" ({n} Jahre)" if n else "") + ": " + ", ".join(teile).rstrip(".") + "."))
            for k, l in (("g_ums", "Umsatz"), ("g_eps", "Gewinn je Aktie"), ("g_fcfps", "FCF je Aktie")):
                if f(k) is not None:
                    kz.append((f"{l}-Wachstum p.a.", _p(f(k)), _vergleichstext(f(k), med.get(("aktie", k)), "%")))
        if f("roic") is not None:
            kz.append(("Kapitalrendite ROIC Ø", _p(f("roic"), vz=False), _vergleichstext(f("roic"), med.get(("aktie", "roic")), "%")))
        if f("om") is not None:
            trend = f("om_trend")
            kz.append(("Operative Marge Ø", _p(f("om"), vz=False),
                       f"Trend {_de(trend, 0, vz=True)} %-Punkte" if trend is not None else ""))
        if f("akt") is not None:
            kz.append(("Aktienanzahl p.a.", _p(f("akt")), "Rückkäufe" if f("akt") < -0.5 else
                       "Verwässerung" if f("akt") > 1 else "stabil"))
        # Bewertungsentwicklung
        kgv, h_kgv = f("fkgv") or f("kgv"), f("h_kgv")
        fcfy, h_fcfy = f("fcfy"), f("h_fcfy")
        if kgv is not None:
            kz.append(("KGV (erwartet bzw. aktuell)", _de(kgv), f"eigener Schnitt {_de(h_kgv)}" if h_kgv else
                       _vergleichstext(kgv, med.get(("aktie", "fkgv")), "", besser_hoch=False)))
        if fcfy is not None:
            kz.append(("Free-Cashflow-Rendite", _p(fcfy, 2, vz=False), f"eigener Schnitt {_p(h_fcfy, 2, vz=False)}"
                       if h_fcfy else ""))
        if h_kgv and kgv:
            texte.append((FAKT, f"Bewertungsentwicklung: KGV heute {_de(kgv)} gegenüber eigenem Schnitt {_de(h_kgv)} "
                                f"({'teurer' if kgv > h_kgv * 1.1 else 'günstiger' if kgv < h_kgv * 0.9 else 'ähnlich'} "
                                "als historisch)."))
    # Was davon fuer die Zukunft zaehlt
    if typ == "aktie":
        relevant = ("Für die Zukunft am aussagekräftigsten sind Kapitalrendite, Margenstabilität und "
                    "FCF-Wachstum je Aktie – Kursrenditen der Vergangenheit spiegeln oft schon eingepreistes Wachstum.")
    elif typ == "wikifolio":
        relevant = ("Am aussagekräftigsten sind Länge der Historie, Beständigkeit und der Rückgang in Schwächephasen "
                    "– sie zeigen, ob der Trader sein Risiko kontrolliert, nicht nur, ob er Glück hatte.")
    else:
        relevant = ("Am aussagekräftigsten sind die langen Zeiträume (5/10 J.) und das Verhältnis von Rendite zu "
                    "Rückgang; die 1-Jahres-Rendite sagt über die Zukunft wenig.")
    texte.append((EINSCHAETZUNG, relevant))
    return kz, texte


def _renditetreiber(z):
    typ, name = z.get("typ"), z.get("name")
    if typ == "wikifolio":
        return ("Renditetreiber: Auswahl und Timing des Traders. Die Strategie kann sich ändern; Gebühren "
                "(typisch Performance-Gebühr) mindern die Rendite laufend.")
    if typ == "aktie":
        return None
    punkte, art = BW.streuung_geschaetzt(name)
    texte = {
        "Weltweit breit gestreut": "Gewinnwachstum tausender Unternehmen weltweit, Dividenden und Bewertungsänderungen "
                                   "des Gesamtmarkts – Rendite nahe dem globalen Aktienmarkt.",
        "Breiter Regional-Index": "Gewinnwachstum und Bewertung einer Region; Währung und Ländergewicht bestimmen die "
                                  "Abweichung vom Weltmarkt.",
        "Sektor-ETF": "Gewinnzyklus und Bewertung einer Branche – stärker konjunktur- und zinsabhängig als der "
                      "Gesamtmarkt.",
        "Themen-/Branchen-ETF": "Erfolg eines Themas; nach starken Jahren oft hoch bewertet, daher anfällig für "
                                "Rückschläge, wenn Erwartungen nicht erfüllt werden.",
        "Einzelnes Land": "Wirtschaft, Währung und Politik eines Landes – Klumpenrisiko gegenüber breiten Indizes.",
        "Faktor- oder Small-Cap-Strategie": "Prämie eines Faktors (z. B. Value, Quality, Small Caps); sie kann über "
                                            "Jahre ausbleiben.",
        "Anleihen-Index": "Zinsniveau und Bonität: fallende Zinsen heben Kurse, steigende senken sie.",
        "Hebel-/Short-Produkt": "Tägliche Hebelung: in Seitwärtsphasen verliert das Produkt Wert "
                                "(Pfadabhängigkeit) – nur kurzfristig geeignet.",
        "Einzelne Kryptowährung": "Angebot/Nachfrage und Regulierung einer Kryptowährung, keine laufenden Erträge.",
        "Einzelner Rohstoff": "Preis eines Rohstoffs; keine laufenden Erträge, oft Absicherung gegen Inflation/Krisen.",
    }
    return "Renditetreiber: " + texte.get(art, "Zusammensetzung aus dem Namen nicht eindeutig erkennbar.")


def _zukunft(z, b, detail, sz):
    typ = z.get("typ")
    aus = []
    if typ == "aktie":
        f = lambda k: _z(_q(z, k, detail))        # noqa: E731
        if f("g1") is not None:
            aus.append((PROGNOSE, f"Analysten erwarten für das nächste Geschäftsjahr {_p(f('g1'))} Gewinnwachstum "
                                  "(Yahoo Finance, Konsens)."))
        if f("rev90") is not None:
            r = f("rev90")
            aus.append((PROGNOSE, f"Gewinnschätzungen für das laufende Jahr in 90 Tagen {_p(r)} – "
                                  + ("Analysten werden optimistischer." if r > 2 else
                                     "Analysten werden vorsichtiger." if r < -2 else "weitgehend stabil.")))
        if f("g_ref") is not None:
            aus.append((MODELL, f"Referenzwachstum (Median aus Umsatz-, Gewinn-, FCF-Wachstum und Konsens): "
                                f"{_p(f('g_ref'))} p.a."))
        if f("g_impl") is not None:
            erw = _q(z, "erw", detail)
            aus.append((MODELL, f"Der aktuelle Kurs preist {_p(f('g_impl'))} FCF-Wachstum p.a. ein (Reverse-DCF) – "
                                f"Erwartung „{erw}“." if erw else ""))
        for t in (_q(z, "kat", detail) or [])[:3]:
            aus.append((FAKT, f"Möglicher Treiber: {t}."))
        if f("om_trend") is not None and abs(f("om_trend")) >= 3:
            aus.append((FAKT, f"Margentrend {_de(f('om_trend'), 0, vz=True)} %-Punkte – "
                              + ("Rückenwind für Gewinne." if f("om_trend") > 0 else "Gegenwind für Gewinne.")))
        if not detail:
            aus.append((MODELL, "Detaildaten (Analystenkonsens, Reverse-DCF) erscheinen in der Detailanalyse."))
    else:
        t = _renditetreiber(z)
        if t:
            aus.append((EINSCHAETZUNG, t))
    if sz:
        aus.append((MODELL, f"Basisannahme {_p(sz['base'] * 100)} p.a.: historische {sz['quelle']} "
                            f"({_p(sz['hist'] * 100)}) zu {sz['vertrauen'] * 100:.0f} % gewichtet, der Rest mit dem "
                            "langfristigen Anker 8 % p.a. – Vergangenheit wird nicht einfach fortgeschrieben."))
    aus.append((EINSCHAETZUNG, "Zinsen, Konjunktur und Branchenstudien sind nicht Teil der Datenbasis und daher "
                               "nicht bewertet."))
    return [x for x in aus if x[1]]


def _bewertung(z, detail):
    """-> (stufe 'günstig'/'fair'/'teuer'/'heiß gelaufen'/'im Trend'/'unter Trend'/None, text, art)"""
    typ = z.get("typ")
    if typ == "aktie":
        bew = _q(z, "bew", detail)
        mos = _z(_q(z, "mos", detail))
        erw = _q(z, "erw", detail)
        fkgv, fcfy = _z(_q(z, "fkgv", detail)), _z(_q(z, "fcfy", detail))
        if bew:
            teile = [f"Bewertungspunkte: „{bew}“"]
            if mos is not None:
                teile.append(f"Kurs {'unter' if mos >= 0 else 'über'} dem fairen Wert des Basis-DCF "
                             f"({_de(abs(mos), 0)} %)")
            if fkgv:
                teile.append(f"erwartetes KGV {_de(fkgv)}")
            if fcfy is not None:
                teile.append(f"FCF-Rendite {_p(fcfy, 2, vz=False)}")
            if erw:
                teile.append(f"eingepreiste Erwartung „{erw}“")
            stufe = "günstig" if bew == "günstig" else "fair" if bew == "fair" else "teuer"
            return stufe, "; ".join(teile) + ".", MODELL
        return None, "Keine Fundamentaldaten für eine Bewertung.", FAKT
    r1, r5, vola = _z(z.get("r1")), _z(z.get("r5")) or _z(z.get("r3")), _z(z.get("vola")) or 15
    pre = ("Keine fundamentale Bewertung möglich (KGV des Index/Portfolios nicht in der Datenquelle). "
           if typ == "etf" else "Wikifolios haben keine eigene Bewertungskennzahl. ")
    if r1 is None or r5 is None:
        return None, pre + "Für eine Trend-Einordnung fehlen Renditen.", FAKT
    if r1 > r5 + max(15, vola):
        return "heiß gelaufen", pre + (f"Zuletzt {_p(r1)} in 1 J. gegenüber {_p(r5)} p.a. langfristig – deutlich "
                                       "über dem eigenen Trend, erhöhtes Rückschlagrisiko."), EINSCHAETZUNG
    if r1 < r5 - vola:
        return "unter Trend", pre + (f"Zuletzt {_p(r1)} in 1 J. gegenüber {_p(r5)} p.a. langfristig – schwächer als "
                                     "gewohnt; Chance oder Zeichen einer Strategie-/Marktänderung."), EINSCHAETZUNG
    return "im Trend", pre + f"1 J. {_p(r1)} liegt im Rahmen des langfristigen Schnitts ({_p(r5)} p.a.).", EINSCHAETZUNG


def _szenarien(z, sz, detail):
    zeilen = []
    if sz:
        for key, name, annahme in (
                ("bull", "Optimistisch", "Stärken halten an; Aufschlag nach Schwankung (mind. +20 % der Basis)"),
                ("base", "Basis", f"Historie ({sz['quelle']}) zu {sz['vertrauen'] * 100:.0f} % gewichtet, "
                                  "Rest 8 % p.a."),
                ("bear", "Pessimistisch", "Schwächephase; Abschlag nach Schwankung (mind. −50 % der Basis)")):
            r = sz[key]
            zeilen.append({"name": name, "pa": r * 100, "werte": {n: _endwert(r, n) for n in (1, 3, 5)},
                           "annahme": annahme})
    stress = None
    dd = _z(z.get("maxdd"))
    if dd is not None:
        stress = (f"Stresstest: Ein erneuter Rückgang wie der bisher größte ({_p(dd, vz=False)}) würde "
                  f"{_eur(STARTBETRAG)} auf {_eur(STARTBETRAG * (1 + dd / 100))} drücken.")
    band = None
    if sz and sz.get("vola"):
        lo, hi = sz["base"] - sz["vola"], sz["base"] + sz["vola"]
        band = (f"Einzelne Jahre: Bei {_p(sz['vola'] * 100, vz=False)} Schwankung liegt ein Jahresergebnis "
                f"statistisch in etwa 2 von 3 Fällen zwischen {_p(lo * 100)} und {_p(hi * 100)} – Ausreißer "
                "darüber und darunter sind möglich.")
    dcf = []
    for key, name in (("bull", "Optimistisch"), ("base", "Basis"), ("bear", "Pessimistisch")):
        s = ((detail or {}).get("szen") or {}).get(key)
        if s and s.get("pot") is not None:
            dcf.append({"name": name, "pot": s["pot"], "g": s.get("g"), "r": s.get("r"), "m": s.get("m")})
    return {"zeilen": zeilen, "stress": stress, "band": band, "dcf": dcf}


# ---------------------------------------------------------------------------
# Gesamtanalyse
# ---------------------------------------------------------------------------
def analysiere(z, b, ctx, detail=None, platz=None, stand=None, q_stand=None):
    """Vollstaendige Analyse eines Werts. z = Katalogzeile (r1/r3/r5/r10 in % p.a., vola, maxdd,
    div, jahre, qd), b = Ergebnis von bewertung.Modell.bewerte, detail = Detaildatei des
    Qualitaets-Agenten (nur Aktien, optional)."""
    typ = z.get("typ")
    klasse = _klasse_mehrzahl(typ)
    sz = renditeszenarien(z)
    kz, hist_texte = _vergangenheit(z, b, ctx, detail)
    zukunft = _zukunft(z, b, detail, sz)
    stufe, bew_text, bew_art = _bewertung(z, detail)
    szen = _szenarien(z, sz, detail)
    med = ctx["median"]
    bench = ctx.get("benchmark")

    # --- Argumente und Risiken (konkret, mit Zahlen) ---
    argumente = list(b.get("plus") or [])
    if typ == "aktie":
        argumente += [s for s in (_q(z, "staerken", detail) or []) if s not in argumente]
    risiken = list(b.get("minus") or [])
    risiken += [h for h in b.get("hinweise") or []]
    if typ == "aktie":
        risiken += [r for r in (_q(z, "risiken", detail) or [])]
        if not detail and _q(z, "risiko", detail) in ("hoch", "mittel"):
            risiken.append(f"Risikoeinstufung des Qualitäts-Agenten: {_q(z, 'risiko', detail)}")
    if stufe in ("teuer", "heiß gelaufen"):
        risiken.append(f"Bewertung: {stufe}")
    if typ == "wikifolio":
        risiken.append("Abhängigkeit von einer Person (Trader) und Gebühren, die nicht in der Datenquelle stehen")
    vola = _z(z.get("vola"))
    if vola is not None and med.get((typ, "vola")) and vola > med[(typ, "vola")] * 1.4:
        risiken.append(f"Schwankung {_p(vola, vz=False)} deutlich über dem Median der {klasse}")
    if not argumente:
        argumente = ["Keine Kennzahl hebt sich deutlich vom Durchschnitt der Vergleichsgruppe ab"]
    if not risiken:
        risiken = ["Keine auffälligen Schwächen in den vorhandenen Kennzahlen – Risiken außerhalb der "
                   "Datenbasis (Branche, Zinsen) bleiben"]

    # --- These: 3-5 Saetze ---
    these = []
    stark = BW.top_gruppen(b, 2, True)
    r5 = _z(z.get("r5"))
    if stark:
        these.append(f"Der Score von {b['score']}/100 stützt sich vor allem auf "
                     + " und ".join(g["label"] for g in stark) + ".")
    if r5 is not None and med.get((typ, "r5")) is not None:
        abst = r5 - med[(typ, "r5")]
        these.append(f"Über 5 Jahre {_p(r5)} p.a. – {_de(abs(abst))} %-Punkte {'mehr' if abst >= 0 else 'weniger'} "
                     f"als der Median der {klasse}"
                     + (f" und {_p(_z(bench['r5']))} beim Welt-ETF {bench['name']}" if bench and bench is not z
                        and _z(bench.get("r5")) is not None else "") + ".")
    dd, md = _z(z.get("maxdd")), med.get((typ, "maxdd"))
    if dd is not None and md is not None:
        these.append(f"Der größte Rückgang ({_p(dd, vz=False)}) war {'kleiner' if dd > md else 'größer'} als "
                     f"üblich ({_p(md, vz=False)}) – {'ein Zeichen kontrollierten Risikos' if dd > md else 'die Rendite wurde mit hohem Risiko erkauft'}.")
    if typ == "aktie" and _z(_q(z, "roic", detail)) is not None:
        moat = {"stark": "ein starker", "mittel": "ein mittlerer", "schwach": "ein schwacher",
                "gering": "ein geringer"}.get(_q(z, "moat", detail))
        these.append(f"Kapitalrendite Ø {_p(_z(_q(z, 'roic', detail)), vz=False)}"
                     + (f" und {moat} Burggraben" if moat else "") + " beschreiben die Qualität des Geschäfts.")
    if typ == "aktie":
        mos = _z(_q(z, "mos", detail))
        these.append(f"Bewertung {stufe or 'nicht einzuordnen'}"
                     + (f": Kurs {_de(abs(mos), 0)} % {'unter' if mos >= 0 else 'über'} dem fairen Wert des "
                        "Basis-DCF." if mos is not None else "."))
    else:
        these.append(bew_text.split(". ", 1)[-1] if ". " in bew_text else bew_text)
    these = these[:5]

    # --- Gegenargument ---
    if sz and sz["hist"] * 100 > sz["base"] * 100 + 3:
        gegen = (f"Gegenargument: Die starke Vergangenheit ({_p(sz['hist'] * 100)} p.a.) kann Glück oder ein "
                 f"auslaufender Trend sein (Winner Bias); vorsichtig angesetzt bleiben {_p(sz['base'] * 100)} p.a.")
    elif stufe in ("teuer", "heiß gelaufen"):
        gegen = "Gegenargument: Die Qualität ist bekannt und eingepreist – Enttäuschungen treffen teure Werte hart."
    else:
        gegen = ("Gegenargument: Eine gute Platzierung beruht auf Vergangenheitsdaten; Änderungen bei Strategie, "
                 "Management oder Markt zeigen sich erst mit Verzögerung.")

    # --- Urteil ---
    score = b["score"]
    gruende = []
    hebel = typ == "etf" and BW.streuung_geschaetzt(z.get("name"))[0] <= 20
    teuer = stufe in ("teuer",) or (_q(z, "erw", detail) == "extrem optimistisch")
    if score >= 70 and b["datenqualitaet"] != "gering" and not hebel and not teuer:
        urteil = "attraktiv"
        gruende.append(f"Score {score} im oberen Bereich der {klasse}")
    elif score < 50 or b["datenqualitaet"] == "gering" or (hebel and score < 70):
        urteil = "unattraktiv"
        gruende.append(f"Score {score}" + (" bei geringer Datenlage" if b["datenqualitaet"] == "gering" else ""))
    else:
        urteil = "eingeschraenkt"
        gruende.append(f"Score {score}")
    if teuer:
        gruende.append("hohe Bewertung begrenzt das Potenzial")
    if hebel:
        gruende.append("Hebel-/Spezialprodukt")
    if stufe == "heiß gelaufen":
        gruende.append("zuletzt weit über dem eigenen Trend")
    if (_z(z.get("jahre")) or 0) < 3:
        gruende.append("kurze Historie")
        if urteil == "attraktiv":
            urteil = "eingeschraenkt"
    emoji, urteil_txt = URTEILE[urteil]

    # --- Potenzial 3-5 Jahre: Rendite gegen Risiko ---
    if sz:
        w5 = _endwert(sz["base"], 5)
        potenzial = (f"Basis {_p(sz['base'] * 100)} p.a. → aus {_eur(STARTBETRAG)} würden in 5 Jahren etwa "
                     f"{_eur(w5)} (Spanne {_eur(_endwert(sz['bear'], 5))} bis {_eur(_endwert(sz['bull'], 5))}). ")
        if vola:
            q = sz["base"] * 100 / vola
            potenzial += (f"Je Prozentpunkt Schwankung {_de(q, 2)} %-Punkte erwartete Rendite – "
                          + ("gutes" if q >= 0.5 else "mäßiges" if q >= 0.3 else "schwaches")
                          + " Verhältnis von Chance zu Risiko.")
    else:
        potenzial = "Für eine Hochrechnung fehlt eine ausreichende Historie."

    # --- Kompakte Box ---
    vg = [f"{l} {_p(_z(z.get(f)))}" for f, l in (("r1", "1J"), ("r3", "3J p.a."), ("r5", "5J p.a."),
                                                  ("r10", "10J p.a.")) if _z(z.get(f)) is not None]
    if dd is not None:
        vg.append(f"max. Rückgang {_p(dd, vz=False)}")
    zk = next((t for a, t in zukunft if a in (PROGNOSE,)), None) or next(
        (t for a, t in zukunft if a == EINSCHAETZUNG and t.startswith("Renditetreiber")), None)
    box = {
        "warum": " ".join(these[:2]) if these else "–",
        "vergangenheit": " · ".join(vg) or "–",
        "zukunft": (f"Basis {_p(sz['base'] * 100)} p.a. (Spanne {_p(sz['bear'] * 100)} bis {_p(sz['bull'] * 100)})"
                    if sz else "–") + (f" · {zk}" if zk else ""),
        "bewertung": f"{stufe or '–'}" + (f" · Rendite je Schwankung {_de(sz['base'] * 100 / vola, 2)}"
                                           if sz and vola else ""),
        "risiken": "; ".join(risiken[:2]),
        "gesamt": f"{emoji} {urteil_txt} – " + ", ".join(gruende) + ".",
    }

    quellen = [f"Kurse und Renditen: ls-tc.de / Yahoo Finance, Stand {stand or '–'} (Watchlist-Agent)."]
    if typ == "aktie":
        quellen.append(f"Fundamentaldaten und Analystenkonsens: Yahoo Finance über den Qualitäts-Agenten, Stand "
                       f"{q_stand or '–'}.")
        quellen.append("Fairer Wert: Discounted-Cashflow-Modell des Qualitäts-Agenten (Annahmen siehe Szenarien).")
    quellen.append("Vergleichsgruppe: Median aller " + klasse + " der Watchlist"
                   + (f"; Benchmark {bench['name']}" if bench else "") + ".")
    quellen.append("Szenarien: eigene Modellrechnung (Historie gedämpft Richtung 8 % p.a.) – keine Prognose, "
                   "keine Anlageberatung.")
    nicht = BW.NICHT_IN_QUELLE.get(typ, [])

    return {
        "urteil": urteil, "urteil_text": urteil_txt, "emoji": emoji, "urteil_gruende": gruende,
        "box": box, "these": these, "argumente": argumente[:3], "risiken": risiken[:3], "gegenargument": gegen,
        "kennzahlen": kz, "vergangenheit": hist_texte, "zukunft": zukunft,
        "bewertung": {"stufe": stufe, "text": bew_text, "art": bew_art},
        "potenzial": potenzial, "szenarien": szen, "renditeszenario": sz, "quellen": quellen,
        "nicht_in_quelle": nicht, "platz": platz,
    }
