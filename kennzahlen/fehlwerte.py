"""Fehlende Daten im Qualitaets-Score sichtbar machen (Abweichung A5).

Der Qualitaets-Agent vergibt fuer ein Kriterium ohne Daten 0 Punkte (punkte_stufen(None) = 0). Ein Unternehmen
mit Datenluecken wirkt dadurch schlechter, als es gemessen ist. Hier wird je Bereich ermittelt, wie viele Punkte
auf Kriterien entfallen, deren Eingangswert fehlt - naeherungsweise, je Kriterium ueber den Haupt-Eingangswert
(Tabelle REGELN spiegelt die Punktevergabe in qualitaet_agent.bewerte).

Kriterien, bei denen der Agent fehlende Werte bereits wohlwollend behandelt (z. B. aktienbasierte Verguetung
"unbekannt" = volle Punkte), fehlen hier bewusst - dort entsteht kein Nachteil.

Das klassische Modell bleibt unveraendert; die Hochrechnung ist nur eine Vergleichsvariante.
"""

BEREICHE = (("qualitaet", "Qualität", 20), ("wachstum", "Wachstum", 15), ("fcf", "Cashflow", 15),
            ("bilanz", "Bilanz", 10), ("management", "Management", 10), ("moat", "Burggraben", 10),
            ("bewertung", "Bewertung", 15), ("chance", "Chance", 5))

# (Bereich, Eingangswert, Hoechstpunkte, Bedingung) - Bedingung: Funktion(werte) -> zaehlt das Kriterium?
REGELN = (
    ("qualitaet", "roic_avg", 8, None),
    ("qualitaet", "om_avg", 3, None),
    ("qualitaet", "cc", 2, None),
    ("qualitaet", "capex", 2, None),
    ("wachstum", "g_ums", 4, None),
    ("wachstum", "g_eps", 4, None),
    ("wachstum", "g_fcfps", 5, None),
    ("fcf", "g_fcfps", 3, None),
    ("fcf", "fm_avg", 3, None),
    ("fcf", "cc", 2, None),
    ("bilanz", "nd_ebitda", 6, lambda w: (w.get("nd") or 0) > 0),        # Nettocash bekommt die Punkte ohnehin
    ("bilanz", "zinsd", 4, lambda w: (w.get("nd") or 0) > 0),
    ("management", "g_akt", 5, None),
    ("moat", "roic_avg", 4, None),
    ("moat", "gm_avg", 3, None),
    ("moat", "om_std", 3, lambda w: (w.get("om_avg") or 0) >= 5),
    ("bewertung", "fcfy", 5, None),
    ("bewertung", "ev_ebit", 3, None),
    ("bewertung", "peg", 2, None),
    ("bewertung", "h_fcfy", 3, None),
    ("chance", "mos", 4, None),
    ("chance", "bear", 1, None),
)


def fehlende_punkte(werte):
    """werte: Kennzahlen des Agenten (k) + berechnete Bewertungsgroessen (fcfy, ev_ebit, peg, mos, bear).
    -> {bereich: Punkte, die nur wegen fehlender Daten nicht vergeben werden konnten} (nur Bereiche > 0)."""
    aus = {}
    for bereich, schluessel, punkte, bedingung in REGELN:
        if bedingung is not None and not bedingung(werte):
            continue
        if werte.get(schluessel) is None:
            aus[bereich] = aus.get(bereich, 0) + punkte
    maxi = {b: m for b, _, m in BEREICHE}
    return {b: min(p, maxi[b]) for b, p in aus.items()}


def hochgerechnet(pt, fp):
    """Vergleichsvariante: Punkte je Bereich auf die Kriterien MIT Daten hochgerechnet
    (Bereich mit 8 von 12 messbaren Punkten -> 8/12 x Hoechstpunkte). pt: Liste wie "pt" des Agenten,
    fp: fehlende_punkte. -> (Liste je Bereich, Summe). Bereiche ganz ohne messbare Daten werden nicht
    hochgerechnet (keine Erfindung) - sie behalten ihre tatsaechlichen Punkte."""
    aus = []
    for (b, _, mx), p in zip(BEREICHE, pt or []):
        fehlt = (fp or {}).get(b, 0)
        messbar = mx - fehlt
        aus.append(round(p * mx / messbar, 1) if messbar > 0 and fehlt else float(p))
    return aus, round(sum(aus), 1)


def datenluecke_anteil(fp):
    """Anteil der 100 Punkte, die wegen fehlender Daten nicht bewertbar waren (0..1)."""
    return min(sum((fp or {}).values()), 100) / 100
