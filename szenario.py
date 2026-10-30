"""Szenario-Simulator: monatliche Fortschreibung mit Sparrate und Entnahme, optional mit Abgeltungsteuer auf die
Gewinnanteile der Entnahmen (reine Rechenlogik, ohne Streamlit).

Steuer (Deutschland, Privatvermoegen): Abgeltungsteuer 25 % + Soli 5,5 % (+ ggf. Kirchensteuer 8/9 % mit der
ueblichen Minderung der KapESt), Sparerpauschbetrag je Kalenderjahr, optional Teilfreistellung (Aktienfonds 30 %).
Besteuert wird nur der Gewinnanteil einer Entnahme: Entnahme x (Wert - Einstand) / Wert. Damit die gewuenschte
Netto-Entnahme ankommt, wird entsprechend mehr verkauft (brutto). Vorabpauschale und Verlustverrechnung bleiben
unberuecksichtigt - eine Naeherung.
"""
import datetime

ABGELTUNG = 0.25
SOLI = 0.055
STANDARD_RATEN = [-10.0, 0.0] + [float(p) for p in range(5, 101, 5)]      # % p.a., 5er-Schritte bis 100
ZEITRAEUME = [5, 10, 15, 20, 25, 30]


def steuersatz(kirchensteuer=0.0):
    """Effektiver Satz auf den steuerpflichtigen Gewinn (Abgeltung + Soli + Kirchensteuer), z. B. 26,375 %."""
    k = (kirchensteuer or 0.0) / 100.0
    kest = ABGELTUNG / (1 + ABGELTUNG * k) if k else ABGELTUNG
    return kest * (1 + SOLI + k)


def monatsrate(pa_prozent):
    return (1 + pa_prozent / 100.0) ** (1 / 12) - 1


def jahres_stuetzpunkte(jahre):
    """Fuenf Jahre fuer die Kartenspalten, z. B. 5 -> 1..5, 10 -> 1, 3, 5, 7, 10."""
    if jahre <= 5:
        return list(range(1, jahre + 1))
    punkte = sorted({max(1, round(jahre * f)) for f in (0.1, 0.3, 0.5, 0.7, 1.0)})
    return punkte


def simuliere(start, r_mo, monate, sparrate=0.0, entnahme=0.0, steuer=None, einstand=None, heute=None):
    """Monatliche Fortschreibung. steuer: None (ohne Steuer, wie bisher) oder
    {"kirchensteuer": 0/8/9, "freibetrag": 1000, "teilfreistellung": 0/30}.
    -> {"werte": [Wert nach 0..monate Monaten], "steuern": Summe, "brutto": Summe der Verkaeufe,
        "netto": Summe der ausgezahlten Entnahmen, "leer_ab": Monat, ab dem das Kapital aufgebraucht ist}"""
    heute = heute or datetime.date.today()
    k = float(start)
    e = float(start if einstand is None else einstand)
    werte, steuern, brutto, netto, leer_ab = [max(0.0, k)], 0.0, 0.0, 0.0, None
    satz = steuersatz((steuer or {}).get("kirchensteuer", 0.0)) if steuer else 0.0
    tfs = ((steuer or {}).get("teilfreistellung", 0.0) or 0.0) / 100.0
    frei_jahr = float((steuer or {}).get("freibetrag", 0.0) or 0.0)
    frei, jahr = frei_jahr, heute.year
    for m in range(1, monate + 1):
        monat_jahr = heute.year + (heute.month - 1 + m) // 12
        if monat_jahr != jahr:                           # neues Kalenderjahr: Pauschbetrag wieder voll
            jahr, frei = monat_jahr, frei_jahr
        if k > 0:
            k *= 1 + r_mo
        k += sparrate
        e += sparrate
        if entnahme > 0 and k > 0:
            if not steuer:
                w = entnahme
                st_m = 0.0
            else:
                g = max(0.0, (k - e) / k)                # Gewinnanteil je verkauftem Euro
                q = g * (1 - tfs)                        # steuerpflichtiger Anteil je verkauftem Euro
                if entnahme * q <= frei:
                    w, st_m = entnahme, 0.0
                else:
                    w = (entnahme - satz * frei) / (1 - satz * q)
                    st_m = satz * (w * q - frei)
                frei = max(0.0, frei - w * q)
                e = max(0.0, e - w * (1 - g))            # verkaufter Einstandsanteil
            if w > k:                                    # Kapital reicht nicht mehr: Rest wird entnommen
                anteil = k / w
                w, st_m = k, st_m * anteil
            k -= w
            if k <= 1e-9 and leer_ab is None:
                leer_ab = m
            brutto += w
            steuern += st_m
            netto += w - st_m
        werte.append(max(0.0, k))
    return {"werte": werte, "steuern": steuern, "brutto": brutto, "netto": netto, "leer_ab": leer_ab}


def monate_bis(ziel, start, r_mo, sparrate=0.0, entnahme=0.0, steuer=None, einstand=None, max_monate=1200,
               heute=None):
    """Erster Monat, in dem das Kapital das Ziel erreicht (oder None innerhalb von max_monate)."""
    v = simuliere(start, r_mo, max_monate, sparrate, entnahme, steuer, einstand, heute)["werte"]
    for m, w in enumerate(v[1:], 1):
        if w >= ziel:
            return m
    return None


ZIEL_STUFEN = (100000, 250000, 500000, 750000, 1000000, 1500000, 2000000, 3000000, 5000000, 10000000)


def naechstes_ziel(start):
    """Vorbelegung des Zielwerts: die naechste runde Stufe ueber dem Startkapital (sonst das Doppelte)."""
    for z in ZIEL_STUFEN:
        if z > start:
            return float(z)
    return float(round(2 * start, -5))


def ziel_text(ziel):
    """100000 -> '100k', 1500000 -> '1,5 Mio.'"""
    if ziel >= 1e6:
        return f"{ziel / 1e6:,.2f}".rstrip("0").rstrip(".").replace(".", ",") + " Mio."
    return f"{ziel / 1e3:,.0f}k".replace(",", ".")
