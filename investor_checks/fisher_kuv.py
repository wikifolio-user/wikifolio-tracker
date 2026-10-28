"""Kenneth Fisher - Price/Sales (Kurs-Umsatz-Verhaeltnis).

Quelle: K. Fisher, "Super Stocks" (1984): KUV < 0,75 attraktiv, > 3 meiden. Ergaenzt um einen Margen-Check,
damit ein niedriges KUV nicht nur eine Verlustfirma kennzeichnet.
"""
import investor_config as C

from . import registriere
from .basis import ergebnis, kriterium, letztes, mittel, pct, teile, zahl

INFO = ("Kenneth Fisher (*1950), Sohn von Philip Fisher und Gründer von Fisher Investments, machte das "
        "Kurs-Umsatz-Verhältnis bekannt: Umsatz schwankt weniger als Gewinn und lässt sich kaum schönrechnen.")


def kuv(f):
    """Boersenwert / Umsatz (in Berichtswaehrung); Fallback: Yahoo-Wert."""
    faktor = teile(f.get("kurs_in_bericht"), f.get("kurs"))
    ums = letztes(f, "umsatz")
    if f.get("mcap") and faktor and ums and ums > 0:
        return f["mcap"] * faktor / ums
    return zahl(f.get("kuv"))


@registriere("fisher_kuv", "Kenneth Fisher", "Value", 60)
def check(f, kx):
    cfg = C.FISHER_KUV
    v = kuv(f)
    nm = mittel(pct(j.get("nettogewinn"), j.get("umsatz")) for j in f.get("jahre") or [])
    kr = [kriterium("kuv", "KUV attraktiv", v, f"< {cfg['attraktiv']}".replace(".", ","),
                    None if v is None else v < cfg["attraktiv"], "Börsenwert im Verhältnis zum Jahresumsatz.", fmt="x"),
          kriterium("kuv_max", "KUV nicht zu hoch", v, f"≤ {cfg['meiden']:.0f}", None if v is None else v <= cfg["meiden"],
                    "Über 3 rät Fisher zu meiden.", fmt="x"),
          kriterium("marge", "Nettomarge positiv und ausreichend", nm, f"≥ {cfg['min_nettomarge']:.0f} %",
                    None if nm is None else nm >= cfg["min_nettomarge"],
                    "Damit ein niedriges KUV nicht nur auf Verluste zurückgeht.", fmt="pct")]
    return ergebnis("fisher_kuv", "Kenneth Fisher", "Niedriges Kurs-Umsatz-Verhältnis bei gesunder Marge.", "Value",
                    kr, f, info=INFO)
