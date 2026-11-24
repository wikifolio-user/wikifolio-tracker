"""Kostenvoranschlag einer Produktion (vor dem Start angezeigt). Im Free-Modus sind alle Posten kostenlos; sobald
kostenpflichtige Dienste angebunden werden, kommen sie hier mit Preis dazu und unterliegen der Budgetgrenze."""


def renderminuten(dauer_min):
    """Grobe Rechenzeit in GitHub Actions (gemessen: 49 s Video ~ 1,5 min inkl. Stimme und Schnitt)."""
    return round(3 + float(dauer_min) * 1.6)


def voranschlag(einstellungen, dauer_min, ki_vorhanden):
    """-> (posten [(Posten, Dienst, Betrag €)], summe, im_budget)"""
    posten = [("Skript", "Gemini, kostenloses Kontingent" if ki_vorhanden else "eigenes Skript", 0.0),
              ("Stimme", "Piper lokal (Thorsten, CC0)", 0.0),
              ("Bilder", "Openverse / Wikimedia (CC0, PD, CC BY) oder eigene Grafik", 0.0),
              ("Rendern", f"GitHub Actions, ca. {renderminuten(dauer_min)} Minuten", 0.0)]
    summe = round(sum(p[2] for p in posten), 2)
    return posten, summe, summe == 0 or summe <= float((einstellungen or {}).get("budget_video") or 0)
