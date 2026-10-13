"""Abfindungsmodelle Deutschland (Stand Oktober 2026) - Rechenkern ohne Streamlit.

Trennt strikt zwischen
- gesetzlichem Anspruch mit Voraussetzungen (§ 1a KSchG),
- gerichtlicher Entscheidung im gesetzlichen Rahmen (§§ 9, 10, 13 KSchG, § 113 BetrVG),
- kollektiv-/vertraglichen Anspruechen (Sozialplan, Tarifvertrag, Betriebsvereinbarung, Zusage),
- frei verhandelbaren Szenarien (Faktoren, Aufhebungs-/Abwicklungsvertrag, Vergleich,
  Freiwilligenprogramm, Turbo-/Sprinterklausel).
Keine Rechtsberatung: Wo das Ergebnis vom Einzelfall abhaengt, steht das im Status.

Geldbetraege der Modelle werden mit Decimal gerechnet und auf Cent gerundet.
Die Steuer kommt aus abfindung.py (Tarife 2026 und Entwurf 2027, Fuenftelregel).

Rechtsgrundlagen (gesetze-im-internet.de): KSchG §§ 1a, 4, 9, 10, 13, 23; BGB §§ 622, 628;
BetrVG §§ 111-113; InsO §§ 123, 124; SGB III §§ 38, 147, 148, 158, 159; EStG §§ 24, 32a, 34.
"""
import datetime
import math
from decimal import Decimal, ROUND_HALF_UP

import abfindung as A

CENT = Decimal("0.01")

# ---------------------------------------------------------------------------
# Parameter (gesetzliche Konstanten an EINER Stelle; jahresbezogen erweiterbar)
# ---------------------------------------------------------------------------
PARAM = {
    "1a_faktor": Decimal("0.5"),                      # § 1a Abs. 2 S. 1 KSchG
    "kschg_kleinbetrieb": 10,                         # § 23 Abs. 1 KSchG: mehr als 10 AN
    "kschg_wartezeit_monate": 6,                      # § 1 Abs. 1 KSchG
    "kschg_10_stufen": [(55, 20, 18), (50, 15, 15)],  # § 10 Abs. 2 KSchG: (Alter, Jahre, Monatsverdienste)
    "kschg_10_grund": 12,                             # § 10 Abs. 1 KSchG
    "klagefrist_wochen": 3,                           # § 4 KSchG
    "inso_123_monate": Decimal("2.5"),                # § 123 Abs. 1 InsO (Gesamtvolumen!)
    "inso_123_masse_anteil": Decimal(1) / Decimal(3), # § 123 Abs. 2 S. 2 InsO
    "inso_124_monate": 3,                             # § 124 Abs. 1 InsO
    "alg_158_start": 60, "alg_158_min": 25, "alg_158_stufe": 5,   # § 158 Abs. 2 SGB III (Prozent)
    "alg_159_tage": 84,                               # § 159 Abs. 3 SGB III: 12 Wochen
    "alg_meldung_monate": 3, "alg_meldung_tage": 3,   # § 38 Abs. 1 SGB III
    # § 147 Abs. 2 SGB III: (Versicherungsmonate, Alter, Anspruch Monate)
    "alg_dauer": [(48, 58, 24), (36, 55, 18), (30, 50, 15), (24, 0, 12), (20, 0, 10), (16, 0, 8), (12, 0, 6)],
}
# § 622 Abs. 2 BGB: Betriebszugehoerigkeit (Jahre) -> Monate zum Monatsende (Arbeitgeberkuendigung)
KUENDIGUNGSFRISTEN = [(20, 7), (15, 6), (12, 5), (10, 4), (8, 3), (5, 2), (2, 1)]

STATUS = {
    "gesetz": "Gesetzlicher Anspruch – nur wenn alle Voraussetzungen erfüllt sind",
    "gericht": "Gerichtliche Entscheidung – Betrag ist eine Höchstgrenze, kein Anspruch",
    "kollektiv": "Anspruch nur aus dem konkreten Sozialplan/Tarifvertrag/der Betriebsvereinbarung",
    "vertrag": "Vertraglich – nur wenn so vereinbart",
    "verhandlung": "Frei verhandelbar – Vergleichsszenario, kein Anspruch",
    "nicht": "Nicht anwendbar",
    "pruefen": "Einzelfallprüfung nötig",
}


def d(x):
    """Zahl -> Decimal (ueber str, damit 0.1 nicht zu 0.1000000000000000055 wird)."""
    if x is None:
        return Decimal(0)
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def eur(x):
    return d(x).quantize(CENT, rounding=ROUND_HALF_UP)


def de(x, nk=2):
    if x is None:
        return "–"
    t = f"{float(x):,.{nk}f}"
    return t.replace(",", "§").replace(".", ",").replace("§", ".")


# ---------------------------------------------------------------------------
# Beschaeftigungszeit (datumsexakt)
# ---------------------------------------------------------------------------
def _plus_monate(datum, monate):
    j, m = divmod(datum.month - 1 + monate, 12)
    jahr, monat = datum.year + j, m + 1
    tag = min(datum.day, [31, 29 if jahr % 4 == 0 and (jahr % 100 or jahr % 400 == 0) else 28,
                           31, 30, 31, 30, 31, 31, 30, 31, 30, 31][monat - 1])
    return datetime.date(jahr, monat, tag)


def beschaeftigung(beginn, ende, vorzeit_monate=0):
    """Dauer vom Beginn bis einschliesslich Ende (+ anzurechnende Vorbeschaeftigung).
    -> {"jahre", "monate", "tage", "jahre_dezimal", "jahre_1a"} oder None.
    jahre_1a: § 1a Abs. 2 S. 3 KSchG - ein Zeitraum von MEHR als sechs Monaten wird auf ein
    volles Jahr aufgerundet (genau sechs Monate: keine Aufrundung)."""
    if not beginn or not ende or ende < beginn:
        return None
    # Fristende nach §§ 187 Abs. 2, 188 Abs. 2, 3 BGB: m Monate ab Beginn enden am Tag vor dem
    # gleichen Kalendertag - fehlt dieser Tag im Zielmonat (z. B. 29.02.), am Monatsletzten.
    def periodenende(m):
        t = _plus_monate(beginn, m)
        return t if t.day != beginn.day else t - datetime.timedelta(days=1)
    monate = max((ende.year - beginn.year) * 12 + (ende.month - beginn.month) + 1, 0)
    while monate > 0 and periodenende(monate) > ende:
        monate -= 1
    rest_tage = (ende - periodenende(monate)).days if monate else (ende - beginn).days + 1
    monate += int(vorzeit_monate or 0)
    jahre, rest_m = divmod(monate, 12)
    jahre_1a = jahre + (1 if (rest_m > 6 or (rest_m == 6 and rest_tage > 0)) else 0)
    return {"jahre": jahre, "monate": rest_m, "tage": rest_tage,
            "jahre_dezimal": round(jahre + (rest_m + rest_tage / 30.4375) / 12, 2), "jahre_1a": jahre_1a}


def gesetzliche_frist_monate(jahre):
    """§ 622 Abs. 2 BGB (Arbeitgeberkuendigung) -> Monate zum Monatsende; < 2 Jahre: 4 Wochen."""
    for ab, m in KUENDIGUNGSFRISTEN:
        if jahre >= ab:
            return m
    return 0


def fristende(zugang, monate, wochen4=False):
    """Fiktives Ende bei ordentlicher Kuendigung: 4 Wochen zum 15./Monatsende oder
    'monate' Monate zum Monatsende (§ 622 BGB)."""
    if not zugang:
        return None
    if wochen4 or not monate:
        t = zugang + datetime.timedelta(weeks=4)
        if t.day <= 15:
            return datetime.date(t.year, t.month, 15)
        return _plus_monate(datetime.date(t.year, t.month, 1), 1) - datetime.timedelta(days=1)
    t = _plus_monate(zugang, monate)
    return _plus_monate(datetime.date(t.year, t.month, 1), 1) - datetime.timedelta(days=1)


# ---------------------------------------------------------------------------
# Monatsverdienst (§ 10 Abs. 3 KSchG)
# ---------------------------------------------------------------------------
def monatsverdienst(fall):
    """Monatsverdienst = Geld- und Sachbezuege im Monat der Beendigung. Jahressonderzahlungen
    mit Entgeltcharakter (13. Gehalt, regelmaessige Boni) werden anteilig (1/12) einbezogen,
    wenn 'sonder_einbeziehen' - das ist herrschende Praxis, aber im Einzelfall zu pruefen.
    -> (Decimal, [(bezeichnung, betrag)])"""
    teile = [("Bruttomonatsgehalt", d(fall.get("brutto_monat"))),
             ("Zulagen (monatlich)", d(fall.get("zulagen"))),
             ("Geldwerte Vorteile / Sachbezüge (monatlich)", d(fall.get("sachbezug")))]
    if fall.get("sonder_einbeziehen", True):
        for k, txt in (("weihnachtsgeld", "Weihnachtsgeld / 13. Gehalt"), ("urlaubsgeld", "Urlaubsgeld"),
                       ("boni", "Regelmäßige Boni"), ("provisionen", "Provisionen")):
            if d(fall.get(k)):
                teile.append((f"{txt} (jährlich ÷ 12)", d(fall.get(k)) / 12))
    teile = [(t, eur(b)) for t, b in teile if b]
    return eur(sum((b for _, b in teile), Decimal(0))), teile


# ---------------------------------------------------------------------------
# Hilfen fuer die Modelle
# ---------------------------------------------------------------------------
def _modell(key, name, art, faktor, brutto, status, anwendbar=True, voraussetzungen=None, formel="",
            hinweise=None, grundlage="", bestandteile=None):
    return {"key": key, "name": name, "art": art, "faktor": faktor,
            "brutto": None if brutto is None else eur(brutto), "status": status, "anwendbar": anwendbar,
            "voraussetzungen": voraussetzungen or [], "formel": formel, "hinweise": hinweise or [],
            "grundlage": grundlage, "bestandteile": bestandteile or []}


def _vor(text, erfuellt):
    """Voraussetzung: erfuellt True/False/None (unbekannt)."""
    return {"text": text, "erfuellt": erfuellt}


def _kschg_anwendbar(fall, dauer):
    gross = fall.get("betrieb_gross")
    warte = None if dauer is None else (dauer["jahre"] * 12 + dauer["monate"]) >= PARAM["kschg_wartezeit_monate"]
    return [_vor(f"Betrieb mit mehr als {PARAM['kschg_kleinbetrieb']} Arbeitnehmern (§ 23 KSchG)", gross),
            _vor("Arbeitsverhältnis länger als 6 Monate (Wartezeit § 1 KSchG)", warte)]


def _alle(vor):
    werte = [v["erfuellt"] for v in vor]
    if any(w is False for w in werte):
        return False
    if any(w is None for w in werte):
        return None
    return True


# ---------------------------------------------------------------------------
# A. § 1a KSchG
# ---------------------------------------------------------------------------
def m_1a(fall, mv, dauer):
    vor = _kschg_anwendbar(fall, dauer) + [
        _vor("Betriebsbedingte Kündigung durch den Arbeitgeber", fall.get("art") == "ag_betriebsbedingt"),
        _vor("Hinweis im Kündigungsschreiben auf § 1a KSchG (Abfindung bei Verstreichenlassen der Klagefrist)",
             fall.get("hinweis_1a")),
        _vor("Keine Kündigungsschutzklage innerhalb von 3 Wochen", None if fall.get("klage") is None
             else not fall.get("klage")),
    ]
    jahre = dauer["jahre_1a"] if dauer else 0
    brutto = mv * PARAM["1a_faktor"] * jahre
    ok = _alle(vor)
    status = STATUS["gesetz"] if ok is not False else STATUS["nicht"]
    return _modell("1a", "§ 1a KSchG (gesetzlich)", "gesetz", "0,50", brutto if ok is not False else None,
                   status, ok is not False, vor,
                   f"{de(mv)} € × 0,5 × {jahre} Jahre (Zeitraum über 6 Monate aufgerundet) = {de(eur(brutto))} €",
                   ["Der Anspruch entsteht nur mit Ablauf der Kündigungsfrist und nur, wenn alle Voraussetzungen "
                    "erfüllt sind. Ein Arbeitgeber muss § 1a nicht anbieten."],
                   "§ 1a KSchG")


# ---------------------------------------------------------------------------
# B. Verhandlungsfaktoren
# ---------------------------------------------------------------------------
FAKTOREN = [Decimal("0.25"), Decimal("0.5"), Decimal("0.75"), Decimal("1"), Decimal("1.25"), Decimal("1.5"),
            Decimal("2")]


def m_faktor(mv, jahre, faktor, name=None):
    f = d(faktor)
    return _modell(f"f{f}", name or f"Verhandlung Faktor {de(f, 2)}", "verhandlung", de(f, 2),
                   mv * jahre * f, STATUS["verhandlung"], True, [],
                   f"{de(mv)} € × {de(jahre, 2)} Jahre × {de(f, 2)} = {de(eur(mv * jahre * f))} €",
                   ["Allgemeine Faktorformel – keine gesetzliche Berechnungsmethode."], "Vereinbarung")


# ---------------------------------------------------------------------------
# C./D. Aufhebungs- und Abwicklungsvertrag, F. Vergleich, K. Zusage
# ---------------------------------------------------------------------------
def m_vertrag(key, name, mv, jahre, betrag=None, faktor=None, zusatz=None, status_art="vertrag",
              grundlage="Vertrag", hinweise=None, voraussetzungen=None):
    """Betrag ODER Faktor; zusatz: [(bezeichnung, betrag, art)] - art: 'abfindung' (zaehlt zur
    Abfindung) oder 'entgelt' (Gehalt, Urlaubsabgeltung, Bonus: getrennt, nicht Teil der Abfindung)."""
    if betrag:
        basis, formel, f_txt = d(betrag), f"vereinbarter Betrag {de(betrag)} €", "Festbetrag"
    elif faktor:
        basis = mv * jahre * d(faktor)
        formel, f_txt = f"{de(mv)} € × {de(jahre, 2)} J. × {de(faktor, 2)}", de(faktor, 2)
    else:
        return _modell(key, name, status_art, "–", None, "Keine Werte eingegeben", False, voraussetzungen or [],
                       "", hinweise, grundlage)
    teile = [("Abfindung", eur(basis), "abfindung")]
    for t, b, art in zusatz or []:
        if d(b):
            teile.append((t, eur(b), art))
    abf = sum((b for _, b, a in teile if a == "abfindung"), Decimal(0))
    return _modell(key, name, status_art, f_txt, abf, STATUS.get(status_art, status_art), True,
                   voraussetzungen or [], formel, hinweise, grundlage, teile)


# ---------------------------------------------------------------------------
# E. Gerichtliche Aufloesung §§ 9, 10 KSchG (+ § 13), H. Nachteilsausgleich § 113 BetrVG
# ---------------------------------------------------------------------------
def obergrenze_10(alter, jahre, regelalter_erreicht=False):
    """Hoechstzahl der Monatsverdienste nach § 10 KSchG.
    Abs. 2 S. 2: Die erhoehten Grenzen gelten nicht, wenn der AN zum Aufloesungszeitpunkt die
    Regelaltersgrenze erreicht hat."""
    if not regelalter_erreicht and alter is not None:
        for a, j, m in PARAM["kschg_10_stufen"]:
            if alter >= a and jahre >= j:
                return m
    return PARAM["kschg_10_grund"]


def m_gericht(fall, mv, dauer, key="gericht", name="Gerichtliche Auflösung §§ 9, 10 KSchG",
              grundlage="§§ 9, 10 KSchG"):
    alter = fall.get("alter")
    jahre = dauer["jahre"] if dauer else 0
    grenze = obergrenze_10(alter, jahre, fall.get("regelalter"))
    vor = _kschg_anwendbar(fall, dauer) + [
        _vor("Kündigung sozial ungerechtfertigt (vom Gericht festgestellt)", None),
        _vor("Auflösungsantrag: Fortsetzung unzumutbar (AN) bzw. keine gedeihliche Zusammenarbeit (AG)", None)]
    hinweise = [f"Höchstgrenze {grenze} Monatsverdienste ({_grenze_text(alter, jahre, fall.get('regelalter'))}). "
                "Das Gericht setzt einen angemessenen Betrag fest – oft deutlich darunter.",
                "§ 13 KSchG: Auflösung und Abfindung sind auch bei unwirksamer außerordentlicher oder "
                "sittenwidriger Kündigung möglich (bei außerordentlicher Kündigung nur auf Antrag des AN)."]
    return _modell(key, name, "gericht", f"bis {grenze} MV", mv * grenze, STATUS["gericht"], True, vor,
                   f"höchstens {grenze} × {de(mv)} € = {de(eur(mv * grenze))} €", hinweise, grundlage)


def _grenze_text(alter, jahre, regel):
    if regel:
        return "Regelaltersgrenze erreicht – keine erhöhte Grenze"
    if alter is not None and alter >= 55 and jahre >= 20:
        return "ab 55 Jahren und 20 Jahren Betriebszugehörigkeit"
    if alter is not None and alter >= 50 and jahre >= 15:
        return "ab 50 Jahren und 15 Jahren Betriebszugehörigkeit"
    return "Grundsatz"


def m_nachteilsausgleich(fall, mv, dauer):
    m = m_gericht(fall, mv, dauer, "113", "Nachteilsausgleich § 113 BetrVG", "§ 113 BetrVG i. V. m. § 10 KSchG")
    m["voraussetzungen"] = [
        _vor("Betriebsänderung im Sinne von § 111 BetrVG (Betrieb mit mehr als 20 wahlberechtigten AN)",
             fall.get("betriebsaenderung")),
        _vor("Arbeitgeber weicht ohne zwingenden Grund vom Interessenausgleich ab oder hat keinen "
             "Interessenausgleich versucht", fall.get("ia_verletzt")),
        _vor("Entlassung infolge dieser Abweichung / Betriebsänderung", None)]
    m["hinweise"] = ["Höhe entsprechend § 10 KSchG (Höchstgrenze); andere wirtschaftliche Nachteile werden bis "
                     "zu 12 Monaten ausgeglichen (§ 113 Abs. 2). Keine automatische Gleichsetzung mit einer "
                     "Sozialplanabfindung – Sozialplanleistungen können angerechnet werden."]
    if _alle(m["voraussetzungen"]) is False:
        m.update(anwendbar=False, status=STATUS["nicht"], brutto=None)
    return m


# ---------------------------------------------------------------------------
# G./I./J. Sozialplan, Tarifvertrag, Betriebsvereinbarung - frei konfigurierbares Regelwerk
# ---------------------------------------------------------------------------
def regelwerk(fall, mv, jahre, r):
    """Allgemeine Formel fuer Sozialplan, Tarifvertrag, Betriebsvereinbarung.
    r: {"methode": "faktor"|"divisor"|"punkte"|"fest", "faktor", "divisor", "punktwert",
        "p_jahr", "p_alter", "p_kind", "p_sb", "festbetrag", "sockel", "kind", "unterhalt", "sb",
        "staffel": [(ab_jahren, faktor)], "altersstaffel": [(ab_alter, faktor_zuschlag)],
        "min", "max", "max_monate", "rentennah": {"monate_bis_rente", "prozent"}, "quote"}
    -> (brutto Decimal, [(bezeichnung, betrag)], [hinweise])"""
    alter = d(fall.get("alter") or 0)
    kinder = d(fall.get("kinder") or 0)
    unterhalt = d(fall.get("unterhalt") or 0)
    sb = bool(fall.get("schwerbehindert"))
    teile, hinweise = [], []
    methode = r.get("methode", "faktor")
    faktor = d(r.get("faktor") or 0)
    for ab, f in sorted(r.get("staffel") or [], key=lambda x: x[0]):
        if jahre >= d(ab):
            faktor = d(f)
    alters_zuschlag = Decimal(0)
    for ab, z in sorted(r.get("altersstaffel") or [], key=lambda x: x[0]):
        if alter >= d(ab):
            alters_zuschlag = d(z)                 # hoechste erreichte Altersstufe
    if methode == "faktor":
        faktor += alters_zuschlag
    if methode == "faktor":
        grund = mv * jahre * faktor
        teile.append((f"Grundbetrag {de(mv)} € × {de(jahre, 2)} J. × {de(faktor, 2)}", grund))
    elif methode == "divisor":
        div = d(r.get("divisor") or 0)
        grund = alter * jahre * mv / div if div else Decimal(0)
        teile.append((f"Grundbetrag Alter {de(alter, 0)} × {de(jahre, 2)} J. × {de(mv)} € ÷ {de(div, 0)}", grund))
    elif methode == "punkte":
        punkte = (jahre * d(r.get("p_jahr")) + alter * d(r.get("p_alter")) + kinder * d(r.get("p_kind"))
                  + (d(r.get("p_sb")) if sb else 0))
        grund = punkte * d(r.get("punktwert"))
        teile.append((f"{de(punkte, 1)} Punkte × {de(r.get('punktwert'))} € Punktwert", grund))
    else:
        grund = d(r.get("festbetrag"))
        teile.append(("Festbetrag", grund))
    for k, txt, menge in (("sockel", "Sockelbetrag", 1), ("kind", "Kinderzuschlag", kinder),
                          ("unterhalt", "Zuschlag Unterhaltsberechtigte", unterhalt),
                          ("sb", "Zuschlag Schwerbehinderung", 1 if sb else 0)):
        if d(r.get(k)) and menge:
            teile.append((f"{txt}" + (f" ({de(menge, 0)} ×)" if menge != 1 else ""), d(r.get(k)) * d(menge)))
    summe = sum((b for _, b in teile), Decimal(0))
    rn = r.get("rentennah") or {}
    if rn.get("monate_bis_rente") is not None and d(rn.get("prozent")):
        deckel = mv * d(rn["monate_bis_rente"]) * d(rn["prozent"]) / 100
        if summe > deckel:
            teile.append((f"Rentennah: begrenzt auf {de(rn['prozent'], 0)} % × {rn['monate_bis_rente']} Monate bis "
                          "zur Rente", deckel - summe))
            hinweise.append("Begrenzung für rentennahe Beschäftigte – nur zulässig, wenn der Sozialplan sie vorsieht "
                            "und sie sachlich gerechtfertigt ist (§ 10 Satz 3 Nr. 6 AGG).")
            summe = deckel
    if d(r.get("min")) and summe < d(r["min"]):
        teile.append(("Anhebung auf Mindestabfindung", d(r["min"]) - summe))
        summe = d(r["min"])
    hoechst = [d(r["max"])] if d(r.get("max")) else []
    if d(r.get("max_monate")):
        hoechst.append(mv * d(r["max_monate"]))
    if hoechst and summe > min(hoechst):
        teile.append(("Kappung auf Höchstbetrag", min(hoechst) - summe))
        summe = min(hoechst)
    quote = d(r.get("quote") or 100)
    if quote < 100:
        teile.append((f"Budgetkürzung auf {de(quote, 1)} %", summe * (quote / 100) - summe))
        summe = summe * quote / 100
    hinweise.append("Gleichbehandlung (§ 75 BetrVG) und Diskriminierungsverbote (AGG) beachten: Alters- und "
                    "Zuschlagsregeln müssen sachlich gerechtfertigt sein.")
    return eur(summe), [(t, eur(b)) for t, b in teile], hinweise


def sozialplan_quote(budget, summe_ansprueche):
    """Verteilungsquote, wenn das Budget nicht fuer alle Ansprueche reicht (anteilige Kuerzung)."""
    b, s = d(budget), d(summe_ansprueche)
    if b <= 0 or s <= 0 or b >= s:
        return Decimal(100)
    return (b / s * 100).quantize(Decimal("0.01"))


def m_regelwerk(key, name, fall, mv, jahre, r, art="kollektiv", grundlage=""):
    brutto, teile, hinweise = regelwerk(fall, mv, jahre, r)
    return _modell(key, name, art, {"faktor": de(r.get("faktor") or 0, 2), "divisor": f"Divisor {r.get('divisor')}",
                                    "punkte": "Punkte", "fest": "Festbetrag"}.get(r.get("methode", "faktor")),
                   brutto, STATUS["kollektiv"], True, [], " + ".join(t for t, _ in teile), hinweise, grundlage,
                   [(t, b, "abfindung") for t, b in teile])


# ---------------------------------------------------------------------------
# L. Freiwilligenprogramm, M. Turbo-/Sprinterklausel
# ---------------------------------------------------------------------------
def m_freiwillig(mv, jahre, p):
    basis = mv * jahre * d(p.get("faktor") or 0) + d(p.get("festbetrag"))
    teile = [("Grundabfindung", basis)]
    for k, txt in (("frueh", "Frühentscheiderbonus"), ("unterschrift", "Unterschriftenbonus"),
                   ("praemie", "Zusatzprämie"), ("sonder", "Individuelle Sondervereinbarung")):
        if d(p.get(k)):
            teile.append((txt, d(p[k])))
    if d(p.get("zuschlag_pct")):
        teile.append((f"Freiwilligenzuschlag {de(p['zuschlag_pct'], 1)} %", basis * d(p["zuschlag_pct"]) / 100))
    summe = sum((b for _, b in teile), Decimal(0))
    return _modell("freiwillig", "Freiwilligenprogramm", "verhandlung", de(p.get("faktor") or 0, 2), summe,
                   STATUS["verhandlung"], True, [], " + ".join(f"{t} {de(eur(b))} €" for t, b in teile),
                   ["Angebote mit Frist: Bedingungen (Stichtag, Mindestzahl Freiwilliger) prüfen. Freiwillige "
                    "Aufhebung → Sperrzeitrisiko beim Arbeitslosengeld beachten."],
                   "Freiwilligenprogramm / Vereinbarung", [(t, eur(b), "abfindung") for t, b in teile])


def turbo(mv_gehalt, ende_vertrag, ende_tatsaechlich, beteiligung_pct, ag_sv_pct=0, sprinter_fest=0):
    """Turboklausel: Anteil der eingesparten Gehaelter fuer jeden Monat frueheren Ausscheidens.
    Nur ganze und anteilige Kalendermonate zwischen tatsaechlichem und vertraglichem Ende.
    -> {"monate", "eingespart", "praemie", "gesamt"}"""
    if not ende_vertrag or not ende_tatsaechlich or ende_tatsaechlich >= ende_vertrag:
        return {"monate": Decimal(0), "eingespart": Decimal(0), "praemie": eur(sprinter_fest),
                "gesamt": eur(sprinter_fest)}
    z = beschaeftigung(ende_tatsaechlich + datetime.timedelta(days=1), ende_vertrag)
    monate = (d(z["jahre"] * 12 + z["monate"]) + d(z["tage"]) / d("30.4375")).quantize(Decimal("0.01"))
    eingespart = d(mv_gehalt) * monate * (1 + d(ag_sv_pct) / 100)
    praemie = eingespart * d(beteiligung_pct) / 100
    return {"monate": monate, "eingespart": eur(eingespart), "praemie": eur(praemie),
            "gesamt": eur(praemie + d(sprinter_fest))}


def m_turbo(basis_abfindung, t):
    teile = [("Grundabfindung (vereinbart)", eur(basis_abfindung), "abfindung")]
    if t["praemie"]:
        teile.append((f"Sprinter-/Turboprämie ({de(t['monate'], 2)} Monate früher)", t["gesamt"], "abfindung"))
    summe = sum((b for _, b, _a in teile), Decimal(0))
    return _modell("turbo", "Turboklausel / Sprinterprämie", "vertrag", "Vertrag", summe, STATUS["vertrag"], True,
                   [], f"eingesparte Gehälter {de(t['eingespart'])} € × Beteiligung = {de(t['praemie'])} €"
                   + (" + fester Sprinterbonus" if t["gesamt"] != t["praemie"] else ""),
                   ["Keine Doppelzählung: Gehalt bis zum früheren Ende ist Arbeitslohn, nicht Teil der Prämie.",
                    "Steuer: Die Prämie wird in der Regel als Teil der Entschädigung (§ 24 Nr. 1 EStG) behandelt, "
                    "wenn sie im Aufhebungs-/Abwicklungsvertrag für das vorzeitige Ausscheiden vereinbart ist – "
                    "Einzelfallprüfung."], "Aufhebungs-/Abwicklungsvertrag", teile)


# ---------------------------------------------------------------------------
# N. Insolvenz (§§ 123, 124 InsO)
# ---------------------------------------------------------------------------
def insolvenz(anspruch, p):
    """p: {"betroffene", "summe_mv" (Monatsverdienste aller Betroffenen), "masse", "summe_ansprueche",
    "nach_eroeffnung": bool, "monate_vor_antrag"}. Die 2,5 Monatsverdienste nach § 123 Abs. 1 begrenzen
    das GESAMTVOLUMEN, nicht den einzelnen Anspruch."""
    hinweise = []
    gesamt = d(p.get("summe_ansprueche"))
    grenze1 = PARAM["inso_123_monate"] * d(p.get("summe_mv")) if d(p.get("summe_mv")) else None
    grenze2 = d(p.get("masse")) * PARAM["inso_123_masse_anteil"] if p.get("masse") is not None else None
    quote = Decimal(1)
    if p.get("nach_eroeffnung", True):
        if grenze1 is not None and gesamt > grenze1:
            quote = min(quote, grenze1 / gesamt)
            hinweise.append(f"Gesamtvolumen über 2,5 Monatsverdienste aller Betroffenen ({de(eur(grenze1))} €) – "
                            "Sozialplan insoweit unwirksam, Ansprüche werden anteilig gekürzt (§ 123 Abs. 1 InsO).")
        if grenze2 is not None and gesamt > 0 and min(gesamt * quote, gesamt) > grenze2:
            quote = min(quote, grenze2 / gesamt)
            hinweise.append(f"Für Sozialplanforderungen darf höchstens ein Drittel der Teilungsmasse verwendet werden "
                            f"({de(eur(grenze2))} €) – anteilige Kürzung (§ 123 Abs. 2 InsO).")
        hinweise.append("Sozialplanforderungen nach Eröffnung sind Masseverbindlichkeiten; ausgezahlt wird erst, wenn "
                        "die Masse reicht – Zeitpunkt und Höhe sind unsicher.")
    else:
        mva = p.get("monate_vor_antrag")
        if mva is not None and mva <= PARAM["inso_124_monate"]:
            hinweise.append("Sozialplan in den letzten 3 Monaten vor dem Insolvenzantrag: Verwalter und Betriebsrat "
                            "können ihn widerrufen (§ 124 InsO).")
        else:
            hinweise.append("Sozialplan vor dem Insolvenzantrag: Forderung meist nur Insolvenzforderung (Quote).")
    return {"anspruch": eur(anspruch), "quote": (quote * 100).quantize(Decimal("0.01")),
            "auszahlung": eur(d(anspruch) * quote), "hinweise": hinweise}


# ---------------------------------------------------------------------------
# Sonderfaelle und Personengruppen
# ---------------------------------------------------------------------------
SONDERFAELLE = {
    "kleinbetrieb": ("Kleinbetrieb (≤ 10 AN)", "Kein allgemeiner Kündigungsschutz (§ 23 KSchG) – kein Anspruch nach "
                     "§ 1a, keine Auflösung nach §§ 9, 10. Abfindung nur verhandelt."),
    "probezeit": ("Probezeit / Wartezeit", "In den ersten 6 Monaten kein Kündigungsschutz nach KSchG – Abfindung "
                  "nur freiwillig."),
    "befristet": ("Befristetes Arbeitsverhältnis", "Endet mit Fristablauf ohne Kündigung – keine Abfindung, außer "
                  "vereinbart oder die Befristung ist unwirksam."),
    "altersteilzeit": ("Altersteilzeit", "Abfindung nur nach Vereinbarung; Aufstockung und Rentenfolgen gesondert "
                       "prüfen."),
    "rentennah": ("Rentennahes Ausscheiden", "Sozialpläne dürfen rentennahe Beschäftigte geringer abfinden "
                  "(§ 10 Satz 3 Nr. 6 AGG). Rentenabschläge ggf. über § 187a SGB VI ausgleichen."),
    "schwerbehindert": ("Schwerbehinderung", "Kündigung nur mit Zustimmung des Integrationsamts (§ 168 SGB IX) – "
                        "Schutzrecht, aber kein automatischer Abfindungsanspruch."),
    "mutterschutz": ("Schwangerschaft / Mutterschutz", "Kündigungsverbot (§ 17 MuSchG) – Schutzrecht, kein "
                     "Abfindungsanspruch; Aufhebungsvertrag sorgfältig prüfen."),
    "elternzeit": ("Elternzeit", "Besonderer Kündigungsschutz (§ 18 BEEG) – kein automatischer Abfindungsanspruch."),
    "leitend": ("Leitende Angestellte", "Auflösungsantrag des Arbeitgebers ohne Begründung möglich (§ 14 Abs. 2 "
                "KSchG); Abfindung im Rahmen von § 10."),
    "betriebsuebergang": ("Betriebsübergang", "Arbeitsverhältnis geht über (§ 613a BGB) – Kündigung wegen des "
                          "Übergangs unwirksam; Abfindung nur bei Widerspruch und anschließender Kündigung/Vereinbarung."),
    "ausserordentlich": ("Außerordentliche Kündigung", "Bei unwirksamer fristloser Kündigung Auflösung mit "
                         "Abfindung auf Antrag des AN (§ 13 Abs. 1 KSchG)."),
    "schadensersatz_628": ("Eigenkündigung wegen Vertragsbruch des AG", "Schadensersatz nach § 628 Abs. 2 BGB "
                           "(entgangenes Entgelt bis zum Ende der Kündigungsfrist + ggf. Abfindungsverlust) – "
                           "Einzelfallprüfung."),
    "organ": ("Geschäftsführer / Vorstand", "Kein Arbeitnehmer im Sinne des KSchG (§ 14 Abs. 1) – die "
              "KSchG-Formeln gelten nicht; Abfindung nur aus dem Dienstvertrag."),
    "beamte": ("Beamte", "Kein Arbeitsverhältnis – keine Abfindung nach Arbeitsrecht."),
    "handelsvertreter": ("Selbstständige Handelsvertreter", "Kein Arbeitnehmer – stattdessen ggf. Ausgleichsanspruch "
                         "nach § 89b HGB."),
}
KEINE_ARBEITNEHMER = ("organ", "beamte", "handelsvertreter")


# ---------------------------------------------------------------------------
# Arbeitslosengeld: Sperrzeit (§ 159), Ruhen (§ 158), Meldung (§ 38), Dauer (§ 147)
# ---------------------------------------------------------------------------
def ruhen_158(abfindung, ende, fiktives_ende, jahresentgelt, alter, jahre_betrieb):
    """Ruhen des ALG bei Entlassungsentschaedigung und nicht eingehaltener Kuendigungsfrist.
    Beginn: Tag nach dem Ende des Arbeitsverhaeltnisses. Ende ist das fruehere von
    - dem Tag, an dem das AV bei Einhaltung der ordentlichen Frist geendet haette,
    - einem Jahr nach dem Ende,
    - dem Tag, bis zu dem der AN mit dem bisherigen kalendertaeglichen Entgelt den
      beruecksichtigungsfaehigen Anteil der Entschaedigung verdient haette (60 %, je 5 volle
      Jahre Betriebszugehoerigkeit und je 5 volle Lebensjahre ueber 35 minus 5 %, mindestens 25 %).
    -> dict oder None (Frist eingehalten / Daten fehlen)."""
    if not ende or not fiktives_ende or fiktives_ende <= ende or not abfindung:
        return None
    p = PARAM
    anteil = p["alg_158_start"] - p["alg_158_stufe"] * (int(jahre_betrieb or 0) // 5) \
        - p["alg_158_stufe"] * (max(int(alter or 0) - 35, 0) // 5)
    anteil = max(anteil, p["alg_158_min"])
    tagesentgelt = d(jahresentgelt) / 365 if jahresentgelt else None
    beginn = ende + datetime.timedelta(days=1)
    grenzen = [("ordentliche Kündigungsfrist", fiktives_ende), ("ein Jahr", _plus_monate(ende, 12))]
    tage_anteil = None
    if tagesentgelt:
        tage_anteil = int((d(abfindung) * d(anteil) / 100 / tagesentgelt).to_integral_value(rounding="ROUND_FLOOR"))
        grenzen.append((f"{anteil} % der Abfindung verdient", ende + datetime.timedelta(days=tage_anteil)))
    grund, bis = min(grenzen, key=lambda g: g[1])
    tage = (bis - ende).days
    return {"beginn": beginn, "bis": bis, "tage": max(tage, 0), "anteil": anteil, "grund": grund,
            "tage_anteil": tage_anteil, "tagesentgelt": eur(tagesentgelt) if tagesentgelt else None}


def alg_dauer(versicherungsmonate, alter):
    for vm, ab_alter, monate in PARAM["alg_dauer"]:
        if (versicherungsmonate or 0) >= vm and (alter or 0) >= ab_alter:
            return monate
    return 0


def alg_check(fall, dauer, abfindung, mv):
    """Risiko- und Fristencheck ALG I -> {"sperrzeit", "ruhen", "meldung", "klagefrist", "punkte": [...]}"""
    art = fall.get("art")
    punkte = []
    sperr = None
    wichtiger_grund = fall.get("wichtiger_grund")
    ende = fall.get("ende")
    zugang = fall.get("zugang")
    jahre = dauer["jahre"] if dauer else 0
    frist_m = fall.get("frist_monate")
    if frist_m is None:
        frist_m = gesetzliche_frist_monate(jahre)
    fiktiv = fristende(zugang, frist_m, wochen4=frist_m == 0) if zugang else None
    frist_ok = None if not (fiktiv and ende) else ende >= fiktiv
    if art in ("aufhebung", "eigen"):
        faktor = (d(abfindung) / (mv * max(d(dauer["jahre_dezimal"]), Decimal("0.01")))) if (dauer and mv) else None
        im_korridor = faktor is not None and Decimal("0.25") <= faktor <= Decimal("0.5")
        if wichtiger_grund:
            sperr = {"stufe": "gering", "tage": 0,
                     "text": "Wichtiger Grund angegeben – keine Sperrzeit, wenn die Agentur ihn anerkennt."}
        elif art == "aufhebung" and im_korridor and fall.get("drohende_ag_kuendigung") and frist_ok:
            sperr = {"stufe": "gering", "tage": 0,
                     "text": "Aufhebungsvertrag statt drohender betriebsbedingter AG-Kündigung, Frist eingehalten "
                             f"und Abfindung im Korridor 0,25–0,5 Monatsverdienste je Jahr ({de(faktor, 2)}) – nach "
                             "den Fachlichen Weisungen zu § 159 in der Regel wichtiger Grund."}
        else:
            sperr = {"stufe": "hoch", "tage": PARAM["alg_159_tage"],
                     "text": "Aufhebungsvertrag/Eigenkündigung ohne wichtigen Grund: Sperrzeit 12 Wochen (§ 159 "
                             "Abs. 3 SGB III); der Anspruch verkürzt sich um mindestens ein Viertel (§ 148)."}
    elif art == "abwicklung":
        sperr = {"stufe": "mittel", "tage": 0,
                 "text": "Abwicklungsvertrag nach AG-Kündigung: grundsätzlich keine Sperrzeit, wenn die Kündigung "
                         "nicht offensichtlich rechtswidrig ist und nicht vorher abgesprochen war – prüfen."}
    elif art in ("ag_verhalten",):
        sperr = {"stufe": "hoch", "tage": PARAM["alg_159_tage"],
                 "text": "Verhaltensbedingte Kündigung: Sperrzeit wegen Arbeitsaufgabe möglich (§ 159 Abs. 1 Nr. 1)."}
    elif art in ("ag_betriebsbedingt", "ag_personenbedingt", "vergleich"):
        sperr = {"stufe": "gering", "tage": 0,
                 "text": "Arbeitgeberkündigung (nicht verhaltensbedingt) bzw. gerichtlicher Vergleich danach: in der "
                         "Regel keine Sperrzeit. Die Abfindung allein löst keine Sperrzeit aus."}
    ruhen = None
    if frist_ok is False and abfindung:
        ruhen = ruhen_158(abfindung, ende, fiktiv, fall.get("jahresentgelt"), fall.get("alter"), jahre)
    if frist_ok is False and not ruhen:
        punkte.append("Kündigungsfrist nicht eingehalten – für die Ruhensberechnung fehlen Daten (Jahresentgelt).")
    meldung = None
    if ende:
        spaetestens = _plus_monate(ende, -PARAM["alg_meldung_monate"])
        meldung = {"spaetestens": spaetestens,
                   "text": f"Arbeitsuchend melden spätestens am {spaetestens.strftime('%d.%m.%Y')} (3 Monate vor "
                           "dem Ende) bzw. innerhalb von 3 Tagen nach Kenntnis, wenn das Ende kurzfristiger feststeht "
                           "(§ 38 SGB III). Verspätet: 1 Woche Sperrzeit (§ 159 Abs. 6)."}
    klage = None
    if zugang and art and art.startswith("ag_"):
        bis = zugang + datetime.timedelta(weeks=PARAM["klagefrist_wochen"])
        klage = {"bis": bis, "text": f"Kündigungsschutzklage bis {bis.strftime('%d.%m.%Y')} (3 Wochen nach Zugang, "
                                     "§ 4 KSchG) – danach gilt die Kündigung als wirksam."}
    dauer_alg = alg_dauer(fall.get("versicherungsmonate"), fall.get("alter"))
    return {"sperrzeit": sperr, "ruhen": ruhen, "meldung": meldung, "klagefrist": klage, "frist_ok": frist_ok,
            "fiktives_ende": fiktiv, "frist_monate": frist_m, "alg_monate": dauer_alg, "punkte": punkte}


# ---------------------------------------------------------------------------
# Steuer und Netto je Modell (zusaetzliche Steuerlast durch die Abfindung)
# ---------------------------------------------------------------------------
def steuer_netto(brutto, st_e, jahr=None, fuenftel=None):
    """st_e: {"zve" (ohne Abfindung), "splitting", "kirche", "alg", "fuenftel_moeglich"}.
    -> {"brutto", "steuer", "est", "soli", "kirche", "netto", "lohnsteuer_ca", "erstattung", "fuenftel"}"""
    b = float(brutto or 0)
    jahr = int(jahr or st_e.get("jahr") or A.STEUERJAHR)
    fuenftel = st_e.get("fuenftel_moeglich", True) if fuenftel is None else fuenftel
    sp, ki, zve, pv = st_e.get("splitting", False), st_e.get("kirche", 0.0), st_e.get("zve", 0.0), st_e.get("alg", 0.0)
    ohne = A.steuern(A.est(zve, sp, pv, jahr), sp, ki, jahr)
    mit_f = A.steuern(A.est_mit_abfindung(zve, b, True, sp, pv, jahr), sp, ki, jahr)
    mit_v = A.steuern(A.est_mit_abfindung(zve, b, False, sp, pv, jahr), sp, ki, jahr)
    endg = mit_f if fuenftel else mit_v
    x = {k: eur(endg[k] - ohne[k]) for k in ("est", "soli", "kirche", "summe")}
    voll = eur(mit_v["summe"] - ohne["summe"])
    return {"brutto": eur(b), "steuer": x["summe"], "est": x["est"], "soli": x["soli"], "kirche": x["kirche"],
            "netto": eur(b) - x["summe"], "lohnsteuer_ca": voll, "erstattung": voll - x["summe"],
            "ohne_fuenftel": voll, "fuenftel": bool(fuenftel), "jahr": jahr}


def brutto_fuer_netto(ziel_netto, st_e, jahr=None):
    """Erforderliche Bruttoabfindung fuer ein Wunsch-Netto (Bisektion auf Cent genau)."""
    ziel = float(ziel_netto or 0)
    if ziel <= 0:
        return eur(0)
    lo, hi = ziel, ziel * 3 + 1000
    while float(steuer_netto(hi, st_e, jahr)["netto"]) < ziel and hi < 1e9:
        hi *= 2
    for _ in range(80):
        m = (lo + hi) / 2
        if float(steuer_netto(m, st_e, jahr)["netto"]) >= ziel:
            hi = m
        else:
            lo = m
    return eur(math.ceil(hi * 100) / 100)


# ---------------------------------------------------------------------------
# Fuenftelregel-Status
# ---------------------------------------------------------------------------
def fuenftel_status(abfindung, jahresbrutto_auszahlungsjahr, vorjahr_brutto, alg=0.0, teilzahlung_pct=0.0):
    """-> ("anwendbar"|"nicht anwendbar"|"prüfen", text)"""
    if teilzahlung_pct and teilzahlung_pct > 10:
        return ("nicht anwendbar", "Verteilung auf mehrere Jahre mit Teilzahlung über 10 % der Hauptzahlung – keine "
                                   "Zusammenballung (§ 34 EStG).")
    if not vorjahr_brutto:
        return ("prüfen", "Zusammenballung nicht prüfbar – Vorjahresbrutto fehlt.")
    dieses = float(jahresbrutto_auszahlungsjahr or 0) + float(alg or 0) + float(abfindung or 0)
    if dieses > float(vorjahr_brutto):
        return ("anwendbar", f"Einnahmen im Auszahlungsjahr ({de(dieses, 0)} €) höher als bei Fortsetzung "
                             f"(Vorjahr {de(vorjahr_brutto, 0)} €) – Zusammenballung liegt voraussichtlich vor. "
                             "Seit 2025 nur über die Steuererklärung.")
    return ("nicht anwendbar", f"Einnahmen im Auszahlungsjahr ({de(dieses, 0)} €) nicht höher als im Vorjahr "
                               f"({de(vorjahr_brutto, 0)} €) – voraussichtlich keine Zusammenballung.")


# ---------------------------------------------------------------------------
# Alle Modelle eines Falls
# ---------------------------------------------------------------------------
def alle_modelle(fall, cfg=None):
    """fall: Fall-Daten (siehe UI). cfg: optionale Modell-Einstellungen (Sozialplan, Vertrag ...).
    -> {"mv", "mv_teile", "dauer", "jahre", "modelle": [...], "personengruppe": text|None}"""
    cfg = cfg or {}
    mv, mv_teile = monatsverdienst(fall)
    dauer = beschaeftigung(fall.get("beginn"), fall.get("ende"), fall.get("vorzeit_monate"))
    jahre = d(dauer["jahre_dezimal"]) if dauer else d(fall.get("jahre") or 0)
    if dauer is None and fall.get("jahre") is not None:
        j = d(fall["jahre"])
        dauer = {"jahre": int(j), "monate": int((j - int(j)) * 12), "tage": 0, "jahre_dezimal": float(j),
                 "jahre_1a": int(j) + (1 if (j - int(j)) * 12 > 6 else 0)}
    gruppe = next((k for k in KEINE_ARBEITNEHMER if fall.get("sonder", {}).get(k)), None)
    modelle = []
    if gruppe:
        info = SONDERFAELLE[gruppe]
        modelle.append(_modell("gruppe", info[0], "nicht", "–", None, STATUS["nicht"], False, [], "", [info[1]]))
    else:
        modelle.append(m_1a(fall, mv, dauer))
        for f in FAKTOREN:
            modelle.append(m_faktor(mv, jahre, f))
        if cfg.get("eigener_faktor"):
            modelle.append(m_faktor(mv, jahre, cfg["eigener_faktor"], f"Eigener Faktor {de(cfg['eigener_faktor'], 2)}"))
        modelle.append(m_gericht(fall, mv, dauer))
        modelle.append(m_nachteilsausgleich(fall, mv, dauer))
    if cfg.get("aufhebung"):
        c = cfg["aufhebung"]
        modelle.append(m_vertrag("aufhebung", "Aufhebungsvertrag", mv, jahre, c.get("betrag"), c.get("faktor"),
                                 c.get("zusatz"), "vertrag", "Aufhebungsvertrag",
                                 ["Gehalt bis zum Ende, Urlaubsabgeltung und Boni sind Arbeitsentgelt – getrennt von "
                                  "der Abfindung, normal steuer- und beitragspflichtig.",
                                  "Sperrzeit- und Ruhensrisiko siehe „Arbeitslosengeld & Risiken“."]))
    if cfg.get("abwicklung"):
        c = cfg["abwicklung"]
        modelle.append(m_vertrag("abwicklung", "Abwicklungsvertrag", mv, jahre, c.get("betrag"), c.get("faktor"),
                                 c.get("zusatz"), "vertrag", "Abwicklungsvertrag nach Kündigung",
                                 ["Der Vertrag regelt die Folgen einer bereits ausgesprochenen Kündigung – das "
                                  "Arbeitsverhältnis endet durch die Kündigung, nicht durch den Vertrag."]))
    if cfg.get("vergleich"):
        c = cfg["vergleich"]
        modelle.append(m_vertrag("vergleich", "Gerichtlicher Vergleich", mv, jahre, c.get("betrag"), c.get("faktor"),
                                 c.get("zusatz"), "verhandlung", "Prozessvergleich",
                                 ["Freiwillige Einigung vor Gericht – anders als die Auflösung nach §§ 9, 10 gibt es "
                                  "keine gesetzliche Höchstgrenze."]))
    for k, name, grundlage in (("sozialplan", "Sozialplan", "§§ 111, 112 BetrVG"),
                               ("tarif", "Tarifvertrag", "Tarifvertrag"),
                               ("bv", "Betriebsvereinbarung", "Betriebsvereinbarung")):
        if cfg.get(k):
            modelle.append(m_regelwerk(k, name, fall, mv, jahre, cfg[k], grundlage=grundlage))
    if cfg.get("zusage"):
        c = cfg["zusage"]
        modelle.append(m_vertrag("zusage", "Vertraglich zugesicherte Abfindung", mv, jahre, c.get("betrag"),
                                 c.get("faktor"), None, "vertrag", "Arbeitsvertrag / Zusage",
                                 ["Anspruch nur, wenn die vertraglichen Voraussetzungen (z. B. Kündigung durch den "
                                  "AG, Stichtag) tatsächlich erfüllt sind."],
                                 [_vor("Vertragliche Voraussetzungen erfüllt", c.get("erfuellt"))]))
    if cfg.get("freiwillig"):
        modelle.append(m_freiwillig(mv, jahre, cfg["freiwillig"]))
    if cfg.get("turbo"):
        c = cfg["turbo"]
        t = turbo(mv, c.get("ende_vertrag"), c.get("ende_tatsaechlich"), c.get("beteiligung", 0),
                  c.get("ag_sv", 0), c.get("sprinter", 0))
        modelle.append(m_turbo(c.get("basis") or 0, t))
    return {"mv": mv, "mv_teile": mv_teile, "dauer": dauer, "jahre": jahre, "modelle": modelle,
            "personengruppe": gruppe}


def vergleich(ergebnis, st_e, jahr=None):
    """Steuer/Netto fuer alle anwendbaren Modelle -> Zeilen fuer die Vergleichsansicht."""
    zeilen = []
    for m in ergebnis["modelle"]:
        sn = steuer_netto(m["brutto"], st_e, jahr) if (m["brutto"] is not None and m["anwendbar"]) else None
        zeilen.append({"modell": m, "steuer": sn})
    return zeilen


def faktor_fuer_brutto(brutto, mv, jahre):
    if not mv or not jahre:
        return None
    return (d(brutto) / (d(mv) * d(jahre))).quantize(Decimal("0.01"))
