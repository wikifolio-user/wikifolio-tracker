"""Berechnungs-Engine des Gesundheitsmoduls - ohne Streamlit, getestet in test_gesundheit.py.

Alle Werte sind rechnerische Schaetzungen zur Dokumentation, keine medizinische Beratung.
"""
import datetime

from . import naehrstoffe as N

# Aktivitaet: (Schluessel, Kurztext, Erklaerung, Faktor auf den Grundumsatz)
AKTIVITAET = [
    ("wenig", "Wenig Bewegung", "Meist sitzend, z. B. Büro – kaum Sport", 1.2),
    ("etwas", "Etwas aktiv", "Viel zu Fuß oder 1–2 × Sport pro Woche", 1.375),
    ("aktiv", "Aktiv", "3–5 × Sport pro Woche oder körperliche Arbeit", 1.55),
    ("sehr", "Sehr aktiv", "Fast täglich Sport oder schwere körperliche Arbeit", 1.725),
]
AKTIVITAET_FAKTOR = {k: f for k, _, _, f in AKTIVITAET}

# Ziel: (Schluessel, Text, kcal-Aenderung je Tag, Protein g je kg Koerpergewicht)
ZIELE = [
    ("halten", "Gewicht halten", 0, 1.4),
    ("reduzieren", "Gewicht reduzieren", -500, 1.8),
    ("erhoehen", "Gewicht erhöhen", 300, 1.8),
    ("doku", "Nur Ernährung dokumentieren", 0, 1.4),
]
ZIEL_KCAL = {k: d for k, _, d, _ in ZIELE}
ZIEL_PROTEIN = {k: p for k, _, _, p in ZIELE}
KCAL_MINIMUM = 1200          # Tagesziel nie darunter (auch beim Abnehmen)
GESCHLECHT_KONSTANTE = {"m": 5, "w": -161, "x": -78}   # Mifflin-St Jeor; x = Mittelwert (keine Angabe)
FETT_ANTEIL = 0.30           # Anteil der Kalorien aus Fett (Standard)


def alter(geburtsjahr, heute=None):
    heute = heute or datetime.date.today()
    try:
        return max(0, heute.year - int(geburtsjahr))
    except (TypeError, ValueError):
        return None


def bmr(gewicht_kg, groesse_cm, alter_jahre, geschlecht="x"):
    """Grundumsatz nach Mifflin-St Jeor (kcal/Tag): Kalorien, die der Koerper in Ruhe braucht."""
    if not (gewicht_kg and groesse_cm and alter_jahre is not None):
        return None
    return 10 * float(gewicht_kg) + 6.25 * float(groesse_cm) - 5 * float(alter_jahre) \
        + GESCHLECHT_KONSTANTE.get(geschlecht, GESCHLECHT_KONSTANTE["x"])


def tdee(bmr_kcal, aktivitaet="wenig"):
    """Gesamtbedarf (kcal/Tag) = Grundumsatz × Aktivitaetsfaktor (Alltag inkl. gewohntem Sport)."""
    if bmr_kcal is None:
        return None
    return bmr_kcal * AKTIVITAET_FAKTOR.get(aktivitaet, AKTIVITAET_FAKTOR["wenig"])


def ziele(profil, heute=None):
    """Profil -> {bmr, tdee, kcal, protein, kh, fett, wasser_ml} (gerundet). Eigene Vorgaben im Profil
    (kcal_eigen, protein_eigen, wasser_eigen) haben Vorrang. Fehlen Pflichtangaben: Werte None."""
    p = profil or {}
    b = bmr(p.get("gewicht_kg"), p.get("groesse_cm"), alter(p.get("geburtsjahr"), heute), p.get("geschlecht", "x"))
    t = tdee(b, p.get("aktivitaet", "wenig"))
    ziel = p.get("ziel", "halten")
    kcal = p.get("kcal_eigen") or (max(KCAL_MINIMUM, t + ZIEL_KCAL.get(ziel, 0)) if t else None)
    gewicht = p.get("gewicht_kg")
    protein = p.get("protein_eigen") or (gewicht * ZIEL_PROTEIN.get(ziel, 1.4) if gewicht else None)
    fett = kcal * FETT_ANTEIL / 9 if kcal else None
    kh = max(0.0, (kcal - protein * 4 - fett * 9) / 4) if kcal and protein and fett else None
    wasser = p.get("wasser_eigen") or (min(3500, max(1500, round(gewicht * 35 / 100) * 100)) if gewicht else None)
    r = lambda x, n=0: None if x is None else round(x, n)
    return {"bmr": r(b), "tdee": r(t), "kcal": r(kcal), "protein": r(protein), "kh": r(kh), "fett": r(fett),
            "wasser_ml": r(wasser)}


# ---------------------------------------------------------------- Mengen und Naehrwerte
def gramm(menge, einheit, einheiten):
    """Menge in einer Einheit des Lebensmittels -> Gramm bzw. ml der Basis. einheiten: {name: gramm_je_einheit};
    "g" und "ml" gelten immer 1:1, "kg"/"L" ×1000. -> None, wenn die Einheit unbekannt ist oder die Menge ungueltig."""
    try:
        menge = float(menge)
    except (TypeError, ValueError):
        return None
    if menge < 0:
        return None
    fest = {"g": 1.0, "ml": 1.0, "kg": 1000.0, "L": 1000.0, "l": 1000.0}
    if einheit in fest:
        return menge * fest[einheit]
    je = (einheiten or {}).get(einheit)
    return menge * float(je) if je else None


def naehrwerte(pro100, gramm_menge):
    """Naehrwerte je 100 g/ml -> fuer die Menge. Unbekannte (fehlende/None) Werte bleiben unbekannt."""
    if gramm_menge is None:
        return {}
    return {k: float(v) * gramm_menge / 100 for k, v in (pro100 or {}).items() if v is not None}


def menge_fuer_kcal(pro100, kcal):
    """Rueckwaertsrechnung: wie viel g/ml ergeben kcal? -> None ohne Kalorienangabe."""
    k = (pro100 or {}).get("kcal")
    return None if not k else float(kcal) * 100 / float(k)


def summe(eintraege, schluessel=None):
    """Tagessumme ueber Eintraege mit Naehrwerten (dict je Eintrag). -> {id: {"wert", "bekannt", "anzahl"}}:
    wert = Summe der BEKANNTEN Werte, bekannt = Anzahl Eintraege mit Wert, anzahl = alle Eintraege.
    So bleibt sichtbar, wenn ein Wert fuer manche Lebensmittel fehlt (unbekannt ist nicht 0)."""
    schluessel = schluessel or list(N.NAEHRSTOFFE)
    n = len(eintraege)
    aus = {}
    for s in schluessel:
        werte = [e[s] for e in eintraege if e.get(s) is not None]
        aus[s] = {"wert": sum(werte), "bekannt": len(werte), "anzahl": n}
    return aus


def bilanz(ziel_kcal, tdee_kcal, gegessen, sport=0.0, sport_zusaetzlich=False):
    """Tagesbilanz. Sportkalorien zaehlen nur, wenn sie ausdruecklich ZUSAETZLICH zum Aktivitaetsfaktor gerechnet
    werden sollen (sonst doppelt). -> {ziel, gegessen, sport, verbleibend, bilanz} (bilanz < 0 = Defizit)."""
    extra = float(sport or 0) if sport_zusaetzlich else 0.0
    ziel = (ziel_kcal or 0) + extra
    verbrauch = (tdee_kcal or 0) + extra
    return {"ziel": ziel, "gegessen": gegessen, "sport": float(sport or 0), "verbleibend": ziel - gegessen,
            "bilanz": gegessen - verbrauch if tdee_kcal else None}


def mahlzeit_vorschlag(zeit):
    """Mahlzeit passend zur Uhrzeit (Standard beim Erfassen)."""
    h = zeit.hour
    if h < 10:
        return "Frühstück"
    if h < 14:
        return "Mittagessen"
    if h < 17:
        return "Nachmittag"
    if h < 21:
        return "Abendessen"
    return "Snacks"
