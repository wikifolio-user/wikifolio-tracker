"""John Templeton - Kaufen beim maximalen Pessimismus.

Quelle: J. Templeton, "16 Rules for Investment Success" (1993) und Templeton-Fondsberichte: Kaufen, wenn der Kurs
nahe am Tief ist und die Bewertung weit unter dem eigenen historischen Niveau liegt - aber nur bei solider
Bilanz (sonst "Value Trap").
"""
import investor_config as C

from . import registriere
from .basis import ergebnis, kriterium, letztes, mittel, teile, zahl
from .daten import kurs_tief_hoch
from .buffett import kurs_am

INFO = ("Sir John Templeton (1912–2008), Gründer der Templeton-Fonds: „Die Zeit maximalen Pessimismus ist die "
        "beste Zeit zum Kaufen.“ Er suchte weltweit nach Aktien, die niemand mehr wollte.")


def historisches_kgv(f):
    """KGV je Geschaeftsjahr = Kurs am Geschaeftsjahresende / EPS (nur positive EPS). -> Liste."""
    faktor = teile(f.get("kurs_in_bericht"), f.get("kurs")) or 1.0
    aus = []
    for j in f.get("jahre") or []:
        eps, k = zahl(j.get("eps")), kurs_am(f, j["datum"])
        if eps and eps > 0 and k:
            aus.append(k * faktor / eps)
    return aus


@registriere("templeton", "John Templeton", "Value", 50)
def check(f, kx):
    cfg, bil = C.TEMPLETON, C.TEMPLETON_BILANZ
    kurs = (f.get("kurse") or [[None, None]])[-1][1] if f.get("kurse") else f.get("kurs")
    t52, _ = kurs_tief_hoch(f, 365)
    t5, _ = kurs_tief_hoch(f, 5 * 365)
    ab52 = (kurs / t52 - 1) * 100 if kurs and t52 else None
    ab5 = (kurs / t5 - 1) * 100 if kurs and t5 else None
    kgvs = historisches_kgv(f)
    eps = letztes(f, "eps")
    kgv_jetzt = teile(f.get("kurs_in_bericht"), eps) if eps and eps > 0 else None
    kgv_hist = mittel(kgvs[:-1] or kgvs)
    abschlag = (1 - kgv_jetzt / kgv_hist) * 100 if kgv_jetzt and kgv_hist else None
    n_kgv = len(kgvs)
    kr = [
        kriterium("tief52", "Kurs nahe 52-Wochen-Tief", ab52, f"≤ {cfg['max_abstand_tief']:.0f} % darüber",
                  None if ab52 is None else ab52 <= cfg["max_abstand_tief"], "Abstand zum Tief der letzten 12 Monate.",
                  fmt="pct"),
        kriterium("tief5", "Kurs nahe 5-Jahres-Tief", ab5, f"≤ {cfg['max_abstand_tief']:.0f} % darüber",
                  None if ab5 is None else ab5 <= cfg["max_abstand_tief"], "Abstand zum Tief der letzten 5 Jahre.",
                  fmt="pct"),
        kriterium("kgv_abschlag", "KGV unter eigenem Durchschnitt", abschlag, f"≥ {cfg['min_abschlag_kgv']:.0f} % Abschlag",
                  None if abschlag is None else abschlag >= cfg["min_abschlag_kgv"],
                  "Aktuelles KGV vs. Ø-KGV der früheren Geschäftsjahre (Kurs am Jahresende / EPS)."
                  if abschlag is not None else "Kein positiver Gewinn bzw. zu kurze Historie.",
                  eingeschraenkt=f"{n_kgv} von 5 Jahren" if 0 < n_kgv < 5 else None, fmt="pct"),
    ]
    ekq = teile(letztes(f, "ek"), letztes(f, "bilanzsumme"))
    ekq = ekq * 100 if ekq is not None else None
    zd = teile(letztes(f, "ebit"), letztes(f, "zinsaufwand"))
    if zd is None and letztes(f, "ebit") is not None and not letztes(f, "zinsaufwand") and \
            (letztes(f, "schulden") or 0) == 0:
        zd = float("inf")
    solide = None if ekq is None else ekq >= bil["min_ek_quote"] and (zd is None or zd >= bil["min_zinsdeckung"])
    kr.append(kriterium("bilanz", "Solide Bilanz", f"EK-Quote {ekq:.0f} %" if ekq is not None else None,
                        f"EK-Quote ≥ {bil['min_ek_quote']:.0f} %, Zinsdeckung ≥ {bil['min_zinsdeckung']:.0f}",
                        solide, "Ohne solide Bilanz ist ein tiefer Kurs oft berechtigt (Value Trap).", fmt="text"))
    warn = []
    guenstig = any(k["status"] == "pass" for k in kr[:3])
    if guenstig and solide is False:
        warn.append("Templeton: Kurs/Bewertung günstig, aber Bilanz schwach – mögliche Value Trap.")
    return ergebnis("templeton", "John Templeton", "Kaufen, wenn alle verkaufen – mit solider Bilanz.", "Value",
                    kr, f, warnungen=warn, info=INFO)
