"""Trading Intelligence - Historical Intelligence (ohne Streamlit): Historical Pattern Matching Engine.

Vergleicht die Lage eines Werts am Tag i mit historischen Lagen (gleicher Wert und andere Werte derselben
Marktgruppe) und wertet aus, wie es danach tatsaechlich weiterging.

Merkmale (alle skalenfrei, je Tag nur aus Daten bis zu diesem Tag): Rendite 5/20/60 Tage in Volatilitaetseinheiten,
Abstand zu SMA 50/200 in ATR, Abstand zum 1-Jahres-Hoch, RSI, Volatilitaetsregime (20 zu 120 Tage),
Volumenentwicklung (5 zu 50 Tage), Trendsteigung des SMA 50, relative Staerke zum Leitindex. Die Skalierung ist fest
vorgegeben (SKALA), nicht aus den Daten geschaetzt - damit fliesst keine Information aus spaeteren Jahren ein.

Ergebnisse je Vergleichsfall: Einstieg zur naechsten Eroeffnung nach dem Tag, Schluss nach h = 1/5/10/20/60/120
Handelstagen, guenstigste und unguenstigste Auslenkung (Hoch/Tief) waehrend der Haltedauer, abzueglich
Transaktionskosten (KOSTEN, Hin und Zurueck). Ein Vergleichsfall zaehlt nur, wenn sein Ergebnis zum Abfragetag
bereits feststand (Endtag < Abfragetag) - kein Look-Ahead.

Unsicherheit: Faelle desselben Werts mit ueberlappender Haltedauer zaehlen fuer das Konfidenzintervall nur einmal
(effektive Fallzahl). Keine erfundenen Zahlen: zu wenige Faelle -> keine Quote.
"""
import math

import numpy as np

import ti_technik as T

HORIZONTE = (1, 5, 10, 20, 60, 120)
K_NACHBARN = 60
MIN_FAELLE = 20                  # darunter keine Trefferquote
KOSTEN = {"aktie": 0.002, "etf": 0.002, "index": 0.001, "krypto": 0.003, "rohstoff": 0.001, "devisen": 0.0005}
GRUPPE = {"aktie": "aktien", "etf": "aktien", "index": "aktien", "krypto": "krypto", "rohstoff": "rohstoff",
          "devisen": "devisen"}
MERKMALE = ["r5", "r20", "r60", "abst50", "abst200", "drawdown", "rsi", "vola_regime", "volumen", "trend", "rel_staerke"]
SKALA = {"abst50": 5.0, "abst200": 10.0, "rsi": 20.0, "vola_regime": 0.4, "volumen": 0.5}
AUSDUENNEN = 3                   # jeder 3. Tag in den Vergleichspool (benachbarte Tage sind fast identisch)


def _vol(c, n=60):
    lr = np.diff(np.log(c), prepend=np.nan)
    return T.roll_std(lr, n)


def merkmale(ind, leit=None):
    """-> np.array (Tage x Merkmale), NaN wo nicht berechenbar. leit: Schlusskurse des Leitindex, auf die
    Tage des Werts ausgerichtet (oder None)."""
    c, a = ind["c"], ind["atr"]
    n = ind["n"]
    sd = _vol(c, 60)
    f = np.full((n, len(MERKMALE)), np.nan)

    def r(h):
        x = np.full(n, np.nan)
        x[h:] = np.log(c[h:] / c[:-h])
        return x
    for j, h in enumerate((5, 20, 60)):
        f[:, j] = r(h) / (sd * math.sqrt(h))
    f[:, 3] = (c - ind["sma50"]) / a / SKALA["abst50"]
    f[:, 4] = (c - ind["sma200"]) / a / SKALA["abst200"]
    f[:, 5] = (c / T.roll_max(ind["h"], 250) - 1) / (sd * math.sqrt(60))
    f[:, 6] = (ind["rsi"] - 50) / SKALA["rsi"]
    f[:, 7] = np.log(_vol(c, 20) / _vol(c, 120)) / SKALA["vola_regime"]
    if ind["hat_volumen"]:
        v5, v50 = T.sma(ind["v"], 5), T.sma(ind["v"], 50)
        with np.errstate(divide="ignore", invalid="ignore"):
            f[:, 8] = np.where((v5 > 0) & (v50 > 0), np.log(v5 / v50), 0.0) / SKALA["volumen"]
    else:
        f[:, 8] = 0.0
    s50 = ind["sma50"]
    tr = np.full(n, np.nan)
    tr[20:] = np.log(s50[20:] / s50[:-20])
    f[:, 9] = tr / (sd * math.sqrt(20))
    if leit is not None:
        lr = np.full(n, np.nan)
        lr[60:] = np.log(leit[60:] / leit[:-60])
        f[:, 10] = (r(60) - lr) / (sd * math.sqrt(60))
    else:
        f[:, 10] = 0.0
    return np.clip(f, -6, 6)


def ergebnisse(ind):
    """Je Tag und Horizont: Rendite (Long, vor Kosten), MFE, MAE ab Einstieg zur naechsten Eroeffnung, Endindex."""
    o, h, lo, c = ind["o"], ind["h"], ind["l"], ind["c"]
    n = ind["n"]
    aus = {}
    for hz in HORIZONTE:
        ret, mfe, mae = (np.full(n, np.nan) for _ in range(3))
        for i in range(n - hz - 1 + 1):
            if i + hz >= n:
                break
            e = o[i + 1]
            ret[i] = c[i + hz] / e - 1
            mfe[i] = h[i + 1:i + hz + 1].max() / e - 1
            mae[i] = lo[i + 1:i + hz + 1].min() / e - 1
        aus[hz] = (ret, mfe, mae)
    return aus


class Pool:
    """Vergleichsfaelle einer Marktgruppe. Aufbau mit hinzufuegen(), danach abfragen()."""

    def __init__(self):
        self._teile = []

    def hinzufuegen(self, wert_id, ind, f, erg):
        n = ind["n"]
        idx = np.arange(0, n, AUSDUENNEN)
        ok = ~np.isnan(f[idx]).any(axis=1)
        idx = idx[ok]
        if not len(idx):
            return
        tage = np.array([np.datetime64(d) for d in ind["datum"]])
        teil = {"id": wert_id, "f": f[idx], "datum": tage[idx], "pos": idx}
        for hz in HORIZONTE:
            ret, mfe, mae = erg[hz]
            ende = np.full(len(idx), np.datetime64("2999-01-01"))
            gueltig = idx + hz < n
            ende[gueltig] = tage[idx[gueltig] + hz]
            teil[hz] = (ret[idx], mfe[idx], mae[idx], ende)
        self._teile.append(teil)
        self._fertig = None

    def _bauen(self):
        if getattr(self, "_fertig", None) is None:
            t = self._teile
            self._fertig = {"f": np.concatenate([x["f"] for x in t]),
                            "datum": np.concatenate([x["datum"] for x in t]),
                            "pos": np.concatenate([x["pos"] for x in t]),
                            "id": np.concatenate([[x["id"]] * len(x["pos"]) for x in t])}
            for hz in HORIZONTE:
                self._fertig[hz] = tuple(np.concatenate([x[hz][j] for x in t]) for j in range(4))
        return self._fertig

    def __len__(self):
        return sum(len(x["pos"]) for x in self._teile)

    def abfragen(self, merkmal, datum, k=K_NACHBARN, horizonte=HORIZONTE):
        """Aehnlichste Faelle, deren Ergebnis am `datum` je Horizont bereits feststand.
        -> {h: {"ret","mfe","mae","id","pos","dist"} oder None}"""
        p = self._bauen()
        if np.isnan(merkmal).any():
            return {hz: None for hz in horizonte}
        d = np.sqrt(((p["f"] - merkmal) ** 2).sum(axis=1))
        tag = np.datetime64(datum)
        aus = {}
        for hz in horizonte:
            ret, mfe, mae, ende = p[hz]
            maske = (ende < tag) & ~np.isnan(ret)
            if maske.sum() < k:
                aus[hz] = None
                continue
            kand = np.where(maske)[0]
            wahl = kand[np.argpartition(d[kand], k - 1)[:k]]
            aus[hz] = {"ret": ret[wahl], "mfe": mfe[wahl], "mae": mae[wahl], "id": p["id"][wahl],
                       "pos": p["pos"][wahl], "dist": d[wahl], "basis": ret[maske]}
        return aus


def effektiv(ids, pos, hz):
    """Faelle ohne ueberlappende Haltedauer je Wert (gierig)."""
    n = 0
    for w in set(ids):
        frei = -10 ** 9
        for q in sorted(pos[ids == w]):
            if q >= frei:
                n += 1
                frei = q + hz + 1
    return n


def wilson(p, n, z=1.96):
    if not n:
        return None, None
    m = (p + z * z / (2 * n)) / (1 + z * z / n)
    b = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, m - b), min(1.0, m + b)


def statistik(treffer, richtung, kosten):
    """Abfrageergebnis -> Kennzahlen je Horizont (Renditen nach Kosten, Short = gespiegelt)."""
    aus = {}
    for hz, t in treffer.items():
        if t is None:
            aus[hz] = None
            continue
        sgn = 1 if richtung == "long" else -1
        ret = sgn * t["ret"] - kosten
        basis = sgn * t["basis"] - kosten
        guenstig = t["mfe"] if richtung == "long" else -t["mae"]
        unguenstig = t["mae"] if richtung == "long" else -t["mfe"]
        n_eff = effektiv(t["id"], t["pos"], hz)
        q = float((ret > 0).mean())
        ki = wilson(q, n_eff) if n_eff >= MIN_FAELLE else (None, None)
        aus[hz] = {"n": len(ret), "n_eff": n_eff, "quote": q if n_eff >= MIN_FAELLE else None, "ki": ki,
                   "basis_quote": float((basis > 0).mean()), "basis_median": float(np.median(basis)),
                   "median": float(np.median(ret)), "mittel": float(ret.mean()),
                   "quantile": {p_: float(np.percentile(ret, p_)) for p_ in (10, 25, 50, 75, 90)},
                   "guenstig": {p_: float(np.percentile(guenstig, p_)) for p_ in (50, 75, 90)},
                   "verlust_median": float(np.median(unguenstig)), "verlust_p10": float(np.percentile(unguenstig, 10)),
                   "werte": len(set(t["id"])), "distanz": float(np.median(t["dist"]))}
    return aus


def leit_ausrichten(datum, leit_kerzen):
    """Schlusskurse des Leitindex auf die Tage eines Werts (letzter bekannter Schluss bis zu diesem Tag)."""
    if not leit_kerzen:
        return None
    ld = [x[0] for x in leit_kerzen]
    lc = [x[4] for x in leit_kerzen]
    aus, j = np.full(len(datum), np.nan), -1
    for i, d in enumerate(datum):
        while j + 1 < len(ld) and ld[j + 1] <= d:
            j += 1
        if j >= 0:
            aus[i] = lc[j]
    return aus
