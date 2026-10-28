"""Altman Z-Score - Insolvenzrisiko.

Quelle: E. Altman, "Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy",
Journal of Finance 23 (1968): Z = 1,2A + 1,4B + 3,3C + 0,6D + 1,0E (Produzierende);
E. Altman, "Corporate Financial Distress and Bankruptcy" (2. Aufl. 1993): Z'' = 6,56A + 3,26B + 6,72C + 1,05D
fuer Nicht-Produzierende (D mit Buchwert des Eigenkapitals). Fuer Banken/Versicherungen nicht anwendbar.
"""
import investor_config as C

from . import registriere
from .basis import ergebnis, extra, kriterium, letztes, teile

INFO = ("Edward Altman (*1941), Professor an der NYU, entwickelte 1968 den Z-Score: fünf Bilanzkennzahlen, "
        "gewichtet zu einer Zahl, die das Pleiterisiko der nächsten zwei Jahre einschätzt.")


def ist_produzierend(f):
    text = f"{f.get('sektor') or ''} {f.get('branche') or ''}".lower()
    return any(s in text for s in C.ALTMAN_PRODUZIERENDE)


def z_score(f, produzierend=None):
    """-> {z, modell, teile: {A..E}} oder None (zu wenige Daten)."""
    ta = letztes(f, "bilanzsumme")
    if not ta or ta <= 0:
        return None
    umlauf, kv = letztes(f, "umlauf"), letztes(f, "kurzfr_verb")
    re_, ebit = letztes(f, "gewinnruecklagen"), letztes(f, "ebit")
    tl = letztes(f, "verbindlichkeiten")
    if None in (umlauf, kv, re_, ebit) or not tl:
        return None
    A, B, C_, = (umlauf - kv) / ta, re_ / ta, ebit / ta
    produzierend = ist_produzierend(f) if produzierend is None else produzierend
    if produzierend:
        faktor = teile(f.get("kurs_in_bericht"), f.get("kurs"))
        mve = f["mcap"] * faktor if f.get("mcap") and faktor else None
        umsatz = letztes(f, "umsatz")
        if mve is None or umsatz is None:
            return None
        D, E = mve / tl, umsatz / ta
        z = 1.2 * A + 1.4 * B + 3.3 * C_ + 0.6 * D + 1.0 * E
        return {"z": z, "modell": "Z (Produzierende)", "teile": {"A": A, "B": B, "C": C_, "D": D, "E": E}}
    ek = letztes(f, "ek")
    if ek is None:
        return None
    D = ek / tl
    z = 6.56 * A + 3.26 * B + 6.72 * C_ + 1.05 * D
    return {"z": z, "modell": "Z'' (Nicht-Produzierende)", "teile": {"A": A, "B": B, "C": C_, "D": D}}


def zone(z, produzierend):
    s = C.ALTMAN["sicher"] if produzierend else C.ALTMAN["sicher_2"]
    g = C.ALTMAN["grau"] if produzierend else C.ALTMAN["grau_2"]
    return "sicher" if z > s else "grau" if z >= g else "gefährdet"


TEILE_TEXT = {"A": "Working Capital / Bilanzsumme (Liquidität)", "B": "Gewinnrücklagen / Bilanzsumme (Alter, "
              "Selbstfinanzierung)", "C": "EBIT / Bilanzsumme (Ertragskraft)", "D": "Marktkap. (bzw. Buchwert EK) / "
              "Verbindlichkeiten (Puffer)", "E": "Umsatz / Bilanzsumme (Kapitalumschlag)"}


@registriere("altman", "Altman Z-Score", "Risiko", 100)
def check(f, kx):
    prod = ist_produzierend(f)
    z = z_score(f, prod)
    if z is None:
        return ergebnis("altman", "Altman Z-Score", "Wie hoch ist das Insolvenzrisiko?", "Risiko", [], f,
                        fazit="Zu wenige Bilanzdaten (Umlaufvermögen, Gewinnrücklagen, EBIT).", info=INFO)
    zo = zone(z["z"], prod)
    s = C.ALTMAN["sicher"] if prod else C.ALTMAN["sicher_2"]
    g = C.ALTMAN["grau"] if prod else C.ALTMAN["grau_2"]
    kr = [kriterium("z", z["modell"], z["z"], f"> {s:.2f} sicher · < {g:.2f} gefährdet".replace(".", ","),
                    zo == "sicher",
                    f"Zone: {zo}.", fmt="zahl")]
    kr[0]["zone"] = zo
    extras = [extra(k, v, TEILE_TEXT[k], fmt="zahl3") for k, v in z["teile"].items()]
    warn = [f"Altman Z-Score {z['z']:.2f}".replace(".", ",") + ": Gefahrenzone (Insolvenzrisiko erhöht)."] if zo == "gefährdet" else []
    score = {"sicher": 100.0, "grau": 50.0, "gefährdet": 0.0}[zo]
    return ergebnis("altman", "Altman Z-Score", "Wie hoch ist das Insolvenzrisiko?", "Risiko", kr, f, extras=extras,
                    warnungen=warn, score=score, fazit=f"{z['modell']}: {z['z']:.2f} – Zone „{zo}“.".replace(".", ",", 1), info=INFO)
