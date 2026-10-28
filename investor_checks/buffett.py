"""Warren Buffett - Qualitaet zu fairem Preis (10 Kriterien) + Owner Earnings, DCF, Burggraben-Proxy.

Quellen: Berkshire-Aktionaersbriefe (Owner Earnings: Brief 1986; einbehaltene Gewinne / "$1-Test": Brief 1983),
M. Buffett & D. Clark, "Buffettology" (ROE, Schulden < 4 x Gewinn, Kapitalintensitaet). Buffett schaut auf
10 Jahre - hier mit der verfuegbaren Historie (Yahoo: 4 Jahre), als eingeschraenkt gekennzeichnet.
"""
import investor_config as C

from . import registriere
from .basis import (de, ergebnis, extra, kriterium, letztes, mittel, reihe, schwelle_versorger, teile, vorhanden,
                    zahl)

INFO = ("Warren Buffett (*1930), Berkshire Hathaway: kauft „wunderbare Unternehmen zu fairen Preisen“ – "
        "hohe, beständige Kapitalrenditen, wenig Schulden, wenig Investitionsbedarf und ein dauerhafter "
        "Wettbewerbsvorteil (Burggraben).")


def roe_reihe(f):
    """ROE je Jahr in % (Nettogewinn / Eigenkapital); None bei Eigenkapital <= 0 (nicht aussagekraeftig)."""
    return [teile(j.get("nettogewinn"), j.get("ek")) * 100 if zahl(j.get("ek")) and j["ek"] > 0
            and zahl(j.get("nettogewinn")) is not None else None for j in f.get("jahre") or []]


def roic_reihe(f, steuer=None):
    """ROIC je Jahr in %: NOPAT / investiertes Kapital = EBIT x (1 - s) / (EK + Finanzschulden - Cash)."""
    s = (C.BUFFETT["steuersatz"] if steuer is None else steuer) / 100.0
    aus = []
    for j in f.get("jahre") or []:
        ebit, ek = zahl(j.get("ebit")), zahl(j.get("ek"))
        ic = None if ek is None else ek + (zahl(j.get("schulden")) or 0) - (zahl(j.get("cash")) or 0)
        aus.append(ebit * (1 - s) / ic * 100 if ebit is not None and ic and ic > 0 else None)
    return aus


def stabil(werte, max_spanne, relativ=None):
    """Stabil, wenn die Spanne (max - min) hoechstens max_spanne Prozentpunkte betraegt - oder hoechstens
    `relativ` % des Durchschnitts (sonst waere eine Firma mit 60 % ROIC nie "stabil")."""
    w = vorhanden(werte)
    if len(w) < 2:
        return None, None
    spanne = max(w) - min(w)
    relativ = C.BUFFETT["stabil_relativ"] if relativ is None else relativ
    m = mittel(w)
    return spanne <= max_spanne or (m and m > 0 and spanne <= m * relativ / 100), spanne


def owner_earnings(j):
    """Owner Earnings (Buffett 1986) = Nettogewinn + Abschreibungen - Erhaltungs-Capex.
    Vereinfachung: Erhaltungs-Capex = gesamter Capex (konservativ; in der UI gekennzeichnet)."""
    ni, ab, cx = zahl(j.get("nettogewinn")), zahl(j.get("abschreibungen")), zahl(j.get("capex"))
    if ni is None or ab is None or cx is None:
        return None
    return ni + ab - cx


def dcf(oe0, wachstum, diskont, ewig, jahre=10):
    """Barwert: oe0 waechst `jahre` mit `wachstum` %, danach ewige Rente mit `ewig` %, abgezinst mit `diskont` %.
    -> Unternehmenswert (gleiche Einheit wie oe0) oder None (oe0 <= 0 oder diskont <= ewig)."""
    oe0 = zahl(oe0)
    g, r, ge = wachstum / 100.0, diskont / 100.0, ewig / 100.0
    if oe0 is None or oe0 <= 0 or r <= ge:
        return None
    wert, cf = 0.0, oe0
    for t in range(1, jahre + 1):
        cf *= 1 + g
        wert += cf / (1 + r) ** t
    rest = cf * (1 + ge) / (r - ge)
    return wert + rest / (1 + r) ** jahre


def kurs_am(f, datum):
    """Schlusskurs am letzten Handelstag bis `datum` (YYYY-MM-DD) aus der Kurshistorie."""
    k = [c for d, c, _ in f.get("kurse") or [] if d <= datum]
    return k[-1] if k else None


@registriere("buffett", "Warren Buffett", "Qualität", 20)
def check(f, kx):
    cfg = C.BUFFETT
    J = f.get("jahre") or []
    n = len(J)
    eing = f"{n} von {C.SOLL_JAHRE} Jahren" if n < C.SOLL_JAHRE else None
    kr = []

    roe = roe_reihe(f)
    roe_v = vorhanden(roe)
    neg_ek = any(zahl(j.get("ek")) is not None and j["ek"] <= 0 for j in J)
    kr.append(kriterium("roe", "ROE > 15 % in jedem Jahr", min(roe_v) if roe_v else ("negatives EK" if neg_ek else None),
                        cfg["min_roe"], None if len(roe_v) < 2 or neg_ek else min(roe_v) > cfg["min_roe"],
                        "Kleinster Jahreswert zählt, nicht der Durchschnitt." + (
                            " Negatives Eigenkapital (z. B. durch Rückkäufe) – ROE nicht aussagekräftig."
                            if neg_ek else ""), eingeschraenkt=eing, fmt="pct"))
    roic = roic_reihe(f)
    st_roic, sp_roic = stabil(roic, cfg["roic_max_schwankung"])
    roic_v = vorhanden(roic)
    kr.append(kriterium("roic", "ROIC > 12 % und stabil", min(roic_v) if roic_v else None,
                        cfg["min_roic"], None if st_roic is None else (min(roic_v) > cfg["min_roic"] and st_roic),
                        f"NOPAT (EBIT × {100 - cfg['steuersatz']:.0f} %) / (EK + Schulden − Cash); "
                        + (f"Spanne {de(sp_roic)} Prozentpunkte." if sp_roic is not None else ""),
                        eingeschraenkt=eing, fmt="pct"))
    ni, lfs = letztes(f, "nettogewinn"), letztes(f, "langfr_schulden")
    if lfs is None and letztes(f, "bilanzsumme") is not None and (letztes(f, "schulden") or 0) == 0:
        lfs = 0.0
    faktor = teile(lfs, ni) if ni and ni > 0 else None
    s_max = schwelle_versorger(f, cfg["max_schulden_x_gewinn"], "schulden")
    kr.append(kriterium("schulden", f"Langfr. Schulden < {s_max:.0f} × Nettogewinn", faktor if faktor is not None else (
        "Verlust" if ni is not None and ni <= 0 else None), s_max,
        False if ni is not None and ni <= 0 else None if faktor is None else faktor < s_max,
        "In wie vielen Jahresgewinnen wären die langfristigen Schulden getilgt?", fmt="x"))
    gm = [pct_or_none(j.get("bruttogewinn"), j.get("umsatz")) for j in J]
    st_gm, sp_gm = stabil(gm, cfg["bruttomarge_max_schwankung"], relativ=0)
    gm_v = vorhanden(gm)
    kr.append(kriterium("bruttomarge", "Bruttomarge > 40 % und stabil", min(gm_v) if gm_v else None,
                        cfg["min_bruttomarge"], None if st_gm is None else (min(gm_v) > cfg["min_bruttomarge"] and st_gm),
                        "Hohe, stabile Bruttomarge zeigt Preissetzungsmacht. " +
                        (f"Spanne {de(sp_gm)} Prozentpunkte (max. 5)." if sp_gm is not None else ""),
                        eingeschraenkt=eing, fmt="pct"))
    nm = mittel(pct_or_none(j.get("nettogewinn"), j.get("umsatz")) for j in J)
    kr.append(kriterium("nettomarge", "Nettomarge > 10 %", nm, cfg["min_nettomarge"],
                        None if nm is None else nm > cfg["min_nettomarge"], "Durchschnitt über die Jahre.",
                        fmt="pct"))
    fcf = vorhanden(reihe(f, "fcf"))
    kr.append(kriterium("fcf", "Free Cashflow in allen Jahren positiv", f"{sum(1 for x in fcf if x > 0)} von {len(fcf)}",
                        "alle", None if len(fcf) < 2 else all(x > 0 for x in fcf),
                        "Das Geschäft muss Bargeld abwerfen, nicht nur Buchgewinne.", eingeschraenkt=eing, fmt="text"))
    capq = None
    cx, nis = mittel(reihe(f, "capex")), mittel(reihe(f, "nettogewinn"))
    if cx is not None and nis and nis > 0:
        capq = cx / nis * 100
    kr.append(kriterium("capex", "Capex < 50 % des Nettogewinns", capq if capq is not None else (
        "Verlust" if nis is not None and nis <= 0 else None), cfg["max_capex_quote"],
        False if nis is not None and nis <= 0 else None if capq is None else capq < cfg["max_capex_quote"],
        "Kapitalleichtes Geschäft: wenig Investitionen nötig, um den Gewinn zu halten.", fmt="pct"))
    nr = vorhanden(reihe(f, "nettogewinn"))
    kr.append(kriterium("gewinn_stetig", "Gewinn stetig, keine Verlustjahre",
                        f"{sum(1 for x in nr if x > 0)} von {len(nr)} positiv", "alle positiv, Ende > Anfang",
                        None if len(nr) < 2 else all(x > 0 for x in nr) and nr[-1] > nr[0],
                        "Kein Verlustjahr und der jüngste Gewinn liegt über dem ältesten.", eingeschraenkt=eing,
                        fmt="text"))
    ak = vorhanden(reihe(f, "aktien"))
    vera = (ak[-1] / ak[0] - 1) * 100 if len(ak) >= 2 and ak[0] > 0 else None
    kr.append(kriterium("aktien", "Rückkäufe statt Verwässerung", vera, "≤ 0 %",
                        None if vera is None else vera <= 0.5,
                        "Veränderung der Aktienanzahl über den Zeitraum (sinkend oder stabil = gut).", fmt="pct"))
    # 10. Einbehaltene-Gewinne-Test ("$1-Test")
    test = einbehalten_test(f)
    kr.append(kriterium("einbehalten", "Einbehaltene-Gewinne-Test", test["zuwachs"], test["einbehalten"],
                        test["ok"], "Jeder einbehaltene Dollar soll mindestens einen Dollar Börsenwert schaffen "
                        "(Zuwachs Börsenwert ≥ Summe einbehaltener Gewinne).", eingeschraenkt=eing, fmt="geld"))

    # Zusatz: Owner Earnings, Burggraben-Proxy
    extras = []
    oe = owner_earnings(J[-1]) if J else None
    aktien = letztes(f, "aktien") or f.get("aktien")
    extras.append(extra("Owner Earnings", oe, "Nettogewinn + Abschreibungen − Erhaltungs-Capex. Annahme: "
                        "Erhaltungs-Capex = gesamter Capex (konservativ).", fmt="geld"))
    extras.append(extra("Owner Earnings je Aktie", teile(oe, aktien), "Basis für den DCF unten.", fmt="kurs"))
    moat = burggraben(f, kx, roic, gm)
    extras.append(extra("Burggraben-Proxy", moat["stufe"], moat["text"], fmt="text"))
    return ergebnis("buffett", "Warren Buffett", "Wunderbare Unternehmen zu einem fairen Preis.", "Qualität",
                    kr, f, extras=extras, info=INFO) | {"owner_earnings": oe, "aktien": aktien, "moat": moat}


def pct_or_none(a, b):
    v = teile(a, b)
    return None if v is None else v * 100


def einbehalten_test(f):
    """Zuwachs Boersenwert (Kurs x Aktien, erstes -> letztes Geschaeftsjahresende) vs. Summe einbehaltener
    Gewinne (Nettogewinn - Dividenden) der Jahre danach."""
    J = f.get("jahre") or []
    leer = {"zuwachs": None, "einbehalten": None, "ok": None}
    if len(J) < 2:
        return leer
    a, z = J[0], J[-1]
    ka, kz = kurs_am(f, a["datum"]), kurs_am(f, z["datum"])
    if ka is None or kz is None or not zahl(a.get("aktien")) or not zahl(z.get("aktien")):
        return leer
    # Kurs in Berichtswaehrung umrechnen (gleiches Verhaeltnis wie beim aktuellen Kurs)
    faktor = teile(f.get("kurs_in_bericht"), f.get("kurs")) or 1.0
    zuwachs = kz * faktor * z["aktien"] - ka * faktor * a["aktien"]
    einb = 0.0
    for j in J[1:]:
        ni = zahl(j.get("nettogewinn"))
        if ni is None:
            return leer
        einb += ni - (zahl(j.get("dividenden")) or 0)
    if einb <= 0:
        return {"zuwachs": zuwachs, "einbehalten": einb, "ok": None}
    return {"zuwachs": zuwachs, "einbehalten": einb, "ok": zuwachs >= einb}


def burggraben(f, kx, roic=None, gm=None):
    """Burggraben-Proxy: stabil hohe ROIC + stabile Bruttomarge + Marktfuehrerschaft (Rang im Sektor).
    Rang: kx["sektor_rang"] = (rang, anzahl) nach Boersenwert (Umsatz liegt nicht fuer alle Werte vor)."""
    cfg = C.BUFFETT
    roic = roic_reihe(f) if roic is None else roic
    gm = gm or []
    punkte, gruende = 0, []
    rv = vorhanden(roic)
    st_r, _ = stabil(roic, cfg["roic_max_schwankung"])
    if rv and min(rv) >= cfg["moat_min_roic"] and st_r:
        punkte += 1
        gruende.append(f"ROIC stabil ≥ {cfg['moat_min_roic']:.0f} %")
    gv = vorhanden(gm)
    st_g, _ = stabil(gm, cfg["bruttomarge_max_schwankung"], relativ=0)
    if gv and min(gv) >= cfg["moat_min_bruttomarge"] and st_g:
        punkte += 1
        gruende.append(f"Bruttomarge stabil ≥ {cfg['moat_min_bruttomarge']:.0f} %")
    rang = (kx or {}).get("sektor_rang")
    if rang and rang[0] <= cfg["moat_top_rang"]:
        punkte += 1
        gruende.append(f"Nr. {rang[0]} von {rang[1]} im Sektor (Börsenwert)")
    stufe = {3: "breit", 2: "schmal", 1: "schwach"}.get(punkte, "keiner erkennbar")
    if not rv and not gv:
        stufe = "n/a"
    return {"punkte": punkte, "stufe": stufe,
            "text": ("; ".join(gruende) if gruende else "keines der drei Merkmale erfüllt") +
                    " – Näherung aus Kennzahlen, kein Ersatz für die qualitative Prüfung."}


__all__ = ["check", "dcf", "owner_earnings", "roe_reihe", "roic_reihe", "einbehalten_test", "burggraben"]
