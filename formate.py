"""Zahlenformate fuer die ganze App - EINE Quelle (UX 10/2026).

Deutsche Schreibweise: Punkt = Tausender, Komma = Dezimal, kaufmaennisch gerundet.
Einheit mit geschuetztem Leerzeichen ("1.234,56 €", "+2,3 %") - so bricht sie nie allein in
die naechste Zeile. Minus als typografisches Minus (U+2212), Plus nur auf Wunsch (vz=True).
Werte, die auf 0 runden, bekommen nie ein Minus ("-0,00 €" gibt es nicht).

Konvention: Ist-Werte (Depot, Positionen, Gewinne) mit Cent (nk=2), Planungs- und
Prognosewerte ganzzahlig (nk=0), Kurse mit 2 Nachkommastellen.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

NBSP = " "
MINUS = "−"
LEER = "–"


def runden(wert, nk=2):
    """Kaufmaennisch runden (0,5 aufwaerts, ab der Dezimaldarstellung): 2,675 -> 2,68 statt 2,67 bei
    der binaeren Gleitkomma-Rundung. -> float"""
    return float(Decimal(repr(float(wert))).quantize(Decimal(1).scaleb(-nk), rounding=ROUND_HALF_UP))


def zahl(wert, nk=2, vz=False, minus=MINUS):
    """1234.5 -> '1.234,50'; vz=True -> '+1.234,50'. None/ungueltig -> '–'."""
    try:
        v = runden(wert, max(nk, 0)) + 0.0          # + 0.0: -0.0 -> 0.0
    except (TypeError, ValueError, ArithmeticError, InvalidOperation):
        return LEER
    if v != v or v in (float("inf"), float("-inf")):
        return LEER
    s = f"{abs(v):,.{max(nk, 0)}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if v < 0:
        return minus + s
    return ("+" + s) if vz else s


def eur(wert, nk=2, vz=False, minus=MINUS):
    """'1.234,56 €' (vz=True: '+1.234,56 €')."""
    z = zahl(wert, nk, vz, minus)
    return z if z == LEER else f"{z}{NBSP}€"


def pct(wert, nk=1, vz=False, minus=MINUS):
    """Prozentwert, bereits in Prozent: 2.345 -> '2,3 %' (vz=True: '+2,3 %')."""
    z = zahl(wert, nk, vz, minus)
    return z if z == LEER else f"{z}{NBSP}%"


def kurs(wert, nk=2):
    """Kurs je Stueck: '150,00 €'."""
    return eur(wert, nk)


def richtung(wert, nk=2):
    """'up' / 'down' / 'flat' nach dem gerundeten Wert - fuer Farbe UND Pfeil (nie nur Farbe)."""
    try:
        v = runden(wert, nk)
    except (TypeError, ValueError, ArithmeticError, InvalidOperation):
        return "flat"
    return "up" if v > 0 else "down" if v < 0 else "flat"


PFEIL = {"up": "▲", "down": "▼", "flat": "■"}
