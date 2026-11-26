"""Pyramidenrechner - Rechenkern (ohne Streamlit). Reine Planrechnung: keine Kursdaten, kein Depot, keine Buchungen.

Stufe i (ab 0): Stueckzahl = Startstueckzahl x Multiplikator^i
                Stueckpreis = eigener Preis der Stufe, sonst Startpreis x (1 + Preisaenderung %)^i (automatisch),
                ohne automatische Preisaenderung der Startpreis
Preise werden wahlweise als Stueckpreis oder als Gesamtpreis der Stufe eingegeben (modus "stueck"/"gesamt").
Rechnet mit Decimal; Eingaben wie im Durchschnittskurs-Rechner (deutsches Format, bis 8 Nachkommastellen)."""
from decimal import Decimal

import durchschnittskurs as DK

MAX_STUFEN = 50
MODI = {"stueck": "Stückpreis", "gesamt": "Gesamtpreis je Stufe"}
EingabeFehler = DK.EingabeFehler


def _prozent(text):
    """Preisaenderung in %: darf negativ sein (fallende Preise), groesser als -100."""
    s = str(text or "").strip().replace(" ", "").replace("%", "")
    if not s:
        return Decimal(0)
    neg = s.startswith(("-", "−"))
    d = DK.zahl(s.lstrip("-−+"), "Preisänderung", null_erlaubt=True)
    d = -d if neg else d
    if d <= -100:
        raise EingabeFehler("Die Preisänderung muss über −100 % liegen.")
    if d > 1000:
        raise EingabeFehler("Die Preisänderung ist zu groß.")
    return d


def parameter(start_stueck, start_preis, multiplikator="2", modus="stueck", auto=False, aenderung_pct="",
              budget=""):
    """Eingaben pruefen -> dict mit Decimal-Werten. Wirft EingabeFehler."""
    modus = modus if modus in MODI else "stueck"
    s = DK.zahl(start_stueck, "Startstückzahl")
    p = DK.zahl(start_preis, "Startpreis")
    m = DK.zahl(multiplikator, "Multiplikator")
    if m > 100:
        raise EingabeFehler("Der Multiplikator ist zu groß (höchstens 100).")
    b = DK.zahl(budget, "Budget", leer_null=True, null_erlaubt=True)
    return {"start_stueck": s, "start_preis": p / s if modus == "gesamt" else p, "multiplikator": m, "modus": modus,
            "auto": bool(auto), "aenderung": _prozent(aenderung_pct) if auto else Decimal(0),
            "budget": b if b > 0 else None}


def stueck(p, i):
    return p["start_stueck"] * p["multiplikator"] ** i


def auto_preis(p, i):
    """Stueckpreis der Stufe i ohne eigenen Preis."""
    return p["start_preis"] * (1 + p["aenderung"] / 100) ** i


def stufen(p, anzahl, eigene=None):
    """-> (Zeilen, Fehler). eigene: {index: Preistext} (je Modus Stueck- oder Gesamtpreis der Stufe).
    Zeile: stufe, stueck, preis (je Stueck), kosten, eigen, stueck_ges, kosten_ges, durchschnitt, im_budget."""
    n = max(0, min(int(anzahl), MAX_STUFEN))
    zeilen, fehler = [], []
    s_ges, k_ges = Decimal(0), Decimal(0)
    for i in range(n):
        st = stueck(p, i)
        preis, eigen = auto_preis(p, i), False
        text = str((eigene or {}).get(i) or "").strip() if i > 0 else ""
        if text:
            try:
                wert = DK.zahl(text, f"Preis Stufe {i + 1}")
                preis, eigen = (wert / st if p["modus"] == "gesamt" else wert), True
            except EingabeFehler as ex:
                fehler.append((i + 1, str(ex)))
        kosten = st * preis
        s_ges += st
        k_ges += kosten
        zeilen.append({"stufe": i + 1, "stueck": st, "preis": preis, "kosten": kosten, "eigen": eigen,
                       "stueck_ges": s_ges, "kosten_ges": k_ges, "durchschnitt": k_ges / s_ges,
                       "im_budget": p["budget"] is None or k_ges <= p["budget"]})
    return zeilen, fehler


def weitere_finanzierbar(p, zeilen, grenze=MAX_STUFEN):
    """Wie viele weitere Stufen (mit Multiplikator, automatischem Preis) passen noch ins Budget?"""
    if p["budget"] is None:
        return None
    rest = p["budget"] - (zeilen[-1]["kosten_ges"] if zeilen else Decimal(0))
    n, i = 0, len(zeilen)
    while i < grenze:
        kosten = stueck(p, i) * auto_preis(p, i)
        if kosten > rest:
            break
        rest -= kosten
        n += 1
        i += 1
    return n


def bis_budget(p, eigene=None):
    """Groesste Stufenzahl, deren Gesamtkosten das Budget nicht uebersteigen (mindestens 1). Ohne Budget: None."""
    if p["budget"] is None:
        return None
    zeilen, _ = stufen(p, MAX_STUFEN, eigene)
    n = sum(1 for z in zeilen if z["im_budget"])
    return max(1, n)


def uebersicht(p, zeilen):
    letzte = zeilen[-1] if zeilen else None
    gesamt = letzte["kosten_ges"] if letzte else Decimal(0)
    return {"stufen": len(zeilen), "stueck": letzte["stueck_ges"] if letzte else Decimal(0), "kosten": gesamt,
            "durchschnitt": letzte["durchschnitt"] if letzte else None,
            "budget": p["budget"], "rest": p["budget"] - gesamt if p["budget"] is not None else None,
            "ueber_budget": p["budget"] is not None and gesamt > p["budget"],
            "weitere": weitere_finanzierbar(p, zeilen)}


def eigene_verschieben(eigene, entfernt):
    """Eigene Preise nach dem Entfernen der Stufe mit Index `entfernt` neu zuordnen."""
    aus = {}
    for i, t in (eigene or {}).items():
        if i < entfernt:
            aus[i] = t
        elif i > entfernt:
            aus[i - 1] = t
    return aus
