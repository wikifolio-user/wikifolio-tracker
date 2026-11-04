"""classic_v2: katalogkonformes VERGLEICHSmodell (aktiv bleibt classic_v1 = heutiger Code).

Gesamt = 55 % Qualitaet + 35 % Legenden-Konsens + 10 % Risiko (laut Bewertungskatalog), fehlende Teile werden
hochgerechnet (Gewichte der vorhandenen Teile auf 100 %).
  Qualitaet v2   Qualitaets-Score mit Red-Flag-Abzug hoechstens 30 Punkte (Katalog; v1: ohne Deckel)
  Konsens        Legenden-Konsens der Investoren-Checks (unveraendert)
  Risiko         VORLAEUFIG, NICHT KATALOGBESTAETIGT: 0-100 (100 = geringes Risiko) aus vorhandenen Signalen -
                 Risiko-Stufe des Qualitaets-Agenten und Score der Risiko-Modelle (Altman, Beneish, Piotroski,
                 Warnsignale). Wird durch die Katalogdefinition ersetzt, sobald das PDF vorliegt.
"""
GEWICHTE = {"qualitaet": 55, "konsens": 35, "risiko": 10}
RED_FLAG_DECKEL = 30
RISIKO_STUFE = {"niedrig": 85.0, "mittel": 55.0, "hoch": 25.0}
RISIKO_MODELLE = ("altman", "beneish", "piotroski", "red_flags")
VORLAEUFIG = "Risiko-Score vorläufig aus vorhandenen Signalen – nicht katalogbestätigt"


def qualitaet_v2(pt, abzug, gesamt_v1=None):
    """Qualitaets-Score mit gedeckeltem Red-Flag-Abzug. pt: Punkte je Bereich, abzug: Red-Flag-Summe (v1).
    Ohne Abzugsangabe: Rueckrechnung aus gesamt_v1 (exakt, solange v1 nicht auf 0 begrenzt war)."""
    if not pt:
        return None
    roh = sum(pt)
    if abzug is None:
        if gesamt_v1 is None:
            return None
        abzug = roh - gesamt_v1
    return max(roh - min(abzug, RED_FLAG_DECKEL), 0)


def risiko_vorlaeufig(stufe=None, checks=None):
    """-> (Score 0-100 oder None, Bestandteile). checks: {check_id: [score, erfuellt, gesamt]} (Investoren-Checks)."""
    teile = {}
    if stufe in RISIKO_STUFE:
        teile["stufe"] = RISIKO_STUFE[stufe]
    werte = [z[0] for cid, z in (checks or {}).items()
             if cid in RISIKO_MODELLE and isinstance(z, (list, tuple)) and z and z[0] is not None]
    if werte:
        teile["modelle"] = sum(werte) / len(werte)
    if not teile:
        return None, teile
    return round(sum(teile.values()) / len(teile), 1), teile


def gesamt_v2(q_v2, konsens=None, risiko=None):
    """-> (Score oder None, verwendete Gewichte). Fehlt ein Teil, verteilen sich die Gewichte der vorhandenen."""
    teile = {"qualitaet": q_v2, "konsens": konsens, "risiko": risiko}
    da = {k: v for k, v in teile.items() if v is not None}
    if "qualitaet" not in da:
        return None, {}
    g = sum(GEWICHTE[k] for k in da)
    return round(sum(GEWICHTE[k] * v for k, v in da.items()) / g, 1), {k: round(GEWICHTE[k] / g * 100) for k in da}


def bewerte(q, inv=None):
    """q: Zeile Qualitaets-Score, inv: Kurzform Investoren-Checks. -> dict mit v1, v2 und Bestandteilen."""
    q, inv = q or {}, inv or {}
    qv2 = qualitaet_v2(q.get("pt"), q.get("abz"), q.get("gesamt"))
    risiko, r_teile = risiko_vorlaeufig(q.get("risiko"), inv.get("c"))
    # E1 (Etappe 4): Finanzdienstleister im Vergleichsmodell mit allen Kriterien ("s2"), v1 unveraendert
    konsens = inv.get("s2") if inv.get("s2") is not None else inv.get("score")
    g, gew = gesamt_v2(qv2, konsens, risiko)
    return {"v1": q.get("gesamt"), "qualitaet_v2": qv2, "konsens": konsens, "risiko": risiko,
            "risiko_teile": r_teile, "v2": g, "gewichte": gew, "hinweis": VORLAEUFIG}


def vergleich(zeilen, top=50):
    """zeilen: [{id, v1, v2}] -> Rangkorrelation (Spearman), Ueberschneidung der Top-n, groesste Verschiebungen."""
    mit = [z for z in zeilen if z.get("v1") is not None and z.get("v2") is not None]
    if len(mit) < 3:
        return {"n": len(mit), "spearman": None, "top_gleich": None, "aufsteiger": [], "absteiger": []}

    def raenge(schl):
        s = sorted(mit, key=lambda z: (-z[schl], str(z["id"])))
        return {z["id"]: i for i, z in enumerate(s, 1)}
    r1, r2 = raenge("v1"), raenge("v2")
    n = len(mit)
    d2 = sum((r1[i] - r2[i]) ** 2 for i in r1)
    rho = 1 - 6 * d2 / (n * (n * n - 1))
    t1 = {i for i, r in r1.items() if r <= top}
    t2 = {i for i, r in r2.items() if r <= top}
    bewegung = sorted(((r1[i] - r2[i], i) for i in r1), reverse=True)
    return {"n": n, "spearman": round(rho, 3), "top_gleich": len(t1 & t2), "top": min(top, n),
            "neu_in_top": sorted(t2 - t1, key=lambda i: r2[i]), "raus_aus_top": sorted(t1 - t2, key=lambda i: r1[i]),
            "aufsteiger": [(i, r1[i], r2[i]) for d, i in bewegung[:10] if d > 0],
            "absteiger": [(i, r1[i], r2[i]) for d, i in bewegung[::-1][:10] if d < 0]}
