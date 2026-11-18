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
    Naehrstoff("salz", "Salz", "other", "g"),
    # --- Vitamine
    Naehrstoff("vit_a", "Vitamin A", "vitamin", "µg", "Für Sehen, Haut und Abwehr (als Retinol-Äquivalent)"),
    Naehrstoff("vit_b1", "Vitamin B1 (Thiamin)", "vitamin", "mg", "Für den Energiestoffwechsel und die Nerven"),
    Naehrstoff("vit_b2", "Vitamin B2 (Riboflavin)", "vitamin", "mg", "Für den Energiestoffwechsel"),
    Naehrstoff("vit_b3", "Vitamin B3 (Niacin)", "vitamin", "mg", "Für den Energiestoffwechsel"),
    Naehrstoff("vit_b5", "Vitamin B5 (Pantothensäure)", "vitamin", "mg"),
    Naehrstoff("vit_b6", "Vitamin B6", "vitamin", "mg", "Für den Eiweißstoffwechsel"),
    Naehrstoff("vit_b7", "Biotin (B7)", "vitamin", "µg"),
    Naehrstoff("vit_b9", "Folat (B9)", "vitamin", "µg", "Für Zellteilung und Blutbildung"),
    Naehrstoff("vit_b12", "Vitamin B12", "vitamin", "µg", "Für Blutbildung und Nerven – vor allem in tierischen Lebensmitteln"),
    Naehrstoff("vit_c", "Vitamin C", "vitamin", "mg", "Für Abwehr und Bindegewebe"),
    Naehrstoff("vit_d", "Vitamin D", "vitamin", "µg", "Für Knochen – bildet der Körper auch selbst durch Sonnenlicht"),
    Naehrstoff("vit_e", "Vitamin E", "vitamin", "mg", "Schützt Zellen (Antioxidans)"),
    Naehrstoff("vit_k", "Vitamin K", "vitamin", "µg", "Für Blutgerinnung und Knochen"),
    # --- Mineralstoffe
    Naehrstoff("calcium", "Calcium", "mineral", "mg", "Für Knochen und Zähne"),
    Naehrstoff("magnesium", "Magnesium", "mineral", "mg", "Für Muskeln und Nerven"),
    Naehrstoff("kalium", "Kalium", "mineral", "mg", "Für Herz, Muskeln und Blutdruck"),
    Naehrstoff("natrium", "Natrium", "mineral", "mg", "Steckt vor allem im Kochsalz"),
    Naehrstoff("phosphor", "Phosphor", "mineral", "mg"),
    Naehrstoff("chlorid", "Chlorid", "mineral", "mg"),
    # --- Spurenelemente
    Naehrstoff("eisen", "Eisen", "trace_element", "mg", "Für den Sauerstofftransport im Blut"),
    Naehrstoff("zink", "Zink", "trace_element", "mg", "Für Abwehr und Wundheilung"),
    Naehrstoff("kupfer", "Kupfer", "trace_element", "mg"),
    Naehrstoff("mangan", "Mangan", "trace_element", "mg"),
    Naehrstoff("selen", "Selen", "trace_element", "µg"),
    Naehrstoff("jod", "Jod", "trace_element", "µg", "Für die Schilddrüse"),
    Naehrstoff("chrom", "Chrom", "trace_element", "µg"),
    Naehrstoff("molybdaen", "Molybdän", "trace_element", "µg"),
    Naehrstoff("fluorid", "Fluorid", "trace_element", "mg"),
    # --- Fettsaeuren und weitere
    Naehrstoff("omega3", "Omega-3-Fettsäuren", "fatty_acid", "g"),
    Naehrstoff("epa", "EPA (Omega-3)", "fatty_acid", "mg"),
    Naehrstoff("dha", "DHA (Omega-3)", "fatty_acid", "mg"),
    Naehrstoff("ala", "ALA (pflanzliches Omega-3)", "fatty_acid", "g"),
    Naehrstoff("omega6", "Omega-6-Fettsäuren", "fatty_acid", "g"),
    Naehrstoff("cholesterin", "Cholesterin", "other", "mg"),
    Naehrstoff("kreatin", "Kreatin", "amino_acid", "g"),
]}

# Gruppen der Mikronaehrstoff-Uebersicht (Anzeige-Reihenfolge)
GRUPPEN = [
    ("Vitamine", ["vit_a", "vit_b1", "vit_b2", "vit_b3", "vit_b5", "vit_b6", "vit_b7", "vit_b9", "vit_b12", "vit_c",
                  "vit_d", "vit_e", "vit_k"]),
    ("Mineralstoffe", ["calcium", "magnesium", "kalium", "natrium", "phosphor", "chlorid"]),
    ("Spurenelemente", ["eisen", "zink", "kupfer", "mangan", "selen", "jod", "chrom", "molybdaen", "fluorid"]),
    ("Fettsäuren & weitere", ["omega3", "epa", "dha", "ala", "omega6", "cholesterin", "kreatin"]),
]
MIKRO = [n for _, ids in GRUPPEN for n in ids]
# Einfache Ansicht: die Naehrstoffe, auf die im Alltag am haeufigsten geachtet wird
EINFACH = ["vit_d", "vit_c", "vit_b12", "vit_b9", "magnesium", "calcium", "eisen", "zink", "jod"]

# Internationale Einheiten: nur stoffabhaengig und fachlich definiert (sonst keine Umrechnung)
#   Vitamin D: 1 IE = 0,025 µg Cholecalciferol
#   Vitamin A: 1 IE = 0,3 µg Retinol (Retinol-Aequivalent)
#   Vitamin E: 1 IE = 0,67 mg natuerliches RRR-alpha-Tocopherol (synthetisches all-rac: 0,45 mg - hier nicht angenommen)
IE_FAKTOR = {"vit_d": ("µg", 0.025), "vit_a": ("µg", 0.3), "vit_e": ("mg", 0.67)}

# Hauptwerte der einfachen Ansicht (Reihenfolge der Anzeige)
MAKROS = ("kcal", "protein", "kh", "fett")

# Masseeinheiten -> Faktor zu Gramm
_MASSE = {"kg": 1000.0, "g": 1.0, "mg": 1e-3, "µg": 1e-6, "ug": 1e-6, "mcg": 1e-6}
_VOLUMEN = {"l": 1000.0, "L": 1000.0, "ml": 1.0}


def in_basis(naehrstoff, menge, einheit):
    """Menge eines Naehrstoffs in seine Basiseinheit (z. B. Vitamin D 1000 IE -> 25 µg, Magnesium 0,3 g -> 300 mg).
    -> float oder None (unbekannter Naehrstoff, unpassende Einheit, IE bei einem Stoff ohne definierte Umrechnung)."""
    n = NAEHRSTOFFE.get(naehrstoff)
    if n is None or menge is None:
        return None
    if einheit in ("IE", "IU"):
        e = IE_FAKTOR.get(naehrstoff)
        return umrechnen(float(menge) * e[1], e[0], n.einheit) if e else None
    return umrechnen(menge, einheit, n.einheit)


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
