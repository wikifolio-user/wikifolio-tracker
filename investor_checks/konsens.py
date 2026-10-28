"""Legenden-Konsens: Zusammenfassung aller Investoren-Checks (Abschnitt 11).

- "x von y Investoren wuerden kaufen": Checks der Investoren (Kategorien Value/Qualitaet/Wachstum/Momentum/
  Dividende) mit Score >= KAUFEN_AB_SCORE. Risiko-Modelle (Piotroski, Altman, Beneish, Warnsignale) zaehlen nicht
  als "Investor", fliessen aber in Note und Warnungen ein.
- Gesamtnote A-F: 75 % Durchschnitt der Investoren-Scores + 25 % Durchschnitt der Risiko-Modelle
  (n/a zaehlt nicht mit). So ziehen Warnsignale die Note herunter, ueberdecken aber nicht das Urteil der Investoren.
"""
import investor_config as C

RISIKO = "Risiko"


def note(score):
    if score is None:
        return "–"
    return next(n for grenze, n in C.NOTEN if score >= grenze)


def konsens(ergebnisse, kategorien=None):
    """-> {kaufen, investoren, note, score, satz, warnungen, staerken, schwaechen, badges}"""
    erg = [e for e in ergebnisse if not kategorien or e["kategorie"] in kategorien]
    inv = [e for e in erg if e["kategorie"] != RISIKO and e["score_0_100"] is not None]
    kaufen = [e for e in inv if e["kauf"]]
    s_inv = [e["score_0_100"] for e in inv]
    s_ris = [e["score_0_100"] for e in erg if e["kategorie"] == RISIKO and e["score_0_100"] is not None]
    m_inv = sum(s_inv) / len(s_inv) if s_inv else None
    m_ris = sum(s_ris) / len(s_ris) if s_ris else None
    score = (0.75 * m_inv + 0.25 * m_ris if m_inv is not None and m_ris is not None else
             m_inv if m_inv is not None else m_ris)
    warn = [w for e in ergebnisse for w in e.get("warnungen") or []]
    badges = [b for e in ergebnisse for b in e.get("badges") or []]
    staerken = [f"{e['investor']}: {e['erfuellt']} von {e['gesamt']} Kriterien erfüllt" if e["kategorie"] != RISIKO
                else f"{e['investor']}: {e['fazit']}" for e in sorted(erg, key=lambda e: -(e["score_0_100"] or 0))
                if e["score_0_100"] is not None and e["score_0_100"] >= C.KAUFEN_AB_SCORE][:5]
    schwaechen = [f"{e['investor']}: nur {e['erfuellt']} von {e['gesamt']} erfüllt" if e["kategorie"] != RISIKO
                  else f"{e['investor']}: {e['fazit']}" for e in sorted(erg, key=lambda e: e["score_0_100"] or 0)
                  if e["score_0_100"] is not None and e["score_0_100"] < 40][:5]
    n = note(score)
    if not inv:
        satz = "Für ein Urteil der Investoren fehlen die Daten."
    else:
        anteil = len(kaufen) / len(inv)
        satz = ("Breite Zustimmung der Legenden" if anteil >= 0.6 else "Geteilte Meinung der Legenden"
                if anteil >= 0.3 else "Die meisten Legenden würden nicht kaufen")
        satz += f" – Gesamtnote {n}" + (f", {len(warn)} Warnsignal(e) beachten." if warn else ".")
    return {"kaufen": len(kaufen), "investoren": len(inv), "note": n, "score": score, "satz": satz,
            "warnungen": warn, "staerken": staerken, "schwaechen": schwaechen, "badges": badges}
