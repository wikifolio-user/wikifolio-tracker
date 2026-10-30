"""Einkommensteuer (Tarif 2026 aus den Parametern), Rentenbesteuerung, Abgeltungsteuer.

- Jahressteuer (Veranlagung), nicht die monatliche Lohnsteuer: die Steuerklasse veraendert nur den
  Abzug im Jahr; ueber die Steuererklaerung gleicht sich das aus.
- Spaetere Jahre: Tarifeckwerte optional mit der Inflation fortgeschrieben (Ausgleich der kalten
  Progression wie in den letzten Jahren ueblich) - faktor = (1 + Inflation)^(Jahr - 2026).
"""
import math


# ---------------------------------------------------------------------------
# Tabellen aus dem Gesetz
# ---------------------------------------------------------------------------
def besteuerungsanteil(jahr_rentenbeginn):
    """§ 22 Nr. 1 S. 3 a aa EStG i. d. F. Wachstumschancengesetz: 2005 50 %, bis 2020 +2, bis 2022 +1,
    ab 2023 +0,5 Prozentpunkte je Jahrgang -> 100 % ab 2058. -> Anteil 0..1"""
    j = int(jahr_rentenbeginn)
    if j <= 2005:
        pct = 50.0
    elif j <= 2020:
        pct = 50.0 + 2.0 * (j - 2005)
    elif j <= 2022:
        pct = 80.0 + 1.0 * (j - 2020)
    else:
        pct = min(82.5 + 0.5 * (j - 2023), 100.0)
    return pct / 100.0


# § 22 Nr. 1 S. 3 a bb EStG: Ertragsanteil nach vollendetem Lebensjahr bei Rentenbeginn (ab 50 Jahren)
_ERTRAG = [(50, 30), (51, 29), (53, 28), (54, 27), (55, 26), (57, 25), (58, 24), (59, 23), (60, 22), (62, 21),
           (63, 20), (64, 19), (65, 18), (67, 17), (68, 16), (69, 15), (71, 14), (72, 13), (74, 12), (75, 11),
           (76, 10), (78, 9), (80, 8), (81, 7), (83, 6), (85, 5), (88, 4), (92, 3), (94, 2), (97, 1)]


def ertragsanteil(alter):
    """Ertragsanteil privater Leibrenten (Anteil 0..1); unter 50 Jahren pauschal 30 % (Tabelle reicht weiter)."""
    a = int(alter)
    pct = 30
    for ab, wert in _ERTRAG:
        if a >= ab:
            pct = wert
    return pct / 100.0


def altersentlastung(jahr_nach_64):
    """§ 24a EStG (Wachstumschancengesetz): (Anteil, Hoechstbetrag) fuer das Kalenderjahr nach Vollendung
    des 64. Lebensjahres. 2005: 40 %/1.900 €; bis 2020 −1,6 Pkt./−76 €; bis 2023 −0,8/−38; ab 2024 −0,4/−19."""
    j = int(jahr_nach_64)
    if j <= 2005:
        return 0.40, 1900.0
    if j <= 2020:
        return (40.0 - 1.6 * (j - 2005)) / 100.0, 1900.0 - 76.0 * (j - 2005)
    if j <= 2023:
        return (16.0 - 0.8 * (j - 2020)) / 100.0, 760.0 - 38.0 * (j - 2020)
    pct = max(13.6 - 0.4 * (j - 2023), 0.0)
    return pct / 100.0, max(646.0 - 19.0 * (j - 2023), 0.0)


def versorgungsfreibetrag(jahr_beginn):
    """§ 19 Abs. 2 EStG (Wachstumschancengesetz): (Anteil, Hoechstbetrag, Zuschlag) nach Jahr des
    Versorgungsbeginns. 2005: 40 %/3.000/900; bis 2020 −1,6/−120/−36; bis 2023 −0,8/−60/−18;
    ab 2024 −0,4/−30/−9 (2026: 12,4 %, 930 €, 279 €)."""
    j = int(jahr_beginn)
    if j <= 2005:
        return 0.40, 3000.0, 900.0
    if j <= 2020:
        n = j - 2005
        return (40.0 - 1.6 * n) / 100.0, 3000.0 - 120.0 * n, 900.0 - 36.0 * n
    if j <= 2023:
        n = j - 2020
        return (16.0 - 0.8 * n) / 100.0, 1200.0 - 60.0 * n, 360.0 - 18.0 * n
    n = j - 2023
    return max(13.6 - 0.4 * n, 0.0) / 100.0, max(1020.0 - 30.0 * n, 0.0), max(306.0 - 9.0 * n, 0.0)


def halbeinkuenfte(vertragsbeginn, auszahlungsjahr, alter_bei_auszahlung):
    """Kapital-Lebensversicherung/private RV mit Kapitalauszahlung (§ 20 Abs. 1 Nr. 6 EStG):
    -> "steuerfrei" (Altvertrag vor 2005, >= 12 Jahre), "halb" (>= 12 Jahre und ab 60 bzw. ab 62 bei
    Vertraegen ab 2012) oder "voll" (Ertrag mit Abgeltungsteuer)."""
    laufzeit = int(auszahlungsjahr) - int(vertragsbeginn)
    if int(vertragsbeginn) < 2005:
        return "steuerfrei" if laufzeit >= 12 else "voll"
    mindestalter = 62 if int(vertragsbeginn) >= 2012 else 60
    return "halb" if laufzeit >= 12 and alter_bei_auszahlung >= mindestalter else "voll"


# ---------------------------------------------------------------------------
# Tarif
# ---------------------------------------------------------------------------
def tarif(zve, p, faktor=1.0):
    """Grundtarif § 32a EStG (Eckwerte * faktor), volle Euro."""
    f = max(faktor, 1e-9)
    x = math.floor(max(zve, 0.0) / f)
    if x <= p["gfb"]:
        return 0.0
    if x <= p["z2_ende"]:
        y = (x - p["gfb"]) / 10000.0
        st = (p["z2_a"] * y + p["z2_b"]) * y
    elif x <= p["z3_ende"]:
        z = (x - p["z2_ende"]) / 10000.0
        st = (p["z3_a"] * z + p["z3_b"]) * z + p["z3_c"]
    elif x <= p["z4_ende"]:
        st = 0.42 * x - p["z4_abzug"]
    else:
        st = 0.45 * x - p["z5_abzug"]
    return float(math.floor(st * f))


def est(zve, p, splitting=False, pv=0.0, faktor=1.0):
    """Einkommensteuer mit Splitting und Progressionsvorbehalt (pv: steuerfreie Leistungen wie
    Altersteilzeit-Aufstockung oder Arbeitslosengeld - erhoehen nur den Steuersatz, § 32b EStG)."""
    if zve <= 0:
        return 0.0

    def t(x):
        return 2.0 * tarif(x / 2.0, p, faktor) if splitting else tarif(x, p, faktor)
    if pv <= 0:
        return t(zve)
    satz = t(zve + pv) / (zve + pv)
    return float(math.floor(zve * satz))


def est_fuenftel(zve_rest, ao, p, splitting=False, pv=0.0, faktor=1.0):
    """§ 34 Abs. 1 EStG: ausserordentliche Einkuenfte (Abfindung, Kapitalabfindung) mit Fuenftelregelung,
    Guenstigerpruefung gegen die normale Besteuerung."""
    a = max(ao, 0.0)
    normal = est(zve_rest + a, p, splitting, pv, faktor)
    if a <= 0:
        return normal
    if zve_rest < 0:
        gesamt = zve_rest + a
        return min(5.0 * est(gesamt / 5.0, p, splitting, pv, faktor), normal) if gesamt > 0 else 0.0
    basis = est(zve_rest, p, splitting, pv, faktor)
    return min(basis + 5.0 * (est(zve_rest + a / 5.0, p, splitting, pv, faktor) - basis), normal)


def soli(est_betrag, p, splitting=False, faktor=1.0):
    frei = p["soli_freigrenze"] * (2 if splitting else 1) * faktor
    if est_betrag <= frei:
        return 0.0
    return min(p["soli_satz"] / 100.0 * est_betrag, p["soli_milderung"] / 100.0 * (est_betrag - frei))


def steuern(est_betrag, p, splitting=False, kist=0.0, faktor=1.0):
    s = soli(est_betrag, p, splitting, faktor)
    k = est_betrag * kist if est_betrag > 0 else 0.0
    return {"est": est_betrag, "soli": s, "kirche": k, "summe": est_betrag + s + k}


def grenzsteuersatz(zve, p, splitting=False, kist=0.0, faktor=1.0, schritt=100.0):
    a = steuern(est(zve, p, splitting, 0, faktor), p, splitting, kist, faktor)["summe"]
    b = steuern(est(zve + schritt, p, splitting, 0, faktor), p, splitting, kist, faktor)["summe"]
    return max(b - a, 0.0) / schritt


def abgeltung_satz(p, kist=0.0):
    """Abgeltungsteuer inkl. Soli und Kirchensteuer (§ 32d Abs. 1: KiSt mindert die Bemessung)."""
    s = p["abgeltung"] / 100.0
    kest = s / (1 + s * kist)
    return kest * (1 + p["soli_satz"] / 100.0 + kist)


# ---------------------------------------------------------------------------
# Arbeitnehmer-Netto (Vergleich vorher / waehrend Altersteilzeit)
# ---------------------------------------------------------------------------
def sv_arbeitnehmer(brutto_monat, p, kinder=True, sachsen=False, privat=False, pkv_beitrag=0.0, jahr=2026,
                    lohnfaktor=1.0):
    """Monatliche Arbeitnehmerbeitraege. -> dict rv, av, kv, pv, summe, vorsorge (steuerlich absetzbar)"""
    bbg_rv = p["bbg_rv"] * lohnfaktor / 12.0
    bbg_kv = p["bbg_kv"] * lohnfaktor / 12.0
    b_rv = min(max(brutto_monat, 0.0), bbg_rv)
    b_kv = min(max(brutto_monat, 0.0), bbg_kv)
    rv = b_rv * p["rv_satz"] / 200.0
    av = b_rv * p["av_satz"] / 200.0
    if privat:
        zuschuss = min(pkv_beitrag / 2.0, bbg_kv * ((p["kv_satz"] + p["kv_zusatz"]) / 200.0 + p["pv_satz"] / 200.0))
        kv, pv = max(pkv_beitrag - zuschuss, 0.0), 0.0
        vorsorge_kv = kv
    else:
        kv = b_kv * (p["kv_satz"] + p["kv_zusatz"]) / 200.0
        pv = b_kv * (p["pv_satz"] / 200.0 + (0 if kinder else p["pv_kinderlos"] / 100.0)
                     + (p["pv_sachsen"] / 100.0 if sachsen else 0.0))
        vorsorge_kv = kv * 0.96 + pv          # Basisabsicherung ohne Krankengeld-Anteil (4 %)
    return {"rv": rv, "av": av, "kv": kv, "pv": pv, "summe": rv + av + kv + pv, "vorsorge": rv + vorsorge_kv}


def netto_arbeitnehmer(brutto_monat, p, splitting=False, kist=0.0, kinder=True, sachsen=False, privat=False,
                       pkv_beitrag=0.0, steuerfrei_monat=0.0, andere_zve=0.0):
    """Netto im Jahr 2026 (Jahressteuer/12) - fuer den Vergleich vorher/waehrend ATZ.
    steuerfrei_monat: ATZ-Aufstockung (Progressionsvorbehalt); andere_zve: Einkommen Partner (Splitting)."""
    sv = sv_arbeitnehmer(brutto_monat, p, kinder, sachsen, privat, pkv_beitrag)
    jahr_brutto = 12 * brutto_monat
    zve = (jahr_brutto - min(p["wk_arbeitnehmer"], jahr_brutto) - 12 * sv["vorsorge"]
           - p["sonderausgaben_pausch"] * (2 if splitting else 1) + andere_zve)
    gesamt = steuern(est(max(zve, 0.0), p, splitting, 12 * steuerfrei_monat), p, splitting, kist)["summe"]
    # Splitting: dem Arbeitnehmer zugerechnet wird die Mehrsteuer gegenueber dem Partnereinkommen allein
    nur_partner = (steuern(est(max(andere_zve - p["sonderausgaben_pausch"] * 2, 0.0), p, True), p, True, kist)["summe"]
                   if splitting and andere_zve > 0 else 0.0)
    st = {"summe": max(gesamt - nur_partner, 0.0)}
    netto = brutto_monat + steuerfrei_monat - sv["summe"] - st["summe"] / 12.0
    return {"brutto": brutto_monat, "steuerfrei": steuerfrei_monat, "sv": sv["summe"], "sv_teile": sv,
            "steuer": st["summe"] / 12.0, "netto": netto}


def alg_schaetzung(brutto_monat_vollzeit, p, splitting=False, kind=False, lohnfaktor=1.0):
    """Arbeitslosengeld I (grob, § 149 ff. SGB III): Bemessungsentgelt bis BBG minus 20 % SV-Pauschale minus
    Lohnsteuer/Soli -> 60 % bzw. 67 %. Nach Altersteilzeit zaehlt das Vollzeit-Entgelt (§ 150 Abs. 2 Nr. 5)."""
    b = min(max(brutto_monat_vollzeit, 0.0), p["bbg_rv"] * lohnfaktor / 12.0)
    pausch = b * p["alg_sv_pauschale"] / 100.0
    zve = 12 * b - p["wk_arbeitnehmer"] - p["sonderausgaben_pausch"] * (2 if splitting else 1) - 12 * pausch * 0.9
    e = est(max(zve, 0.0), p, splitting)
    st = e + soli(e, p, splitting)
    leistungsentgelt = max(b - pausch - st / 12.0, 0.0)
    return leistungsentgelt * (p["alg_satz_kind"] if kind else p["alg_satz"]) / 100.0
