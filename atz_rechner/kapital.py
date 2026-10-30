"""Kapital & Geldanlage: Wachstum, Entnahmeplan, Abgeltungsteuer auf Entnahmen.

Vereinfachungen (in der Oberflaeche genannt): Rendite gleichmaessig je Jahr, Zahlungen zur Jahresmitte,
Steuer erst bei Entnahme (thesaurierend; Vorabpauschale nicht gerechnet), Gewinnanteil einer Entnahme
= (Wert - Einstand) / Wert.
"""

MODI = ("luecke", "verzehr", "ertraege", "fest")
MODUS_NAMEN = {
    "luecke": "Versorgungslücke decken",
    "verzehr": "Kapitalverzehr bis Alter X",
    "ertraege": "Nur Erträge entnehmen",
    "fest": "Feste Monatsentnahme",
}


def wachse(k, rendite_pa, monate=12):
    return k * (1 + rendite_pa) ** (monate / 12.0)


def jahr_fortschreiben(k, rendite_pa, zufluss, monate=12):
    """Kapital nach einem (Teil-)Jahr: Zinsen auf den Bestand, Zufluss (negativ = Abfluss) zur Jahresmitte."""
    return wachse(k, rendite_pa, monate) + zufluss * (1 + rendite_pa) ** (monate / 24.0)


def sparplan_endwert(k, sparrate_monat, rendite_pa, jahre):
    """Endwert mit monatlicher Sparrate (nachschuessig, monatliche Verzinsung aus dem Jahreszins)."""
    r = (1 + rendite_pa) ** (1 / 12.0) - 1
    n = int(round(jahre * 12))
    if abs(r) < 1e-12:
        return k + sparrate_monat * n
    return k * (1 + r) ** n + sparrate_monat * ((1 + r) ** n - 1) / r


def steuer_auf_entnahme(brutto, wert, einstand, satz, pausch_rest, teilfreistellung=0.0):
    """Abgeltungsteuer auf eine Entnahme. -> (steuer, steuerpflichtiger Gewinn, verbrauchter Pauschbetrag)"""
    if brutto <= 0 or wert <= 0:
        return 0.0, 0.0, 0.0
    anteil = max(wert - einstand, 0.0) / wert
    gewinn = brutto * anteil * (1 - teilfreistellung)
    genutzt = min(gewinn, max(pausch_rest, 0.0))
    return (gewinn - genutzt) * satz, gewinn, genutzt


def brutto_fuer_netto(netto, wert, einstand, satz, pausch_rest, teilfreistellung=0.0):
    """Wie viel muss entnommen werden, damit nach Steuer `netto` uebrig bleibt? (hoechstens der Wert)"""
    if netto <= 0 or wert <= 0:
        return 0.0
    b = netto
    for _ in range(30):
        st, _, _ = steuer_auf_entnahme(b, wert, einstand, satz, pausch_rest, teilfreistellung)
        neu = netto + st
        if abs(neu - b) < 0.005:
            b = neu
            break
        b = neu
    return min(b, wert)


def annuitaet(k, rendite_pa, jahre, dynamik_pa=0.0):
    """Erste Jahresentnahme, die das Kapital in `jahre` Jahren aufbraucht; die Entnahme steigt jaehrlich um
    `dynamik_pa` (Inflation). Zahlung am Jahresende (wachsende Rente)."""
    n = max(int(jahre), 0)
    if k <= 0 or n == 0:
        return max(k, 0.0)
    r, g = rendite_pa, dynamik_pa
    if abs(r - g) < 1e-12:
        return k * (1 + r) / n
    q = (1 + g) / (1 + r)
    return k * (r - g) / (1 - q ** n)


def reichweite(k, rendite_pa, entnahme_jahr, dynamik_pa=0.0, max_jahre=100):
    """Jahre, bis das Kapital bei jaehrlicher Entnahme (Jahresende, dynamisch) aufgebraucht ist.
    None = reicht laenger als max_jahre (z. B. Ertraege >= Entnahme)."""
    if entnahme_jahr <= 0:
        return None
    w = entnahme_jahr
    for j in range(1, max_jahre + 1):
        k = k * (1 + rendite_pa) - w
        if k <= 0:
            # Bruchteil des letzten Jahres
            return j - 1 + (w + k) / w
        w *= 1 + dynamik_pa
    return None


def szenarien(rendite_pa, spanne):
    """Pessimistisch / realistisch / optimistisch (Rendite in Anteilen)."""
    return {"pessimistisch": rendite_pa - spanne, "realistisch": rendite_pa, "optimistisch": rendite_pa + spanne}
