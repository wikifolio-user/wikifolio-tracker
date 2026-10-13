"""Transparente Bewertung fuer Aktien, ETFs und Wikifolios (Score 0-100).

Grundsaetze (so steht es auch in der App unter "Wie wird bewertet?"):
- Jede Anlageklasse wird nur mit ihresgleichen verglichen. Ein Kriterium wie
  "5 J. p.a." bekommt 0-100 Punkte nach seinem Rang unter allen Werten derselben
  Klasse ("besser als 80 % der ETFs" = 80 Punkte). Wenige Kriterien sind feste
  Skalen (z. B. Qualitaets-Punkte des Aktien-Agenten, Laenge der Historie).
- Kriterien werden zu Teilscores zusammengefasst (Rendite, Risiko, Qualitaet ...),
  die Teilscores je nach Strategie gewichtet.
- Der Gesamt-Score startet bei 50 (neutral). Jeder Teilscore schiebt ihn um
  "Beitrag" Punkte nach oben oder unten - die Beitraege addieren sich exakt
  zum Gesamt-Score. So ist sichtbar, WARUM ein Wert vorne steht.
- Fehlende Daten werden nicht belohnt: je weniger Kriterien vorliegen, desto
  staerker wird der Score zur Mitte (50) gezogen; die Datenabdeckung wird angezeigt.
- Kriterien, die die Datenquelle gar nicht liefert (z. B. TER bei ETFs), stehen
  ausdruecklich als "nicht in der Datenquelle" da, statt still zu fehlen.
- Keine Scheingenauigkeit: Scores ganzzahlig, Abstaende unter 3 Punkten gelten
  als praktisch gleichwertig.

Reine Rechenlogik ohne Streamlit - getestet in test_bewertung.py.
"""
import bisect
import math
import re

KLASSEN = {"aktie": "Aktien", "etf": "ETFs", "wikifolio": "Wikifolios"}
KLASSE_EINZAHL = {"aktie": "Aktien", "etf": "ETFs", "wikifolio": "Wikifolios"}

GRUPPEN = {
    "rendite": "Rendite (langfristig)", "momentum": "Momentum (kurzfristig)", "risiko": "Risiko & Rückgang",
    "risikoadj": "Rendite je Risiko", "konsistenz": "Beständigkeit", "track": "Track Record",
    "dividende": "Dividende", "divers": "Streuung", "qualitaet": "Qualität", "wachstum": "Wachstum",
    "bilanz": "Bilanz & Schulden", "bewertung": "Bewertung", "analysten": "Analysten-Revisionen",
}

STRATEGIEN = {
    "Ausgewogen": "Alle Kriterien in ausgewogener Mischung.",
    "Wachstum": "Betont Rendite, Momentum und Umsatz-/Gewinnwachstum; Risiko zählt weniger.",
    "Dividende": "Betont Dividendenrendite, solide Bilanz und geringe Schwankung.",
    "Sicherheit": "Betont geringe Schwankung, kleine Rückgänge, Beständigkeit und Bilanz.",
    "Momentum": "Betont die Kursentwicklung der letzten 6–12 Monate.",
    "Vermögensaufbau": "Langfristig: Rendite über 5–10 Jahre, Beständigkeit, Track Record und Qualität.",
}

# Gewichte der Teilscores in % je Strategie und Anlageklasse (Summe je 100)
GEWICHTE = {
    "Ausgewogen": {
        "aktie": {"rendite": 15, "momentum": 10, "risiko": 15, "qualitaet": 20, "wachstum": 10, "bilanz": 10,
                  "bewertung": 15, "analysten": 5},
        "etf": {"rendite": 30, "momentum": 10, "risiko": 20, "risikoadj": 20, "konsistenz": 10, "divers": 10},
        "wikifolio": {"rendite": 25, "momentum": 5, "risiko": 20, "risikoadj": 20, "konsistenz": 15, "track": 15},
    },
    "Wachstum": {
        "aktie": {"rendite": 20, "momentum": 15, "risiko": 5, "qualitaet": 15, "wachstum": 25, "bilanz": 5,
                  "bewertung": 10, "analysten": 5},
        "etf": {"rendite": 40, "momentum": 20, "risiko": 10, "risikoadj": 20, "konsistenz": 5, "divers": 5},
        "wikifolio": {"rendite": 40, "momentum": 15, "risiko": 10, "risikoadj": 15, "konsistenz": 10, "track": 10},
    },
    "Dividende": {
        "aktie": {"dividende": 30, "rendite": 10, "risiko": 15, "qualitaet": 15, "bilanz": 15, "bewertung": 15},
        "etf": {"dividende": 35, "rendite": 20, "risiko": 20, "risikoadj": 10, "konsistenz": 10, "divers": 5},
        "wikifolio": {"rendite": 25, "risiko": 30, "risikoadj": 20, "konsistenz": 15, "track": 10},
    },
    "Sicherheit": {
        "aktie": {"rendite": 10, "risiko": 30, "qualitaet": 20, "bilanz": 20, "bewertung": 15, "momentum": 5},
        "etf": {"rendite": 15, "risiko": 35, "risikoadj": 20, "konsistenz": 15, "divers": 15},
        "wikifolio": {"rendite": 15, "risiko": 35, "risikoadj": 20, "konsistenz": 15, "track": 15},
    },
    "Momentum": {
        "aktie": {"momentum": 45, "rendite": 15, "risiko": 10, "qualitaet": 10, "wachstum": 10, "analysten": 10},
        "etf": {"momentum": 50, "rendite": 20, "risiko": 10, "risikoadj": 15, "divers": 5},
        "wikifolio": {"momentum": 45, "rendite": 20, "risiko": 10, "risikoadj": 15, "track": 10},
    },
    "Vermögensaufbau": {
        "aktie": {"rendite": 25, "risiko": 10, "qualitaet": 25, "wachstum": 15, "bilanz": 10, "bewertung": 15},
        "etf": {"rendite": 35, "risiko": 15, "risikoadj": 20, "konsistenz": 15, "divers": 15},
        "wikifolio": {"rendite": 30, "risiko": 15, "risikoadj": 20, "konsistenz": 15, "track": 20},
    },
}

# Kriterien, die die Datenquelle (ls-tc.de Kurse, Yahoo-Fundamentaldaten) nicht liefert
NICHT_IN_QUELLE = {
    "aktie": ["KUV und KBV (verwendet werden erwartetes KGV und Free-Cashflow-Rendite)"],
    "etf": ["TER / laufende Kosten", "Tracking Difference", "Fondsvolumen und Handelsliquidität",
            "Indexqualität (Anzahl Titel, Gewichtung)"],
    "wikifolio": ["Gebühren (Performance- und Zertifikategebühr)", "Investiertes Kapital / investierbares Volumen",
                  "Konzentration (Anzahl und Gewicht der Positionen)", "Handelsaktivität"],
}

ABDECKUNG_GUT, ABDECKUNG_MITTEL = 0.85, 0.6
GLEICHWERTIG = 3          # Score-Abstand, unter dem zwei Werte als gleichwertig gelten
MIN_VERGLEICH = 5         # so viele Werte braucht ein Rang-Kriterium mindestens


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
def _zahl(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _de(x, dec=1, vz=False):
    if x is None:
        return "–"
    t = f"{x:+,.{dec}f}" if vz else f"{x:,.{dec}f}"
    return t.replace(",", "§").replace(".", ",").replace("§", ".")


def _klemme(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _lang(z):
    """Rendite fuer Risikoverhaeltnisse: 5 J. p.a., sonst 3 J. p.a."""
    return _zahl(z.get("r5")) if _zahl(z.get("r5")) is not None else _zahl(z.get("r3"))


def _q(z, feld):
    q = z.get("qd") or {}
    return q.get(feld)


def _pt(z, i, maximum):
    pt = _q(z, "pt")
    if isinstance(pt, (list, tuple)) and len(pt) == 8 and _zahl(pt[i]) is not None:
        return _klemme(_zahl(pt[i]) / maximum * 100)
    return None


def streuung_geschaetzt(name):
    """Breite eines ETF/ETP grob aus dem Namen (0-100) -> (punkte, einordnung)."""
    n = (name or "").lower()
    regeln = (
        (r"\b[235]x\b|lever|daily|hebel|short|inverse", 10, "Hebel-/Short-Produkt"),
        (r"crypto|bitcoin|ethereum|krypto|solana|xrp", 10, "Einzelne Kryptowährung"),
        (r"gold|silver|silber|platin|palladium|copper|kupfer|oil|öl|wti|brent|gas\b", 20, "Einzelner Rohstoff"),
        (r"semicon|halbleiter|cyber|robot|\bai\b|artificial|cloud|clean|solar|hydrogen|wasserstoff|battery|"
         r"uranium|uran|defen|rüstung|water|wasser|biotech|gaming|blockchain|space|lithium|miner", 30,
         "Themen-/Branchen-ETF"),
        (r"tech|information|health|energy|financ|bank|util|real estate|reit|consumer|industrial|material",
         40, "Sektor-ETF"),
        (r"\bdax\b|mdax|tecdax|japan|china|india|indien|uk\b|ftse 100|swiss|schweiz|korea|taiwan|brazil|"
         r"brasil|canada|kanada|australia|france|italy|spain|nikkei|topix", 50, "Einzelnes Land"),
        (r"small ?cap|nebenwerte|momentum|quality|value|factor|min(imum)? vol|dividend", 60,
         "Faktor- oder Small-Cap-Strategie"),
        (r"all[- ]?world|acwi|ftse all|msci world|\bworld\b|global|welt", 90, "Weltweit breit gestreut"),
        (r"bond|anleihe|treasury|govt|aggregate|corporate", 75, "Anleihen-Index"),
        (r"s&p 500|sp500|usa|\bus\b|europe|europa|euro stoxx|stoxx 600|emerging|schwellen|pacific|asia|"
         r"nasdaq", 65, "Breiter Regional-Index"),
    )
    for muster, punkte, text in regeln:
        if re.search(muster, n):
            return punkte, text
    return 55, "Nicht eindeutig erkennbar"


# ---------------------------------------------------------------------------
# Kriterien
# art "rang": Rang unter allen Werten derselben Klasse; richtung +1 = hoeher ist besser
# art "skala": feste 0-100-Skala (wert -> punkte)
# ---------------------------------------------------------------------------
def _konsistenz(z):
    """Spanne zwischen bester und schlechtester Rendite p.a. (1/3/5/10 J.) - negativ, klein = beständig."""
    werte = [_zahl(z.get(k)) for k in ("r1", "r3", "r5", "r10")]
    werte = [w for w in werte if w is not None]
    if len(werte) < 3:
        return None
    return -(max(werte) - min(werte))


def _sharpe(z):
    r, v = _lang(z), _zahl(z.get("vola"))
    return r / v if r is not None and v and v > 0.5 else None


def _calmar(z):
    r, d = _lang(z), _zahl(z.get("maxdd"))
    return r / abs(d) if r is not None and d is not None and d < -1 else None


def _nde(z):
    if _q(z, "netcash"):
        return -1.0
    return _zahl(_q(z, "nde"))


KRITERIEN = {
    # key: (gruppe, label, wertfunktion, art, richtung/skala, format, klassen, gewicht_in_gruppe)
    "r10": ("rendite", "Rendite 10 J. p.a.", lambda z: _zahl(z.get("r10")), "rang", 1, "pct", "aew", 0.35),
    "r5": ("rendite", "Rendite 5 J. p.a.", lambda z: _zahl(z.get("r5")), "rang", 1, "pct", "aew", 0.40),
    "r3": ("rendite", "Rendite 3 J. p.a.", lambda z: _zahl(z.get("r3")), "rang", 1, "pct", "aew", 0.25),
    "r1": ("momentum", "Kursentwicklung 1 Jahr", lambda z: _zahl(z.get("r1")), "rang", 1, "pct", "aew", 0.6),
    "p6": ("momentum", "Kursentwicklung 6 Monate", lambda z: _zahl(_q(z, "p6")), "rang", 1, "pct", "a", 0.4),
    "vola": ("risiko", "Schwankung (Vola 1 J.)", lambda z: _zahl(z.get("vola")), "rang", -1, "pct0", "aew", 0.5),
    "maxdd": ("risiko", "Größter Rückgang (seit Beginn)", lambda z: _zahl(z.get("maxdd")), "rang", 1, "pct0",
              "aew", 0.5),
    "sharpe": ("risikoadj", "Rendite je Schwankung", _sharpe, "rang", 1, "x", "ew", 0.5),
    "calmar": ("risikoadj", "Rendite je Rückgang", _calmar, "rang", 1, "x", "ew", 0.5),
    "konsistenz": ("konsistenz", "Gleichmäßigkeit 1/3/5/10 J.", _konsistenz, "rang", 1, "spanne", "ew", 1.0),
    "jahre": ("track", "Länge der Historie", lambda z: _zahl(z.get("jahre")), "skala",
              lambda j: _klemme(j / 10 * 100), "jahre", "w", 1.0),
    "div": ("dividende", "Dividendenrendite", lambda z: _zahl(z.get("div")), "rang", 1, "pct", "ae", 1.0),
    "divers": ("divers", "Streuung (geschätzt aus dem Namen)", lambda z: streuung_geschaetzt(z.get("name"))[0],
               "skala", lambda p: p, "divers", "e", 1.0),
    # Aktien - Fundamentaldaten des Qualitaets-Agenten
    "q_pkt": ("qualitaet", "Qualitäts-Punkte (ROIC, Margen, FCF, Moat, Management)",
              lambda z: _qualitaet_pkt(z), "skala", lambda p: p, "punkte", "a", 0.6),
    "roic": ("qualitaet", "Kapitalrendite ROIC Ø", lambda z: _zahl(_q(z, "roic")), "rang", 1, "pct0", "a", 0.4),
    "w_pkt": ("wachstum", "Wachstums-Punkte", lambda z: _pt(z, 1, 15), "skala", lambda p: p, "punkte", "a", 0.4),
    "g_ums": ("wachstum", "Umsatzwachstum p.a.", lambda z: _zahl(_q(z, "g_ums")), "rang", 1, "pct", "a", 0.3),
    "g_eps": ("wachstum", "Gewinnwachstum je Aktie p.a.", lambda z: _zahl(_q(z, "g_eps")), "rang", 1, "pct", "a",
              0.3),
    "b_pkt": ("bilanz", "Bilanz-Punkte", lambda z: _pt(z, 3, 10), "skala", lambda p: p, "punkte", "a", 0.5),
    "nde": ("bilanz", "Nettoschulden / EBITDA", _nde, "rang", -1, "nde", "a", 0.5),
    "bw_pkt": ("bewertung", "Bewertungs-Punkte (inkl. Chance/Risiko)", lambda z: _bewertung_pkt(z), "skala",
               lambda p: p, "punkte", "a", 0.5),
    "fkgv": ("bewertung", "KGV (erwartet)", lambda z: _zahl(_q(z, "fkgv")), "rang", -1, "x", "a", 0.25),
    "fcfy": ("bewertung", "Free-Cashflow-Rendite", lambda z: _zahl(_q(z, "fcfy")), "rang", 1, "pct", "a", 0.25),
    "rev": ("analysten", "Gewinnschätzungen 90 Tage", lambda z: _zahl(_q(z, "rev90")), "skala",
            lambda r: _klemme(50 + r * 5), "pct", "a", 1.0),
}
_KLASSE_KUERZEL = {"aktie": "a", "etf": "e", "wikifolio": "w"}


def _qualitaet_pkt(z):
    pt = _q(z, "pt")
    if isinstance(pt, (list, tuple)) and len(pt) == 8 and all(_zahl(pt[i]) is not None for i in (0, 2, 4, 5)):
        return _klemme((pt[0] + pt[2] + pt[4] + pt[5]) / 55 * 100)
    qa = _zahl(_q(z, "q_ant"))                   # aeltere Datendatei: Qualitaetsanteil in %
    return _klemme(qa) if qa is not None else None


def _bewertung_pkt(z):
    pt = _q(z, "pt")
    if isinstance(pt, (list, tuple)) and len(pt) == 8 and _zahl(pt[6]) is not None and _zahl(pt[7]) is not None:
        return _klemme((pt[6] + pt[7]) / 20 * 100)
    ba = _zahl(_q(z, "b_ant"))
    return _klemme(ba) if ba is not None else None


def kriterien_der_klasse(typ):
    k = _KLASSE_KUERZEL.get(typ, "")
    return {key: d for key, d in KRITERIEN.items() if k in d[6]}


def _wert_text(fmt, w):
    if w is None:
        return "–"
    if fmt == "pct":
        return f"{_de(w, 1, vz=True)} %"
    if fmt == "pct0":
        return f"{_de(w, 1)} %"
    if fmt == "x":
        return f"{_de(w, 2)}"
    if fmt == "spanne":
        return f"Spanne {_de(-w, 1)} %-Punkte"
    if fmt == "jahre":
        return f"{_de(w, 1)} Jahre"
    if fmt == "punkte":
        return f"{_de(w, 0)} von 100"
    if fmt == "nde":
        return "Nettocash" if w < 0 else f"{_de(w, 1)}x"
    if fmt == "divers":
        return f"{_de(w, 0)} von 100"
    return _de(w)


# ---------------------------------------------------------------------------
# Modell
# ---------------------------------------------------------------------------
class Modell:
    """Vergleichsbasis aus ALLEN Werten (nicht nur den gefilterten), damit sich ein
    Score nicht aendert, wenn man die Filter aendert."""

    def __init__(self, zeilen, strategie="Ausgewogen"):
        self.strategie = strategie if strategie in GEWICHTE else "Ausgewogen"
        self.vergleich = {}             # (typ, key) -> sortierte Werte
        for typ in KLASSEN:
            krit = kriterien_der_klasse(typ)
            for key, d in krit.items():
                if d[3] != "rang":
                    continue
                werte = sorted(w for w in (d[2](z) for z in zeilen if z.get("typ") == typ) if w is not None)
                self.vergleich[(typ, key)] = werte

    def anzahl(self, typ):
        return max((len(v) for (t, _), v in self.vergleich.items() if t == typ), default=0)

    def _rang(self, typ, key, wert, richtung):
        werte = self.vergleich.get((typ, key)) or []
        n = len(werte)
        if n < MIN_VERGLEICH or wert is None:
            return None
        lo, hi = bisect.bisect_left(werte, wert), bisect.bisect_right(werte, wert)
        anteil = (lo + (hi - lo) / 2) / n          # Anteil schlechterer Werte (bei richtung +1)
        return _klemme(anteil * 100 if richtung > 0 else (1 - anteil) * 100)

    def gewichte(self, typ):
        g = GEWICHTE[self.strategie].get(typ) or {}
        return {k: v for k, v in g.items() if v > 0}

    def bewerte(self, z):
        typ = z.get("typ")
        if typ not in KLASSEN:
            return None
        klasse = KLASSE_EINZAHL[typ]
        krit = kriterien_der_klasse(typ)
        gew = self.gewichte(typ)
        gruppen = []
        for g, w_g in gew.items():
            eintraege, summe_w, summe_s, alle_w = [], 0.0, 0.0, 0.0
            for key, d in krit.items():
                if d[0] != g:
                    continue
                alle_w += d[7]
                wert = d[2](z)
                if d[3] == "rang":
                    s = self._rang(typ, key, wert, d[4])
                    if s is None:
                        info = "keine Daten" if wert is None else "zu wenige Vergleichswerte"
                    elif d[4] > 0:
                        info = f"besser als {s:.0f} % der {klasse}"
                    else:
                        info = f"{'ruhiger' if key == 'vola' else 'besser'} als {s:.0f} % der {klasse}"
                else:
                    s = None if wert is None else d[4](wert)
                    info = "keine Daten" if s is None else (
                        streuung_geschaetzt(z.get("name"))[1] if key == "divers" else "feste Skala")
                eintraege.append({"key": key, "label": d[1], "wert": wert, "wert_txt": _wert_text(d[5], wert),
                                  "score": None if s is None else round(s), "info": info, "gewicht": d[7],
                                  "_s": s})
                if s is not None:
                    summe_w += d[7]
                    summe_s += d[7] * s
            gruppen.append({"key": g, "label": GRUPPEN[g], "gewicht": w_g,
                            "score": summe_s / summe_w if summe_w else None,
                            "abdeckung": summe_w / alle_w if alle_w else 0.0, "kriterien": eintraege})

        verfuegbar = [x for x in gruppen if x["score"] is not None]
        gesamt_w = sum(x["gewicht"] for x in gruppen) or 1
        w_verf = sum(x["gewicht"] for x in verfuegbar)
        abdeckung = sum(x["gewicht"] * x["abdeckung"] for x in gruppen) / gesamt_w
        roh = sum(x["gewicht"] * x["score"] for x in verfuegbar) / w_verf if w_verf else 50.0
        # Beitrag je Teilscore: 50 + Summe(Beitraege) = Gesamt-Score
        for x in gruppen:
            if x["score"] is None:
                x["beitrag"] = 0.0
            else:
                x["beitrag"] = abdeckung * x["gewicht"] / w_verf * (x["score"] - 50)
            x["gewicht_eff"] = (x["gewicht"] / w_verf * 100) if (w_verf and x["score"] is not None) else 0.0
        score = 50 + abdeckung * (roh - 50)

        fehlend = [k["label"] for x in gruppen for k in x["kriterien"] if k["_s"] is None]
        hinweise = []
        jahre = _zahl(z.get("jahre"))
        if jahre is not None and jahre < 3:
            hinweise.append(f"Kurze Historie ({_de(jahre, 1)} Jahre) – Renditen und Risiko wenig aussagekräftig")
        if typ == "etf" and streuung_geschaetzt(z.get("name"))[0] <= 20:
            hinweise.append("Hebel-, Short- oder Einzelrohstoff-Produkt – nicht mit breiten ETFs vergleichbar")
        r10, r5 = _zahl(z.get("r10")), _zahl(z.get("r5"))
        if (r5 or 0) >= 25 or (r10 or 0) >= 25:
            hinweise.append("Sehr hohe Vergangenheitsrendite – keine Zukunftserwartung (Winner Bias)")

        # Staerken / Schwaechen auf Kriterienebene, gewichtet nach Einfluss
        einfluesse = []
        for x in verfuegbar:
            anteil = x["gewicht"] / w_verf
            for k in x["kriterien"]:
                if k["_s"] is None:
                    continue
                gew_k = k["gewicht"] / sum(e["gewicht"] for e in x["kriterien"] if e["_s"] is not None)
                einfluesse.append((abdeckung * anteil * gew_k * (k["_s"] - 50), k, x))
        plus = [_faktor_text(k) for e, k, _ in sorted(einfluesse, key=lambda t: -t[0])
                if e > 0.4 and k["_s"] >= 60][:3]
        minus = [_faktor_text(k) for e, k, _ in sorted(einfluesse, key=lambda t: t[0])
                 if e < -0.4 and k["_s"] <= 40][:3]
        for x in gruppen:
            x.pop("_s", None)
            for k in x["kriterien"]:
                k.pop("_s", None)
        return {
            "score": int(round(score)), "score_genau": score, "roh": roh, "abdeckung": abdeckung,
            "datenqualitaet": datenqualitaet(abdeckung), "gruppen": gruppen, "plus": plus, "minus": minus,
            "fehlend": fehlend, "hinweise": hinweise, "klasse": typ, "strategie": self.strategie,
            "nicht_in_quelle": NICHT_IN_QUELLE.get(typ, []),
        }


def _faktor_text(k):
    return f"{k['label']}: {k['wert_txt']} ({k['info']})"


def datenqualitaet(abdeckung):
    if abdeckung >= ABDECKUNG_GUT:
        return "gut"
    if abdeckung >= ABDECKUNG_MITTEL:
        return "mittel"
    return "gering"


def ampel(score):
    """'gruen' >= 65, 'gelb' 45-64, 'rot' < 45."""
    if score is None:
        return "grau"
    return "gruen" if score >= 65 else "gelb" if score >= 45 else "rot"


# ---------------------------------------------------------------------------
# Erklaerungen
# ---------------------------------------------------------------------------
def top_gruppen(b, n=2, positiv=True):
    g = [x for x in b["gruppen"] if x["score"] is not None]
    g.sort(key=lambda x: -x["beitrag"] if positiv else x["beitrag"])
    return [x for x in g if (x["beitrag"] > 0.5 if positiv else x["beitrag"] < -0.5)][:n]


def vergleich(a, b):
    """Teilscore-Beitraege von a gegen b -> (abstand, [(label, differenz)] absteigend)."""
    labels = {}
    for x in a["gruppen"]:
        labels.setdefault(x["key"], [x["label"], 0.0])[1] += x["beitrag"]
    for x in b["gruppen"]:
        labels.setdefault(x["key"], [x["label"], 0.0])[1] -= x["beitrag"]
    diffs = sorted(((lbl, d) for lbl, d in labels.values() if abs(d) >= 0.05), key=lambda t: -t[1])
    return a["score_genau"] - b["score_genau"], diffs


def warum(platz, b, naechster=None, name_naechster=None, sortiert_nach_score=True, sortierung=None):
    """Kurzer Satz: Warum steht dieser Wert auf diesem Platz?"""
    teile = []
    if not sortiert_nach_score and sortierung:
        teile.append(f"Platz {platz} nach „{sortierung}“; der Gesamt-Score ({b['score']}) ist davon unabhängig.")
    stark = top_gruppen(b, 2, True)
    schwach = top_gruppen(b, 1, False)
    if stark:
        teile.append("Stark bei " + " und ".join(f"{x['label']} ({x['beitrag']:+.0f})" for x in stark) + ".")
    else:
        teile.append("Keine ausgeprägte Stärke – der Score liegt nahe der Mitte.")
    if schwach:
        teile.append(f"Schwäche: {schwach[0]['label']} ({schwach[0]['beitrag']:+.0f}).")
    if naechster is not None and sortiert_nach_score:
        abstand, diffs = vergleich(b, naechster)
        ziel = f"Platz {platz + 1}" + (f" ({name_naechster})" if name_naechster else "")
        if abs(abstand) < GLEICHWERTIG:
            teile.append(f"Gegenüber {ziel} praktisch gleichwertig (Abstand {_de(abs(abstand), 1)} Punkte).")
        elif diffs and diffs[0][1] > 0:
            teile.append(f"Vorsprung auf {ziel}: {_de(abstand, 1)} Punkte, vor allem durch {diffs[0][0]} "
                         f"({_de(diffs[0][1], 1, vz=True)}).")
    if b["datenqualitaet"] != "gut":
        teile.append(f"Datenlage {b['datenqualitaet']} ({b['abdeckung'] * 100:.0f} % der Kriterien) – "
                     "Score mit Vorsicht lesen.")
    return " ".join(teile)
