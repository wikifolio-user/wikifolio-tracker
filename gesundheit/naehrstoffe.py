"""Zentrale Naehrstoff-Tabelle und Einheiten-Umrechnung.

Jede Naehrstoffangabe im Modul (Lebensmittel, Getraenke, spaeter Supplements) ist ein dict {naehrstoff_id: menge}
in der Basiseinheit des Naehrstoffs. Ein FEHLENDER Schluessel heisst "unbekannt" - nicht 0 (siehe rechnen.summe).
Neue Naehrstoffe (Vitamine, Mineralstoffe … in Etappe 2) werden nur hier ergaenzt.
"""
from dataclasses import dataclass

KATEGORIEN = ("calorie", "macro", "vitamin", "mineral", "trace_element", "fatty_acid", "amino_acid", "other")


@dataclass(frozen=True)
class Naehrstoff:
    id: str
    name: str           # Anzeigename
    kategorie: str
    einheit: str        # Basiseinheit
    beschreibung: str = ""


NAEHRSTOFFE = {n.id: n for n in [
    Naehrstoff("kcal", "Kalorien", "calorie", "kcal", "Energie aus der Nahrung"),
    Naehrstoff("protein", "Protein", "macro", "g", "Eiweiß – Baustoff für Muskeln und Gewebe"),
    Naehrstoff("kh", "Kohlenhydrate", "macro", "g", "Hauptenergiequelle, z. B. aus Brot, Reis, Obst"),
    Naehrstoff("zucker", "davon Zucker", "macro", "g"),
    Naehrstoff("fett", "Fett", "macro", "g"),
    Naehrstoff("fett_ges", "davon gesättigte Fettsäuren", "fatty_acid", "g"),
    Naehrstoff("ballast", "Ballaststoffe", "macro", "g", "Unverdauliche Pflanzenfasern, gut für die Verdauung"),
    Naehrstoff("salz", "Salz", "mineral", "g"),
]}

# Hauptwerte der einfachen Ansicht (Reihenfolge der Anzeige)
MAKROS = ("kcal", "protein", "kh", "fett")

# Masseeinheiten -> Faktor zu Gramm
_MASSE = {"kg": 1000.0, "g": 1.0, "mg": 1e-3, "µg": 1e-6, "ug": 1e-6, "mcg": 1e-6}
_VOLUMEN = {"l": 1000.0, "L": 1000.0, "ml": 1.0}


def umrechnen(menge, von, nach):
    """Menge zwischen Masse- (kg, g, mg, µg) oder Volumeneinheiten (L, ml) umrechnen. -> float oder None, wenn die
    Einheiten nicht ineinander umrechenbar sind (z. B. g -> ml oder IE: dafuer gibt es keine allgemeine Regel)."""
    if menge is None:
        return None
    if von == nach:
        return float(menge)
    for tabelle in (_MASSE, _VOLUMEN):
        if von in tabelle and nach in tabelle:
            return float(menge) * tabelle[von] / tabelle[nach]
    return None
