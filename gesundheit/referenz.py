"""Referenzwerte fuer Mikronaehrstoffe (Erwachsene) - eigene Tabelle, nicht in der Oberflaeche verdrahtet.

Zielwerte: D-A-CH-Referenzwerte (DGE/OeGE/SGE), gerundet und vereinfacht auf Altersgruppen ab 19 Jahren; bei
"Schaetzwert" gibt es keine genaue Empfehlung, nur eine Orientierung. Obere Werte (ul): tolerierbare Hoechstmengen
der EFSA - bei Magnesium gilt die Hoechstmenge nur fuer Supplemente (nicht fuer Lebensmittel).
Die Werte dienen nur dem rechnerischen Vergleich der dokumentierten Aufnahme - keine Diagnose, keine Beratung.
Neue Fassung: Zeilen ergaenzen und VERSION erhoehen; alte Zeilen bleiben fuer die Nachvollziehbarkeit erhalten.
"""
from dataclasses import dataclass

VERSION = "2026-11-v1"
QUELLE_ZIEL = "D-A-CH-Referenzwerte (DGE/ÖGE/SGE), gerundet"
QUELLE_UL = "EFSA – tolerierbare Höchstmenge"


@dataclass(frozen=True)
class Referenz:
    naehrstoff: str
    gruppe: str          # Berechnungsgruppe: "m", "w" oder "alle"
    alter_min: int
    alter_max: int       # einschliesslich
    ziel: float
    einheit: str
    ul: float = None     # oberer Referenzwert (None = keiner festgelegt)
    bemerkung: str = ""
    quelle: str = QUELLE_ZIEL
    version: str = VERSION


def _r(n, m, w, einheit, ul=None, bem="", ab=19, bis=120):
    if m == w:
        return [Referenz(n, "alle", ab, bis, m, einheit, ul, bem)]
    return [Referenz(n, "m", ab, bis, m, einheit, ul, bem), Referenz(n, "w", ab, bis, w, einheit, ul, bem)]


REFERENZWERTE = [
    *_r("vit_a", 850, 700, "µg", 3000, "als Retinol-Äquivalent; Höchstmenge gilt für vorgeformtes Retinol"),
    *_r("vit_b1", 1.2, 1.0, "mg"),
    *_r("vit_b2", 1.4, 1.1, "mg"),
    *_r("vit_b3", 15, 12, "mg", bem="Höchstmengen je nach Form verschieden"),
    *_r("vit_b5", 5, 5, "mg", bem="Schätzwert"),
    *_r("vit_b6", 1.6, 1.4, "mg", 12),
    *_r("vit_b7", 40, 40, "µg", bem="Schätzwert"),
    *_r("vit_b9", 300, 300, "µg", 1000, "Höchstmenge gilt für Folsäure aus Supplementen"),
    *_r("vit_b12", 4.0, 4.0, "µg", bem="Schätzwert"),
    *_r("vit_c", 110, 95, "mg"),
    *_r("vit_d", 20, 20, "µg", 100, "Schätzwert bei fehlender Eigenbildung durch Sonnenlicht"),
    *_r("vit_e", 14, 12, "mg", 300, "Schätzwert"),
    *_r("vit_k", 70, 60, "µg", bem="Schätzwert"),
    *_r("calcium", 1000, 1000, "mg", 2500),
    *_r("magnesium", 350, 300, "mg", 250, "Schätzwert; Höchstmenge nur für Supplemente"),
    *_r("kalium", 4000, 4000, "mg", bem="Schätzwert"),
    *_r("natrium", 1500, 1500, "mg", bem="Schätzwert – eher eine Obergrenze zur Orientierung als ein Ziel"),
    *_r("phosphor", 700, 700, "mg", bem="Schätzwert"),
    *_r("chlorid", 2300, 2300, "mg", bem="Schätzwert"),
    *_r("eisen", 11, 16, "mg", bis=50),
    *_r("eisen", 11, 14, "mg", ab=51),
    *_r("zink", 14, 8, "mg", 25, "bei mittlerer Phytatzufuhr (Vollkorn, Hülsenfrüchte)"),
    *_r("kupfer", 1.5, 1.25, "mg", 5, "Schätzwert"),
    *_r("mangan", 3.5, 3.5, "mg", bem="Schätzwert (Bereich 2–5 mg)"),
    *_r("selen", 70, 60, "µg", 255, "Schätzwert"),
    *_r("jod", 200, 200, "µg", 600, bis=50),
    *_r("jod", 180, 180, "µg", 600, ab=51),
    *_r("chrom", 30, 30, "µg", bem="Schätzwert (Bereich 30–100 µg)"),
    *_r("molybdaen", 80, 65, "µg", 600, "Schätzwert"),
    *_r("fluorid", 3.8, 3.1, "mg", 7, "Richtwert"),
]


def suchen(naehrstoff, gruppe="x", alter=40):
    """Passender Referenzwert. gruppe "x" (keine Angabe): Mittelwert aus m und w. -> Referenz oder None."""
    try:
        alter = int(alter)
    except (TypeError, ValueError):
        alter = 40
    kandidaten = [r for r in REFERENZWERTE if r.naehrstoff == naehrstoff and r.alter_min <= alter <= r.alter_max]
    if not kandidaten:
        return None
    for r in kandidaten:
        if r.gruppe in (gruppe, "alle"):
            return r
    m = next((r for r in kandidaten if r.gruppe == "m"), None)
    w = next((r for r in kandidaten if r.gruppe == "w"), None)
    if m and w:
        return Referenz(naehrstoff, "x", m.alter_min, m.alter_max, round((m.ziel + w.ziel) / 2, 2), m.einheit,
                        m.ul, (m.bemerkung + " – Mittelwert aus den Werten für Männer und Frauen").strip(" –"))
    return kandidaten[0]
