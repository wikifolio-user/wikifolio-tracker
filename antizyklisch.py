"""Antizyklische Einstiege - Rechenkern (ohne Streamlit, ohne Netz).

Fragt: Ab wann war ein Einstieg nach dem Unterschreiten der 200-Tage-Linie historisch interessant - abhaengig von
der Dauer von Extreme Fear (CNN Fear & Greed) und vom VIX?

Daten (vom Kurs-Agenten, nur lesen): Yahoo-Tageskerzen der Cash-Indizes und des VIX (state/markt/ohlc.json, nur
abgeschlossene Handelstage), CNN Fear & Greed mit Verlauf (state/markt/sentiment.json). Keine Ersatzhistorie: Wo
Daten fehlen, gilt der Wert als unbekannt.

Alle Festlegungen stehen VOR der Auswertung in PARAM (die Oberflaeche zeigt sie an). Begriffe:
  Kreuzung        Schluss am Vortag >= SMA 200 des Vortags und Schluss heute < SMA 200 von heute (nach Handelsschluss
                  bestaetigt - es werden nur abgeschlossene Kerzen verwendet).
  Signalphase     beginnt mit einer Kreuzung und endet erst, wenn der Index PARAM["phase_ende"] Handelstage in Folge
                  auf oder ueber dem SMA 200 schliesst (ein Seitwaertsmarkt um die Linie zaehlt so nur einmal).
                  Je Signalphase und Bedingung zaehlt nur der ERSTE qualifizierte Einstieg.
  Extreme Fear    CNN-Wert < 25 (CNN: 0-24 Extreme Fear, 25-44 Fear, 45-55 Neutral, 56-75 Greed, 76-100 Extreme Greed).
  Dauer           aufeinanderfolgende bestaetigte NYSE-Handelstage in der Kategorie; Wochenenden und Boersenfeiertage
                  unterbrechen nicht. Fehlt ein erwarteter Tageswert, ist die Fortsetzung unbekannt: gezaehlt wird
                  danach nur ab dem naechsten bekannten Wert ("seit mindestens X"). Am Signaltag zaehlen nur Werte bis
                  einschliesslich dieses Tages.
  VIX hoch        Schluss >= PARAM["vix_perzentil"]-Perzentil der PARAM["vix_fenster"] VIX-Schlusskurse VOR dem
                  Signaltag (nur damals bekannte Daten). Richtung: Veraenderung ueber 5 Handelstage > 0 = steigend.
  Zeitliche Zuordnung  Signaltag d = Handelstag des Zielindex. US-Werte (VIX, Fear & Greed) vom letzten NYSE-Handelstag
                  <= d (US-Indizes: genau d; DAX: derselbe Kalendertag, NYSE-Schluss 22:00 MEZ, sonst der letzte
                  US-Handelstag davor). Einstieg zur Eroeffnung des naechsten Handelstags des Zielindex - dann sind
                  alle Signalwerte (Schlusskurse, VIX-Schluss, CNN-Tageswert) veroeffentlicht.
  Ergebnis        Rendite = Schluss h Handelstage nach dem Signaltag / Einstiegskurs - 1. Zwischenverlust = tiefstes
                  Tagestief vom Einstiegstag bis zum Ende / Einstiegskurs - 1 (hoechstens 0). Nur vollstaendige Faelle.
  Unsicherheit    95-%-Intervall nach Wilson mit effektiver Fallzahl = Faelle ohne ueberlappende Haltedauer.
  Lern/Test       erste 70 % des gemeinsamen Zeitraums (nach Signaltag) zum Finden, letzte 30 % zum Pruefen.
"""
import bisect
import datetime
import math
import statistics

import boersenkalender as BK

PARAM = {
    "sma": 200,
    "stufen": (1, 3, 5, 10),          # Tage Extreme Fear (bestaetigte Handelstage)
    "horizonte": (20, 60, 120),       # Handelstage
    "vix_perzentil": 80,              # "historisch hoch" ab diesem Perzentil
    "vix_fenster": 1260,              # 5 Jahre Handelstage vor dem Signaltag
    "vix_richtung_tage": 5,
    "phase_ende": 10,                 # Handelstage in Folge auf/ueber SMA 200 beenden eine Signalphase
    "min_lern": 8,                    # Mindestfallzahl (Signalphasen) im Lernzeitraum
    "min_test": 3,                    # und im Testzeitraum
    "vorteil_pp": 10,                 # Trefferquote mind. so viele Prozentpunkte ueber "unter SMA 200"
    "lern_anteil": 0.7,
    "ef_grenze": 25,                  # Extreme Fear: Wert < 25
    "eg_grenze": 76,                  # Extreme Greed: Wert >= 76
    "platzhalter_lauf": 10,           # >= so viele gleiche Werte in Folge = Platzhalter der Quelle (CNN bis 01/2021)
}
INDIZES = {  # Code -> (Yahoo-Symbol, Name, Boerse) - wie in Gap Analyzer / KO-Rechner
    "SPX": ("^GSPC", "S&P 500", "NYSE"), "NDX": ("^NDX", "Nasdaq 100", "NYSE"),
    "DJI": ("^DJI", "Dow Jones", "NYSE"), "DAX": ("^GDAXI", "DAX 40", "XETRA"),
}
VIX = "^VIX"
KAT_EN = {"ef": "Extreme Fear", "eg": "Extreme Greed"}
KAT_DE = {"ef": "Extreme Angst", "eg": "Extreme Gier"}


# ---------------------------------------------------------------------------------------------------- Daten
def _d(text):
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def kerzen(ohlc, symbol, boerse=None):
    """state/markt/ohlc.json -> [(datum, o, h, l, c)] aufsteigend, nur Handelstage der Boerse (falls angegeben)."""
    e = ((ohlc or {}).get("indizes") or {}).get(symbol) or {}
    aus = {}
    for k in e.get("kerzen") or []:
        try:
            d = _d(k[0])
            o, h, lo, c = (float(x) for x in k[1:5])
        except (TypeError, ValueError, IndexError):
            continue
        if d and min(o, h, lo, c) > 0 and (boerse is None or BK.ist_handelstag(boerse, d)):
            aus[d] = (d, o, h, lo, c)
    return [aus[d] for d in sorted(aus)]


def fg_verlauf(sentiment):
    """CNN-Verlauf -> ([(datum, wert)], eintrag). Nur gueltige Werte 0..100."""
    e = (((sentiment or {}).get("quellen") or {}).get("cnn")) or {}
    aus = {}
    for p in e.get("verlauf") or []:
        try:
            d, v = _d(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if d and 0 <= v <= 100:
            aus[d] = v
    return [(d, aus[d]) for d in sorted(aus)], e


def belastbar_ab(verlauf, lauf=None):
    """Erster Tag nach dem letzten Platzhalter-Lauf (>= lauf gleiche Werte in Folge). CNN liefert anfangs ueber
    Wochen 50,0 - das ist keine Messung. -> datum oder None (leer)."""
    lauf = lauf or PARAM["platzhalter_lauf"]
    if not verlauf:
        return None
    ab, n = verlauf[0][0], 1
    for i in range(1, len(verlauf)):
        n = n + 1 if verlauf[i][1] == verlauf[i - 1][1] else 1
        if n >= lauf and i + 1 < len(verlauf):
            ab = verlauf[i + 1][0]
    return ab


def us_tage(von, bis):
    return BK.handelstage_zwischen("NYSE", von, bis) if von and bis and von <= bis else []


# ---------------------------------------------------------------------------------------------------- SMA 200
def sma(schluss, n=None):
    n = n or PARAM["sma"]
    aus, summe = [None] * len(schluss), 0.0
    for i, c in enumerate(schluss):
        summe += c
        if i >= n:
            summe -= schluss[i - n]
        if i >= n - 1:
            aus[i] = summe / n
    return aus


def kreuzungen(schluss, linie):
    """Indizes i mit Schluss[i-1] >= SMA[i-1] und Schluss[i] < SMA[i]."""
    return [i for i in range(1, len(schluss)) if linie[i - 1] is not None and linie[i] is not None
            and schluss[i - 1] >= linie[i - 1] and schluss[i] < linie[i]]


def sma_status(kz):
    """Karte 200-Tage-Linie fuer die Kerzen kz -> dict."""
    n = PARAM["sma"]
    if len(kz) < n:
        return {"ok": False, "vorhanden": len(kz), "fehlend": n - len(kz),
                "datum": kz[-1][0] if kz else None, "schluss": kz[-1][4] if kz else None}
    sc = [k[4] for k in kz]
    li = sma(sc)
    kr = kreuzungen(sc, li)
    i = len(sc) - 1
    unter = sc[i] < li[i]
    # Handelstage in Folge unter der Linie (einschliesslich heute) und Beginn dieser Strecke
    j = i
    while unter and j > 0 and li[j - 1] is not None and sc[j - 1] < li[j - 1]:
        j -= 1
    seit = i - j + 1 if unter else 0
    beginn_kreuzung = unter and j in kr
    hoch = [k for k in range(1, len(sc)) if li[k - 1] is not None and sc[k - 1] < li[k - 1] and sc[k] >= li[k]]
    return {"ok": True, "datum": kz[i][0], "schluss": sc[i], "sma": li[i], "abstand": sc[i] / li[i] - 1,
            "unter": unter, "heute_unterschritten": bool(kr and kr[-1] == i), "seit": seit,
            "seit_kreuzung": beginn_kreuzung, "beginn": kz[j][0] if unter else None,
            "letzte_kreuzung_unter": kz[kr[-1]][0] if kr else None,
            "letzte_kreuzung_ueber": kz[hoch[-1]][0] if hoch else None, "vorhanden": len(sc)}


# ---------------------------------------------------------------------------------------------------- Fear & Greed
def _in_kat(v, kat):
    return v < PARAM["ef_grenze"] if kat == "ef" else v >= PARAM["eg_grenze"]


def fg_tage(verlauf, ab=None, bis=None):
    """Je NYSE-Handelstag von `ab` bis `bis`: (datum, wert oder None). Werte an Nicht-Handelstagen fallen weg."""
    werte = dict(verlauf)
    if not verlauf:
        return []
    ab = ab or verlauf[0][0]
    bis = bis or verlauf[-1][0]
    return [(d, werte.get(d)) for d in us_tage(ab, bis)]


def laufende_dauer(tage, kat):
    """-> Liste je Tag: (dauer, mindestens). dauer = bekannte aufeinanderfolgende Tage in der Kategorie bis
    einschliesslich dieses Tages (0 = nicht in der Kategorie / Wert unbekannt). mindestens = Beginn unklar
    (Luecke davor oder Beginn der belastbaren Reihe)."""
    aus, n, mind = [], 0, True
    for _, v in tage:
        if v is None:
            n, mind = 0, True                        # Fortsetzung unbekannt
        elif _in_kat(v, kat):
            n += 1
        else:
            n, mind = 0, False
        aus.append((n, mind if n else False))
    return aus


def phasen(tage, kat):
    """Abgeschnittene und vollstaendige Phasen -> [{"start","ende","dauer","beginn_unklar","ende_unklar","laufend"}]."""
    aus, cur = [], None
    vorher_unbekannt = True
    for idx, (d, v) in enumerate(tage):
        if v is not None and _in_kat(v, kat):
            if cur is None:
                cur = {"start": d, "ende": d, "dauer": 0, "beginn_unklar": vorher_unbekannt, "ende_unklar": False,
                       "laufend": False}
            cur["ende"], cur["dauer"] = d, cur["dauer"] + 1
        else:
            if cur:
                cur["ende_unklar"] = v is None
                aus.append(cur)
                cur = None
        vorher_unbekannt = v is None
    if cur:
        cur["laufend"] = True
        aus.append(cur)
    return aus


def fg_status(verlauf, ab=None):
    """Karte Fear & Greed: letzter Wert, Kategorie, Dauer von Extreme Fear und Extreme Greed."""
    if not verlauf:
        return {"ok": False}
    ab = ab or belastbar_ab(verlauf)
    d, v = verlauf[-1]
    tage = fg_tage(verlauf, ab, d)
    aus = {"ok": True, "datum": d, "wert": v, "belastbar_ab": ab, "handelstag": BK.ist_handelstag("NYSE", d)}
    for kat in ("ef", "eg"):
        ph = phasen(tage, kat)
        fertig = [p for p in ph if not p["laufend"] and not p["beginn_unklar"] and not p["ende_unklar"]]
        median = statistics.median([p["dauer"] for p in fertig]) if fertig else None
        lauf = ph[-1] if ph and ph[-1]["laufend"] else None
        letzte = next((p for p in reversed(ph) if not p["laufend"]), None)
        aus[kat] = {"laufend": lauf, "letzte": letzte, "median": median, "anzahl_fertig": len(fertig)}
    return aus


# ---------------------------------------------------------------------------------------------------- VIX
def vix_reihe(vk):
    """VIX-Kerzen (nur NYSE-Handelstage) -> je Tag {"datum","schluss","aend5","aend5_pct","perzentil"}.
    Perzentil = Anteil der PARAM["vix_fenster"] Schlusskurse VOR dem Tag, die <= dem Schluss sind (x 100)."""
    w, r = PARAM["vix_fenster"], PARAM["vix_richtung_tage"]
    sc = [k[4] for k in vk]
    fenster, aus = [], []
    for i, c in enumerate(sc):
        pz = 100.0 * bisect.bisect_right(fenster, c) / w if len(fenster) >= w else None
        a = c - sc[i - r] if i >= r else None
        aus.append({"datum": vk[i][0], "schluss": c, "aend5": a, "aend5_pct": c / sc[i - r] - 1 if i >= r else None,
                    "perzentil": pz})
        bisect.insort(fenster, c)
        if len(fenster) > w:
            fenster.pop(bisect.bisect_left(fenster, sc[i - w]))
    return aus


def richtung(aend):
    if aend is None:
        return None
    return "steigend" if aend > 0 else "fallend"


# ---------------------------------------------------------------------------------------------------- Zeitreihe
def tabelle(code, ohlc, sentiment):
    """Gemeinsame Tagesreihe des Zielindex mit den zum Signaltag bekannten US-Werten -> dict.
    zeilen: [{"datum","o","h","l","c","sma","unter","us_tag","fg","ef","ef_mind","vix","vix_pz","vix_aend5",
    "vix_dir"}], dazu Zeitraeume und Datenstaende."""
    symbol, name, boerse = INDIZES[code]
    kz = kerzen(ohlc, symbol, boerse)
    vk = kerzen(ohlc, VIX, "NYSE")
    fv, fg_e = fg_verlauf(sentiment)
    ab = belastbar_ab(fv)
    vr = {x["datum"]: x for x in vix_reihe(vk)}
    fg_tag = fg_tage(fv, ab, fv[-1][0]) if fv else []
    ef = dict(zip([d for d, _ in fg_tag], laufende_dauer(fg_tag, "ef")))
    fgw = dict(fg_tag)
    us_liste = sorted(set(d for d, _ in fg_tag) | set(vr))
    sc = [k[4] for k in kz]
    li = sma(sc)
    zeilen = []
    for i, (d, o, h, lo, c) in enumerate(kz):
        j = bisect.bisect_right(us_liste, d) - 1
        u = us_liste[j] if j >= 0 else None
        # letzter NYSE-Handelstag <= d (an der NYSE muss d selbst Handelstag sein, sonst der Tag davor)
        if u is not None and boerse == "NYSE" and u != d:
            u = None
        v = vr.get(u) or {}
        e = ef.get(u)
        zeilen.append({"datum": d, "o": o, "h": h, "l": lo, "c": c, "sma": li[i],
                       "unter": li[i] is not None and c < li[i], "us_tag": u,
                       "fg": fgw.get(u), "ef": e[0] if e else None, "ef_mind": e[1] if e else None,
                       "vix": v.get("schluss"), "vix_pz": v.get("perzentil"), "vix_aend5": v.get("aend5"),
                       "vix_dir": richtung(v.get("aend5"))})
    # gemeinsamer Zeitraum: SMA, belastbares Fear & Greed und VIX-Perzentil vorhanden
    gem = [z["datum"] for z in zeilen if z["sma"] is not None and z["fg"] is not None and z["vix_pz"] is not None]
    return {"code": code, "name": name, "boerse": boerse, "symbol": symbol, "zeilen": zeilen, "kerzen": kz,
            "vix": vk, "fg": fv, "fg_eintrag": fg_e, "fg_ab": ab,
            "gemeinsam": (gem[0], gem[-1]) if gem else None,
            "stand": {"index": kz[-1][0] if kz else None, "vix": vk[-1][0] if vk else None,
                      "fg": fv[-1][0] if fv else None}}


# ---------------------------------------------------------------------------------------------------- Bedingungen
def bedingungen():
    """Reihenfolge der untersuchten Bedingungen -> [(id, Beschreibung, pruef(z) oder None fuer A)]."""
    aus = [("A", "Beliebiger Handelstag", None),
           ("B", "Index unter SMA 200", lambda z: z["unter"])]
    for k in PARAM["stufen"]:
        aus.append((f"C{k}", f"unter SMA 200 + Extreme Fear seit ≥ {k} Tag{'en' if k > 1 else ''}",
                    lambda z, k=k: z["unter"] and (z["ef"] or 0) >= k))
    for k in PARAM["stufen"]:
        for r in ("steigend", "fallend"):
            aus.append((f"D{k}{r[0]}", f"wie C{k} + VIX hoch, {r}",
                        lambda z, k=k, r=r: z["unter"] and (z["ef"] or 0) >= k and z["vix_pz"] is not None
                        and z["vix_pz"] >= PARAM["vix_perzentil"] and z["vix_dir"] == r))
    return aus


def signalphasen(zeilen, von=None):
    """Signalphasen [(start_index, ende_index)] - Start = Kreuzung unter den SMA 200 (ab `von`), Ende nach
    PARAM["phase_ende"] Tagen in Folge auf/ueber dem SMA (ende_index = letzter Tag der Phase)."""
    aus, start, ueber = [], None, 0
    for i, z in enumerate(zeilen):
        if z["sma"] is None:
            continue
        vorher = zeilen[i - 1] if i else None
        if start is None:
            if (vorher and vorher["sma"] is not None and vorher["c"] >= vorher["sma"] and z["unter"]
                    and (von is None or z["datum"] >= von)):
                start, ueber = i, 0
            continue
        ueber = 0 if z["unter"] else ueber + 1
        if ueber >= PARAM["phase_ende"]:
            aus.append((start, i))
            start = None
    if start is not None:
        aus.append((start, len(zeilen) - 1))
    return aus


def einstiege(zeilen, phasen_liste, pruef):
    """Erster qualifizierter Signaltag je Phase -> [index]."""
    aus = []
    for a, b in phasen_liste:
        for i in range(a, b + 1):
            if pruef(zeilen[i]):
                aus.append(i)
                break
    return aus


def ergebnis(zeilen, i, h):
    """Signaltag i, Horizont h -> {"rendite","verlust","einstieg_datum","einstieg"} oder None (unvollstaendig)."""
    if i + h >= len(zeilen) or i + 1 >= len(zeilen):
        return None
    einstieg = zeilen[i + 1]["o"]
    tief = min(z["l"] for z in zeilen[i + 1:i + h + 1])
    return {"rendite": zeilen[i + h]["c"] / einstieg - 1, "verlust": min(0.0, tief / einstieg - 1),
            "einstieg": einstieg, "einstieg_datum": zeilen[i + 1]["datum"], "ende_datum": zeilen[i + h]["datum"]}


def wilson(treffer, n, z=1.96):
    if not n:
        return None, None
    p = treffer / n
    nenner = 1 + z * z / n
    mitte = (p + z * z / (2 * n)) / nenner
    breite = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / nenner
    return max(0.0, mitte - breite), min(1.0, mitte + breite)


def effektiv(indizes, h):
    """Faelle ohne ueberlappende Haltedauer (gierig nach Datum)."""
    n, frei_ab = 0, -1
    for i in sorted(indizes):
        if i >= frei_ab:
            n += 1
            frei_ab = i + h + 1
    return n


def statistik(zeilen, indizes, h):
    faelle = [(i, ergebnis(zeilen, i, h)) for i in indizes]
    faelle = [(i, e) for i, e in faelle if e]
    n = len(faelle)
    if not n:
        return {"n": 0, "n_eff": 0, "quote": None, "ki": (None, None), "median": None, "verlust": None, "faelle": []}
    treffer = sum(1 for _, e in faelle if e["rendite"] > 0)
    n_eff = max(1, effektiv([i for i, _ in faelle], h))
    q = treffer / n
    return {"n": n, "n_eff": n_eff, "treffer": treffer, "quote": q, "ki": wilson(q * n_eff, n_eff),
            "median": statistics.median(e["rendite"] for _, e in faelle),
            "verlust": statistics.median(e["verlust"] for _, e in faelle), "faelle": faelle}


def teilung(gemeinsam):
    a, b = gemeinsam
    return a + datetime.timedelta(days=round((b - a).days * PARAM["lern_anteil"]))


def auswertung(t):
    """Alle Bedingungen x Horizonte x Zeitraeume (gesamt/lern/test) im gemeinsamen Zeitraum -> dict."""
    zeilen = t["zeilen"]
    if not t["gemeinsam"]:
        return {"ok": False, "grund": "Kein gemeinsamer Zeitraum von Index, Fear & Greed und VIX."}
    von, bis = t["gemeinsam"]
    grenze = teilung(t["gemeinsam"])
    im = [i for i, z in enumerate(zeilen) if von <= z["datum"] <= bis]
    ph = [(a, b) for a, b in signalphasen(zeilen, von) if zeilen[a]["datum"] <= bis]
    erg = {}
    for bid, text, pruef in bedingungen():
        idx = im if pruef is None else einstiege(zeilen, ph, pruef)
        for h in PARAM["horizonte"]:
            for teil, f in (("gesamt", lambda d: True), ("lern", lambda d: d < grenze), ("test", lambda d: d >= grenze)):
                erg[(bid, h, teil)] = statistik(zeilen, [i for i in idx if f(zeilen[i]["datum"])], h)
    return {"ok": True, "von": von, "bis": bis, "grenze": grenze, "phasen": ph, "erg": erg,
            "bedingungen": [(b, t_) for b, t_, _ in bedingungen()]}


def vergleich_von(bid):
    return "A" if bid == "B" else "B"


def vorteil(a, bid, h, teil="lern"):
    """Erfuellt Bedingung bid im Zeitraum das vorab festgelegte Kriterium gegenueber B? -> (ja, grund)."""
    s, b = a["erg"][(bid, h, teil)], a["erg"][("B", h, teil)]
    if s["n"] < PARAM["min_lern"] or b["n"] < PARAM["min_lern"]:
        return False, "zu wenige Fälle"
    diff = (s["quote"] - b["quote"]) * 100
    if diff < PARAM["vorteil_pp"]:
        return False, f"Differenz {diff:+.0f} Pp."
    if s["median"] < b["median"]:
        return False, "Medianrendite niedriger"
    return True, ""


def bestaetigt(a, bid, h):
    s, b = a["erg"][(bid, h, "test")], a["erg"][("B", h, "test")]
    if s["n"] < PARAM["min_test"] or not b["n"]:
        return None                                       # nicht pruefbar
    return s["quote"] > b["quote"]


def einordnung(a, h):
    """Dashboard-Aussage fuer Horizont h -> {"zustand","bid","gruende",...}.
    Zustaende: auffaellig / kein_vorteil / unklar."""
    if not a.get("ok"):
        return {"zustand": "unklar", "grund": a.get("grund", "keine Daten")}
    b_l, b_t = a["erg"][("B", h, "lern")], a["erg"][("B", h, "test")]
    if b_l["n"] < PARAM["min_lern"] or b_t["n"] < PARAM["min_test"]:
        return {"zustand": "unklar", "grund": f"Zu wenige Unterschreitungen der 200-Tage-Linie (Lernzeitraum "
                                              f"{b_l['n']}, Testzeitraum {b_t['n']} – nötig {PARAM['min_lern']}/"
                                              f"{PARAM['min_test']})."}
    kandidaten = [b for b, _ in a["bedingungen"] if b[0] in "CD"]
    pruefbar, treffer, nur_lern = [], [], []
    for bid in kandidaten:
        ok, _ = vorteil(a, bid, h)
        best = bestaetigt(a, bid, h)
        if a["erg"][(bid, h, "lern")]["n"] >= PARAM["min_lern"] and best is not None:
            pruefbar.append(bid)
        if ok and best:
            treffer.append(bid)
        elif ok:
            nur_lern.append(bid)
    stufe = lambda b: (int("".join(c for c in b[1:] if c.isdigit())), b[0] != "C")     # noqa: E731
    if treffer:
        bid = min(treffer, key=stufe)
        return {"zustand": "auffaellig", "bid": bid}
    if not pruefbar:
        return {"zustand": "unklar", "grund": "Keine untersuchte Stufe erreicht die Mindestfallzahl in Lern- und "
                                              "Testzeitraum.", "nur_lern": nur_lern}
    return {"zustand": "kein_vorteil", "pruefbar": pruefbar, "nur_lern": nur_lern}


def aktuell_erfuellt(t):
    """Welche Bedingungen erfuellt der letzte Tag (ohne die Phasenregel - die gilt nur fuer die Zaehlung)?"""
    if not t["zeilen"]:
        return {}
    z = t["zeilen"][-1]
    return {bid: bool(pruef(z)) for bid, _, pruef in bedingungen() if pruef}
