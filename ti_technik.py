"""Trading Intelligence - Technical Analyst (ohne Streamlit): Indikatoren, Marktstruktur und Setup-Erkennung.

Grundsatz gegen Look-Ahead und Repainting: Jeder Wert am Tag i verwendet nur Kerzen bis einschliesslich i (nur
abgeschlossene Tageskerzen, siehe ti_daten). Wendepunkte (Swing-Hochs/-Tiefs) gelten erst als bekannt, wenn
SWING_K Kerzen danach vorliegen - ein Signal am Tag i nutzt nur Wendepunkte, die bis i bestaetigt waren.

Jedes Setup liefert je Tag einen Zustand: 0 = nichts, 1 = frueh (spekulativ, Bestaetigung steht aus),
2 = bestaetigt (zusaetzliche Bestaetigung durch Kurs/Volumen). Die Regeln stehen in SETUPS mit Beschreibung; die
Parameter in P sind vor jeder Auswertung festgelegt (nicht an Ergebnisse angepasst).
"""
import bisect

import numpy as np

P = {
    "swing_k": 3,              # Wendepunkt bestaetigt nach 3 Kerzen
    "atr": 14, "rsi": 14,
    "z_fenster": 500,          # ~2 Jahre: Verteilung der 20-Tage-Rendite bzw. des Abstands zum SMA 200
    "z_extrem": 2.5,           # statistisch aussergewoehnliche Abweichung (Standardabweichungen)
    "vol_hoch": 2.0,           # Volumen >= 2x Durchschnitt der letzten 50 Tage
    "range_lang": 120,         # langfristige Konsolidierung
    "bb_pz": 0.2,              # Bandbreite im untersten 20-%-Bereich des letzten Jahres
    "fehlausbruch_tage": 3,    # Rueckeroberung innerhalb von 3 Tagen
    "support_tage": 60,        # Unterstuetzung/Widerstand = Tief/Hoch der letzten 60 Tage (ohne die letzten 3)
}

LONG = ["L_kapitulation", "L_divergenz", "L_spring", "L_rueckeroberung", "L_struktur", "L_kaufdruck", "L_ausbruch",
        "L_ruecksetzer", "L_mittelwert"]
SHORT = ["S_uebertreibung", "S_divergenz", "S_volumenschwaeche", "S_upthrust", "S_ablehnung", "S_bruch",
         "S_struktur", "S_erholung", "S_mittelwert"]
TEXT = {
    "L_kapitulation": "Kapitulation: 20-Tage-Verlust statistisch extrem, Volumenspitze, Schluss in der oberen "
                      "Tageshälfte (Verkaufsdruck lässt nach); bestätigt, wenn der nächste Schluss über dem Hoch liegt",
    "L_divergenz": "Bullische Divergenz: tieferes Swing-Tief im Kurs, höheres Tief im RSI; bestätigt bei Schluss über "
                   "dem letzten Swing-Hoch",
    "L_spring": "Wyckoff Spring: nach Seitwärtsphase kurzer Bruch unter die Range-Unterstützung und Schluss zurück in "
                "der Range; bestätigt mit erhöhtem Volumen oder Folgetag über dem Spring-Hoch",
    "L_rueckeroberung": "Fehlausbruch nach unten: Schluss unter der 60-Tage-Unterstützung und Rückeroberung "
                        "innerhalb von 3 Tagen; bestätigt bei Schluss über dem Hoch des Bruchtags",
    "L_struktur": "Bullischer Strukturwechsel: nach tieferen Hochs Schluss über dem letzten bestätigten Swing-Hoch; "
                  "bestätigt, wenn zusätzlich ein höheres Tief vorliegt",
    "L_kaufdruck": "Ungewöhnlicher Kaufdruck: Volumen ≥ 2× Durchschnitt, Anstieg ≥ 1,5 ATR, Schluss nahe Tageshoch",
    "L_ausbruch": "Ausbruch aus langer Konsolidierung: enge Bandbreite (unterstes Fünftel des Jahres), Schluss über "
                  "dem 120-Tage-Hoch; bestätigt mit Volumen ≥ 1,5× Durchschnitt",
    "L_ruecksetzer": "Rücksetzer im Aufwärtstrend: Kurs und SMA 50 über steigendem SMA 200, Rücksetzer an den SMA 50 "
                     "bzw. RSI < 40; bestätigt bei Schluss über dem Vortageshoch",
    "L_mittelwert": "Statistisch extreme Abweichung unter den langfristigen Mittelwert (Abstand zum SMA 200 ≤ −2,5 "
                    "Standardabweichungen der letzten 2 Jahre); bestätigt bei Schluss über dem Vortageshoch",
    "S_uebertreibung": "Extreme Übertreibung nach oben: 20-Tage-Gewinn statistisch extrem; bestätigt bei Schluss "
                       "unter dem Vortagestief",
    "S_divergenz": "Bärische Divergenz: höheres Swing-Hoch im Kurs, tieferes Hoch im RSI; bestätigt bei Schluss "
                   "unter dem letzten Swing-Tief",
    "S_volumenschwaeche": "Nachlassendes Kaufvolumen: neues 20-Tage-Hoch bei Volumen (20 T.) unter dem Schnitt "
                          "(60 T.) und fallendem OBV; bestätigt bei Schluss unter dem Vortagestief",
    "S_upthrust": "Upthrust / Fehlausbruch nach oben: Hoch über dem 60-Tage-Widerstand, Schluss wieder darunter; "
                  "bestätigt bei Schluss unter dem Tief des Ausbruchstags",
    "S_ablehnung": "Ablehnung am Widerstand: Hoch am 60-Tage-Widerstand (± 0,5 ATR), langer oberer Docht, Schluss im "
                   "unteren Drittel",
    "S_bruch": "Bruch der Unterstützung: Schluss unter dem 60-Tage-Tief; bestätigt mit Volumen ≥ 1,5× Durchschnitt",
    "S_struktur": "Bärischer Strukturwechsel: nach höheren Tiefs Schluss unter dem letzten bestätigten Swing-Tief; "
                  "bestätigt, wenn zusätzlich ein tieferes Hoch vorliegt",
    "S_erholung": "Erholungsrally im Abwärtstrend: Kurs und SMA 50 unter fallendem SMA 200, Erholung an den SMA 50 "
                  "bzw. RSI > 60; bestätigt bei Schluss unter dem Vortagestief",
    "S_mittelwert": "Statistisch extreme Überdehnung über den langfristigen Mittelwert (Abstand zum SMA 200 ≥ +2,5 "
                    "Standardabweichungen der letzten 2 Jahre); bestätigt bei Schluss unter dem Vortagestief",
}
FAMILIE = {  # unabhaengige Bestaetigungen zaehlen nur je Familie einmal
    "L_kapitulation": "extrem", "L_mittelwert": "extrem", "L_divergenz": "momentum", "L_spring": "fehlausbruch",
    "L_rueckeroberung": "fehlausbruch", "L_struktur": "struktur", "L_kaufdruck": "volumen", "L_ausbruch": "ausbruch",
    "L_ruecksetzer": "trend",
    "S_uebertreibung": "extrem", "S_mittelwert": "extrem", "S_divergenz": "momentum", "S_volumenschwaeche": "volumen",
    "S_upthrust": "fehlausbruch", "S_ablehnung": "widerstand", "S_bruch": "struktur", "S_struktur": "struktur",
    "S_erholung": "trend",
}


# ---------------------------------------------------------------------------------------------------- Indikatoren
def sma(x, n):
    x = np.asarray(x, float)
    aus = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        aus[n - 1:] = (c[n:] - c[:-n]) / n
    return aus


def ema(x, n):
    x = np.asarray(x, float)
    aus = np.full(len(x), np.nan)
    if len(x) < n:
        return aus
    a = 2 / (n + 1)
    aus[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        aus[i] = a * x[i] + (1 - a) * aus[i - 1]
    return aus


def rsi(c, n=14):
    c = np.asarray(c, float)
    aus = np.full(len(c), np.nan)
    if len(c) <= n:
        return aus
    d = np.diff(c)
    auf, ab = np.clip(d, 0, None), np.clip(-d, 0, None)
    ma, mb = auf[:n].mean(), ab[:n].mean()
    for i in range(n, len(c)):
        if i > n:
            ma = (ma * (n - 1) + auf[i - 1]) / n
            mb = (mb * (n - 1) + ab[i - 1]) / n
        aus[i] = 100.0 if mb == 0 else 100 - 100 / (1 + ma / mb)
    return aus


def atr(h, lo, c, n=14):
    h, lo, c = (np.asarray(v, float) for v in (h, lo, c))
    tr = np.maximum(h - lo, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(lo - np.roll(c, 1))))
    tr[0] = h[0] - lo[0]
    aus = np.full(len(c), np.nan)
    if len(c) < n:
        return aus
    aus[n - 1] = tr[:n].mean()
    for i in range(n, len(c)):
        aus[i] = (aus[i - 1] * (n - 1) + tr[i]) / n
    return aus


def obv(c, v):
    c, v = np.asarray(c, float), np.asarray(v, float)
    s = np.sign(np.diff(c, prepend=c[0]))
    return np.cumsum(s * v)


def roll_max(x, n):
    x = np.asarray(x, float)
    aus = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        aus[i] = x[i - n + 1:i + 1].max()
    return aus


def roll_min(x, n):
    return -roll_max(-np.asarray(x, float), n)


def roll_mean(x, n):
    """Gleitender Mittelwert, der fehlende Werte (NaN) auslaesst (mind. n/2 Werte)."""
    x = np.asarray(x, float)
    aus = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        w = w[~np.isnan(w)]
        if len(w) >= n // 2:
            aus[i] = w.mean()
    return aus


def roll_std(x, n):
    x = np.asarray(x, float)
    aus = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        w = w[~np.isnan(w)]
        if len(w) >= n // 2:
            aus[i] = w.std()
    return aus


def pz_rang(x, n):
    """Perzentil des heutigen Werts in den n Werten davor (nur Vergangenheit) -> 0..1."""
    x = np.asarray(x, float)
    aus = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        w = x[i - n:i]
        w = w[~np.isnan(w)]
        if len(w) >= n // 2 and not np.isnan(x[i]):
            aus[i] = (w <= x[i]).mean()
    return aus


def swings(h, lo, k=None):
    """Bestaetigte Wendepunkte. -> (hochs, tiefs): Listen (index_wendepunkt, index_bestaetigt, wert)."""
    k = k or P["swing_k"]
    hochs, tiefs = [], []
    for j in range(k, len(h) - k):
        if h[j] == max(h[j - k:j + k + 1]) and h[j] > max(h[j - k:j]):
            hochs.append((j, j + k, h[j]))
        if lo[j] == min(lo[j - k:j + k + 1]) and lo[j] < min(lo[j - k:j]):
            tiefs.append((j, j + k, lo[j]))
    return hochs, tiefs


def bekannt(punkte, i):
    """Wendepunkte, die am Tag i bereits bestaetigt waren (punkte nach Bestaetigungstag sortiert)."""
    return punkte[:bisect.bisect_right([p[1] for p in punkte], i)] if len(punkte) < 64 else \
        punkte[:_bis(punkte, i)]


def _bis(punkte, i):
    lo_, hi_ = 0, len(punkte)
    while lo_ < hi_:
        m = (lo_ + hi_) // 2
        if punkte[m][1] <= i:
            lo_ = m + 1
        else:
            hi_ = m
    return lo_


def indikatoren(k):
    """Kerzen [[iso,o,h,l,c,v]] -> dict mit numpy-Arrays."""
    o, h, lo, c, v = (np.array([x[j] for x in k], float) for j in range(1, 6))
    ind = {"o": o, "h": h, "l": lo, "c": c, "v": v, "n": len(c), "datum": [x[0] for x in k]}
    ind["sma20"], ind["sma50"], ind["sma200"] = sma(c, 20), sma(c, 50), sma(c, 200)
    ind["ema10"] = ema(c, 10)
    ind["rsi"] = rsi(c, P["rsi"])
    ind["atr"] = atr(h, lo, c, P["atr"])
    ind["vol50"] = sma(v, 50)
    ind["vol20"], ind["vol60"] = sma(v, 20), sma(v, 60)
    ind["obv"] = obv(c, v)
    ind["hat_volumen"] = (v[-250:] > 0).mean() > 0.9 if len(v) else False
    r20 = np.full(len(c), np.nan)
    r20[20:] = c[20:] / c[:-20] - 1
    ind["r20"] = r20
    sd = roll_std(r20, P["z_fenster"])
    ind["z_r20"] = r20 / sd
    abst = np.log(c / ind["sma200"])
    ind["abst200"] = abst
    ind["z_abst200"] = (abst - roll_mean(abst, P["z_fenster"])) / roll_std(abst, P["z_fenster"])
    std20 = roll_std(c, 20)
    bw = 4 * std20 / ind["sma20"]
    ind["bb_pz"] = pz_rang(bw, 250)
    ind["hoch120"], ind["tief120"] = roll_max(h, P["range_lang"]), roll_min(lo, P["range_lang"])
    n_s, lag = P["support_tage"], 3
    sup, wid = np.full(len(c), np.nan), np.full(len(c), np.nan)
    for i in range(n_s + lag, len(c)):
        sup[i] = lo[i - n_s - lag + 1:i - lag + 1].min()
        wid[i] = h[i - n_s - lag + 1:i - lag + 1].max()
    ind["support"], ind["widerstand"] = sup, wid
    ind["hoch20"] = roll_max(h, 20)
    ind["swings"] = swings(h, lo)
    return ind


# ---------------------------------------------------------------------------------------------------- Setups
def _letzte(punkte, i, n=2):
    b = bekannt(punkte, i)
    return b[-n:] if len(b) >= n else None


def setups(ind):
    """-> {setup_id: np.array (0/1/2) je Tag}. Nur Daten bis zum jeweiligen Tag."""
    o, h, lo, c, v, a = ind["o"], ind["h"], ind["l"], ind["c"], ind["v"], ind["atr"]
    n = ind["n"]
    mit_vol = ind["hat_volumen"]
    with np.errstate(divide="ignore", invalid="ignore"):
        vrel = np.where(ind["vol50"] > 0, v / ind["vol50"], np.nan) if mit_vol else np.full(n, np.nan)
    hochs, tiefs = ind["swings"]
    r = ind["rsi"]
    s = {x: np.zeros(n, int) for x in LONG + SHORT}
    ft = P["fehlausbruch_tage"]
    z = P["z_extrem"]

    def pos_j(j):
        rr = h[j] - lo[j]
        return (c[j] - lo[j]) / rr if rr > 0 else 0.5

    for i in range(1, n):
        if np.isnan(a[i]) or np.isnan(ind["sma200"][i]):
            continue
        rng = h[i] - lo[i]
        pos = (c[i] - lo[i]) / rng if rng > 0 else 0.5
        # --- Long
        # Kapitulation: frueh am Tag der Kapitulation, bestaetigt am Folgetag
        kap = lambda j: (not np.isnan(ind["z_r20"][j]) and ind["z_r20"][j] <= -z and pos_j(j) >= 0.5   # noqa: E731
                         and (not mit_vol or (vrel[j] >= P["vol_hoch"])))
        if kap(i):
            s["L_kapitulation"][i] = 1
        if i >= 1 and kap(i - 1) and c[i] > h[i - 1]:
            s["L_kapitulation"][i] = 2
        # Divergenzen (bestaetigte Wendepunkte)
        t2 = _letzte(tiefs, i)
        if t2 and t2[1][1] >= i - 5 and t2[1][2] < t2[0][2] and r[t2[1][0]] > r[t2[0][0]] + 2:
            s["L_divergenz"][i] = 1
            hb = bekannt(hochs, i)
            if hb and c[i] > hb[-1][2] and hb[-1][0] > t2[0][0]:
                s["L_divergenz"][i] = 2
        h2 = _letzte(hochs, i)
        if h2 and h2[1][1] >= i - 5 and h2[1][2] > h2[0][2] and r[h2[1][0]] < r[h2[0][0]] - 2:
            s["S_divergenz"][i] = 1
            tb = bekannt(tiefs, i)
            if tb and c[i] < tb[-1][2] and tb[-1][0] > h2[0][0]:
                s["S_divergenz"][i] = 2
        sup, wid = ind["support"][i], ind["widerstand"][i]
        if not np.isnan(sup):
            breite = (wid - sup) / a[i]
            # Spring: Seitwaertsphase (Range <= 12 ATR), Tief unter Support (< 1 ATR), Schluss zurueck darueber
            if breite <= 12 and lo[i] < sup and lo[i] > sup - a[i] and c[i] > sup:
                s["L_spring"][i] = 2 if (mit_vol and vrel[i] >= 1.5) else 1
            if i >= 1 and s["L_spring"][i - 1] >= 1 and c[i] > h[i - 1]:
                s["L_spring"][i] = 2
            # Rueckeroberung: Schluss unter Support in den letzten 3 Tagen, heute wieder darueber
            unter = [j for j in range(max(0, i - ft), i) if c[j] < ind["support"][j]]
            if unter and c[i] > ind["support"][unter[0]]:
                s["L_rueckeroberung"][i] = 2 if c[i] > h[unter[0]] else 1
            # Upthrust: Hoch ueber Widerstand, Schluss darunter
            if h[i] > wid and c[i] < wid and h[i] < wid + a[i]:
                s["S_upthrust"][i] = 1
            if i >= 1 and s["S_upthrust"][i - 1] >= 1 and c[i] < lo[i - 1]:
                s["S_upthrust"][i] = 2
            # Ablehnung am Widerstand
            body = abs(c[i] - o[i])
            if abs(h[i] - wid) <= 0.5 * a[i] and pos <= 1 / 3 and (h[i] - max(o[i], c[i])) >= 2 * max(body, 1e-9):
                s["S_ablehnung"][i] = 2 if c[i] < o[i] else 1
            # Bruch der Unterstuetzung
            if c[i] < sup and c[i - 1] >= ind["support"][i - 1]:
                s["S_bruch"][i] = 2 if (mit_vol and vrel[i] >= 1.5) else 1
        # Strukturwechsel
        hb, tb = bekannt(hochs, i), bekannt(tiefs, i)
        if len(hb) >= 2 and hb[-1][2] < hb[-2][2] and c[i] > hb[-1][2] and c[i - 1] <= hb[-1][2]:
            s["L_struktur"][i] = 2 if (len(tb) >= 2 and tb[-1][2] > tb[-2][2]) else 1
        if len(tb) >= 2 and tb[-1][2] > tb[-2][2] and c[i] < tb[-1][2] and c[i - 1] >= tb[-1][2]:
            s["S_struktur"][i] = 2 if (len(hb) >= 2 and hb[-1][2] < hb[-2][2]) else 1
        # Kaufdruck
        if mit_vol and vrel[i] >= P["vol_hoch"] and c[i] - c[i - 1] >= 1.5 * a[i] and pos >= 0.75:
            s["L_kaufdruck"][i] = 2
        # Ausbruch aus Konsolidierung
        if (i >= 1 and not np.isnan(ind["bb_pz"][i - 1]) and ind["bb_pz"][i - 1] <= P["bb_pz"]
                and not np.isnan(ind["hoch120"][i - 1]) and c[i] > ind["hoch120"][i - 1]):
            s["L_ausbruch"][i] = 2 if (mit_vol and vrel[i] >= 1.5) else 1
        # Trend-Ruecksetzer
        s50, s200 = ind["sma50"], ind["sma200"]
        if i >= 20 and not np.isnan(s200[i - 20]):
            auf = c[i] > s200[i] and s50[i] > s200[i] and s200[i] > s200[i - 20]
            abw = c[i] < s200[i] and s50[i] < s200[i] and s200[i] < s200[i - 20]
            if auf and (lo[i] <= s50[i] or r[i] < 40):
                s["L_ruecksetzer"][i] = 1
            if auf and (lo[i - 1] <= s50[i - 1] or r[i - 1] < 40) and c[i] > h[i - 1]:
                s["L_ruecksetzer"][i] = 2
            if abw and (h[i] >= s50[i] or r[i] > 60):
                s["S_erholung"][i] = 1
            if abw and (h[i - 1] >= s50[i - 1] or r[i - 1] > 60) and c[i] < lo[i - 1]:
                s["S_erholung"][i] = 2
        # Mittelwert-Abweichung
        za = ind["z_abst200"]
        if not np.isnan(za[i]):
            if za[i] <= -z:
                s["L_mittelwert"][i] = 2 if c[i] > h[i - 1] else 1
            if za[i] >= z:
                s["S_mittelwert"][i] = 2 if c[i] < lo[i - 1] else 1
        # Uebertreibung nach oben
        if not np.isnan(ind["z_r20"][i]) and ind["z_r20"][i] >= z:
            s["S_uebertreibung"][i] = 2 if c[i] < lo[i - 1] else 1
        # Volumenschwaeche trotz Anstieg
        if (mit_vol and i >= 10 and h[i] >= ind["hoch20"][i - 1] and ind["vol20"][i] < 0.85 * ind["vol60"][i]
                and ind["obv"][i] < ind["obv"][i - 10]):
            s["S_volumenschwaeche"][i] = 1
        if i >= 1 and s["S_volumenschwaeche"][i - 1] >= 1 and c[i] < lo[i - 1]:
            s["S_volumenschwaeche"][i] = 2
    return s


def aktiv(s, i, richtung):
    """Setups am Tag i -> [(id, stufe)] fuer 'long'/'short'."""
    ids = LONG if richtung == "long" else SHORT
    return [(x, int(s[x][i])) for x in ids if s[x][i] > 0]


def bestaetigungen(liste):
    """Unabhaengige Bestaetigungen = Familien mit mindestens einem Setup (bestaetigte zaehlen voll)."""
    fam = {}
    for x, stufe in liste:
        fam[FAMILIE[x]] = max(fam.get(FAMILIE[x], 0), stufe)
    return sum(1 for v in fam.values() if v == 2), len(fam)


# ---------------------------------------------------------------------------------------------------- Marken
def _staffeln(werte, a, abstand=1.0):
    """Marken mit mindestens `abstand` ATR Abstand zueinander (die naechste zuerst)."""
    aus = []
    for x in werte:
        if not aus or abs(x - aus[-1]) >= abstand * a:
            aus.append(float(x))
    return aus


def marken(ind, i, richtung, ziele_hist=None):
    """Einstiegsspanne, Trigger, Stop, Ziele, CRV fuer Tag i (nur Daten bis i).
    ziele_hist: empirische guenstige Auslenkungen (Anteile, z. B. Quantile aus der Historie) fuer fehlende Ziele.
    -> dict oder None."""
    c, h, lo, a = ind["c"][i], ind["h"][i], ind["l"][i], ind["atr"][i]
    if np.isnan(a) or a <= 0:
        return None
    hochs, tiefs = ind["swings"]
    hb = [p[2] for p in bekannt(hochs, i)]
    tb = [p[2] for p in bekannt(tiefs, i)]
    # Kursziele nur aus Wendepunkten der letzten 2 Jahre (aeltere Marken sind kaum noch relevant)
    hb_jung = [p[2] for p in bekannt(hochs, i) if p[0] >= i - 500]
    tb_jung = [p[2] for p in bekannt(tiefs, i) if p[0] >= i - 500]
    if richtung == "long":
        trigger = h
        zone = (c - 0.5 * a, h)
        einstieg = trigger
        unter = [x for x in tb[-6:] if x < c]
        stop = min(max(unter) if unter else c - 2 * a, lo) - 0.25 * a
        stop = max(stop, einstieg - 4 * a)                  # sehr weite Stops begrenzen (sonst CRV verzerrt)
        kand = _staffeln(sorted(x for x in hb_jung + [ind["hoch120"][i]] if x > einstieg + 0.5 * a), a)
        risiko = einstieg - stop
    else:
        trigger = lo
        zone = (lo, c + 0.5 * a)
        einstieg = trigger
        ueber = [x for x in hb[-6:] if x > c]
        stop = max(min(ueber) if ueber else c + 2 * a, h) + 0.25 * a
        stop = min(stop, einstieg + 4 * a)
        kand = _staffeln(sorted((x for x in tb_jung + [ind["tief120"][i]] if x < einstieg - 0.5 * a), reverse=True), a)
        risiko = stop - einstieg
    if risiko <= 0:
        return None
    ziele, quelle = list(kand[:3]), ["Widerstand" if richtung == "long" else "Unterstützung"] * min(3, len(kand))
    for q in (ziele_hist or []):
        if len(ziele) >= 3:
            break
        z = einstieg * (1 + q) if richtung == "long" else einstieg * (1 - q)
        if (richtung == "long" and z > (ziele[-1] if ziele else einstieg)) or \
                (richtung == "short" and z < (ziele[-1] if ziele else einstieg)):
            ziele.append(z)
            quelle.append("historische Spanne")
    if not ziele:
        return None
    crv = [abs(z - einstieg) / risiko for z in ziele]
    return {"richtung": richtung, "zone": zone, "trigger": trigger, "einstieg": einstieg, "stop": stop,
            "ziele": ziele, "ziel_quelle": quelle, "crv": crv, "crv_haupt": crv[min(1, len(crv) - 1)],
            "risiko_pct": risiko / einstieg, "atr_pct": a / c}
