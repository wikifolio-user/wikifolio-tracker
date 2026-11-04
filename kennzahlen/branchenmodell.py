"""Etappe 4a: Branchenmodelle fuer Banken, Versicherer und REITs (nur ANGEZEIGT - kein Einfluss auf bestehende
Scores, Ranglisten oder die KI_Invest-Auswahl).

Warum: Das Standardmodell (FCF, ROIC, EBITDA, Bruttomarge) passt fuer diese Branchen nicht. Banken und Versicherer
fehlen deshalb heute im Qualitaets-Score, REITs werden durch hohe Abschreibungen systematisch schlecht bewertet.

Typen (typ_fein):
  bank               Banken, Hypothekenfinanzierer, Finanzkonglomerate
  versicherer        Versicherer (ohne Makler); Schaden-Kosten-Quote nur bei Schaden/Unfall, Spezial, Rueck
  reit               Eigentuemer-REITs (Immobilien im Bestand) - FFO statt Gewinn
  hypotheken_reit    Hypotheken-REITs - rechnen wie Banken (Eigenkapitalrendite, Buchwert, Dividendendeckung)
  finanzdienstleister Vermoegensverwalter, Broker, Boersen, Kreditkarten, Versicherungsmakler: Standardmodell
  None               alle anderen: Standardmodell

Grundsaetze (wie Etappe 3):
- Je Kennzahl 0-100 Punkte linear zwischen "schwach" und "stark" (SCHWELLEN, an einer Stelle aenderbar).
- Fehlende Daten werden nie erfunden: die Kennzahl entfaellt. Branchen-Score erst ab MIN_KENNZAHLEN Kennzahlen.
- Negative Ergebnisse (z. B. negative FFO-Rendite) sind echte Werte und bekommen 0 Punkte.
- Abdeckungsregel: Eine Kennzahl zaehlt fuer einen Typ nur, wenn sie bei mindestens MIN_ABDECKUNG der Werte
  dieses Typs vorliegt (ab MIN_N Werten; ermittelt im Investoren-Agenten). Sonst: "Datenluecke".
- Aufsichtszahlen (CET1, Solvency II, NAV ...) liefert Yahoo nicht: "nicht verfuegbar", nie geschaetzt.
- Herkunft je Kennzahl: berechnet / Naeherung / Modellannahme (HERKUNFT).
"""
import investor_config as C

TYPEN = ("bank", "versicherer", "reit", "hypotheken_reit")
TYP_TITEL = {"bank": "Bank", "versicherer": "Versicherer", "reit": "REIT (Immobilienbestand)",
             "hypotheken_reit": "Hypotheken-REIT", "finanzdienstleister": "Finanzdienstleister"}

# Erkennung ueber die Yahoo-Branche (Kleinschreibung; "Banks—Regional" und "Banks - Regional" beide erkannt)
FINANZDIENSTLEISTER = ("asset management", "capital markets", "credit services", "financial data",
                       "stock exchanges", "insurance brokers", "insurance - brokers", "insurance—brokers")
SCHADEN_UNFALL = ("property & casualty", "specialty", "reinsurance")
_WACHSTUM_EWIG = 0.025          # Modellannahme fuer den fairen Kurs-Buchwert (wie DCF im Qualitaets-Agenten)
MARKTRISIKOPRAEMIE = 5.0        # % (wie kennzahlen.fundamental)

# Kennzahl: (schwach, stark) - linear dazwischen; schwach > stark heisst "niedriger ist besser"
SCHWELLEN = {
    "roe": (0.05, 0.15),             # Nettogewinn / Ø Eigenkapital
    "rote": (0.06, 0.18),            # Nettogewinn / materielles Eigenkapital
    "roa": (0.005, 0.015),           # Nettogewinn / Ø Bilanzsumme
    "cir": (0.70, 0.45),             # Kosten-Ertrags-Quote: zinsunabhaengiger Aufwand / Ertraege (Total Revenue)
    "risikokosten": (0.015, 0.002),  # Risikovorsorge / Kredite
    "ek_quote": (0.04, 0.10),        # Eigenkapital / Bilanzsumme (Bank)
    "kredit_einlagen": (1.10, 0.80),  # Kredite / Einlagen
    "tbvps_cagr": (0.0, 0.10),       # materieller Buchwert je Aktie p. a.
    "bvps_cagr": (0.0, 0.10),        # Buchwert je Aktie p. a.
    "kbv_fair": (1.5, 0.7),          # Kurs-Buchwert / fairer Kurs-Buchwert aus EK-Rendite (Modellannahme)
    "combined": (1.05, 0.90),        # Schaden-Kosten-Quote (Naeherung)
    "ek_quote_vers": (0.05, 0.15),   # Eigenkapital / Bilanzsumme (Versicherer)
    "ausschuettung_gewinn": (0.8, 2.0),  # Nettogewinn / (Dividenden + Rueckkaeufe)
    "ffo_rendite": (0.04, 0.10),     # FFO / Boersenwert
    "ffops_cagr": (0.0, 0.06),       # FFO je Aktie p. a.
    "ffo_deckung": (1.0, 1.43),      # FFO / Dividenden (1,43 = Ausschuettung 70 % des FFO)
    "nde_reit": (9.0, 5.0),          # Nettoschulden / EBITDA
    "zinsdeckung": (2.0, 5.0),       # EBITDA / Zinsaufwand
    "schuldenquote": (0.60, 0.35),   # Schulden / Bilanzsumme
    "ek_quote_mreit": (0.08, 0.25),  # Eigenkapital / Bilanzsumme (Hypotheken-REIT)
    "div_deckung_gewinn": (0.8, 1.2),  # Nettogewinn / Dividenden
}
TITEL = {
    "roe": "Eigenkapitalrendite", "rote": "Materielle Eigenkapitalrendite", "roa": "Gesamtkapitalrendite",
    "cir": "Kosten-Ertrags-Quote", "risikokosten": "Risikovorsorge / Kredite", "ek_quote": "Eigenkapital / Bilanzsumme",
    "kredit_einlagen": "Kredite / Einlagen", "tbvps_cagr": "Materieller Buchwert je Aktie p. a.",
    "bvps_cagr": "Buchwert je Aktie p. a.", "kbv_fair": "Kurs-Buchwert im Verhältnis zur EK-Rendite",
    "combined": "Schaden-Kosten-Quote", "ek_quote_vers": "Eigenkapital / Bilanzsumme",
    "ausschuettung_gewinn": "Ausschüttungsdeckung durch Gewinn", "ffo_rendite": "FFO-Rendite",
    "ffops_cagr": "FFO je Aktie p. a.", "ffo_deckung": "Dividendendeckung durch FFO",
    "nde_reit": "Nettoschulden / EBITDA", "zinsdeckung": "Zinsdeckung (EBITDA / Zinsen)",
    "schuldenquote": "Schulden / Bilanzsumme", "ek_quote_mreit": "Eigenkapital / Bilanzsumme",
    "div_deckung_gewinn": "Dividendendeckung durch Gewinn",
}
FAKTOR = {"cir", "kredit_einlagen", "kbv_fair", "combined", "ausschuettung_gewinn", "ffo_deckung", "nde_reit",
          "zinsdeckung", "div_deckung_gewinn"}          # als Faktor bzw. Quote anzeigen, Rest als Prozent
PROZENT_QUOTE = {"cir", "kredit_einlagen", "combined"}  # Quoten, die als Prozent lesbarer sind
HERKUNFT = {"kbv_fair": "Modellannahme", "combined": "Näherung", "ffo_rendite": "Näherung", "ffops_cagr": "Näherung",
            "ffo_deckung": "Näherung"}                  # sonst "berechnet"

MODULE = {
    "bank": {"ren": ("Rentabilität", ("roe", "rote", "roa")),
             "eff": ("Effizienz & Kreditqualität", ("cir", "risikokosten")),
             "kap": ("Kapital & Refinanzierung", ("ek_quote", "kredit_einlagen")),
             "wert": ("Wertentwicklung & Bewertung", ("tbvps_cagr", "kbv_fair"))},
    "versicherer": {"ren": ("Rentabilität", ("roe", "combined")),
                    "kap": ("Kapital & Ausschüttung", ("ek_quote_vers", "ausschuettung_gewinn")),
                    "wert": ("Wertentwicklung & Bewertung", ("bvps_cagr", "kbv_fair"))},
    "reit": {"ffo": ("Ertrag & Bewertung (FFO)", ("ffo_rendite", "ffops_cagr")),
             "aus": ("Ausschüttung", ("ffo_deckung",)),
             "bil": ("Bilanz", ("nde_reit", "zinsdeckung", "schuldenquote"))},
    "hypotheken_reit": {"ren": ("Rentabilität", ("roe",)),
                        "kap": ("Kapital", ("ek_quote_mreit",)),
                        "aus": ("Ausschüttung", ("div_deckung_gewinn",)),
                        "wert": ("Wertentwicklung & Bewertung", ("bvps_cagr", "kbv_fair"))},
}
NICHT_VERFUEGBAR = {
    "bank": ("Harte Kernkapitalquote (CET1)", "Liquiditätsdeckungsquote (LCR)", "Quote notleidender Kredite (NPL)"),
    "versicherer": ("Solvency-II-Quote", "Abwicklung der Schadenreserven"),
    "reit": ("Nettoinventarwert (NAV) je Aktie", "AFFO (bereinigt um Erhaltungsinvestitionen)", "Belegungsquote"),
    "hypotheken_reit": ("Nettoinventarwert (NAV) je Aktie", "Zinsänderungsrisiko des Portfolios"),
}
MIN_KENNZAHLEN = 3      # Branchen-Score erst ab so vielen bewerteten Kennzahlen
MIN_ABDECKUNG = 0.60    # Anteil der Werte eines Typs, bei denen eine Kennzahl vorliegen muss
MIN_N = 20              # Abdeckungsregel erst ab so vielen Werten des Typs (kleinere Stichproben: keine Regel)


def _z(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _t(a, b):
    a, b = _z(a), _z(b)
    return a / b if a is not None and b not in (None, 0) else None


def _mittel(a, b):
    a, b = _z(a), _z(b)
    if a is None:
        return b
    return (a + b) / 2 if b is not None else a


def _cagr(erst, letzt, jahre):
    erst, letzt = _z(erst), _z(letzt)
    if not erst or not letzt or erst <= 0 or letzt <= 0 or jahre <= 0:
        return None
    return (letzt / erst) ** (1 / jahre) - 1


def _text(f):
    return f"{f.get('sektor') or ''} {f.get('branche') or ''}".lower().replace(" - ", "—")


def typ_fein(f):
    """Feiner Branchentyp aus Yahoo-Sektor und -Branche (siehe Moduldoku) oder None (Standardmodell)."""
    t = _text(f)
    if "reit" in t:
        return "hypotheken_reit" if "mortgage" in t else "reit"
    if any(s in t for s in FINANZDIENSTLEISTER):
        return "finanzdienstleister"
    if "insurance" in t:
        return "versicherer"
    if any(s in t for s in C.SEKTOR_BANK):
        return "bank"
    return None


def punkte(schluessel, wert):
    if wert is None:
        return None
    schwach, stark = SCHWELLEN[schluessel]
    return max(0.0, min(100.0, (wert - schwach) / (stark - schwach) * 100))


def _je_aktie(j, feld):
    return _t(j.get(feld), j.get("aktien"))


def _ffo(j):
    """FFO-Naeherung: Nettogewinn + Abschreibungen - Veraeusserungsgewinne. -> (wert, bereinigt?)"""
    ng, ab = _z(j.get("nettogewinn")), _z(j.get("abschreibungen"))
    if ng is None or ab is None:
        return None, False
    vg = _z(j.get("verkaufsgewinne"))
    return ng + ab - (vg or 0.0), vg is not None


def _mat_ek(j):
    tb = _z(j.get("mat_buchwert"))
    if tb is not None:
        return tb
    ek = _z(j.get("ek"))
    imm = _z(j.get("immat"))
    if imm is None:
        imm = _z(j.get("goodwill"))
    return ek - imm if ek is not None and imm is not None else None


def _boersenwert(f, j):
    """Boersenwert in Berichtswaehrung (Kurs in Berichtswaehrung x Aktienanzahl) - sonst None."""
    k = _z(f.get("kurs_in_bericht"))
    a = _z(j.get("aktien")) or _z(f.get("aktien"))
    return k * a if k and a else None


def _kbv_fair(f, j, roe, warn):
    """Kurs-Buchwert im Verhaeltnis zum fairen Kurs-Buchwert (ROE - g) / (Ke - g) - Modellannahme (CAPM)."""
    mw, ek = _boersenwert(f, j), _z(j.get("ek"))
    if roe is None or not mw or not ek or ek <= 0:
        return None
    beta = _z(f.get("beta"))
    beta = min(max(beta, 0.5), 2.0) if beta is not None else 1.0
    ke = C.STAATSANLEIHE_10J / 100 + beta * MARKTRISIKOPRAEMIE / 100
    if roe <= _WACHSTUM_EWIG or ke <= _WACHSTUM_EWIG:
        warn.append("Eigenkapitalrendite unter der Wachstumsannahme – kein fairer Kurs-Buchwert berechenbar")
        return None
    return (mw / ek) / ((roe - _WACHSTUM_EWIG) / (ke - _WACHSTUM_EWIG))


def kennzahlen(f, typ=None):
    """f: fakten (investor_checks.daten) -> (typ, {kennzahl: wert}, warnungen, nicht_anwendbar)."""
    typ = typ or typ_fein(f)
    if typ not in TYPEN:
        return typ, {}, [], []
    J = [j for j in (f.get("jahre") or []) if j]
    if not J:
        return typ, {}, ["keine Abschlussdaten"], []
    a, z = J[0], J[-1]
    v = J[-2] if len(J) > 1 else {}
    n_j = len(J) - 1
    k, warn, na = {}, [], []
    ng = _z(z.get("nettogewinn"))
    roe = _t(ng, _mittel(z.get("ek"), v.get("ek")))
    if typ in ("bank", "versicherer", "hypotheken_reit"):
        k["roe"] = roe
        k["kbv_fair"] = _kbv_fair(f, z, roe, warn)
        if typ != "bank":
            k["bvps_cagr"] = _cagr(_je_aktie(a, "ek"), _je_aktie(z, "ek"), n_j)
    if typ == "bank":
        mek = _mat_ek(z)
        k["rote"] = _t(ng, mek) if mek and mek > 0 else None
        k["roa"] = _t(ng, _mittel(z.get("bilanzsumme"), v.get("bilanzsumme")))
        k["cir"] = _t(z.get("zinsunabh_aufwand"), z.get("umsatz"))
        rv = _z(z.get("risikovorsorge"))
        k["risikokosten"] = _t(abs(rv), z.get("kredite")) if rv is not None else None
        k["ek_quote"] = _t(z.get("ek"), z.get("bilanzsumme"))
        k["kredit_einlagen"] = _t(z.get("kredite"), z.get("einlagen"))
        tb_a, tb_z = _mat_ek(a), _mat_ek(z)
        k["tbvps_cagr"] = _cagr(_t(tb_a, a.get("aktien")), _t(tb_z, z.get("aktien")), n_j)
        if k["risikokosten"] is not None and k["risikokosten"] > 0.02:
            warn.append("hohe Risikovorsorge im Verhältnis zu den Krediten")
        if k["ek_quote"] is not None and k["ek_quote"] < 0.04:
            warn.append("dünne Eigenkapitaldecke (unter 4 % der Bilanzsumme)")
    if typ == "versicherer":
        if any(s in _text(f) for s in SCHADEN_UNFALL):
            sch, pr = _z(z.get("schaeden")), _z(z.get("praemien"))
            sch = abs(sch) if sch is not None else None
            kosten = _z(z.get("sga"))
            k["combined"] = (sch + kosten) / pr if None not in (sch, kosten, pr) and pr > 0 else None
            if k["combined"] is not None and k["combined"] > 1.0:
                warn.append("Schaden-Kosten-Quote über 100 % – versicherungstechnischer Verlust")
        else:
            na.append("combined")             # Lebensversicherer/Mischkonzerne: Quote nicht aussagekraeftig
        k["ek_quote_vers"] = _t(z.get("ek"), z.get("bilanzsumme"))
        aussch = (_z(z.get("dividenden")) or 0.0) + (_z(z.get("rueckkaeufe")) or 0.0)
        k["ausschuettung_gewinn"] = _t(ng, aussch) if aussch > 0 else None
    if typ == "hypotheken_reit":
        k["ek_quote_mreit"] = _t(z.get("ek"), z.get("bilanzsumme"))
        div = _z(z.get("dividenden"))
        k["div_deckung_gewinn"] = _t(ng, div) if div and div > 0 else None
        if k["div_deckung_gewinn"] is not None and k["div_deckung_gewinn"] < 0.8:
            warn.append("Dividende nicht durch den Gewinn gedeckt")
    if typ == "reit":
        ffo, bereinigt = _ffo(z)
        mw = _boersenwert(f, z)
        k["ffo_rendite"] = _t(ffo, mw) if mw and mw > 0 else None
        ffo_a, _ = _ffo(a)
        k["ffops_cagr"] = _cagr(_t(ffo_a, a.get("aktien")), _t(ffo, z.get("aktien")), n_j)
        div = _z(z.get("dividenden"))
        k["ffo_deckung"] = _t(ffo, div) if div and div > 0 else None
        ebitda, sch, cash = _z(z.get("ebitda")), _z(z.get("schulden")), _z(z.get("cash")) or 0.0
        k["nde_reit"] = (sch - cash) / ebitda if sch is not None and ebitda and ebitda > 0 else None
        zins = _z(z.get("zinsaufwand"))
        k["zinsdeckung"] = _t(ebitda, abs(zins)) if zins and ebitda is not None else None
        k["schuldenquote"] = _t(sch, z.get("bilanzsumme"))
        if ffo is not None and not bereinigt:
            warn.append("FFO ohne Bereinigung um Veräußerungsgewinne (Posten fehlt)")
        if k["ffo_deckung"] is not None and k["ffo_deckung"] < 1.0:
            warn.append("Dividende nicht durch FFO gedeckt")
        if k["ffo_rendite"] is not None and mw:
            k["_p_ffo"] = mw / ffo if ffo and ffo > 0 else None
    return typ, {s_: w for s_, w in k.items() if w is not None}, warn, na


def bewerten(typ, k, ausgeschlossen=()):
    """-> (Branchen-Score oder None, {modul: (titel, score, {kennzahl: (wert, punkte)})})"""
    module, alle = {}, []
    for kurz, (titel, schl) in (MODULE.get(typ) or {}).items():
        werte = {s_: (k[s_], punkte(s_, k[s_])) for s_ in schl if s_ in k and s_ not in ausgeschlossen}
        p = [w[1] for w in werte.values()]
        alle += p
        module[kurz] = (titel, round(sum(p) / len(p)) if p else None, werte)
    m = [sc for _, sc, _ in module.values() if sc is not None]
    score = round(sum(m) / len(m)) if len(alle) >= MIN_KENNZAHLEN and m else None
    return score, module


def analyse(f, typ=None, ausgeschlossen=()):
    """-> dict (typ, score, module, warnungen, nicht_anwendbar, nicht_verfuegbar, p_ffo) oder None (Standardmodell)."""
    typ, k, warn, na = kennzahlen(f, typ)
    if typ not in TYPEN:
        return None
    p_ffo = k.pop("_p_ffo", None)
    score, module = bewerten(typ, k, ausgeschlossen)
    return {"typ": typ, "score": score, "module": module, "k": k, "warnungen": warn, "nicht_anwendbar": na,
            "datenluecke": sorted(set(ausgeschlossen)), "nicht_verfuegbar": list(NICHT_VERFUEGBAR.get(typ, ())),
            "p_ffo": p_ffo}


def kompakt(a):
    """Speicherform fuer state/investoren/ergebnis_NN.json (Feld "b")."""
    if not a:
        return None
    aus = {"t": a["typ"], "s": a["score"], "m": {kz: sc for kz, (_, sc, _) in a["module"].items()},
           "k": {s_: round(w, 4) for s_, w in a["k"].items()}}
    if a.get("warnungen"):
        aus["w"] = a["warnungen"][:5]
    if a.get("nicht_anwendbar"):
        aus["na"] = a["nicht_anwendbar"]
    if a.get("datenluecke"):
        aus["dl"] = a["datenluecke"]
    if a.get("p_ffo") is not None:
        aus["pffo"] = round(a["p_ffo"], 2)
    return aus


def neu_bewerten(b, ausgeschlossen=()):
    """Speicherform mit neuer Abdeckungsregel neu bewerten (ohne neuen Abruf)."""
    if not b or b.get("t") not in TYPEN:
        return b
    score, module = bewerten(b["t"], b.get("k") or {}, ausgeschlossen)
    b = dict(b, s=score, m={kz: sc for kz, (_, sc, _) in module.items()})
    b.pop("dl", None)
    if ausgeschlossen:
        b["dl"] = sorted(set(ausgeschlossen))
    return b


def abdeckung(werte):
    """werte: {symbol: kurzform mit "b"} -> {typ: {"n": Anzahl, kennzahl: Anteil mit Wert}}"""
    je = {}
    for w in werte.values():
        b = (w or {}).get("b") or {}
        if b.get("t") in TYPEN:
            je.setdefault(b["t"], []).append(b)
    aus = {}
    for typ, liste in je.items():
        schl = [s_ for _, s__ in MODULE[typ].values() for s_ in s__]
        aus[typ] = {"n": len(liste)}
        for s_ in schl:
            anwendbar = [b for b in liste if s_ not in (b.get("na") or ())]   # "nicht anwendbar" ist keine Luecke
            if anwendbar:
                aus[typ][s_] = round(sum(1 for b in anwendbar if s_ in (b.get("k") or {})) / len(anwendbar), 3)
    return aus


def ausgeschlossen(abd, typ):
    """Kennzahlen unter MIN_ABDECKUNG fuer diesen Typ (erst ab MIN_N Werten - sonst keine)."""
    a = (abd or {}).get(typ) or {}
    if (a.get("n") or 0) < MIN_N:
        return []
    return sorted(s_ for s_, v in a.items() if s_ != "n" and v < MIN_ABDECKUNG)


def wert_text(schluessel, w):
    if schluessel in PROZENT_QUOTE:
        return f"{w * 100:.1f} %".replace(".", ",")
    if schluessel in FAKTOR:
        return f"{w:.2f}".replace(".", ",")
    return f"{w * 100:.1f} %".replace(".", ",")


def anzeigen(b):
    """Speicherform -> (Typ-Titel, Score, [(Modultitel, Score, [(Kennzahl, Text, Punkte, Herkunft)])], Hinweise)"""
    if not b or b.get("t") not in TYPEN:
        return None
    k, m = b.get("k") or {}, b.get("m") or {}
    dl = set(b.get("dl") or [])
    module = []
    for kurz, (titel, schl) in MODULE[b["t"]].items():
        zeilen = [(TITEL[s_], wert_text(s_, k[s_]), round(punkte(s_, k[s_])), HERKUNFT.get(s_, "berechnet"))
                  for s_ in schl if s_ in k and s_ not in dl]
        module.append((titel, m.get(kurz), zeilen))
    hinweise = list(b.get("w") or [])
    if b.get("pffo") is not None:
        hinweise.append(f"Kurs/FFO {b['pffo']:.1f}".replace(".", ","))
    if dl:
        hinweise.append("Datenlücke (zu selten geliefert, nicht gewertet): " + ", ".join(TITEL[s_] for s_ in sorted(dl)))
    if b.get("na"):
        hinweise.append("Nicht anwendbar: " + ", ".join(TITEL.get(s_, s_) for s_ in b["na"]))
    hinweise.append("Nicht verfügbar (liefert Yahoo nicht): " + ", ".join(NICHT_VERFUEGBAR[b["t"]]))
    return TYP_TITEL[b["t"]], b.get("s"), module, hinweise


def textzeilen(b):
    """Speicherform -> (Typ-Titel, Score, Textzeilen je Modul + Hinweise) - fuer Oberflaeche und Begruendungen."""
    a = anzeigen(b)
    if not a:
        return None, None, []
    titel, score, module, hinweise = a
    zeilen = []
    for mt, sc, kz in module:
        if sc is None and not kz:
            zeilen.append(f"{mt}: keine Daten")
            continue
        zeilen.append(f"{mt}: {'–' if sc is None else f'{sc}/100'} – " +
                      " · ".join(f"{t} {v}" + ("" if h_ == "berechnet" else f" ({h_})") for t, v, _, h_ in kz))
    return titel, score, zeilen + hinweise
