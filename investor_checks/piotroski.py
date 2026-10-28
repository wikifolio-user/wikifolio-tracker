"""Piotroski F-Score (0-9).

Quelle: J. Piotroski, "Value Investing: The Use of Historical Financial Statement Information to Separate Winners
from Losers", Journal of Accounting Research 38 (2000). Neun Signale, je 1 Punkt; Vergleich juengstes vs.
vorheriges Geschaeftsjahr. ROA mit der Bilanzsumme zu Jahresbeginn (= Vorjahr), wie im Original.
"""
import investor_config as C

from . import registriere
from .basis import ergebnis, kriterium, teile, zahl

INFO = ("Joseph Piotroski (Professor, Stanford) zeigte 2000, dass neun einfache Bilanz-Signale unter günstigen "
        "Aktien die Gewinner von den Verlierern trennen: 8–9 Punkte = stark, 0–2 = schwach.")


def signale(t, v, vv=None):
    """Die neun Signale aus Jahr t, Vorjahr v und (fuer die Vorjahres-ROA) dem Jahr davor vv.
    -> [(id, name, wert, ok oder None, erklaerung)]"""
    def g(j, k):
        return zahl((j or {}).get(k))

    roa_t = teile(g(t, "nettogewinn"), g(v, "bilanzsumme"))
    roa_v = teile(g(v, "nettogewinn"), g(vv, "bilanzsumme") or g(v, "bilanzsumme"))
    cfo = g(t, "op_cf")
    acc = None if cfo is None or g(t, "nettogewinn") is None else cfo > g(t, "nettogewinn")
    lev_t = teile(g(t, "langfr_schulden") or 0, g(t, "bilanzsumme")) if g(t, "bilanzsumme") else None
    lev_v = teile(g(v, "langfr_schulden") or 0, g(v, "bilanzsumme")) if g(v, "bilanzsumme") else None
    cr_t, cr_v = teile(g(t, "umlauf"), g(t, "kurzfr_verb")), teile(g(v, "umlauf"), g(v, "kurzfr_verb"))
    ak_t, ak_v = g(t, "aktien"), g(v, "aktien")
    gm_t, gm_v = teile(g(t, "bruttogewinn"), g(t, "umsatz")), teile(g(v, "bruttogewinn"), g(v, "umsatz"))
    at_t, at_v = teile(g(t, "umsatz"), g(v, "bilanzsumme")), teile(g(v, "umsatz"), g(vv, "bilanzsumme") or g(v, "bilanzsumme"))

    def vgl(a, b, hoeher=True):
        if a is None or b is None:
            return None
        return a > b if hoeher else a < b

    return [
        ("roa", "ROA positiv", roa_t, None if roa_t is None else roa_t > 0, "Nettogewinn / Bilanzsumme (Vorjahr) > 0."),
        ("cfo", "Operativer Cashflow positiv", cfo, None if cfo is None else cfo > 0, "Das Geschäft erzeugt Bargeld."),
        ("roa_delta", "ROA gestiegen", (roa_t - roa_v) if roa_t is not None and roa_v is not None else None,
         vgl(roa_t, roa_v), "Rentabilität besser als im Vorjahr."),
        ("accrual", "Operativer Cashflow > Nettogewinn", cfo, acc, "Gewinn ist durch Cash gedeckt (Gewinnqualität)."),
        ("leverage", "Verschuldungsgrad gesunken", lev_t, vgl(lev_t, lev_v, hoeher=False),
         "Langfristige Schulden / Bilanzsumme kleiner als im Vorjahr."),
        ("current_ratio", "Current Ratio gestiegen", cr_t, vgl(cr_t, cr_v), "Liquidität verbessert."),
        ("aktien", "Keine neuen Aktien ausgegeben", ak_t, None if ak_t is None or ak_v is None else ak_t <= ak_v * 1.001,
         "Aktienanzahl nicht gestiegen (keine Verwässerung)."),
        ("bruttomarge", "Bruttomarge gestiegen", gm_t, vgl(gm_t, gm_v), "Preissetzungsmacht/Kosten verbessert."),
        ("umschlag", "Kapitalumschlag gestiegen", at_t, vgl(at_t, at_v), "Umsatz / Bilanzsumme (Vorjahr) gestiegen."),
    ]


@registriere("piotroski", "Piotroski F-Score", "Risiko", 90)
def check(f, kx):
    J = f.get("jahre") or []
    if len(J) < 2:
        return ergebnis("piotroski", "Piotroski F-Score", "Neun Bilanzsignale: Wird die Firma stärker oder schwächer?",
                        "Risiko", [], f, fazit="Mindestens zwei Geschäftsjahre nötig.", info=INFO)
    fmt = {"roa": "pctf", "cfo": "geld", "roa_delta": "ppf", "accrual": "geld", "leverage": "pctf",
           "current_ratio": "x", "aktien": "stueck", "bruttomarge": "pctf", "umschlag": "x"}
    kr = [kriterium(i, n, w, "", ok, e, fmt=fmt[i])
          for i, n, w, ok, e in signale(J[-1], J[-2], J[-3] if len(J) >= 3 else None)]
    ergeb = ergebnis("piotroski", "Piotroski F-Score", "Neun Bilanzsignale: Wird die Firma stärker oder schwächer?",
                     "Risiko", kr, f, info=INFO)
    pkt, n = ergeb["erfuellt"], ergeb["gesamt"]
    if n >= 6:
        # Hochrechnung auf 9 nur fuer den Score; angezeigt wird "F x von n"
        ergeb["score_0_100"] = 100.0 * pkt / n
        stark, schwach = C.PIOTROSKI["stark_ab"], C.PIOTROSKI["schwach_bis"]
        f9 = pkt if n == 9 else round(pkt * 9 / n)
        ergeb["fazit"] = (f"F-Score {pkt} von {n}" + ("" if n == 9 else f" (≈ {f9} von 9)") + " – " +
                          ("stark." if f9 >= stark else "schwach." if f9 <= schwach else "durchschnittlich."))
        ergeb["kauf"] = f9 >= stark - 1
    else:
        ergeb["score_0_100"], ergeb["kauf"] = None, False
        ergeb["fazit"] = "Zu wenige Signale berechenbar."
    return ergeb
