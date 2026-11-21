"""Daily-Leveraged-ETF/ETP-Rechner - reine Rechenlogik ohne Streamlit.

Taeglich gehebelte Produkte werden JEDEN Handelstag neu gehebelt:
    Produktwert_t = Produktwert_(t-1) x (1 + L x Basiswertrendite_t)  (- anteilige laufende Kosten)
Der Endwert ergibt sich aus der Verkettung aller Tagesrenditen - deshalb fuehren unterschiedliche Kursverlaeufe trotz
gleichem Anfangs- und Endstand zu unterschiedlichen Ergebnissen (Pfadabhaengigkeit, "Volatility Decay").
Ein rechnerischer Tageswert <= 0 bedeutet Totalverlust (kein negativer Produktwert; viele Produkte stoppen in
solchen Faellen ohnehin - die konkreten Produktbedingungen gelten).

Kursverlaeufe (alle enden GENAU am Kursziel; die Schwankung ist fest vorgegeben = reproduzierbar, kein Zufall je
Aufruf): gleichmaessig, schwankend (Brownsche Bruecke mit der gewaehlten Volatilitaet), seitwaerts (Wellen),
Crash mit Erholung, historisch (echte Tagesrenditen der letzten Handelstage, an das Kursziel angepasst).
Alles hier sind HYPOTHETISCHE Simulationen - keine Prognose.
"""
import math
import random

VERLAEUFE = {
    "gleichmaessig_auf": "Gleichmäßiger Kursanstieg",
    "gleichmaessig_ab": "Gleichmäßiger Kursrückgang",
    "schwankend_auf": "Schwankender Aufwärtstrend",
    "schwankend_ab": "Schwankender Abwärtstrend",
    "seitwaerts": "Seitwärtsmarkt",
    "crash": "Zwischenzeitlicher Crash mit Erholung",
    "historisch": "Historischer Kursverlauf",
}
SZENARIO_VERGLEICH = ("gleichmaessig_auf", "schwankend_auf", "seitwaerts", "crash")
EINSATZ = {"min": 1000, "max": 100000, "schritt": 500, "standard": 10000}
HEBEL = {"min": -5, "max": 5, "standard": 3}
HALTEDAUER = {"min": 1, "max": 252, "standard": 40}
VOLA = {"min": 5, "max": 80, "schritt": 5, "standard": 25}
SAAT = 20261121                       # feste Saat: gleiche Eingaben -> gleiche Schwankung
HANDELSTAGE_JAHR = 252


def de(x, n=2):
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pruefe(einsatz=None, start=None, ziel=None, hebel=None, tage=None, vola=None):
    f = []
    if einsatz is not None and not EINSATZ["min"] <= einsatz <= 10_000_000:
        f.append(f"Der Einsatz muss mindestens {de(EINSATZ['min'], 0)} € betragen.")
    if start is not None and not (start > 0 and math.isfinite(start)):
        f.append("Der Indexstand muss größer als 0 sein.")
    if ziel is not None and not (ziel > 0 and math.isfinite(ziel)):
        f.append("Das Kursziel muss größer als 0 sein.")
    if hebel is not None and (not -10 <= hebel <= 10 or hebel == 0):
        f.append("Der tägliche Hebel muss zwischen −10 und +10 liegen und darf nicht 0 sein.")
    if tage is not None and not 1 <= tage <= 2520:
        f.append("Die Haltedauer muss mindestens 1 Handelstag betragen.")
    if vola is not None and not 0 <= vola <= 200:
        f.append("Die Volatilität muss zwischen 0 und 200 % liegen.")
    return f


# ---------------------------------------------------------------------------------------------------- Kursverlaeufe
def _bruecke(n, sigma_tag, saat):
    """Brownsche Bruecke (Start 0, Ende 0) mit Tagesschwankung sigma_tag - feste Saat."""
    r = random.Random(saat)
    b, weg = [0.0], 0.0
    for _ in range(n):
        weg += r.gauss(0.0, sigma_tag)
        b.append(weg)
    return [b[t] - t / n * b[n] for t in range(n + 1)]


def kursverlauf(start, ziel, tage, vola_pct, art, historische_renditen=None, saat=SAAT):
    """Indexstaende Tag 0..tage (Laenge tage+1), Tag 0 = start, letzter Tag = ziel (exakt)."""
    fehler = pruefe(start=start, ziel=ziel, tage=tage, vola=vola_pct)
    if fehler:
        raise ValueError(fehler[0])
    n = int(tage)
    gesamt = math.log(ziel / start)
    sigma = vola_pct / 100 / math.sqrt(HANDELSTAGE_JAHR)
    drift = [gesamt * t / n for t in range(n + 1)]
    if art.startswith("gleichmaessig"):
        log = drift
    elif art.startswith("schwankend"):
        log = [d + x for d, x in zip(drift, _bruecke(n, sigma, saat))]
    elif art == "seitwaerts":
        periode = 20.0
        amp = sigma * periode * math.sqrt(2) / (2 * math.pi)      # Tagesschwankung ~ gewaehlte Volatilitaet
        welle = [amp * math.sin(2 * math.pi * t / periode) for t in range(n + 1)]
        log = [d + w - t / n * welle[n] for t, (d, w) in enumerate(zip(drift, welle))]
    elif art == "crash":
        tiefe = min(0.5, max(0.10, vola_pct / 100 * 0.8))          # z. B. 25 % Vola -> 20 % Einbruch
        t_tief = max(1, round(n * 0.3))
        unten = math.log(1 - tiefe)
        log = []
        for t in range(n + 1):
            if t <= t_tief:
                log.append(unten * t / t_tief)
            else:
                log.append(unten + (gesamt - unten) * (t - t_tief) / (n - t_tief))
    elif art == "historisch":
        ren = [r for r in (historische_renditen or []) if r is not None and r > -1]
        if len(ren) < n:
            raise ValueError(f"Für einen historischen Verlauf über {n} Handelstage fehlen Tagesdaten "
                             f"(vorhanden: {len(ren)}).")
        lr = [math.log(1 + r) for r in ren[-n:]]
        korr = (gesamt - sum(lr)) / n                              # gleichmaessig angepasst -> endet am Ziel
        log, s = [0.0], 0.0
        for x in lr:
            s += x + korr
            log.append(s)
    else:
        raise ValueError(f"Unbekannter Kursverlauf: {art}")
    pfad = [start * math.exp(x) for x in log]
    pfad[-1] = ziel                                                 # Rundungsfehler ausschliessen
    return pfad


def renditen(pfad):
    return [b / a - 1 for a, b in zip(pfad[:-1], pfad[1:])]


# ---------------------------------------------------------------------------------------------------- Produkt
def produkt_verlauf(pfad, hebel, kosten_pa=0.0, start_wert=100.0):
    """Taeglich neu gehebelter Produktwert je Tag (Laenge wie pfad). kosten_pa: laufende Kosten + Finanzierung in %
    p. a. (taeglich anteilig abgezogen). Nie negativ: ein Tag mit 1 + L x r <= 0 -> 0 (Totalverlust) und bleibt 0."""
    k_tag = (kosten_pa or 0) / 100 / HANDELSTAGE_JAHR
    werte, v, aus = [start_wert], start_wert, False
    for r in renditen(pfad):
        if aus:
            werte.append(0.0)
            continue
        faktor = (1 + hebel * r) * (1 - k_tag)
        if faktor <= 0:
            v, aus = 0.0, True
        else:
            v *= faktor
        werte.append(v)
    return werte


def max_drawdown(werte):
    """Groesster Rueckgang vom bisherigen Hoch in % (0 ... 100) -> (prozent, tag_hoch, tag_tief)."""
    hoch, t_hoch, best = werte[0], 0, (0.0, 0, 0)
    for t, w in enumerate(werte):
        if w > hoch:
            hoch, t_hoch = w, t
        if hoch > 0:
            dd = (1 - w / hoch) * 100
            if dd > best[0]:
                best = (dd, t_hoch, t)
    return best


def ergebnis(einsatz, pfad, hebel, kosten_pa=0.0, fx_faktor=1.0, gebuehren=0.0):
    """Alle Kennzahlen einer Simulation. fx_faktor: Waehrungseffekt bis zum Ende (z. B. EUR/USD Start / Ziel bei einem
    nicht waehrungsgesicherten Produkt auf einen US-Index), gebuehren: Handelskosten in EUR (Kauf + Verkauf)."""
    fehler = pruefe(einsatz=einsatz, hebel=hebel)
    if fehler:
        raise ValueError(fehler[0])
    prod = produkt_verlauf(pfad, hebel, kosten_pa)
    index = [100 * x / pfad[0] for x in pfad]
    endwert = max(0.0, einsatz * prod[-1] / 100 * fx_faktor - gebuehren)
    dd, t_hoch, t_tief = max_drawdown(prod)
    index_pct = (pfad[-1] / pfad[0] - 1) * 100
    return {"einsatz": einsatz, "hebel": hebel, "tage": len(pfad) - 1, "endwert": endwert, "gv": endwert - einsatz,
            "rendite_pct": (endwert / einsatz - 1) * 100, "index_pct": index_pct,
            "naiv_pct": index_pct * hebel,                     # "Hebel x Indexrendite" - stimmt nur ohne Schwankung
            "ungehebelt_endwert": einsatz * pfad[-1] / pfad[0] * fx_faktor,
            "max_dd_pct": dd, "dd_hoch_tag": t_hoch, "dd_tief_tag": t_tief, "totalverlust": prod[-1] == 0,
            "hoch": max(prod), "tief": min(prod), "produkt": prod, "index": index}


def hebel_vergleich(einsatz, pfad, hebel_liste=(-3, -2, 1, 2, 3, 5), kosten_pa=0.0):
    return [ergebnis(einsatz, pfad, h, kosten_pa) for h in hebel_liste]


def szenarien(einsatz, start, ziel, tage, vola_pct, hebel, kosten_pa=0.0, arten=SZENARIO_VERGLEICH,
              historische_renditen=None):
    """Gleiches Start- und Endniveau, verschiedene Verlaeufe -> [(art, ergebnis oder None)]."""
    aus = []
    for art in arten:
        try:
            p = kursverlauf(start, ziel, tage, vola_pct, art, historische_renditen)
        except ValueError:
            aus.append((art, None))
            continue
        aus.append((art, ergebnis(einsatz, p, hebel, kosten_pa)))
    return aus


# ---------------------------------------------------------------------------------------------------- Knock-out
def ko_auf_pfad(einsatz, pfad, hebel_ko, richtung, finanzierung_pa=0.0):
    """Vereinfachtes Knock-out-Produkt auf DEMSELBEN Kursverlauf: Anfangshebel hebel_ko, Basispreis = KO-Schwelle
    (S0 x (1 - 1/H) Long bzw. S0 x (1 + 1/H) Short), Basispreis wandert mit den Finanzierungskosten gegen den Anleger.
    Beruehrt der Verlauf die Schwelle (Schlusskurse), ist das Produkt wertlos."""
    if hebel_ko <= 1:
        raise ValueError("Der Knock-out-Hebel muss größer als 1 sein.")
    s0 = pfad[0]
    long = richtung == "long"
    basis0 = s0 * (1 - 1 / hebel_ko) if long else s0 * (1 + 1 / hebel_ko)
    r_tag = (finanzierung_pa or 0) / 100 / HANDELSTAGE_JAHR
    werte, ko_tag = [], None
    for t, s in enumerate(pfad):
        basis = basis0 * ((1 + r_tag) ** t if long else (1 - r_tag) ** t)
        innen = (s - basis) if long else (basis - s)
        if innen <= 0 and ko_tag is None:
            ko_tag = t
        werte.append(0.0 if ko_tag is not None else innen / (s0 / hebel_ko) * 100)
    endwert = einsatz * werte[-1] / 100
    return {"hebel": hebel_ko, "richtung": richtung, "endwert": endwert, "gv": endwert - einsatz,
            "rendite_pct": (endwert / einsatz - 1) * 100, "ko_tag": ko_tag, "ko_schwelle": basis0,
            "max_dd_pct": max_drawdown(werte)[0], "werte": werte}


VERGLEICH_ZEILEN = [
    ("Anfangshebel", "variabel (täglich zurückgesetzt)", "produktabhängig, ändert sich mit dem Kurs"),
    ("Tägliche Neugewichtung", "Ja", "Nein"),
    ("Finanzierungskosten", "produktabhängig (laufende Kosten)", "produktabhängig (Basispreis wandert)"),
    ("Pfadabhängigkeit", "tägliche Renditeverkettung", "Knock-out-Ereignis"),
    ("Knock-out-Schwelle", "keine klassische KO-Schwelle", "Ja"),
]


# ---------------------------------------------------------------------------------------------------- Backtest
def backtest(kerzen, von, bis, hebel, einsatz, kosten_pa=0.0):
    """Historische Simulation aus echten Tageskerzen [[iso, o, h, l, c]] zwischen von und bis (iso, einschliesslich).
    -> dict mit Kennzahlen oder ValueError (zu wenige Daten). Modellrechnung, kein reales Produkt."""
    teil = [k for k in kerzen if von <= k[0] <= bis]
    if len(teil) < 2:
        raise ValueError("Für diesen Zeitraum liegen zu wenige Tageskerzen vor.")
    pfad = [k[4] for k in teil]
    e = ergebnis(einsatz, pfad, hebel, kosten_pa)
    tr = [(teil[i + 1][0], hebel * r) for i, r in enumerate(renditen(pfad))]
    beste, schlechteste = max(tr, key=lambda x: x[1]), min(tr, key=lambda x: x[1])
    e.update({"von": teil[0][0], "bis": teil[-1][0], "daten": [k[0] for k in teil],
              "bester_tag": (beste[0], beste[1] * 100), "schlechtester_tag": (schlechteste[0], schlechteste[1] * 100),
              "index_max_dd_pct": max_drawdown(e["index"])[0]})
    return e


def historische_renditen(kerzen):
    """Tagesrenditen aus Schlusskursen (aelteste zuerst)."""
    c = [k[4] for k in kerzen]
    return renditen(c) if len(c) > 1 else []


def csv_zeilen(kopf, haupt, szen=(), pfad_tage=None):
    z = [("Eingaben", k, v) for k, v in kopf.items()]
    for k, t in (("gv", "Gewinn/Verlust €"), ("endwert", "Endwert €"), ("rendite_pct", "Rendite %"),
                 ("index_pct", "Indexveränderung %"), ("max_dd_pct", "Max. Drawdown %"),
                 ("ungehebelt_endwert", "Endwert ungehebelt €")):
        z.append(("Ergebnis", t, round(haupt[k], 4)))
    for art, e in szen:
        if e:
            z.append(("Szenario", VERLAEUFE[art], f"Index {e['index_pct']:.2f} % / ETP {e['rendite_pct']:.2f} % / "
                                                 f"{e['gv']:.2f} € / Endwert {e['endwert']:.2f} € / DD {e['max_dd_pct']:.2f} %"))
    return z
