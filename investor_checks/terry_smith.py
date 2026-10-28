"""Terry Smith (Fundsmith) - "Buy good companies, don't overpay, do nothing".

Quelle: Fundsmith-Aktionaersbriefe (jaehrlich seit 2010) und T. Smith, "Investing for Growth" (2020):
ROCE, Brutto- und operative Marge, Cash Conversion, Zinsdeckung, FCF-Rendite vs. Anleihen.
"""
import investor_config as C

from . import registriere
from .basis import de, ergebnis, kriterium, letztes, mittel, pct, teile, vorhanden

INFO = ("Terry Smith (*1953), Gründer von Fundsmith: kauft nur sehr profitable, kapitalleichte Qualitätsfirmen, "
        "die mehr Bargeld als Buchgewinn erzeugen – und hält sie möglichst lange.")


def roce(j):
    """ROCE = EBIT / (Bilanzsumme - kurzfristige Verbindlichkeiten) in %."""
    return pct(j.get("ebit"), (j.get("bilanzsumme") or 0) - (j.get("kurzfr_verb") or 0)) \
        if j.get("bilanzsumme") and j.get("kurzfr_verb") is not None else None


def zinsdeckung(f):
    """EBIT / Zinsaufwand. Ohne Zinsaufwand und ohne Schulden: unendlich (keine Zinslast)."""
    ebit, zins = letztes(f, "ebit"), letztes(f, "zinsaufwand")
    if ebit is None:
        return None
    if not zins:
        return float("inf") if (letztes(f, "schulden") or 0) == 0 else None
    return ebit / abs(zins)


@registriere("terry_smith", "Terry Smith", "Qualität", 70)
def check(f, kx):
    cfg = C.TERRY_SMITH
    J = f.get("jahre") or []
    r = mittel(roce(j) for j in J)
    gm = mittel(pct(j.get("bruttogewinn"), j.get("umsatz")) for j in J)
    om = mittel(pct(j.get("ebit"), j.get("umsatz")) for j in J)
    fcf, ni = vorhanden([j.get("fcf") for j in J]), vorhanden([j.get("nettogewinn") for j in J])
    cc = sum(fcf) / sum(ni) * 100 if fcf and ni and sum(ni) > 0 and len(fcf) == len(ni) else None
    zd = zinsdeckung(f)
    faktor = teile(f.get("kurs_in_bericht"), f.get("kurs"))
    mcap = f["mcap"] * faktor if f.get("mcap") and faktor else None
    fcfy = pct(letztes(f, "fcf"), mcap)
    kr = [kriterium("roce", "ROCE > 20 %", r, cfg["min_roce"], None if r is None else r > cfg["min_roce"],
                    "EBIT / eingesetztes Kapital (Bilanzsumme − kurzfr. Verbindlichkeiten), Ø der Jahre.", fmt="pct"),
          kriterium("bruttomarge", "Bruttomarge > 50 %", gm, cfg["min_bruttomarge"],
                    None if gm is None else gm > cfg["min_bruttomarge"], "Ø der Jahre.", fmt="pct"),
          kriterium("op_marge", "Operative Marge > 20 %", om, cfg["min_op_marge"],
                    None if om is None else om > cfg["min_op_marge"], "EBIT / Umsatz, Ø der Jahre.", fmt="pct"),
          kriterium("cash_conversion", "Cash Conversion > 90 %", cc, cfg["min_cash_conversion"],
                    None if cc is None else cc > cfg["min_cash_conversion"],
                    "Summe Free Cashflow / Summe Nettogewinn – wird der Gewinn zu Bargeld?", fmt="pct"),
          kriterium("zinsdeckung", "Zinsdeckung > 10", zd, cfg["min_zinsdeckung"],
                    None if zd is None else zd > cfg["min_zinsdeckung"], "EBIT / Zinsaufwand.", fmt="x"),
          kriterium("fcf_rendite", "FCF-Rendite über Staatsanleihe", fcfy, C.STAATSANLEIHE_10J,
                    None if fcfy is None else fcfy > C.STAATSANLEIHE_10J,
                    f"Free Cashflow / Börsenwert vs. 10-j. Staatsanleihe ({de(C.STAATSANLEIHE_10J)} %, Annahme "
                    f"{C.ANNAHMEN_STAND}).", fmt="pct")]
    return ergebnis("terry_smith", "Terry Smith", "Gute Firmen kaufen, nicht zu viel zahlen, nichts tun.",
                    "Qualität", kr, f, info=INFO)
