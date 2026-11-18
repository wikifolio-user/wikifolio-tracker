"""Sport: Aktivitaeten mit MET-Werten und Kalorienverbrauch - ohne Streamlit.

Verbrauch = (MET - 1) x Koerpergewicht (kg) x Stunden. Abgezogen wird 1 MET (der Ruheumsatz, der im Tagesbedarf
ohnehin steckt) - so zaehlt nur der ZUSAETZLICHE Verbrauch. MET-Werte gerundet nach dem Compendium of Physical
Activities. Der Benutzer kann den berechneten Wert jederzeit ueberschreiben.
"""
INTENSITAETEN = ["leicht", "mittel", "intensiv"]

# (id, Name, MET leicht, MET mittel, MET intensiv, Standarddauer in Minuten)
_DATEN = [
    ("gehen", "Gehen / Spazieren", 3.0, 3.5, 5.0, 30),
    ("laufen", "Laufen / Joggen", 7.0, 9.8, 11.5, 30),
    ("rad", "Radfahren", 4.0, 6.8, 10.0, 45),
    ("kraft", "Krafttraining", 3.5, 5.0, 6.0, 60),
    ("schwimmen", "Schwimmen", 5.8, 7.0, 9.8, 30),
    ("fussball", "Fußball", 5.0, 7.0, 10.0, 60),
    ("wandern", "Wandern", 5.3, 6.0, 7.8, 120),
    ("rudern", "Rudern", 4.8, 7.0, 8.5, 30),
    ("cross", "Crosstrainer", 5.0, 7.0, 9.0, 30),
    ("yoga", "Yoga / Dehnen", 2.5, 3.0, 4.0, 30),
    ("tanzen", "Tanzen", 4.5, 5.5, 7.8, 60),
    ("hiit", "Zirkel / HIIT", 6.0, 8.0, 10.0, 20),
]
AKTIVITAETEN = {i: {"id": i, "name": n, "met": dict(zip(INTENSITAETEN, (a, b, c))), "minuten": m}
                for i, n, a, b, c, m in _DATEN}
EIGENE = "eigene"            # individuelle Aktivitaet: Kalorien gibt der Benutzer selbst an


def kcal(art, minuten, intensitaet, gewicht_kg):
    """Zusaetzlicher Verbrauch in kcal (gerundet) oder None (unbekannte Aktivitaet / fehlende Angaben)."""
    a = AKTIVITAETEN.get(art)
    try:
        minuten, gewicht_kg = float(minuten), float(gewicht_kg)
    except (TypeError, ValueError):
        return None
    if not a or minuten <= 0 or gewicht_kg <= 0:
        return None
    met = a["met"].get(intensitaet, a["met"]["mittel"])
    return round((met - 1) * gewicht_kg * minuten / 60)


def eintrag(art, name, minuten, intensitaet, kcal_wert, manuell, zeit, eid):
    return {"id": eid, "art": art, "name": name, "minuten": float(minuten), "intensitaet": intensitaet,
            "kcal": float(kcal_wert or 0), "manuell": bool(manuell), "zeit": zeit.strftime("%H:%M")}


def summe(t):
    """Sportkalorien und -minuten eines Tages."""
    sp = t.get("sport") or []
    return sum(float(x.get("kcal") or 0) for x in sp), sum(float(x.get("minuten") or 0) for x in sp)
