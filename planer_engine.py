"""
Portfolio-Planer - RECHEN-ENGINE (reine Funktionen, keine Oberflaeche, kein Netz).

Alle Funktionen arbeiten auf dem Modell-Dict aus planer_daten.seed_modell()
und sind ohne Streamlit testbar (test_planer.py).

Bausteine:
  Grundformeln        required_cagr, future_value, runden_ungefaehr
  Assumption Engine   rendite_fuer, alle_renditen  (aktive Methode, Fallbacks, Herkunft)
  Portfolio           gewichte, normalisieren, projektion (monatlich, Sparrate,
                      Rebalancing, Stresspfad, Nachkaufreserve)
  Szenarien           szenario_vergleich, max_modell_verlust
  Sensitivitaet       tornado, gruppen_sensitivitaet
  Datenqualitaet      confidence_score, bias_hinweise
  Fundamental Score   fundamental_score, korb_gewichte, korb_fundamental_rendite
  Risiko              risiko_kennzahlen, effektive_exposure
  Optimizer           optimiere (eigener Simplex-LP-Loeser, siehe _simplex)
"""
import math

import planer_daten as D

# ===========================================================================
# Grundformeln
# ===========================================================================
def required_cagr(start, ziel, jahre):
    """(ziel/start)^(1/jahre) - 1"""
    if not start or start <= 0 or not jahre or jahre <= 0 or ziel is None or ziel <= 0:
        return None
    return (ziel / start) ** (1.0 / jahre) - 1.0


def future_value(kapital, rendite, jahre, sparrate_monat=0.0):
    """Endwert bei jaehrlicher Rendite (monatlich verzinst) und Sparrate am Monatsende."""
    fv = kapital * (1.0 + rendite) ** jahre
    if sparrate_monat:
        rm = (1.0 + rendite) ** (1.0 / 12.0)
        n = int(round(jahre * 12))
        fv += sparrate_monat * sum(rm ** (n - k) for k in range(1, n + 1))
    return fv


def erforderliche_rendite(start, ziel, jahre, sparrate_monat=0.0):
    """Benoetigte Jahresrendite; mit Sparrate per Bisektion, ohne = required_cagr."""
    if not sparrate_monat:
        return required_cagr(start, ziel, jahre)
    if not jahre or jahre <= 0:
        return None
    if future_value(start, 0.0, jahre, sparrate_monat) >= ziel:
        lo, hi = -0.99, 0.0
    else:
        lo, hi = 0.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if future_value(start, mid, jahre, sparrate_monat) >= ziel:
            hi = mid
        else:
            lo = mid
    return hi


def runden_ungefaehr(wert, stellen=3):
    """Keine falsche Praezision: auf 'stellen' signifikante Ziffern runden
    (100.013 -> 100.000, 57.684 -> 57.700)."""
    if wert is None or wert == 0:
        return wert
    grad = int(math.floor(math.log10(abs(wert))))
    faktor = 10 ** (grad - stellen + 1)
    return round(wert / faktor) * faktor


def _typ(asset):
    return D.KATEGORIEN.get(asset["category"], {}).get("typ", "index")


def aktive_assets(modell):
    return [a for a in modell["assets"] if a.get("enabled")]


# ===========================================================================
# Gewichte
# ===========================================================================
def gewichte_summe(modell):
    return sum(float(a.get("targetWeight") or 0) for a in aktive_assets(modell))


def normalisieren(modell):
    """Skaliert die Gewichte der aktiven Assets auf genau 100 %."""
    summe = gewichte_summe(modell)
    if summe <= 0:
        return modell
    for a in aktive_assets(modell):
        a["targetWeight"] = round(float(a.get("targetWeight") or 0) * 100.0 / summe, 4)
    return modell


def gewichte(modell):
    """{asset_id: Anteil 0..1} der aktiven Assets, auf 1 normiert (fuer die
    Rechnung - die Anzeige zeigt die Abweichung von 100 % separat an)."""
    summe = gewichte_summe(modell)
    if summe <= 0:
        return {}
    return {a["id"]: float(a.get("targetWeight") or 0) / summe for a in aktive_assets(modell)}


# ===========================================================================
# Assumption Engine
# ===========================================================================
def annahme(modell, asset_id, quelle):
    for a in modell["annahmen"]:
        if a["assetId"] == asset_id and a["sourceType"] == quelle and a.get("value") is not None:
            return a
    return None


def setze_annahme(modell, asset_id, quelle, wert, notiz=None, source="User assumption", stand=None,
                  beobachtung=None, auto=False):
    """Legt eine Annahme an oder aktualisiert sie (eine je Asset und Quelle).
    auto=True: Wert wird automatisch aus der Kurshistorie nachgefuehrt
    (siehe annahmen_aus_historie); jede eigene Eingabe setzt auto=False."""
    for a in modell["annahmen"]:
        if a["assetId"] == asset_id and a["sourceType"] == quelle:
            a["value"] = wert
            a["auto"] = bool(auto)
            if notiz is not None:
                a["notes"] = notiz
            a["source"] = source
            if stand:
                a["dataDate"] = stand
            if beobachtung is not None:
                a["observationYears"] = beobachtung
            return a
    neu = {"assetId": asset_id, "value": wert, "sourceType": quelle, "observationYears": beobachtung,
           "dataDate": stand, "source": source, "notes": notiz or "", "auto": bool(auto)}
    modell["annahmen"].append(neu)
    return neu


HIST_REIHENFOLGE = (("historical5Y", "5 J. p.a."), ("historical3Y", "3 J. p.a."), ("gesamt_cagr", "seit Start p.a."),
                    ("historical1Y", "1 J."))


def ist_rendite(h, methode=None):
    """Tatsaechliche Rendite aus der Kurshistorie: 5 J. p.a., sonst 3 J., sonst
    seit Start (ab 1 Jahr Historie), sonst 1 J. Bei Methode "Historische 10
    Jahre" zuerst 10 J. -> (wert, bezeichnung) oder (None, None)"""
    h = h or {}
    reihenfolge = HIST_REIHENFOLGE
    if methode == "historical10Y":
        reihenfolge = (("historical10Y", "10 J. p.a."),) + reihenfolge
    for feld, text in reihenfolge:
        if h.get(feld) is not None:
            return h[feld], text
    # Historie juenger als 1 Jahr: tatsaechliche Rendite seit Start, NICHT
    # hochgerechnet (eine Annualisierung weniger Monate wuerde Werte weit ueber
    # 100 % p.a. erzeugen). Ab 1 Monat Historie.
    if h.get("seit_start") is not None and (h.get("jahre") or 0) >= 1.0 / 12.0:
        mon = max(1, int(round(float(h["jahre"]) * 12)))
        return h["seit_start"], f"seit Start, {mon} Mon."
    return None, None


# Standardwert je Kategorie, wenn es gar keine Kursdaten gibt (Instrument nicht
# gefunden / zu jung). Neutraler Platzhalter nahe am langfristigen Aktienmittel -
# wird automatisch ersetzt, sobald Kursdaten da sind.
STANDARD_RENDITE = {"global_equity": 0.07, "regional_equity": 0.07, "factor": 0.08, "small_cap": 0.07,
                    "technology": 0.10, "semiconductor": 0.12, "sector": 0.07, "mining": 0.07,
                    "single_stock": 0.08, "stock_basket": 0.08, "wikifolio": 0.08, "leveraged_etf": 0.10,
                    "crypto": 0.10}


def standard_rendite(asset):
    return STANDARD_RENDITE.get(asset.get("category"), 0.07)


def _szenario_um(wert, sz, regel):
    """Bear/Bull um einen Basiswert (vorzeichenrichtig, auch bei negativer Basis)."""
    if sz == "bear":
        return wert - (1.0 - regel["bear_faktor"]) * abs(wert)
    if sz == "bull":
        return wert + (regel["bull_faktor"] - 1.0) * abs(wert)
    return wert


def rendite_fuer(modell, asset, historie=None, methode=None, szenario=None):
    """Rendite eines Assets fuer die aktive Methode.
    -> (wert oder None, herkunft-dict, hinweis oder None)

    historie = {asset_id: {"historical5Y", "historical10Y", "fundamentalModel", ...}}
    (Historical Layer, zur Laufzeit aus echten Daten). Fehlt der Wert der
    gewaehlten Methode, gilt die eigene Annahme - mit Hinweis."""
    methode = methode or modell["rahmen"]["methode"]
    historie = historie or {}
    aid = asset["id"]
    eigene = annahme(modell, aid, "manualScenario")
    if _typ(asset) == "cash":
        return (eigene["value"] if eigene else 0.0), (eigene or {"sourceType": "manualScenario"}), None

    # Ist-Werte statt Annahme (Standard fuer Wikifolios): in JEDER Methode die
    # tatsaechliche Rendite laut Kurshistorie; Bear/Bull nach der Szenario-Regel.
    hinweis_ist = None
    if asset.get("renditequelle") == "historisch":
        h = historie.get(aid) or {}
        wert, text = ist_rendite(h, methode)
        if wert is not None:
            if methode == "szenario":
                sz = szenario or modell["rahmen"].get("szenario", "base")
                wert = _szenario_um(wert, sz, modell.get("szenario_regel", D.SZENARIO_REGEL))
            return wert, {"sourceType": "historisch", "source": f"Kurshistorie ({text})",
                          "dataDate": h.get("stand")}, None
        hinweis_ist = "Keine Kurshistorie (≥ 1 Jahr) – Annahme verwendet"

    if methode in ("historical5Y", "historical10Y", "fundamentalModel"):
        h = (historie.get(aid) or {}).get(methode)
        if h is not None:
            return h, {"sourceType": methode, "source": (historie.get(aid) or {}).get("quelle", "Historie"),
                       "dataDate": (historie.get(aid) or {}).get("stand")}, None
        if eigene:
            return eigene["value"], eigene, f"Keine Daten für „{D.METHODEN[methode]}“ – eigene Annahme verwendet"
        return None, {}, "Keine Annahme vorhanden"

    if methode == "szenario":
        sz = szenario or modell["rahmen"].get("szenario", "base")
        explizit = annahme(modell, aid, sz)
        if explizit:
            return explizit["value"], explizit, None
        basis = annahme(modell, aid, "base") or eigene
        if not basis:
            return None, {}, "Keine Annahme vorhanden"
        regel = modell.get("szenario_regel", D.SZENARIO_REGEL)
        if sz == "bear":
            return basis["value"] * regel["bear_faktor"], {"sourceType": "bear", "source": "Standardregel"}, \
                regel["text"]
        if sz == "bull":
            return basis["value"] * regel["bull_faktor"], {"sourceType": "bull", "source": "Standardregel"}, \
                regel["text"]
        return basis["value"], basis, hinweis_ist

    if eigene:
        return eigene["value"], eigene, hinweis_ist
    return None, {}, "Keine Annahme vorhanden – bitte eintragen"


def netto_rendite(asset, brutto, kosten_an):
    """Kosten optional: laufende Kosten (TER) und Performance Fee auf den Gewinn."""
    if brutto is None or not kosten_an:
        return brutto
    r = (1.0 + brutto) * (1.0 - (asset.get("expenseRatio") or 0.0)) - 1.0
    pf = asset.get("performanceFee") or 0.0
    if r > 0 and pf:
        r *= (1.0 - pf)
    return r


def alle_renditen(modell, historie=None, methode=None, szenario=None):
    """{asset_id: {"brutto", "netto", "herkunft", "hinweis"}} fuer alle aktiven Assets."""
    kosten = modell["rahmen"].get("kosten_beruecksichtigen")
    aus = {}
    for a in aktive_assets(modell):
        wert, herkunft, hinweis = rendite_fuer(modell, a, historie, methode, szenario)
        aus[a["id"]] = {"brutto": wert, "netto": netto_rendite(a, wert, kosten), "herkunft": herkunft,
                        "hinweis": hinweis}
    return aus


def rendite_map(renditen):
    """{id: netto} - fehlende Annahmen zaehlen als 0 % (und werden angezeigt)."""
    return {k: (v["netto"] if v["netto"] is not None else 0.0) for k, v in renditen.items()}


# ===========================================================================
# Stresspfad (Marktindex je Monat, Start 1,0)
# ===========================================================================
def stress_pfad(stress, monate):
    """Marktpfad OHNE Trend: 1,0 -> Einbruch -> Rueckkehr auf 1,0.
    Der Trend steckt in den Renditeannahmen der Assets; der Pfad wirkt als
    zusaetzlicher Schock (und Erholung)."""
    pfad = [1.0]
    tief = 1.0 - stress["einbruch"] / 100.0
    s, d, e = int(stress["start"]), max(int(stress["dauer"]), 1), max(int(stress["erholung"]), 1)
    for m in range(1, monate + 1):
        if m < s:
            wert = 1.0
        elif m < s + d:
            wert = 1.0 - (1.0 - tief) * (m - s + 1) / d
        elif m < s + d + e:
            wert = tief + (1.0 - tief) * (m - s - d + 1) / e
        else:
            wert = 1.0
        pfad.append(wert)
    return pfad


def _beta(asset, stress):
    typ = _typ(asset)
    if typ == "cash":
        return 0.0
    if typ == "wikifolio":
        return float(stress.get("wikifolio_beta", 1.0))
    return float(asset.get("leverage") or 1.0)


# ===========================================================================
# Projektion (monatlich)
# ===========================================================================
REBAL_MONATE = {"jaehrlich": 12, "halbjaehrlich": 6, "quartalsweise": 3}


def projektion(modell, renditen, *, jahre=None, sparrate=None, rebalancing=None, stress=None,
               nachkauf=None, scores=None, confidences=None):
    """Monatliche Modellrechnung.

    renditen   {asset_id: jahresrendite (netto)}
    rebalancing {"art": keins|jaehrlich|halbjaehrlich|quartalsweise|schwelle, "schwelle_relativ": %}
                Die Nachkaufreserve ist vom Rebalancing ausgenommen (sie soll ja
                gerade fuer Rueckschlaege bereitstehen).
    stress     Stress-Parameter -> Marktschock nach stress_pfad (sonst glatte Rechnung)
    nachkauf   Tranchenregeln -> Einsatz der Reserve bei Markt-Drawdowns (nur mit stress)
    Rueckgabe: dict mit Monats-/Jahreswerten, Endwert, Beitraegen je Asset, Nachkaeufen."""
    rahmen = modell["rahmen"]
    jahre = int(jahre or rahmen["horizont_jahre"])
    sparrate = float(rahmen.get("sparrate_monat") or 0.0) if sparrate is None else float(sparrate)
    rebalancing = rebalancing or {"art": "keins"}
    w = gewichte(modell)
    assets = {a["id"]: a for a in aktive_assets(modell)}
    start = float(rahmen["startkapital"])
    monate = jahre * 12
    werte = {i: start * w[i] for i in w}
    eingezahlt = {i: start * w[i] for i in w}
    reserve_ids = [i for i in w if _typ(assets[i]) == "cash"]
    risiko_ids = [i for i in w if i not in reserve_ids]
    ziel_risiko = {i: w[i] for i in risiko_ids}
    summe_risiko_ziel = sum(ziel_risiko.values()) or 1.0
    faktor = {i: (1.0 + renditen.get(i, 0.0)) ** (1.0 / 12.0) for i in w}
    pfad = stress_pfad(stress, monate) if stress else None
    reserve_start = sum(werte[i] for i in reserve_ids)
    tranchen_offen = list(enumerate((nachkauf or {}).get("tranchen", []))) if (stress and nachkauf) else []
    nachkaeufe = []
    verlauf = [sum(werte.values())]
    verlauf_asset = {i: [werte[i]] for i in w}
    markt_hoch = 1.0
    rebalancings = 0

    for m in range(1, monate + 1):
        # 1) Wachstum laut Annahme (+ optionaler Marktschock)
        schock = pfad[m] / pfad[m - 1] if pfad else 1.0
        for i in w:
            f = faktor[i]
            if pfad and schock != 1.0:
                f *= max(1.0 + _beta(assets[i], stress) * (schock - 1.0), 0.0)
            werte[i] *= f
        # 2) Sparrate nach Zielgewicht
        if sparrate:
            for i in w:
                werte[i] += sparrate * w[i]
                eingezahlt[i] += sparrate * w[i]
        # 3) Nachkaufreserve (nur im Stresspfad): Tranchen bei Markt-Drawdown
        if pfad:
            markt_hoch = max(markt_hoch, pfad[m])
            dd = (pfad[m] / markt_hoch - 1.0) * 100.0
            for idx, tr in list(tranchen_offen):
                if dd <= tr["drawdown"] + 1e-9:
                    betrag = min(reserve_start * tr["anteil"], sum(werte[i] for i in reserve_ids))
                    if betrag <= 0:
                        tranchen_offen.remove((idx, tr))
                        continue
                    ziele = nachkauf_ziele(modell, nachkauf, werte, ziel_risiko, scores, confidences)
                    for i in reserve_ids:            # Reserve anteilig entnehmen
                        anteil = werte[i] / (sum(werte[r] for r in reserve_ids) or 1.0)
                        werte[i] -= betrag * anteil
                    for i, a in ziele.items():
                        werte[i] += betrag * a
                    nachkaeufe.append({"monat": m, "drawdown": round(dd, 1), "betrag": betrag,
                                       "ziele": {i: round(a * betrag, 2) for i, a in ziele.items()}})
                    tranchen_offen.remove((idx, tr))
        # 4) Rebalancing (ohne Reserve)
        art = rebalancing.get("art", "keins")
        faellig = False
        if art in REBAL_MONATE and m % REBAL_MONATE[art] == 0:
            faellig = True
        elif art == "schwelle" and risiko_ids:
            band = float(rebalancing.get("schwelle_relativ", 25.0)) / 100.0
            summe_r = sum(werte[i] for i in risiko_ids) or 1.0
            for i in risiko_ids:
                ziel = ziel_risiko[i] / summe_risiko_ziel
                ist = werte[i] / summe_r
                if ziel > 0 and (ist < ziel * (1 - band) or ist > ziel * (1 + band)):
                    faellig = True
                    break
        if faellig and risiko_ids:
            summe_r = sum(werte[i] for i in risiko_ids)
            for i in risiko_ids:
                werte[i] = summe_r * ziel_risiko[i] / summe_risiko_ziel
            rebalancings += 1
        verlauf.append(sum(werte.values()))
        for i in w:
            verlauf_asset[i].append(werte[i])

    endwert = verlauf[-1]
    gesamt_eingezahlt = start + sparrate * monate
    return {
        "monatswerte": verlauf, "asset_verlauf": verlauf_asset,
        "jahreswerte": [verlauf[j * 12] for j in range(jahre + 1)],
        "endwert": endwert, "eingezahlt": gesamt_eingezahlt,
        "endwerte_asset": dict(werte),
        "beitraege": {i: werte[i] - eingezahlt[i] for i in w},     # Gewinn je Asset
        "nachkaeufe": nachkaeufe, "rebalancings": rebalancings,
        "max_verlust_pfad": _max_verlust(verlauf),
    }


def _max_verlust(verlauf):
    hoch, tief = verlauf[0], 0.0
    for v in verlauf:
        hoch = max(hoch, v)
        tief = min(tief, v / hoch - 1.0)
    return tief * 100.0


def nachkauf_ziele(modell, nachkauf, werte, ziel_risiko, scores=None, confidences=None):
    """{asset_id: anteil} fuer eine Tranche. Einzelwerte/Aktienkorb nur, wenn der
    Fundamental Score die Mindestschwelle erreicht - ein starker Kursrueckgang
    allein ist kein Nachkaufgrund."""
    scores = scores or {}
    confidences = confidences or {}
    assets = {a["id"]: a for a in aktive_assets(modell)}
    kandidaten = {i: z for i, z in ziel_risiko.items() if z > 0}

    def erlaubt(i):
        if not nachkauf.get("min_score_aktiv"):
            return True
        if _typ(assets[i]) != "aktie":
            return True
        s = scores.get(i)
        return s is not None and s >= nachkauf.get("min_score", 70)

    kandidaten = {i: z for i, z in kandidaten.items() if erlaubt(i)}
    if not kandidaten:
        return {}
    art = nachkauf.get("ziel", "proportional")
    if art == "asset" and nachkauf.get("ziel_asset") in assets and erlaubt(nachkauf["ziel_asset"]):
        return {nachkauf["ziel_asset"]: 1.0}
    if art == "allworld":
        aw = [i for i in kandidaten if assets[i]["category"] == "global_equity"]
        if aw:
            return {aw[0]: 1.0}
    if art == "untergewichtet":
        summe = sum(werte[i] for i in ziel_risiko) or 1.0
        summe_z = sum(ziel_risiko.values()) or 1.0
        abw = {i: werte[i] / summe - ziel_risiko[i] / summe_z for i in kandidaten}
        return {min(abw, key=abw.get): 1.0}
    if art == "bester_score":
        mit = {i: scores[i] for i in kandidaten if scores.get(i) is not None}
        if mit:
            return {max(mit, key=mit.get): 1.0}
    if art == "hoechste_confidence":
        mit = {i: confidences[i] for i in kandidaten if confidences.get(i) is not None}
        if mit:
            return {max(mit, key=mit.get): 1.0}
    summe = sum(kandidaten.values())
    return {i: z / summe for i, z in kandidaten.items()}


# ===========================================================================
# Zusammenfassung / Szenarien
# ===========================================================================
def zusammenfassung(modell, renditen_netto, **kw):
    rahmen = modell["rahmen"]
    proj = projektion(modell, renditen_netto, **kw)
    ohne_sparen = projektion(modell, renditen_netto, sparrate=0.0, **{k: v for k, v in kw.items() if k != "sparrate"}) \
        if rahmen.get("sparrate_monat") else proj
    jahre = rahmen["horizont_jahre"]
    start, ziel = rahmen["startkapital"], rahmen["zielvermoegen"]
    return {
        "projektion": proj,
        "endwert": proj["endwert"],
        "erforderliche_cagr": erforderliche_rendite(start, ziel, jahre, rahmen.get("sparrate_monat") or 0.0),
        "modell_cagr": required_cagr(start, ohne_sparen["endwert"], jahre),
        "differenz": proj["endwert"] - ziel,
        "multiplikator": proj["endwert"] / proj["eingezahlt"] if proj["eingezahlt"] else None,
        "ziel_erreicht": proj["endwert"] >= ziel,
    }


def max_modell_verlust(modell, historie=None):
    """Gleichzeitiger Drawdown aller Bausteine (Worst-Case-Naeherung):
    sum(gewicht * drawdown). Drawdown aus der Historie, sonst Standard je Typ."""
    historie = historie or {}
    w = gewichte(modell)
    assets = {a["id"]: a for a in aktive_assets(modell)}
    summe = 0.0
    for i, g in w.items():
        dd = (historie.get(i) or {}).get("maxdd")
        if dd is None:
            dd = D.DRAWDOWN_STANDARD.get(_typ(assets[i]), -35.0)
        summe += g * max(dd, -100.0)
    return summe                    # in % (negativ)


def szenario_vergleich(modell, historie=None, **kw):
    """Bear / Base / Bull / Custom mit Endwert, CAGR, Zielerreichung, Beitraegen."""
    rahmen = modell["rahmen"]
    ergebnis = {}
    for sz in ("bear", "base", "bull", "custom"):
        r = alle_renditen(modell, historie, methode="szenario", szenario=sz)
        proj = projektion(modell, rendite_map(r), **kw)
        stress_proj = projektion(modell, rendite_map(r), stress=modell["stress"], **kw)
        gesamt_gewinn = sum(v for v in proj["beitraege"].values()) or 1.0
        ergebnis[sz] = {
            "endwert": proj["endwert"], "jahreswerte": proj["jahreswerte"],
            "cagr": required_cagr(rahmen["startkapital"], proj["endwert"], rahmen["horizont_jahre"])
            if not rahmen.get("sparrate_monat") else None,
            "ziel_erreicht": proj["endwert"] >= rahmen["zielvermoegen"],
            "abstand": proj["endwert"] - rahmen["zielvermoegen"],
            "anteil_endwert": {i: v / proj["endwert"] for i, v in proj["endwerte_asset"].items()},
            "anteil_gewinn": {i: v / gesamt_gewinn for i, v in proj["beitraege"].items()},
            "max_verlust_stress": stress_proj["max_verlust_pfad"],
            "renditen": {i: v["netto"] for i, v in r.items()},
        }
    return ergebnis


# ===========================================================================
# Sensitivitaet
# ===========================================================================
def tornado(modell, renditen_netto, delta=0.10, **kw):
    """Endwert, wenn die Annahme EINES Assets um +/- delta (Prozentpunkte)
    abweicht. Sortiert nach Spannweite - zeigt, welche Annahme das Ergebnis treibt."""
    basis = projektion(modell, renditen_netto, **kw)["endwert"]
    w = gewichte(modell)
    zeilen = []
    for i, g in w.items():
        if g <= 0:
            continue
        r = renditen_netto.get(i, 0.0)
        tief = dict(renditen_netto, **{i: max(r - delta, -0.95)})
        hoch = dict(renditen_netto, **{i: r + delta})
        e_tief = projektion(modell, tief, **kw)["endwert"]
        e_hoch = projektion(modell, hoch, **kw)["endwert"]
        zeilen.append({"id": i, "tief": e_tief, "hoch": e_hoch, "spanne": e_hoch - e_tief})
    zeilen.sort(key=lambda z: -z["spanne"])
    return basis, zeilen


def gruppen_sensitivitaet(modell, renditen_netto, asset_ids, stufen, **kw):
    """Endwert, wenn ALLE genannten Assets gemeinsam die Rendite der Stufe
    erreichen (z.B. Wikifolios 40 / 30 / 20 %)."""
    aus = []
    for s in stufen:
        r = dict(renditen_netto)
        for i in asset_ids:
            if i in r:
                r[i] = s
        aus.append((s, projektion(modell, r, **kw)["endwert"]))
    return aus


# ===========================================================================
# Confidence Score & Bias
# ===========================================================================
def confidence_score(jahre, typ, params=None):
    """Belastbarkeit der Datenbasis 0-100 - KEINE Wahrscheinlichkeit."""
    params = params or D.CONFIDENCE
    if typ == "cash":
        return params.get("cash_score", 100)
    if jahre is None or jahre <= 0:
        return params.get("ohne_historie", 10)
    wert = 100.0 * (1.0 - math.exp(-jahre / params["k_jahre"])) * params["typfaktor"].get(typ, 1.0)
    return int(round(max(0.0, min(100.0, wert))))


def confidence_fuer(modell, historie=None):
    """{asset_id: score} aus der Laenge der verfuegbaren Historie."""
    historie = historie or {}
    return {a["id"]: confidence_score((historie.get(a["id"]) or {}).get("jahre"), _typ(a))
            for a in aktive_assets(modell)}


def confidence_adjusted_return(rendite, confidence):
    """Interne Dashboard-Kennzahl (kein Finanzstandard): Rendite x Confidence/100."""
    if rendite is None or confidence is None:
        return None
    return rendite * confidence / 100.0


def bias_hinweise(asset, rendite_info, confidence):
    """Warnhinweise je Asset (Liste von Texten)."""
    hinweise = []
    wert = rendite_info.get("brutto")
    quelle = (rendite_info.get("herkunft") or {}).get("sourceType")
    if asset.get("historicalWinnerBias"):
        hinweise.append("⚠ Historical Winner Bias – aus historischen Gewinnern zusammengestellt")
    elif quelle in ("historical5Y", "historical10Y") and wert is not None and wert >= 0.20:
        hinweise.append("⚠ Historical Winner Bias – sehr hohe Vergangenheitsrendite als Annahme")
    if wert is not None and wert >= 0.30 and confidence is not None and confidence < 40:
        hinweise.append("Hohe angenommene Rendite bei geringer Datenbasis")
    if (asset.get("leverage") or 1) > 1 and asset.get("leverageType") == "daily":
        hinweise.append("Täglich gehebelt – Langfristrendite ≠ Hebel × Indexrendite")
    return hinweise


# ===========================================================================
# Fundamental Score
# ===========================================================================
def _skala(wert, schlecht, gut):
    """Linear 0..1 zwischen schlecht und gut (Richtung ergibt sich aus der Lage)."""
    if wert is None:
        return None
    if gut == schlecht:
        return 1.0 if wert >= gut else 0.0
    t = (wert - schlecht) / (gut - schlecht)
    return max(0.0, min(1.0, t))


def fundamental_score(kennzahlen, regeln=None, manuell=None):
    """-> {"gesamt": 0-100 oder None, "kategorien": {key: 0-100|None}, "abdeckung": 0-1}
    Kategorie = Mittel ihrer verfuegbaren Kennzahlen; Gesamt = gewichtetes
    Mittel der Kategorien mit Daten (Gewichte werden auf 100 normiert).
    Weniger als 50 % der Gewichte mit Daten -> kein Gesamtwert."""
    regeln = regeln or D.BEWERTUNGSREGELN
    kennzahlen = dict(kennzahlen or {})
    manuell = manuell or {}
    if manuell.get("moat") is not None:
        kennzahlen["manuell_moat"] = manuell["moat"]
    if manuell.get("risiko") is not None:
        kennzahlen["manuell_risiko"] = manuell["risiko"]
    kategorien, summe_g, summe = {}, 0.0, 0.0
    gesamt_gewicht = sum(max(float(r["gewicht"]), 0.0) for r in regeln.values()) or 1.0
    for key, regel in regeln.items():
        werte = []
        for feld, _, schlecht, gut, _niedriger in regel["kennzahlen"]:
            v = kennzahlen.get(feld)
            if feld == "nde" and kennzahlen.get("netcash"):
                v = -0.5 if v is None else min(v, -0.5)
            s = _skala(v, schlecht, gut)
            if s is not None:
                werte.append(s)
        if werte:
            kategorien[key] = 100.0 * sum(werte) / len(werte)
            g = max(float(regel["gewicht"]), 0.0)
            summe += g * kategorien[key]
            summe_g += g
        else:
            kategorien[key] = None
    abdeckung = summe_g / gesamt_gewicht
    gesamt = summe / summe_g if summe_g and abdeckung >= 0.5 else None
    return {"gesamt": None if gesamt is None else round(gesamt, 1),
            "kategorien": {k: (None if v is None else round(v, 1)) for k, v in kategorien.items()},
            "abdeckung": abdeckung}


KORB_METHODEN = {"manual": "Manuell", "equal": "Equal Weight", "score": "Fundamental Score Weighted",
                 "risk": "Risk Adjusted", "growth": "Growth Weighted"}


def korb_gewichte(korb, methode, scores=None, kennzahlen=None):
    """{aktie_id: gewicht_%} (Summe 100). Faellt eine Methode mangels Daten aus,
    bleibt es bei den bisherigen Gewichten."""
    scores = scores or {}
    kennzahlen = kennzahlen or {}
    ids = [k["id"] for k in korb]
    if not ids:
        return {}
    if methode == "equal":
        roh = {i: 1.0 for i in ids}
    elif methode == "score":
        roh = {i: max(scores.get(i) or 0.0, 0.0) for i in ids}
    elif methode == "risk":
        roh = {}
        for i in ids:
            vola = (kennzahlen.get(i) or {}).get("vola")
            s = scores.get(i)
            roh[i] = (s or 50.0) / vola if vola and vola > 0 else 0.0
    elif methode == "growth":
        roh = {}
        for i in ids:
            k = kennzahlen.get(i) or {}
            werte = [x for x in (k.get("g_ums"), k.get("g_fcfps") or k.get("g_fcf")) if x is not None]
            roh[i] = max(sum(werte) / len(werte), 0.0) if werte else 0.0
    else:
        roh = {k["id"]: float(k.get("gewicht") or 0.0) for k in korb}
    summe = sum(roh.values())
    if summe <= 0:
        roh = {k["id"]: float(k.get("gewicht") or 0.0) for k in korb}
        summe = sum(roh.values()) or 1.0
    return {i: round(100.0 * v / summe, 2) for i, v in roh.items()}


def korb_fundamental_rendite(korb, kennzahlen):
    """Vereinfachtes Fundamental-Modell je Aktie: FCF-Rendite + erwartetes
    Wachstum (Gordon-Naeherung), begrenzt auf -20..+40 %. Gewichtetes Mittel
    ueber den Korb. -> (korb_rendite oder None, {aktie: rendite})"""
    je_aktie, summe_w, summe = {}, 0.0, 0.0
    for k in korb:
        z = kennzahlen.get(k["id"]) or {}
        if z.get("fcfy") is None or z.get("g_ref") is None:
            continue
        r = max(-0.20, min(0.40, (z["fcfy"] + z["g_ref"]) / 100.0))
        je_aktie[k["id"]] = r
        summe += r * float(k["gewicht"])
        summe_w += float(k["gewicht"])
    if summe_w < 50:                       # weniger als die Haelfte des Korbs mit Daten
        return None, je_aktie
    return summe / summe_w, je_aktie


# ===========================================================================
# Risiko & Exposure
# ===========================================================================
def korb_anteile(korb, merkmal_menge):
    summe = sum(float(k["gewicht"]) for k in korb) or 1.0
    return sum(float(k["gewicht"]) for k in korb if k.get("sektor") in merkmal_menge) / summe


def asset_merkmal(asset, modell, merkmal):
    """Anteil eines Assets an Tech ("tech") bzw. Halbleitern ("semi"), 0..1 oder None (unbekannt)."""
    if asset["category"] == "stock_basket":
        return korb_anteile(modell["korb"], D.KORB_HALBLEITER if merkmal == "semi" else D.KORB_TECH)
    wert = asset.get("semiAnteil" if merkmal == "semi" else "techAnteil")
    if wert is None and _typ(asset) == "cash":
        return 0.0
    return wert


TREIBER_GRUPPEN = {"technology": "US-Tech", "semiconductor": "US-Tech", "leveraged_etf": "US-Tech",
                   "factor": "Welt-Aktien", "global_equity": "Welt-Aktien", "small_cap": "Welt-Aktien",
                   "regional_equity": "Welt-Aktien"}


def treiber(asset):
    """Renditetreiber eines Bausteins: eigenes Feld "treiber", sonst nach Kategorie,
    sonst eigener Treiber (Wikifolios, Einzelaktien, Korb, Rohstoffe ...)."""
    return asset.get("treiber") or TREIBER_GRUPPEN.get(asset["category"], asset["id"])


def risiko_kennzahlen(modell, renditen_netto, confidences, historie=None):
    historie = historie or {}
    w = gewichte(modell)
    assets = {a["id"]: a for a in aktive_assets(modell)}
    if not w:
        return {}
    hhi = sum(g * g for g in w.values())
    gruppen = {}
    for i, g in w.items():
        a = assets[i]
        if _typ(a) == "cash":
            continue
        grp = treiber(a)
        gruppen[grp] = gruppen.get(grp, 0.0) + g
    summe_risiko = sum(gruppen.values()) or 1.0
    hhi_treiber = sum((g / summe_risiko) ** 2 for g in gruppen.values())
    tech_bekannt, tech_unbekannt, semi_bekannt, semi_unbekannt = 0.0, [], 0.0, []
    for i, g in w.items():
        t = asset_merkmal(assets[i], modell, "tech")
        s = asset_merkmal(assets[i], modell, "semi")
        if t is None:
            if assets[i]["sector"] in ("Technologie-lastig",) or assets[i]["category"] in ("technology", "global_equity", "factor"):
                tech_unbekannt.append(assets[i]["name"])
        else:
            tech_bekannt += g * t
        if s is None:
            if assets[i]["category"] in ("technology", "global_equity", "factor", "leveraged_etf"):
                semi_unbekannt.append(assets[i]["name"])
        else:
            semi_bekannt += g * s
    dd = max_modell_verlust(modell, historie)
    rendite_w = sum(g * renditen_netto.get(i, 0.0) for i, g in w.items())
    conf_w = sum(g * (confidences.get(i) or 0) for i, g in w.items())
    car = sum(g * (confidence_adjusted_return(renditen_netto.get(i, 0.0), confidences.get(i)) or 0.0)
              for i, g in w.items())
    return {
        "max_gewicht": max(w.values()) * 100, "max_gewicht_name": assets[max(w, key=w.get)]["name"],
        "hhi": hhi, "effektive_positionen": 1.0 / hhi if hhi else None,
        "unabhaengige_treiber": 1.0 / hhi_treiber if hhi_treiber else None,
        "wikifolio_anteil": 100 * sum(g for i, g in w.items() if assets[i]["category"] == "wikifolio"),
        "hebel_anteil": 100 * sum(g for i, g in w.items() if (assets[i].get("leverage") or 1) > 1),
        "hebel_exposure": 100 * sum(g * (assets[i].get("leverage") or 1) for i, g in w.items()
                                    if _typ(assets[i]) != "cash"),
        "cash_quote": 100 * sum(g for i, g in w.items() if _typ(assets[i]) == "cash"),
        "tech_bekannt": 100 * tech_bekannt, "tech_unbekannt": tech_unbekannt,
        "semi_bekannt": 100 * semi_bekannt, "semi_unbekannt": semi_unbekannt,
        "drawdown_gewichtet": dd,
        "rendite_gewichtet": rendite_w, "confidence_gewichtet": conf_w,
        "confidence_adjusted_return": car,
    }


def effektive_exposure(modell, holdings=None):
    """Direkte + indirekte (ueber ETF-Holdings) Anteile je Unternehmen, sowie
    Sektor- und Regionen-Exposure. ETF-Holdings sind optional ({etf_id: {firma:
    anteil_%}}) - fehlen sie, zaehlt nur der direkte Anteil (wird angezeigt)."""
    holdings = holdings if holdings is not None else modell.get("holdings", {})
    w = gewichte(modell)
    assets = {a["id"]: a for a in aktive_assets(modell)}
    firmen, sektoren, regionen = {}, {}, {}
    korb_summe = sum(float(k["gewicht"]) for k in modell["korb"]) or 1.0
    for i, g in w.items():
        a = assets[i]
        if a["category"] == "stock_basket":
            for k in modell["korb"]:
                anteil = g * float(k["gewicht"]) / korb_summe
                f = firmen.setdefault(k["name"], {"direkt": 0.0, "indirekt": 0.0})
                f["direkt"] += anteil * 100
                sektoren[k["sektor"]] = sektoren.get(k["sektor"], 0.0) + anteil * 100
                regionen[k["region"]] = regionen.get(k["region"], 0.0) + anteil * 100
            continue
        for firma, pct in (holdings.get(i) or {}).items():
            f = firmen.setdefault(firma, {"direkt": 0.0, "indirekt": 0.0})
            f["indirekt"] += g * float(pct)
        sektoren[a["sector"]] = sektoren.get(a["sector"], 0.0) + g * 100
        regionen[a["region"]] = regionen.get(a["region"], 0.0) + g * 100
    for f in firmen.values():
        f["effektiv"] = f["direkt"] + f["indirekt"]
    return {"firmen": dict(sorted(firmen.items(), key=lambda x: -x[1]["effektiv"])),
            "sektoren": dict(sorted(sektoren.items(), key=lambda x: -x[1])),
            "regionen": dict(sorted(regionen.items(), key=lambda x: -x[1])),
            "holdings_vorhanden": sorted(k for k, v in holdings.items() if v)}


# ===========================================================================
# Optimizer
# ===========================================================================
def _simplex(c, A_ub, b_ub, A_eq, b_eq, max_iter=5000):
    """Maximiert c.x unter A_ub x <= b_ub, A_eq x = b_eq, x >= 0.
    Zwei-Phasen-Simplex mit Bland-Regel (keine Zyklen). Klein und ohne
    Abhaengigkeiten - die Probleme hier haben < 40 Variablen.
    -> (x, zielwert) oder (None, None) wenn unzulaessig."""
    n = len(c)
    zeilen, rechts, basis = [], [], []
    anz_schlupf = len(A_ub)
    # Zeilen mit negativer rechter Seite umdrehen (dann Ueberschuss- statt Schlupfvariable)
    art_bedarf = []
    for k, (a, b) in enumerate(zip(A_ub, b_ub)):
        zeile = list(a) + [0.0] * anz_schlupf
        if b < 0:
            zeile = [-x for x in zeile]
            zeile[n + k] = -1.0
            art_bedarf.append(True)
            b = -b
        else:
            zeile[n + k] = 1.0
            art_bedarf.append(False)
        zeilen.append(zeile)
        rechts.append(b)
    for a, b in zip(A_eq, b_eq):
        zeile = list(a) + [0.0] * anz_schlupf
        if b < 0:
            zeile = [-x for x in zeile]
            b = -b
        zeilen.append(zeile)
        rechts.append(b)
        art_bedarf.append(True)
    m = len(zeilen)
    anz_art = sum(art_bedarf)
    breite = n + anz_schlupf + anz_art
    t = []
    art_idx = n + anz_schlupf
    for k in range(m):
        zeile = zeilen[k] + [0.0] * anz_art + [rechts[k]]
        if art_bedarf[k]:
            zeile[art_idx] = 1.0
            basis.append(art_idx)
            art_idx += 1
        else:
            basis.append(n + k)
        t.append(zeile)

    def pivot(r, s):
        pv = t[r][s]
        t[r] = [x / pv for x in t[r]]
        for i in range(len(t)):
            if i != r and abs(t[i][s]) > 1e-15:
                f = t[i][s]
                t[i] = [x - f * y for x, y in zip(t[i], t[r])]
        basis[r] = s

    def loesen(ziel, erlaubt):
        # ziel: Liste Laenge breite (Maximierung); reduzierte Kosten im Tableau-Kopf
        for _ in range(max_iter):
            red = [ziel[j] - sum(ziel[basis[i]] * t[i][j] for i in range(m)) for j in range(breite)]
            eintritt = next((j for j in range(breite) if erlaubt[j] and red[j] > 1e-10), None)
            if eintritt is None:
                return True
            quot = [(t[i][-1] / t[i][eintritt], basis[i], i) for i in range(m) if t[i][eintritt] > 1e-12]
            if not quot:
                return False            # unbeschraenkt
            minq = min(q[0] for q in quot)
            r = min((q for q in quot if q[0] <= minq + 1e-12), key=lambda q: q[1])[2]
            pivot(r, eintritt)
        return False

    # Phase 1: Summe der Hilfsvariablen minimieren
    if anz_art:
        ziel1 = [0.0] * (n + anz_schlupf) + [-1.0] * anz_art
        loesen(ziel1, [True] * breite)
        if sum(t[i][-1] for i in range(m) if basis[i] >= n + anz_schlupf) > 1e-7:
            return None, None
        # Hilfsvariablen aus der Basis drueckend
        for i in range(m):
            if basis[i] >= n + anz_schlupf:
                s = next((j for j in range(n + anz_schlupf) if abs(t[i][j]) > 1e-9), None)
                if s is not None:
                    pivot(i, s)
    erlaubt = [True] * (n + anz_schlupf) + [False] * anz_art
    ziel2 = list(c) + [0.0] * (anz_schlupf + anz_art)
    if not loesen(ziel2, erlaubt):
        return None, None
    x = [0.0] * n
    for i in range(m):
        if basis[i] < n:
            x[basis[i]] = t[i][-1]
    return x, sum(ci * xi for ci, xi in zip(c, x))


def _wachstumsfaktor(r, jahre, sparrate_rel=0.0):
    """Endwert je 1 EUR Startgewicht (+ Sparrate relativ zum Startkapital)."""
    f = (1.0 + r) ** jahre
    if sparrate_rel:
        rm = (1.0 + r) ** (1.0 / 12.0)
        f += sparrate_rel * sum(rm ** (jahre * 12 - k) for k in range(1, jahre * 12 + 1))
    return f


def optimiere(modell, renditen_netto, confidences, grenzen=None, ziel=None):
    """Mathematische Zielgewichtung unter den Grenzen:
      1. Zielwert erreichen (sonst: maximal erreichbarer Endwert)
      2. Konzentration minimieren (kleinstes Hoechstgewicht)
      3. Confidence maximieren
    Regeln werden NIE verletzt. -> dict mit gewichte (%), endwert, erreichbar."""
    grenzen = grenzen or modell["grenzen"]
    rahmen = modell["rahmen"]
    assets = [a for a in aktive_assets(modell)
              if renditen_netto.get(a["id"]) is not None]
    if not assets:
        return None
    ids = [a["id"] for a in assets]
    n = len(ids)
    jahre = int(rahmen["horizont_jahre"])
    start = float(rahmen["startkapital"])
    spar_rel = float(rahmen.get("sparrate_monat") or 0.0) / start
    f = [_wachstumsfaktor(renditen_netto[i], jahre, spar_rel) for i in ids]
    ziel_rel = float(rahmen["zielvermoegen"] if ziel is None else ziel) / start

    A_ub, b_ub = [], []
    einzel = float(grenzen.get("einzelasset_max", 100.0)) / 100.0
    for k, a in enumerate(assets):
        if _typ(a) != "cash":
            zeile = [0.0] * n
            zeile[k] = 1.0
            A_ub.append(zeile)
            b_ub.append(einzel)
    for g in grenzen.get("gruppen", []):
        koeff = []
        for a in assets:
            if g.get("merkmal"):
                v = asset_merkmal(a, modell, g["merkmal"]) or 0.0
            else:
                v = 1.0 if a["category"] in g.get("kategorien", []) else 0.0
            koeff.append(v)
        if not any(koeff):
            if g.get("min"):
                return {"fehler": f"Mindestanteil „{g['titel']}“ nicht erfüllbar – kein passendes Asset aktiv."}
            continue
        if g.get("max") is not None:
            A_ub.append(koeff)
            b_ub.append(float(g["max"]) / 100.0)
        if g.get("min") is not None:
            A_ub.append([-v for v in koeff])
            b_ub.append(-float(g["min"]) / 100.0)
    A_eq, b_eq = [[1.0] * n], [1.0]

    # 1) maximal erreichbarer Endwert
    x, fmax = _simplex(f, A_ub, b_ub, A_eq, b_eq)
    if x is None:
        return {"fehler": "Die Grenzen widersprechen sich (z.B. Mindestanteile > 100 % oder "
                          "Hoechstgrenzen zu klein, um 100 % zu verteilen)."}
    erreichbar = fmax >= ziel_rel - 1e-9
    if erreichbar:
        # 2) Hoechstgewicht t minimieren: Variablen x_1..x_n, t
        A2 = [row + [0.0] for row in A_ub] + [[-fi for fi in f] + [0.0]]
        b2 = list(b_ub) + [-ziel_rel]
        for k, a in enumerate(assets):
            if _typ(a) != "cash":
                zeile = [0.0] * (n + 1)
                zeile[k] = 1.0
                zeile[n] = -1.0
                A2.append(zeile)
                b2.append(0.0)
        x2, neg_t = _simplex([0.0] * n + [-1.0], A2, b2, [[1.0] * n + [0.0]], [1.0])
        if x2 is not None:
            t_stern = x2[n]
            # 3) Confidence maximieren bei t <= t* (kleine Toleranz)
            A3 = [row[:] for row in A_ub] + [[-fi for fi in f]]
            b3 = list(b_ub) + [-ziel_rel]
            for k, a in enumerate(assets):
                if _typ(a) != "cash":
                    zeile = [0.0] * n
                    zeile[k] = 1.0
                    A3.append(zeile)
                    b3.append(t_stern + 1e-6)
            conf = [float(confidences.get(i) or 0.0) for i in ids]
            x3, _ = _simplex(conf, A3, b3, A_eq, b_eq)
            x = x3 if x3 is not None else x2[:n]
    endwert = start * sum(fi * xi for fi, xi in zip(f, x))
    return {"gewichte": {i: 100.0 * max(xi, 0.0) for i, xi in zip(ids, x)},
            "endwert": endwert, "max_endwert": start * fmax, "erreichbar": erreichbar}


# ===========================================================================
# Gewichtung fuer das Zielvermoegen ("Gewichtung 100k")
# ===========================================================================
def gewichtung_fuer_ziel(modell, renditen_netto, ziel=None, **kw):
    """Passt die Gewichte so an, dass der Modell-Endwert genau das Ziel trifft.

    Verfahren (nachvollziehbar statt Blackbox): Die bisherigen Gewichte werden
    stufenlos zu den renditestaerkeren Bausteinen gekippt,
        w_i  ~  w_i(bisher) * (1 + r_i) ^ lambda,
    und lambda wird per Bisektion so gewaehlt, dass die Projektion (inkl.
    Sparrate und Rebalancing) den Zielwert erreicht. Liegt das Modell schon
    darueber, kippt es entsprechend Richtung der renditeschwaecheren.
    - Fixierte Bausteine ("fixiert", z.B. die Reserve) behalten ihr Gewicht.
    - Bausteine mit 0 % oder deaktiviert bleiben draussen.
    - Optimizer-Grenzen werden NICHT erzwungen, aber gemeldet (grenzen_verletzungen).
    -> {"gewichte": {id: %}, "endwert", "erreichbar", "max_endwert"} oder {"fehler"}"""
    ziel = float(ziel if ziel is not None else modell["rahmen"]["zielvermoegen"])
    if ziel <= 0:
        return {"fehler": "Kein Zielvermögen gesetzt (0 €)."}
    if int(modell["rahmen"].get("horizont_jahre") or 0) <= 0:
        return {"fehler": "Keine Aufbauphase (0 Jahre) – ein Zielvermögen lässt sich nicht ansteuern."}
    summe = gewichte_summe(modell)
    if summe <= 0:
        return {"fehler": "Keine aktiven Bausteine mit Gewicht."}
    aktiv = aktive_assets(modell)
    bisher = {a["id"]: float(a.get("targetWeight") or 0.0) * 100.0 / summe for a in aktiv}
    fix = {a["id"] for a in aktiv if a.get("fixiert")}
    frei = [i for i in bisher if i not in fix and bisher[i] > 0]
    if not frei:
        offen = [i for i in bisher if i not in fix]
        if not offen:
            return {"fehler": "Alle Bausteine sind fixiert – mindestens einen freigeben."}
        # alle freien Bausteine stehen auf 0 %: gleich verteilt starten
        rest0 = 100.0 - sum(bisher[i] for i in fix)
        for i in offen:
            bisher[i] = rest0 / len(offen)
        frei = offen
    rest = 100.0 - sum(bisher[i] for i in fix)
    basis = {i: max(1.0 + renditen_netto.get(i, 0.0), 1e-6) for i in frei}
    log_b = {i: math.log(basis[i]) for i in frei}

    def gewichte_bei(lam):
        # numerisch stabil: Exponenten relativ zum groessten
        exps = {i: math.log(bisher[i]) + lam * log_b[i] for i in frei}
        mx = max(exps.values())
        roh = {i: math.exp(e - mx) for i, e in exps.items()}
        s = sum(roh.values())
        g = dict(bisher)
        for i in frei:
            g[i] = roh[i] / s * rest
        return g

    def endwert_bei(g):
        m2 = dict(modell)
        m2["assets"] = [dict(a, targetWeight=g.get(a["id"], 0.0)) if a.get("enabled") else a
                        for a in modell["assets"]]
        return projektion(m2, renditen_netto, **kw)["endwert"]

    e0 = endwert_bei(gewichte_bei(0.0))
    richtung = 1.0 if e0 < ziel else -1.0
    grenze = 1.0
    while True:
        e = endwert_bei(gewichte_bei(richtung * grenze))
        if (e >= ziel) if richtung > 0 else (e <= ziel):
            break
        if grenze > 4096:
            g = gewichte_bei(richtung * grenze)
            return {"gewichte": g, "endwert": e, "erreichbar": False, "max_endwert": e if richtung > 0 else None}
        grenze *= 2.0
    lo, hi = 0.0, grenze
    for _ in range(80):
        mitte = (lo + hi) / 2.0
        e = endwert_bei(gewichte_bei(richtung * mitte))
        if (e >= ziel) if richtung > 0 else (e <= ziel):
            hi = mitte
        else:
            lo = mitte
    g = gewichte_bei(richtung * hi)
    return {"gewichte": g, "endwert": endwert_bei(g), "erreichbar": True, "max_endwert": None}


def grenzen_verletzungen(modell, gewichte_pct=None):
    """Liste der verletzten Optimizer-Grenzen (Texte) fuer die aktuelle
    oder eine vorgeschlagene Gewichtung (in %)."""
    grenzen = modell["grenzen"]
    if gewichte_pct is None:
        gewichte_pct = {i: g * 100.0 for i, g in gewichte(modell).items()}
    assets = {a["id"]: a for a in modell["assets"]}
    aus = []
    einzel = float(grenzen.get("einzelasset_max", 100.0))
    for i, g in gewichte_pct.items():
        if _typ(assets[i]) != "cash" and g > einzel + 0.05:
            aus.append(f"{assets[i]['name']} {g:.1f} % > {einzel:.0f} % je Baustein")
    for gr in grenzen.get("gruppen", []):
        summe = 0.0
        for i, g in gewichte_pct.items():
            if gr.get("merkmal"):
                summe += g * (asset_merkmal(assets[i], modell, gr["merkmal"]) or 0.0)
            elif assets[i]["category"] in gr.get("kategorien", []):
                summe += g
        if gr.get("max") is not None and summe > gr["max"] + 0.05:
            aus.append(f"{gr['titel']} {summe:.1f} % > {gr['max']:.0f} %")
        if gr.get("min") is not None and summe < gr["min"] - 0.05:
            aus.append(f"{gr['titel']} {summe:.1f} % < {gr['min']:.0f} %")
    return [t.replace(".", ",") for t in aus]


# ===========================================================================
# Katalog: Risk Score und Rendite-Vorschlag
# ===========================================================================
def risiko_score(vola, maxdd, hebel=1.0, profil="", params=None):
    """Risk Score 0-100 (hoeher = riskanter), Formel in planer_daten.RISIKO.
    vola als Anteil (0.3 = 30 %), maxdd in % (negativ). Ohne Kursdaten None."""
    p = params or D.RISIKO
    if vola is None and maxdd is None:
        return None
    s_vola = min(max((vola or 0.0) * 100.0 / p["vola_max"], 0.0), 1.0) * 100.0
    s_dd = min(max(-(maxdd or 0.0) / p["dd_max"], 0.0), 1.0) * 100.0
    s_hebel = max(float(hebel or 1.0) - 1.0, 0.0) * p["hebel_je_faktor"]
    if any(t in (profil or "").lower() for t in p["hebel_texte"]):
        s_hebel += p["hebel_text_zuschlag"]
    s_hebel = min(s_hebel, 100.0)
    g = p["gewichte"]
    return int(round(g["vola"] * s_vola + g["dd"] * s_dd + g["hebel"] * s_hebel))


def vorschlag_renditen(kennz, typ, params=None):
    """Base/Bear/Bull-Vorschlag aus der Historie (planer_daten.VORSCHLAG).
    -> {"base", "bear", "bull", "hist", "quelle", "confidence"} oder None"""
    p = params or D.VORSCHLAG
    if not kennz:
        return None
    for feld, quelle in (("historical5Y", "5 J."), ("historical3Y", "3 J."), ("gesamt_cagr", "seit Start")):
        hist = kennz.get(feld)
        if hist is not None:
            break
    else:
        return None
    conf = confidence_score(kennz.get("jahre"), typ)
    base = conf / 100.0 * hist + (1.0 - conf / 100.0) * p["anker"]
    return {"base": base, "bear": base - p["bear_abschlag"] * abs(base), "bull": base + p["bull_zuschlag"] * abs(base),
            "hist": hist, "quelle": quelle, "confidence": conf}


# ===========================================================================
# Entnahmeplan (monatlich)
# ===========================================================================
def entnahmeplan(kapital, rendite_pa, monatlich, *, jahre=30, dynamik_pa=0.0, einstand=None, steuersatz=0.0,
                 freibetrag=0.0, max_jahre=100):
    """Monatliche Entnahme aus einem Kapital (Szenariorechnung, keine Prognose).

    - Verzinsung monatlich mit (1 + rendite_pa)^(1/12), Entnahme am Monatsende.
    - Entnahme (netto) steigt jedes Jahr um dynamik_pa (Anteil, 0.02 = 2 %).
    - Steuer (optional, vereinfacht): steuersatz (Anteil) auf den Gewinnanteil
      der Bruttoentnahme nach Durchschnittseinstand; freibetrag je 12 Monate.
      Brutto wird so bestimmt, dass netto = gewuenschte Entnahme.
    -> dict: verlauf (Monatswerte, Start inkl.), dauer_monate (None = reicht
       ueber max_jahre), restwert (nach 'jahre'), summen, jahre_tabelle."""
    rm = (1.0 + rendite_pa) ** (1.0 / 12.0) - 1.0
    wert = float(kapital)
    einstand = float(kapital if einstand is None else einstand)
    verlauf, jahre_tab = [wert], []
    summe_netto = summe_brutto = summe_steuer = 0.0
    dauer, restwert = None, None
    zeile = None
    frei_rest = freibetrag
    for mon in range(1, int(max_jahre * 12) + 1):
        if (mon - 1) % 12 == 0:
            frei_rest = freibetrag
            zeile = {"jahr": (mon - 1) // 12 + 1, "anfang": wert, "ertrag": 0.0, "brutto": 0.0, "netto": 0.0,
                     "steuer": 0.0}
            jahre_tab.append(zeile)
        ertrag = wert * rm
        wert += ertrag
        zeile["ertrag"] += ertrag
        netto = monatlich * (1.0 + dynamik_pa) ** ((mon - 1) // 12)
        anteil_gewinn = max(0.0, 1.0 - einstand / wert) if (steuersatz and wert > 0) else 0.0
        if netto * anteil_gewinn <= frei_rest or not steuersatz:
            brutto = netto
        else:
            brutto = (netto - steuersatz * frei_rest) / (1.0 - steuersatz * anteil_gewinn)
        leer = brutto >= wert
        if leer:
            brutto = wert
        steuerbar = brutto * anteil_gewinn
        steuer = max(0.0, steuerbar - frei_rest) * steuersatz
        frei_rest = max(0.0, frei_rest - steuerbar)
        netto_ist = brutto - steuer
        if wert > 0:
            einstand *= max(0.0, 1.0 - brutto / wert)
        wert -= brutto
        summe_netto += netto_ist
        summe_brutto += brutto
        summe_steuer += steuer
        for k, v in (("brutto", brutto), ("netto", netto_ist), ("steuer", steuer)):
            zeile[k] += v
        zeile["ende"] = wert
        verlauf.append(wert)
        if mon == jahre * 12:
            restwert = wert
        if leer:
            dauer = mon
            break
    if restwert is None:
        restwert = 0.0 if dauer is not None and dauer < jahre * 12 else wert
    return {"verlauf": verlauf, "dauer_monate": dauer, "restwert": restwert, "summe_netto": summe_netto,
            "summe_brutto": summe_brutto, "summe_steuer": summe_steuer, "jahre_tabelle": jahre_tab,
            "reicht_dauerhaft": dauer is None}


def entnahme_fuer(kapital, rendite_pa, *, ziel_restwert=0.0, jahre=30, **kw):
    """Hoechste monatliche Entnahme, bei der nach 'jahre' noch ziel_restwert
    uebrig ist (0 = Kapitalverzehr, kapital = Kapitalerhalt). Bisektion."""
    if kapital <= 0:
        return 0.0
    lo, hi = 0.0, float(kapital)
    for _ in range(70):
        mitte = (lo + hi) / 2.0
        p = entnahmeplan(kapital, rendite_pa, mitte, jahre=jahre, max_jahre=jahre, **kw)
        ok = (p["dauer_monate"] is None or p["dauer_monate"] >= jahre * 12) and p["restwert"] >= ziel_restwert - 1e-6
        if ok:
            lo = mitte
        else:
            hi = mitte
    return lo


def ziel_aus_rendite(modell, rendite_pa):
    """Endwert, der einer gewuenschten Portfoliorendite p.a. entspricht
    (Startkapital + Sparrate, gleiche Monatsrechnung wie die Projektion)."""
    r = modell["rahmen"]
    return future_value(float(r["startkapital"]), float(rendite_pa), int(r["horizont_jahre"]),
                        float(r.get("sparrate_monat") or 0.0))


def annahmen_aus_historie(modell, historie, alle=False):
    """Traegt die bisherige Rendite p.a. (Kurshistorie: 5 J., sonst 3 J., sonst
    seit Start, sonst 1 J.) als eigene Annahme ein - fuer alle Bausteine, deren
    Annahme automatisch gefuehrt wird (auto=True) oder noch fehlt. Selbst
    eingetragene Werte bleiben unangetastet, ausser alle=True.
    -> Anzahl geaenderter Annahmen"""
    historie = historie or {}
    geaendert = 0
    for a in modell["assets"]:
        if _typ(a) == "cash":
            continue
        rec = next((x for x in modell["annahmen"] if x["assetId"] == a["id"] and x["sourceType"] == "manualScenario"),
                   None)
        if rec is not None and not rec.get("auto") and rec.get("value") is not None and not alle:
            continue
        wert, text = ist_rendite(historie.get(a["id"]))
        if wert is None:
            if rec is None or rec.get("value") is None:
                # gar keine Kursdaten und noch kein Wert: Standard der Kategorie,
                # damit ueberall gerechnet werden kann (wird spaeter ersetzt)
                std = standard_rendite(a)
                setze_annahme(modell, a["id"], "manualScenario", std,
                              notiz="Keine Kursdaten gefunden – Standardwert der Kategorie, bitte prüfen.",
                              source="Standard (Kategorie)", auto=True)
                geaendert += 1
            elif alle:
                rec["auto"] = True          # sobald Kursdaten da sind, nachfuehren
            continue
        h = historie.get(a["id"]) or {}
        if rec is None or rec.get("value") is None or abs(rec["value"] - wert) > 1e-9 or not rec.get("auto"):
            setze_annahme(modell, a["id"], "manualScenario", wert, notiz=f"Automatisch: bisherige Rendite {text} "
                          "laut Kurshistorie – keine Prognose.", source=f"Kurshistorie ({text})",
                          stand=h.get("stand"), beobachtung=h.get("jahre"), auto=True)
            geaendert += 1
    return geaendert


def gewichte_nach_rendite(modell, renditen_netto):
    """Verteilt die Gewichte proportional zur Rendite p.a. (die in der Rechnung
    verwendete: Annahme bzw. Ist-Wert). Fixierte Bausteine und Cash behalten
    ihr Gewicht, Bausteine mit Rendite <= 0 bekommen 0 %. Alle aktiven, nicht
    fixierten Bausteine werden beruecksichtigt - auch solche mit bisher 0 %.
    -> {"gewichte": {id: %}} oder {"fehler": text}"""
    aktiv = aktive_assets(modell)
    fest = {a["id"]: float(a.get("targetWeight") or 0.0) for a in aktiv
            if a.get("fixiert") or _typ(a) == "cash"}
    rest = 100.0 - sum(fest.values())
    if rest <= 0:
        return {"fehler": "Fixierte Bausteine und Reserve belegen bereits 100 % – nichts zu verteilen."}
    frei = [a["id"] for a in aktiv if a["id"] not in fest]
    roh = {i: max(float(renditen_netto.get(i) or 0.0), 0.0) for i in frei}
    summe = sum(roh.values())
    if summe <= 0:
        return {"fehler": "Kein freier Baustein hat eine positive Rendite p.a."}
    g = dict(fest)
    for i in frei:
        g[i] = roh[i] / summe * rest
    return {"gewichte": g}


def gewichtung_fuer_rendite(modell, renditen_netto, ziel_r):
    """Verteilt die Gewichte automatisch so, dass die Portfoliorendite p.a.
    (gewichteter Mittelwert der Renditen, jaehrlich ausbalanciert) genau ziel_r
    ergibt. Ausgangspunkt ist eine GLEICHverteilung aller aktiven, nicht
    fixierten Bausteine ("ausgeglichen"); von dort wird stufenlos zu den
    renditestaerkeren bzw. -schwaecheren Bausteinen gekippt:
        w_i ~ exp(lambda * r_i),  lambda per Bisektion.
    Fixierte Bausteine und Cash behalten ihr Gewicht.
    -> {"gewichte": {id: %}, "rendite": erreicht, "erreichbar": bool, "min", "max"} oder {"fehler"}"""
    aktiv = aktive_assets(modell)
    if not aktiv:
        return {"fehler": "Keine aktiven Bausteine."}
    summe = gewichte_summe(modell) or 1.0
    fest = {a["id"]: float(a.get("targetWeight") or 0.0) * 100.0 / summe for a in aktiv
            if a.get("fixiert") or _typ(a) == "cash"}
    offen = [a["id"] for a in aktiv if a["id"] not in fest]
    if not offen:
        return {"fehler": "Alle Bausteine sind fixiert – mindestens einen freigeben."}
    rest = 100.0 - sum(fest.values())
    if rest <= 0:
        return {"fehler": "Fixierte Bausteine und Reserve belegen bereits 100 %."}
    r = {i: float(renditen_netto.get(i) or 0.0) for i in list(fest) + offen}
    beitrag_fest = sum(fest[i] * r[i] for i in fest) / 100.0

    def gewichte_bei(lam):
        mx = max(lam * r[i] for i in offen)
        roh = {i: math.exp(lam * r[i] - mx) for i in offen}
        su = sum(roh.values())
        g = dict(fest)
        for i in offen:
            g[i] = roh[i] / su * rest
        return g

    def rendite_bei(g):
        return sum(g[i] * r[i] for i in g) / 100.0

    r_min = beitrag_fest + rest / 100.0 * min(r[i] for i in offen)
    r_max = beitrag_fest + rest / 100.0 * max(r[i] for i in offen)
    if ziel_r >= r_max - 1e-9 or ziel_r <= r_min + 1e-9:
        lam = 5000.0 if ziel_r >= r_max - 1e-9 else -5000.0
        g = gewichte_bei(lam)
        return {"gewichte": g, "rendite": rendite_bei(g), "erreichbar": abs(rendite_bei(g) - ziel_r) < 1e-4,
                "min": r_min, "max": r_max}
    lo, hi = -5000.0, 5000.0
    for _ in range(200):
        mitte = (lo + hi) / 2.0
        if rendite_bei(gewichte_bei(mitte)) < ziel_r:
            lo = mitte
        else:
            hi = mitte
    g = gewichte_bei(hi)
    return {"gewichte": g, "rendite": rendite_bei(g), "erreichbar": True, "min": r_min, "max": r_max}


def gewichtung_fuer_zielvermoegen(modell, renditen_netto, rebalancing=None):
    """Automatische Gewichtung auf das Zielvermoegen: Benoetigte Rendite p.a.
    (Start, Sparrate, Jahre -> Ziel) berechnen und die Gewichte - ausgehend von
    einer Gleichverteilung, gekippt nach den Renditen der Bausteine wie
    gewichtung_fuer_rendite - so verteilen, dass die ECHTE Modellrechnung
    (inkl. Rebalancing/Drift) genau das Ziel erreicht.
    -> {"gewichte", "benoetigt", "rendite", "endwert", "erreichbar", "min", "max"} oder {"fehler"}"""
    import copy as _copy
    rahmen = modell["rahmen"]
    jahre = int(rahmen.get("horizont_jahre") or 0)
    ziel = float(rahmen.get("zielvermoegen") or 0.0)
    if jahre <= 0 or ziel <= 0:
        return {"fehler": "Kein Zielvermögen oder keine Aufbauphase."}
    benoetigt = erforderliche_rendite(float(rahmen["startkapital"]), ziel, jahre,
                                      float(rahmen.get("sparrate_monat") or 0.0))
    if benoetigt is None:
        return {"fehler": "Benötigte Rendite nicht berechenbar (Startkapital 0 ohne Sparrate?)."}
    probe = _copy.deepcopy(modell)

    def endwert_bei(t):
        erg = gewichtung_fuer_rendite(probe, renditen_netto, t)
        if erg.get("fehler"):
            return None, erg
        for a in probe["assets"]:
            if a["id"] in erg["gewichte"]:
                a["targetWeight"] = erg["gewichte"][a["id"]]
        return projektion(probe, renditen_netto, rebalancing=rebalancing)["endwert"], erg

    basis = gewichtung_fuer_rendite(probe, renditen_netto, benoetigt)
    if basis.get("fehler"):
        return basis
    lo, hi = basis["min"], basis["max"]
    ew_hi, erg_hi = endwert_bei(hi)
    if ew_hi is None:
        return erg_hi
    if ew_hi < ziel:                                  # selbst maximal renditestark reicht nicht
        return {"gewichte": erg_hi["gewichte"], "benoetigt": benoetigt, "rendite": erg_hi["rendite"],
                "endwert": ew_hi, "erreichbar": False, "min": lo, "max": hi}
    ew_lo, erg_lo = endwert_bei(lo)
    if ew_lo >= ziel:                                 # schon die defensivste Verteilung reicht
        return {"gewichte": erg_lo["gewichte"], "benoetigt": benoetigt, "rendite": erg_lo["rendite"],
                "endwert": ew_lo, "erreichbar": True, "min": lo, "max": hi}
    erg, ew = erg_hi, ew_hi
    for _ in range(40):
        mitte = (lo + hi) / 2.0
        ew_m, erg_m = endwert_bei(mitte)
        if ew_m >= ziel:
            hi, erg, ew = mitte, erg_m, ew_m
        else:
            lo = mitte
        if hi - lo < 1e-6:
            break
    return {"gewichte": erg["gewichte"], "benoetigt": benoetigt, "rendite": erg["rendite"], "endwert": ew,
            "erreichbar": True, "min": basis["min"], "max": basis["max"]}


def rendite_fuer_restwert(kapital, monatlich, ziel_restwert, *, jahre=30, **kw):
    """Benoetigte Rendite p.a. in der Entnahme, damit nach 'jahre' Jahren
    (monatliche Entnahme wie entnahmeplan) genau ziel_restwert uebrig ist.
    -> Rendite (Anteil) oder None (nicht berechenbar)"""
    if kapital is None or kapital <= 0 or ziel_restwert is None or ziel_restwert <= 0 or jahre <= 0:
        return None

    def rest(r):
        p = entnahmeplan(kapital, r, monatlich, jahre=jahre, max_jahre=jahre, **kw)
        return p["restwert"] if p["dauer_monate"] is None or p["dauer_monate"] >= jahre * 12 else 0.0

    lo, hi = -0.9, 0.5
    while rest(hi) < ziel_restwert and hi < 50.0:
        hi *= 2.0
    if rest(hi) < ziel_restwert:
        return None
    for _ in range(80):
        mitte = (lo + hi) / 2.0
        if rest(mitte) >= ziel_restwert:
            hi = mitte
        else:
            lo = mitte
    return hi


def kaufplan(positionen, betrag, bruchstuecke=False, nachkommastellen=4):
    """Stueckzahlen fuer einen Kaufbetrag.

    positionen: [{"id", "name", "anteil" (0..1 vom Gesamtbetrag), "kurs" (€ oder None),
                  "cash": bool}]
    - Cash-Positionen (Reserve) bleiben als Geld stehen.
    - Ganze Stuecke (Standard): abrunden, danach wird der Rest stueckweise auf
      die Positionen verteilt, die am weitesten unter ihrem Soll liegen und
      deren Kurs noch in den Rest passt.
    - bruchstuecke=True: exakte Stueckzahl (gerundet auf 'nachkommastellen').
    -> {"zeilen": [{..., "soll", "stueck", "ist", "abweichung"}], "investiert",
        "cash_soll", "rest", "ohne_kurs": [namen]}"""
    betrag = max(float(betrag or 0.0), 0.0)
    zeilen, ohne_kurs = [], []
    for p in positionen:
        soll = betrag * float(p.get("anteil") or 0.0)
        z = dict(p, soll=soll, stueck=0.0, ist=0.0)
        kurs = p.get("kurs")
        if p.get("cash"):
            z["ist"] = soll
        elif kurs and kurs > 0:
            if bruchstuecke:
                f = 10 ** nachkommastellen
                z["stueck"] = math.floor(soll / kurs * f) / f
            else:
                z["stueck"] = float(math.floor(soll / kurs + 1e-6))
            z["ist"] = z["stueck"] * kurs
        else:
            ohne_kurs.append(p.get("name"))
        zeilen.append(z)
    handelbar = [z for z in zeilen if not z.get("cash") and z.get("kurs")]
    rest = betrag - sum(z["ist"] for z in zeilen)
    if not bruchstuecke:
        for _ in range(100000):
            # nur Kaeufe, die naeher ans Soll fuehren (Rueckstand >= halber Kurs)
            kandidaten = [z for z in handelbar if z["kurs"] <= rest + 1e-9 and z["soll"] > 0
                          and z["soll"] - z["ist"] >= z["kurs"] / 2]
            if not kandidaten:
                break                     # Rest bleibt Cash
            # groesster relativer Rueckstand zum Soll zuerst
            z = max(kandidaten, key=lambda z: (z["soll"] - z["ist"]) / z["soll"])
            z["stueck"] += 1
            z["ist"] += z["kurs"]
            rest -= z["kurs"]
    for z in zeilen:
        z["abweichung"] = z["ist"] - z["soll"]
    investiert = sum(z["ist"] for z in zeilen if not z.get("cash"))
    cash_soll = sum(z["ist"] for z in zeilen if z.get("cash"))
    return {"zeilen": zeilen, "investiert": investiert, "cash_soll": cash_soll,
            "rest": max(betrag - investiert - cash_soll, 0.0), "ohne_kurs": ohne_kurs}


# ===========================================================================
# Kreditfinanzierte Investments (Hebel ueber Kredit) - Szenariorechnung
# ===========================================================================
def kredit_rate(betrag, zins_pa, jahre, art="annuitaet"):
    """Monatsrate: Annuitaet (Zins + Tilgung, konstant) oder endfaellig (nur Zins)."""
    n = max(int(round(jahre * 12)), 1)
    zm = zins_pa / 12.0
    if art == "endfaellig":
        return betrag * zm
    if zm == 0:
        return betrag / n
    return betrag * zm / (1 - (1 + zm) ** -n)


def kredit_simulation(betrag, zins_pa, jahre_kredit, art, rate_aus, rendite_pa, horizont_jahre,
                      alt_rendite_pa=None, crash=0.0, steuersatz=0.0, beleihung=0.0, rate=None):
    """Ein kreditfinanziertes Investment gegen die Alternative ohne Kredit.

    - Mit Kredit: 'betrag' wird sofort investiert (Rendite 'rendite_pa', optional
      Sofort-Einbruch 'crash' als Anteil, z. B. 0.3). Raten (Zins + Tilgung bzw. nur
      Zins, endfaellig Schlusszahlung) zahlt entweder das eigene Einkommen
      (rate_aus="einkommen") oder das Investment selbst (Verkauf, "investment").
    - Ohne Kredit (Alternative): genau die Zahlungen, die man aus dem Einkommen
      leisten wuerde, fliessen stattdessen monatlich in eine Anlage mit
      'alt_rendite_pa' (Standard = gleiche Rendite) - fairer Vergleich.
    - Steuer (vereinfacht, am Ende): Satz auf den Kursgewinn (Wert - Einstand);
      Kreditzinsen sind nicht absetzbar (Abgeltungsteuer).
    -> dict mit Endwerten, Vorteil, Zinsen, eigenen Zahlungen, Verlauf, max. Beleihung"""
    alt_rendite_pa = rendite_pa if alt_rendite_pa is None else alt_rendite_pa
    n_kredit = max(int(round(jahre_kredit * 12)), 1)
    n = max(int(round(horizont_jahre * 12)), n_kredit)
    zm = zins_pa / 12.0
    rm = (1 + rendite_pa) ** (1 / 12) - 1 if rendite_pa > -1 else -1.0
    ra = (1 + alt_rendite_pa) ** (1 / 12) - 1 if alt_rendite_pa > -1 else -1.0
    # eigene Rate (laut Vertrag) - tilgt sie nicht vollstaendig, bleibt am Laufzeitende
    # eine Schlussrate, die aus dem Depot bezahlt wird
    rate = kredit_rate(betrag, zins_pa, jahre_kredit, art) if rate is None else float(rate)
    schlussrate = 0.0
    P = betrag * (1 - crash)
    basis = float(betrag)
    S = float(betrag)
    A = 0.0
    basis_a = 0.0
    zinsen = eigene = verkauft = 0.0
    max_ltv, warn_monat, pleite_monat = 0.0, None, None
    verlauf = [(0, P - S, A, S)]
    p_mon, s_mon = [P], [S]                 # Monatswerte fuer die Beleihung des ganzen Depots
    for mon in range(1, n + 1):
        P *= 1 + rm
        A *= 1 + ra
        zahlung = 0.0
        if mon <= n_kredit and S > 1e-9:
            zins = S * zm
            if art == "endfaellig":
                tilg = S if mon == n_kredit else 0.0
                zahlung = zins + tilg
            else:
                zahlung = min(rate, S + zins)
                tilg = zahlung - zins
            zinsen += zins
            S = max(S - tilg, 0.0)
            if mon == n_kredit and S > 1e-6 and art != "endfaellig":
                schlussrate = S                 # Rest am Laufzeitende: aus dem Depot getilgt
                if P > 0:
                    basis -= basis * min(S / P, 1.0)
                P -= S
                verkauft += S
                S = 0.0
                if P < 0 and pleite_monat is None:
                    pleite_monat = mon
        if zahlung:
            if rate_aus == "einkommen":
                eigene += zahlung
                A += zahlung
                basis_a += zahlung
            else:
                if P > 0:
                    anteil = min(zahlung / P, 1.0)
                    basis -= basis * anteil
                P -= zahlung
                verkauft += zahlung
                if P < 0 and pleite_monat is None:
                    pleite_monat = mon
        if P > 0:
            ltv = S / P
            if ltv > max_ltv:
                max_ltv = ltv
            if beleihung and ltv > beleihung and warn_monat is None:
                warn_monat = mon
        elif S > 0:
            max_ltv = float("inf")
        p_mon.append(P)
        s_mon.append(S)
        if mon % 12 == 0 or mon == n:
            verlauf.append((mon, P - S, A, S))
    steuer_b = max(P - max(basis, 0.0), 0.0) * steuersatz if P > 0 else 0.0
    steuer_a = max(A - basis_a, 0.0) * steuersatz
    netto_b = P - S - steuer_b
    netto_a = A - steuer_a
    return {"rate": rate, "zinsen": zinsen, "eigene": eigene, "verkauft": verkauft, "wert": P, "schuld": S,
            "netto_mit": netto_b, "netto_ohne": netto_a, "vorteil": netto_b - netto_a,
            "steuer_mit": steuer_b, "steuer_ohne": steuer_a, "max_ltv": max_ltv, "warn_monat": warn_monat,
            "pleite_monat": pleite_monat, "verlauf": verlauf, "monate": n, "p_mon": p_mon, "s_mon": s_mon,
            "schlussrate": schlussrate}


def kredit_break_even(betrag, zins_pa, jahre_kredit, art, rate_aus, horizont_jahre, alt_rendite_pa=None,
                      steuersatz=0.0):
    """Rendite p.a. des Investments, ab der sich der Kredit gegenueber der
    Alternative lohnt (Vorteil = 0). Bei alt_rendite_pa=None hat die Alternative
    dieselbe Rendite. -> Anteil oder None"""
    def vorteil(r):
        return kredit_simulation(betrag, zins_pa, jahre_kredit, art, rate_aus, r, horizont_jahre,
                                 alt_rendite_pa, 0.0, steuersatz)["vorteil"]
    lo, hi = -0.5, 1.0
    if vorteil(lo) > 0 or vorteil(hi) < 0:
        return None
    for _ in range(60):
        mitte = (lo + hi) / 2
        if vorteil(mitte) >= 0:
            hi = mitte
        else:
            lo = mitte
    return hi


def kredit_zins_aus_rate(betrag, rate, jahre):
    """Effektiver Sollzins p.a. (nominal, monatlich) aus Betrag, Monatsrate und
    Laufzeit einer Annuitaet. -> Anteil (0.065 = 6,5 %) oder None, wenn die Rate
    den Kredit in der Laufzeit nicht tilgt."""
    n = max(int(round(jahre * 12)), 1)
    if betrag <= 0 or rate <= 0 or rate * n < betrag - 1e-6:
        return None
    lo, hi = 0.0, 0.05                       # Monatszins 0 .. 5 %
    if betrag * hi / (1 - (1 + hi) ** -n) < rate:
        return None
    for _ in range(100):
        mitte = (lo + hi) / 2
        r = betrag / n if mitte == 0 else betrag * mitte / (1 - (1 + mitte) ** -n)
        if r < rate:
            lo = mitte
        else:
            hi = mitte
    return (lo + hi) / 2 * 12


def kredit_restschuld(betrag, rate, zins_pa, monate):
    """Restschuld einer Annuitaet nach 'monate' gezahlten Raten (nie negativ)."""
    zm = zins_pa / 12.0
    if monate <= 0:
        return float(betrag)
    if zm == 0:
        return max(betrag - rate * monate, 0.0)
    q = (1 + zm) ** monate
    return max(betrag * q - rate * (q - 1) / zm, 0.0)
