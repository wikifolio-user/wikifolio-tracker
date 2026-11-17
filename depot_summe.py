"""Depotwert und Rendite aus EINER Quelle (Audit FIN-03) - ohne Streamlit testbar.

Depot-Ansicht (Kachel "Depot gesamt", Startseite), Depot-Analyse und Altersteilzeit (Depotwert uebernehmen) rechnen
alle mit summe(). Eingabe ist der Depotbestand, wie ihn app.py aufbaut (je Position: wert, einstand, ausgezahlt,
ohne_kurs). Regeln:
  - Positionen ohne Kurs (ohne_kurs) zaehlen nicht - ihr Wert ist unbekannt (sonst wuerden die Summen still falsch).
  - Jede Position MIT Kurs zaehlt, auch mit Wert 0 (Totalverlust) - sonst schoente ihr Wegfall die Rendite.
  - Gewinn = Wert + bereits ausgezahlte Entnahmen - Einstand (Einstand inkl. Sparraten, Audit DEP-01/A-12).
  - Rendite = Gewinn / Einstand (Gesamtrendite seit Kauf, nicht p. a.); ohne Einstand None.
  - Gewinn und Rendite nur ueber Positionen mit bekanntem Einstand (einstand None: Wert zaehlt zum Depotwert,
    aber nicht als Gewinn).
"""


def _zahl(x):
    try:
        z = float(x)
    except (TypeError, ValueError):
        return None
    return z if z == z else None              # NaN -> None


def mit_kurs(bestand):
    """Positionen, deren Wert bekannt ist."""
    return [p for p in (bestand or []) if isinstance(p, dict) and not p.get("ohne_kurs")
            and _zahl(p.get("wert")) is not None]


def summe(bestand):
    """-> {wert, einstand, ausgezahlt, gewinn, rendite_pct, anzahl, ohne_kurs}"""
    pos = mit_kurs(bestand)
    wert = sum(max(_zahl(p["wert"]), 0.0) for p in pos)
    mit_einstand = [p for p in pos if _zahl(p.get("einstand")) is not None]
    einstand = sum(_zahl(p["einstand"]) for p in mit_einstand)
    ausgezahlt = sum(_zahl(p.get("ausgezahlt")) or 0.0 for p in mit_einstand)
    wert_mit = sum(max(_zahl(p["wert"]), 0.0) for p in mit_einstand)
    gewinn = wert_mit + ausgezahlt - einstand if mit_einstand else None
    return {"wert": wert, "einstand": einstand, "ausgezahlt": ausgezahlt, "gewinn": gewinn,
            "rendite_pct": (gewinn / einstand * 100) if einstand and gewinn is not None else None,
            "anzahl": len(pos),
            "ohne_kurs": [p for p in (bestand or []) if isinstance(p, dict) and p.get("ohne_kurs")]}
