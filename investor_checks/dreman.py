"""David Dreman - Contrarian Investing.

Quelle: D. Dreman, "Contrarian Investment Strategies: The Next Generation" (1998): Aktien aus den
guenstigsten 20 % des Marktes nach KGV, KBV, KCV oder hoechster Dividendenrendite, ergaenzt um
Qualitaetsfilter (solide Bilanz, ueberdurchschnittliche Rentabilitaet).

Vergleich ueber die Top-500-Liste mit den Agenten-Kennzahlen: KGV, Kurs/Free-Cashflow (= 1 / FCF-Rendite,
Naeherung fuer das KCV) und Dividendenrendite. Ein KBV liegt fuer die Liste nicht vor -> n/a.
"""
import investor_config as C
import scoring as SC

from . import registriere
from .basis import de, ergebnis, kriterium, letztes, teile, zahl

INFO = ("David Dreman (*1936), Pionier des „Contrarian Investing“: Der Markt übertreibt bei unbeliebten Aktien – "
        "wer die billigsten soliden Firmen kauft, profitiert, wenn sich die Stimmung dreht.")


def guenstig_perzentil(ver, key, wert, richtung):
    """Anteil der Top-500-Aktien, die bei dieser Kennzahl SCHLECHTER (teurer) sind - 0..100."""
    liste = (ver or {}).get(("aktie", key)) or []
    return SC.perzentil(liste, SC._vergleichswert(key, wert), richtung)


@registriere("dreman", "David Dreman", "Value", 40)
def check(f, kx):
    cfg = C.DREMAN
    ver = (kx or {}).get("verteilungen") or {}
    k = ((kx or {}).get("agent") or {}).get("k") or {}
    grenze = 100 - cfg["anteil"]          # guenstigste 20 % = besser als 80 %
    kgv = zahl(k.get("kgv")) or zahl(k.get("fkgv"))
    p_kgv = guenstig_perzentil(ver, "kgv" if k.get("kgv") else "fkgv", kgv, -1) if kgv else None
    fcfy = zahl(k.get("fcfy"))
    p_kcv = guenstig_perzentil(ver, "fcfy", fcfy, +1) if fcfy is not None else None
    div = zahl(k.get("div"))
    p_div = guenstig_perzentil(ver, "div", div, +1) if div is not None else None
    kbv = f.get("kbv")

    def stufe(p):
        return None if p is None else p >= grenze

    teil = [stufe(p_kgv), stufe(p_kcv), stufe(p_div)]
    treffer = sum(1 for t in teil if t)
    bewertbar = sum(1 for t in teil if t is not None)
    kr = [
        kriterium("kgv", "KGV in den günstigsten 20 %", kgv, f"besser als {grenze:.0f} %", stufe(p_kgv),
                  f"Günstiger als {p_kgv:.0f} % der Top-500-Aktien." if p_kgv is not None else "Kein KGV verfügbar.",
                  fmt="x"),
        kriterium("kbv", "KBV in den günstigsten 20 %", kbv, f"besser als {grenze:.0f} %", None,
                  "Für die Top-500-Liste liegt kein KBV vor – nicht vergleichbar.", fmt="x"),
        kriterium("kcv", "Kurs/Cashflow in den günstigsten 20 %", teile(100, fcfy) if fcfy and fcfy > 0 else None,
                  f"besser als {grenze:.0f} %", stufe(p_kcv),
                  "Näherung über die Free-Cashflow-Rendite (Kurs / FCF)." +
                  (f" Günstiger als {p_kcv:.0f} %." if p_kcv is not None else ""), fmt="x"),
        kriterium("div", "Dividendenrendite in den höchsten 20 %", div, f"besser als {grenze:.0f} %", stufe(p_div),
                  f"Höher als bei {p_div:.0f} % der Top-500-Aktien." if p_div is not None else
                  "Keine Dividendenrendite verfügbar.", fmt="pct"),
        kriterium("mind2", f"Mind. {cfg['min_treffer']} der Bewertungskriterien", f"{treffer} von {bewertbar}",
                  str(cfg["min_treffer"]), None if bewertbar < cfg["min_treffer"] else treffer >= cfg["min_treffer"],
                  "Dreman verlangt Günstigkeit bei mindestens zwei Maßstäben.", fmt="text"),
    ]
    cr = teile(letztes(f, "umlauf"), letztes(f, "kurzfr_verb"))
    nde, p_nde = zahl(k.get("nde")), None
    if nde is not None:
        sek = ver.get(("aktie", "nde", (kx or {}).get("agent", {}).get("sektor"))) or ver.get(("aktie", "nde"))
        p_nde = SC.perzentil(sek or [], nde, -1)
    ok_q = (cr is not None and cr > cfg["min_current_ratio"]) or (p_nde is not None and p_nde >= 50)
    kr.append(kriterium("qualitaet_cr", "Solide Bilanz", f"Current Ratio {de(cr)}" if cr is not None else
                        (f"Verschuldung besser als {p_nde:.0f} %" if p_nde is not None else None),
                        "CR > 2 oder Schulden unter Sektorschnitt",
                        None if cr is None and p_nde is None else ok_q,
                        "Current Ratio über 2 oder Nettoverschuldung/EBITDA unter dem Durchschnitt.", fmt="text"))
    roe = zahl(k.get("roe"))
    p_roe = SC.perzentil(ver.get(("aktie", "roe")) or [], roe, +1) if roe is not None else None
    kr.append(kriterium("roe", "ROE im oberen Drittel", roe, "besser als 67 %", None if p_roe is None else p_roe >= 66.7,
                        f"Besser als {p_roe:.0f} % der Top-500-Aktien." if p_roe is not None else "Kein ROE verfügbar.",
                        fmt="pct"))
    return ergebnis("dreman", "David Dreman", "Contrarian: die billigsten soliden Aktien kaufen.", "Value",
                    kr, f, info=INFO)
