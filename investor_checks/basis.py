"""Gemeinsame Bausteine der Investoren-Checks: Kriterium, Ergebnis, sichere Rechenhilfen, Sektor-Typ.

Einheitliches Rueckgabeformat je Check (siehe ergebnis()):
  {id, investor, strategie, kategorie, kriterien: [{id, name, wert, schwelle, status (pass/fail/na), erklaerung,
   eingeschraenkt}], erfuellt, gesamt, score_0_100, fazit, extras, warnungen, badges, ausgeblendet, datenbasis}
"""
import math

import investor_config as C

PASS, FAIL, NA = "pass", "fail", "na"
ZYKLISCH_HINWEIS_IDS = ("kgv", "kgv_abschlag")


def schwelle_versorger(f, wert, art):
    """Versorger (Abschnitt 10): niedrigere Wachstums-, hoehere Schuldenschwellen. art: "wachstum"/"schulden"."""
    if sektor_typ(f) != "versorger":
        return wert
    return wert * (C.VERSORGER_WACHSTUM_FAKTOR if art == "wachstum" else C.VERSORGER_SCHULDEN_FAKTOR)


# ---------------------------------------------------------------------------
# Rechenhilfen (fehlerrobust: None statt Ausnahme bei fehlenden Werten / Division durch 0)
# ---------------------------------------------------------------------------
def zahl(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def de(x, n=1):
    """Zahl im deutschen Format (Komma als Dezimaltrennzeichen) fuer Erklaerungstexte."""
    x = zahl(x)
    return "n/a" if x is None else f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def teile(a, b):
    """a / b; None bei fehlenden Werten oder b == 0."""
    a, b = zahl(a), zahl(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def pct(a, b):
    v = teile(a, b)
    return None if v is None else v * 100.0


def wachstum(neu, alt):
    """Veraenderung in % (alt -> neu). Bei negativem/null Ausgangswert nicht sinnvoll -> None."""
    neu, alt = zahl(neu), zahl(alt)
    if neu is None or alt is None or alt <= 0:
        return None
    return (neu / alt - 1) * 100.0


def cagr(neu, alt, jahre):
    """Durchschnittliches Wachstum p. a. in % - nur fuer positive Anfangs- und Endwerte definiert."""
    neu, alt = zahl(neu), zahl(alt)
    if neu is None or alt is None or alt <= 0 or neu <= 0 or not jahre or jahre <= 0:
        return None
    return ((neu / alt) ** (1.0 / jahre) - 1) * 100.0


def mittel(werte):
    w = [x for x in (zahl(v) for v in werte) if x is not None]
    return sum(w) / len(w) if w else None


def reihe(f, feld):
    """Werte eines Feldes ueber alle Jahre (aelteste zuerst), fehlende als None."""
    return [zahl(j.get(feld)) for j in f.get("jahre") or []]


def vorhanden(werte):
    return [w for w in werte if w is not None]


def letztes(f, feld, rueck=0):
    """Wert im juengsten (rueck=0) bzw. vorherigen (rueck=1) Geschaeftsjahr."""
    j = f.get("jahre") or []
    if len(j) <= rueck:
        return None
    return zahl(j[-1 - rueck].get(feld))


# ---------------------------------------------------------------------------
# Sektor-Typ (Abschnitt 10)
# ---------------------------------------------------------------------------
def sektor_typ(f):
    """bank / reit / versorger / zyklisch / normal - aus Yahoo-Sektor und -Branche."""
    text = f"{f.get('sektor') or ''} {f.get('branche') or ''}".lower()
    if any(s in text for s in C.SEKTOR_REIT):
        return "reit"
    if any(s in text for s in C.SEKTOR_BANK):
        return "bank"
    if any(s in text for s in C.SEKTOR_VERSORGER):
        return "versorger"
    if f.get("zyklisch") or any(s in text for s in C.SEKTOR_ZYKLISCH):
        return "zyklisch"
    return "normal"


# ---------------------------------------------------------------------------
# Kriterium und Ergebnis
# ---------------------------------------------------------------------------
def kriterium(kid, name, wert, schwelle, ok, erklaerung, eingeschraenkt=None, fmt=None):
    """ok: True/False/None (None = nicht berechenbar -> n/a). wert/schwelle: Anzeige-Texte oder Zahlen."""
    return {"id": kid, "name": name, "wert": wert, "schwelle": schwelle,
            "status": NA if ok is None else PASS if ok else FAIL, "erklaerung": erklaerung,
            "eingeschraenkt": eingeschraenkt, "fmt": fmt}


def datenbasis(f, soll=C.SOLL_JAHRE):
    n = len(f.get("jahre") or [])
    return f"{n} von {soll} Jahren geprüft" if n < soll else f"{n} Jahre geprüft"


def ergebnis(cid, investor, strategie, kategorie, kriterien, f, extras=(), warnungen=(), badges=(),
             score=None, fazit=None, info=""):
    """Baut das einheitliche Ergebnis; blendet Kriterien nach Sektor-Typ aus (mit Begruendung).
    score: eigener Score 0-100 (z. B. Piotroski 0-9 -> %), sonst Anteil erfuellter bewertbarer Kriterien."""
    typ = sektor_typ(f)
    regel = (C.AUSBLENDEN.get(typ) or {}).get(cid)
    ausgeblendet = []
    if regel:
        grund = C.SEKTOR_GRUND.get(typ, "")
        if regel == "alle":
            ausgeblendet = [{"name": k["name"], "grund": grund} for k in kriterien]
            kriterien = []
        else:
            ausgeblendet = [{"name": k["name"], "grund": grund} for k in kriterien if k["id"] in regel]
            kriterien = [k for k in kriterien if k["id"] not in regel]
    if typ == "zyklisch":
        for k in kriterien:
            if k["id"] in ZYKLISCH_HINWEIS_IDS and "Zykliker" not in k["erklaerung"]:
                k["erklaerung"] += (" Zykliker: Ein niedriges KGV kann ein Zyklus-Hoch bedeuten – maßgeblich ist der "
                                    "Durchschnitt über den Zyklus.")
    bewertbar = [k for k in kriterien if k["status"] != NA]
    erfuellt = sum(1 for k in bewertbar if k["status"] == PASS)
    if regel == "alle":
        # Modell gilt fuer diesen Sektor nicht: auch Zusatzwerte, Warnungen und ein vorgegebenes Fazit verwerfen
        score, extras, warnungen, badges = None, (), (), ()
        fazit = "Für diesen Sektor nicht anwendbar."
    elif score is None:
        score = 100.0 * erfuellt / len(bewertbar) if len(bewertbar) >= C.MIN_BEWERTBAR else None
    if fazit is None:
        if regel == "alle":
            fazit = "Für diesen Sektor nicht anwendbar."
        elif score is None:
            fazit = "Zu wenige Daten für ein Urteil."
        else:
            fazit = ("Besteht die Kriterien." if score >= C.KAUFEN_AB_SCORE else
                     "Besteht die Kriterien teilweise." if score >= 40 else "Fällt durch.")
    return {"id": cid, "investor": investor, "strategie": strategie, "kategorie": kategorie, "info": info,
            "kriterien": kriterien, "erfuellt": erfuellt, "gesamt": len(bewertbar), "anzahl": len(kriterien),
            "score_0_100": score, "fazit": fazit, "extras": list(extras), "warnungen": list(warnungen),
            "badges": list(badges), "ausgeblendet": ausgeblendet, "datenbasis": datenbasis(f),
            "sektor_typ": typ, "kauf": score is not None and score >= C.KAUFEN_AB_SCORE}


def extra(name, wert, text, fmt=None):
    return {"name": name, "wert": wert, "text": text, "fmt": fmt}
