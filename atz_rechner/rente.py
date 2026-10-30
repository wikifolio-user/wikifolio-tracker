"""Gesetzliche Rente: Altersgrenzen je Jahrgang, Wartezeiten, Abschlaege, Ausgleichszahlung, Hinterbliebenenrente.

Monate werden als fortlaufender Index gezaehlt: idx = jahr * 12 + (monat - 1).
Altersgrenzen in Lebensmonaten (z. B. 66 Jahre 4 Monate = 796).
Quellen: §§ 35, 36, 37, 38, 235, 236, 236a, 236b SGB VI (Anhebungstabellen), § 77 (Zugangsfaktor),
§ 187a (Ausgleichszahlung), §§ 50, 51 (Wartezeiten), §§ 46, 67, 97 (Hinterbliebenenrente).
"""

ARTEN = ("regel", "langjaehrig", "besonders", "schwerbehindert")
NAMEN = {
    "regel": "Regelaltersrente",
    "langjaehrig": "Rente für langjährig Versicherte (35 J.)",
    "besonders": "Rente für besonders langjährig Versicherte (45 J.)",
    "schwerbehindert": "Rente für schwerbehinderte Menschen (35 J., GdB ≥ 50)",
}
MAX_ABSCHLAG_MONATE = {"regel": 0, "langjaehrig": 48, "besonders": 0, "schwerbehindert": 36}


def idx(jahr, monat):
    return int(jahr) * 12 + int(monat) - 1


def jahr_monat(i):
    return i // 12, i % 12 + 1


def alter_text(monate):
    j, m = divmod(int(monate), 12)
    return f"{j} J." + (f" {m} Mon." if m else "")


def regelaltersgrenze(jahrgang):
    """Lebensmonate (§ 35, § 235 SGB VI): 1947–1958 je +1 Monat, 1959–1963 je +2 Monate, ab 1964: 67."""
    j = int(jahrgang)
    if j < 1947:
        return 65 * 12
    if j <= 1958:
        return 65 * 12 + (j - 1946)
    if j <= 1963:
        return 66 * 12 + 2 * (j - 1958)
    return 67 * 12


def grenze_besonders_langjaehrig(jahrgang):
    """45 Jahre Wartezeit, abschlagsfrei (§ 38, § 236b): vor 1953: 63; 1953–1963 je +2 Monate; ab 1964: 65.
    Ein vorzeitiger Bezug mit Abschlag ist nicht moeglich."""
    j = int(jahrgang)
    if j <= 1952:
        return 63 * 12
    if j <= 1963:
        return 63 * 12 + 2 * (j - 1952)
    return 65 * 12


def grenze_schwerbehindert(jahrgang):
    """(abschlagsfrei, fruehestens) in Lebensmonaten (§ 37, § 236a): 1952–1958 je +1 Monat ab 63,
    1959–1963 je +2 Monate ab 64; ab 1964: 65 bzw. 62 (hoechstens 10,8 % Abschlag)."""
    j = int(jahrgang)
    if j < 1952:
        regulaer = 63 * 12
    elif j <= 1958:
        regulaer = 63 * 12 + (j - 1946)
    elif j <= 1963:
        regulaer = 64 * 12 + 2 * (j - 1958)
    else:
        regulaer = 65 * 12
    return regulaer, regulaer - 36


def grenzen(jahrgang):
    """{art: (abschlagsfrei ab, fruehestens ab)} in Lebensmonaten."""
    regel = regelaltersgrenze(jahrgang)
    sb = grenze_schwerbehindert(jahrgang)
    bes = grenze_besonders_langjaehrig(jahrgang)
    return {"regel": (regel, regel), "langjaehrig": (regel, 63 * 12), "besonders": (bes, bes),
            "schwerbehindert": sb}


def beginn_idx(geb_jahr, geb_monat, alter_monate, am_ersten=False):
    """Rentenbeginn: am Ersten des Monats nach Erreichen des Alters (wer am 1. geboren ist: im Geburtsmonat)."""
    return idx(geb_jahr, geb_monat) + int(alter_monate) + (0 if am_ersten else 1)


def lebensalter(geb_jahr, geb_monat, i, am_ersten=False):
    """Erreichtes Alter in Monaten zu Beginn des Monats i (passend zu beginn_idx)."""
    return i - idx(geb_jahr, geb_monat) - (0 if am_ersten else 1)


def wartezeit_jahre(z):
    """Wartezeiten aus den bisherigen Zeiten (dict, Jahre). -> (35 Jahre, 45 Jahre)
    35 J.: alle rentenrechtlichen Zeiten (Schul-/Hochschulausbildung ab 17 hoechstens 8 Jahre).
    45 J.: Pflichtbeitraege (inkl. Berufsausbildung), Kindererziehung bis 10, Pflege, ALG I."""
    pflicht = max(float(z.get("pflicht", 0)), 0.0)
    kinder = max(float(z.get("kinder", 0)), 0.0)
    pflege = max(float(z.get("pflege", 0)), 0.0)
    ausbildung = min(max(float(z.get("ausbildung", 0)), 0.0), 8.0)
    alg = max(float(z.get("alg", 0)), 0.0)
    return pflicht + kinder + pflege + ausbildung + alg, pflicht + kinder + pflege + alg


def moegliche_arten(jahrgang, schwerbehindert, jahre35, jahre45):
    """Arten, deren Wartezeit erfuellt ist (Regelaltersrente: 5 Jahre)."""
    arten = []
    if jahre35 >= 5:
        arten.append("regel")
    if jahre35 >= 35:
        arten.append("langjaehrig")
        if schwerbehindert:
            arten.append("schwerbehindert")
    if jahre45 >= 45:
        arten.append("besonders")
    return arten


def abschlag(monate_frueher, p):
    """Abschlag als Anteil (0,3 % je Monat, hoechstens 48 Monate = 14,4 %)."""
    return min(max(int(monate_frueher), 0), 48) * p["abschlag_monat"] / 100.0


def beste_art(jahrgang, alter_monate, arten, p):
    """Guenstigste Rentenart fuer ein Beginn-Alter (kleinster Abschlag). -> (art, abschlag) oder (None, None)."""
    g = grenzen(jahrgang)
    beste = None
    for art in arten:
        frei, frueh = g[art]
        if alter_monate < frueh:
            continue
        a = abschlag(frei - alter_monate, p)
        if beste is None or a < beste[1] - 1e-12:
            beste = (art, a)
    return beste if beste else (None, None)


def rentenwert(p, i, basis_jahr=2026):
    """Rentenwert im Monat i: Anpassung jeweils zum 1. Juli mit p['rentenanpassung']."""
    j, m = jahr_monat(i)
    n = max(j - basis_jahr - (1 if m < 7 else 0), 0)
    return p["rentenwert"] * (1 + p["rentenanpassung"] / 100.0) ** n


def lohnfaktor(p, jahr, basis_jahr=2026):
    """Entwicklung von Durchschnittsentgelt und Beitragsbemessungsgrenzen (wie die Rentenanpassung)."""
    return (1 + p["rentenanpassung"] / 100.0) ** max(int(jahr) - basis_jahr, 0)


def ep_monat(brutto_monat, p, jahr):
    """Entgeltpunkte aus einem Monatsentgelt (bis zur BBG)."""
    f = lohnfaktor(p, jahr)
    return min(max(brutto_monat, 0.0), p["bbg_rv"] * f / 12.0) / (p["durchschnittsentgelt"] * f)


def ausgleichszahlung(ep, abschlag_anteil, p, jahr=2026):
    """Beitrag, um den Abschlag vollstaendig auszugleichen (§ 187a SGB VI).
    Zusaetzliche EP so, dass (ep + x) * (1 - a) = ep -> x = ep * a / (1 - a); Preis je EP = DE * Beitragssatz."""
    a = max(min(abschlag_anteil, 0.99), 0.0)
    if ep <= 0 or a <= 0:
        return {"ep": 0.0, "kosten": 0.0, "preis_ep": 0.0}
    x = ep * a / (1 - a)
    preis = p["durchschnittsentgelt"] * lohnfaktor(p, jahr) * p["rv_satz"] / 100.0
    return {"ep": x, "kosten": x * preis, "preis_ep": preis}


def ep_aus_beitrag(betrag, p, jahr=2026):
    preis = p["durchschnittsentgelt"] * lohnfaktor(p, jahr) * p["rv_satz"] / 100.0
    return max(betrag, 0.0) / preis if preis > 0 else 0.0


def break_even_monate(kosten, mehr_rente_monat, anpassung_pa=0.0, max_monate=600):
    """Monate ab Rentenbeginn, bis die Summe der Mehrrente die Kosten erreicht (None = nie innerhalb max)."""
    if kosten <= 0:
        return 0
    if mehr_rente_monat <= 0:
        return None
    summe, r = 0.0, mehr_rente_monat
    for m in range(1, max_monate + 1):
        summe += r
        if summe >= kosten:
            return m
        if m % 12 == 0:
            r *= 1 + anpassung_pa / 100.0
    return None


def witwenrente(partner_rente_brutto, eigenes_einkommen_netto, p, i=None):
    """Grosse Witwen-/Witwerrente (Neurecht, 55 %) nach Einkommensanrechnung (§ 97 SGB VI).
    eigenes_einkommen_netto: pauschaliertes Nettoeinkommen (z. B. eigene Rente minus 14 %)."""
    rw = rentenwert(p, i) if i is not None else p["rentenwert"]
    voll = max(partner_rente_brutto, 0.0) * p["witwe_anteil"] / 100.0
    frei = p["witwe_freibetrag_rw"] * rw
    anrechnung = max(eigenes_einkommen_netto - frei, 0.0) * p["witwe_anrechnung"] / 100.0
    return {"voll": voll, "freibetrag": frei, "anrechnung": min(anrechnung, voll),
            "zahlbetrag": max(voll - anrechnung, 0.0)}
