"""Abfindungsrechner (Deutschland, Steuerjahr 2026) - Szenariorechnung, keine Steuerberatung.

Eingabe ist die Abfindungssumme; gerechnet werden mehrere Varianten, wie viel Steuer
insgesamt anfaellt (Einkommensteuer, Soli, Kirchensteuer):
- Auszahlung dieses Jahr mit/ohne Fuenftelregelung (§ 34 EStG; seit 2025 nur ueber die
  Steuererklaerung - bei der Auszahlung wird zunaechst die volle Lohnsteuer einbehalten)
- Auszahlung im Folgejahr, Aufteilung auf zwei Jahre
- Einzahlung in die gesetzliche Rentenversicherung (Sonderausgaben, Hoechstbetrag 2026)
- Umwandlung in betriebliche Altersversorgung (§ 3 Nr. 63 Satz 3 EStG, Vervielfaeltigung)
- Werbungskosten (z. B. Anwalt), Arbeitslosengeld (Progressionsvorbehalt), Splitting
Ergebnis auch als PDF (eigener kleiner PDF-Schreiber, keine Zusatzpakete noetig).
"""
import datetime
import math

STEUERJAHR = 2026
# --- Tarif 2026 (§ 32a EStG) ---
GRUNDFREIBETRAG = 12348
ZONE2_ENDE = 17799
ZONE3_ENDE = 69878
ZONE4_ENDE = 277825
# --- Soli 2026 ---
SOLI_FREIGRENZE = 20350          # Einzelveranlagung (Splitting: doppelt)
SOLI_SATZ = 0.055
SOLI_MILDERUNG = 0.119
# --- Sozialversicherung / Vorsorge 2026 ---
BBG_RV = 101400.0                # Beitragsbemessungsgrenze Rentenversicherung (jaehrlich)
RV_SATZ = 0.186                  # Arbeitnehmer + Arbeitgeber
HOECHST_ALTERSVORSORGE = 30826.0 # § 10 Abs. 3 EStG, Ledige (Zusammenveranlagung: doppelt)
BAV_JE_JAHR = 0.04 * BBG_RV      # § 3 Nr. 63 S. 3 EStG: 4 % BBG je Dienstjahr ...
BAV_MAX_JAHRE = 10               # ... hoechstens 10 Jahre


# ===========================================================================
# Steuerrechnung
# ===========================================================================
def est_tarif(zve):
    """Einkommensteuer (Grundtarif 2026), volle Euro."""
    x = math.floor(max(zve, 0.0))
    if x <= GRUNDFREIBETRAG:
        return 0.0
    if x <= ZONE2_ENDE:
        y = (x - GRUNDFREIBETRAG) / 10000.0
        return float(math.floor((914.51 * y + 1400.0) * y))
    if x <= ZONE3_ENDE:
        z = (x - ZONE2_ENDE) / 10000.0
        return float(math.floor((173.10 * z + 2397.0) * z + 1034.87))
    if x <= ZONE4_ENDE:
        return float(math.floor(0.42 * x - 11135.63))
    return float(math.floor(0.45 * x - 19470.38))


def est(zve, splitting=False, pv=0.0):
    """Einkommensteuer inkl. Splitting und Progressionsvorbehalt (pv = steuerfreie
    Lohnersatzleistungen wie Arbeitslosengeld: erhoehen nur den Steuersatz)."""
    if zve <= 0:
        return 0.0

    def tarif(x):
        return 2.0 * est_tarif(math.floor(max(x, 0.0) / 2.0)) if splitting else est_tarif(x)
    if pv <= 0:
        return tarif(zve)
    satz = tarif(zve + pv) / (zve + pv)
    return float(math.floor(zve * satz))


def est_mit_abfindung(zve_rest, abfindung, fuenftel=True, splitting=False, pv=0.0):
    """Einkommensteuer des Jahres, Abfindung mit Fuenftelregelung (§ 34 Abs. 1) oder voll."""
    a = max(abfindung, 0.0)
    if not fuenftel or a <= 0:
        return est(zve_rest + a, splitting, pv)
    if zve_rest < 0:
        gesamt = zve_rest + a
        return 5.0 * est(gesamt / 5.0, splitting, pv) if gesamt > 0 else 0.0
    basis = est(zve_rest, splitting, pv)
    return basis + 5.0 * (est(zve_rest + a / 5.0, splitting, pv) - basis)


def soli(est_betrag, splitting=False):
    frei = SOLI_FREIGRENZE * (2 if splitting else 1)
    if est_betrag <= frei:
        return 0.0
    return round(min(SOLI_SATZ * est_betrag, SOLI_MILDERUNG * (est_betrag - frei)), 2)


def steuern(est_betrag, splitting=False, kirche=0.0):
    s = soli(est_betrag, splitting)
    k = round(est_betrag * kirche, 2)
    return {"est": est_betrag, "soli": s, "kirche": k, "summe": est_betrag + s + k}


def _minus(a, b):
    return {k: a[k] - b[k] for k in ("est", "soli", "kirche", "summe")}


def rv_spielraum(e):
    """Wie viel einer Einzahlung in die Rentenversicherung ist zusaetzlich abziehbar?"""
    hoechst = HOECHST_ALTERSVORSORGE * (2 if e["splitting"] else 1)
    bisher = e.get("rv_bisher")
    if bisher is None:
        bisher = min(max(e.get("jahresbrutto", 0.0), 0.0), BBG_RV) * RV_SATZ
    return max(hoechst - bisher, 0.0)


def bav_frei(e):
    """Steuerfreier Hoechstbetrag fuer eine Umwandlung in die bAV (§ 3 Nr. 63 S. 3 EStG)."""
    jahre = min(max(int(e.get("dienstjahre") or 0), 0), BAV_MAX_JAHRE)
    return BAV_JE_JAHR * jahre


def variante(e, titel, kurz, teile, rv=0.0, bav=0.0, hinweis="", abzug_extra=0.0, ermaessigung=0.0):
    """teile: [(jahr_key, betrag, fuenftel)] - 'j1' = Auszahlungsjahr, 'j2' = Folgejahr.
    rv/bav: Teil der Abfindung, der in Rente/bAV fliesst (wirkt im ersten Jahr der Variante).
    abzug_extra: weitere Abzuege (Verluste, Sonderausgaben) im ersten Jahr; ermaessigung: direkte
    Steuerermaessigung (§ 35a/§ 35c) im ersten Jahr."""
    sp, ki = e["splitting"], e["kirche"]
    erg = {"titel": titel, "kurz": kurz, "hinweis": hinweis, "jahre": {}}
    summe = {"est": 0.0, "soli": 0.0, "kirche": 0.0, "summe": 0.0}
    gesamt_jahr = 0.0
    bav_steuerfrei = min(bav, bav_frei(e)) if bav else 0.0
    rv_abzug = min(rv, rv_spielraum(e)) if rv else 0.0
    erstes = next((j for j in ("j1", "j2") if any(t[0] == j for t in teile)), "j1")
    for jk in ("j1", "j2"):
        betraege = [(b, f) for j, b, f in teile if j == jk]
        if not betraege:
            continue
        zve = e["zve1"] if jk == "j1" else e["zve2"]
        pv = e["alg1"] if jk == "j1" else e["alg2"]
        ohne = steuern(est(zve, sp, pv), sp, ki)
        abzug = e["werbungskosten"] if jk == erstes else 0.0
        if jk == erstes:
            abzug += rv_abzug + abzug_extra
        a_f = sum(b for b, f in betraege if f)
        a_n = sum(b for b, f in betraege if not f)
        if jk == erstes and bav_steuerfrei:        # steuerfreier bAV-Teil mindert die steuerpflichtige Abfindung
            if a_f:
                a_f = max(a_f - bav_steuerfrei, 0.0)
            else:
                a_n = max(a_n - bav_steuerfrei, 0.0)
        rest = zve + a_n - abzug
        est_wert = est_mit_abfindung(rest, a_f, True, sp, pv) if a_f else est(rest, sp, pv)
        if jk == erstes and ermaessigung:
            est_wert = max(est_wert - ermaessigung, 0.0)
        mit = steuern(est_wert, sp, ki)
        d = _minus(mit, ohne)
        erg["jahre"][jk] = {"ohne": ohne, "mit": mit, "abfindung": d}
        for k in summe:
            summe[k] += d[k]
        gesamt_jahr += mit["summe"]
    a = e["abfindung"]
    erg.update(steuer=summe, netto=a - summe["summe"] - rv - bav, angelegt=rv + bav,
               satz=summe["summe"] / a if a else 0.0, gesamt=gesamt_jahr, rv_abzug=rv_abzug,
               bav_frei=bav_steuerfrei)
    return erg


def varianten(e):
    """Alle sinnvollen Rechenwege fuer die Eingaben e."""
    a = e["abfindung"]
    f = e["fuenftel_moeglich"]
    v = [variante(e, "Auszahlung dieses Jahr – Lohnsteuerabzug ohne Fünftelregelung", "Dieses Jahr, voll",
                  [("j1", a, False)],
                  hinweis="So viel behält der Arbeitgeber bei der Auszahlung ungefähr ein (seit 2025 ohne "
                          "Fünftelregelung).")]
    if f:
        v.append(variante(e, "Auszahlung dieses Jahr – mit Fünftelregelung (Steuererklärung)", "Dieses Jahr, Fünftel",
                          [("j1", a, True)],
                          hinweis="Endgültige Steuer nach der Steuererklärung; die Differenz zum Lohnsteuerabzug "
                                  "kommt als Erstattung zurück."))
        v.append(variante(e, "Auszahlung im Folgejahr – mit Fünftelregelung", "Folgejahr, Fünftel",
                          [("j2", a, True)],
                          hinweis="Lohnt sich, wenn das Einkommen im Folgejahr niedriger ist (z. B. Auszahlung im "
                                  "Januar nach dem Ausscheiden)."))
    else:
        v.append(variante(e, "Auszahlung im Folgejahr – voll besteuert", "Folgejahr, voll", [("j2", a, False)]))
    v.append(variante(e, "Aufteilung 50/50 auf dieses und nächstes Jahr", "Zwei Jahre, je 50 %",
                      [("j1", a / 2, False), ("j2", a / 2, False)],
                      hinweis="Teilzahlungen verlieren in der Regel die Fünftelregelung (keine Zusammenballung) – "
                              "jede Hälfte wird normal besteuert."))
    if e.get("rv", 0) > 0:
        v.append(variante(e, f"Dieses Jahr + Einzahlung Rentenversicherung {_de(e['rv'])} €", "Mit Rentenversicherung",
                          [("j1", a, f)], rv=e["rv"],
                          hinweis=f"Abziehbar als Sonderausgabe bis zum Höchstbetrag – hier {_de(rv_spielraum(e))} € "
                                  "Spielraum nach den bisherigen Rentenbeiträgen. Erhöht die spätere Rente."))
    if e.get("bav", 0) > 0:
        v.append(variante(e, f"Dieses Jahr + Umwandlung in bAV {_de(e['bav'])} €", "Mit bAV",
                          [("j1", a, f)], bav=e["bav"],
                          hinweis=f"Steuerfrei bis 4 % der BBG je Dienstjahr (max. 10 J.) = hier bis "
                                  f"{_de(bav_frei(e))} €; die spätere Betriebsrente ist steuerpflichtig."))
    if e.get("rv", 0) > 0 or e.get("bav", 0) > 0:
        folge = (e["zve2"] + e["alg2"]) < (e["zve1"] + e["alg1"])
        v.append(variante(e, "Kombination: günstigeres Jahr + Rente + bAV", "Alle Hebel",
                          [("j2" if folge else "j1", a, f)], rv=e.get("rv", 0.0), bav=e.get("bav", 0.0),
                          hinweis=("Auszahlung im Folgejahr" if folge else "Auszahlung dieses Jahr")
                          + ", Rente/bAV im selben Jahr."))
    g = gestaltungen(e)
    aktiv = [x for x in g["massnahmen"] if not x["info"] and (x["abzug"] or x["ermaessigung"])]
    if aktiv:
        jk = g["jahr"]
        v.append(variante(e, "Mit Gestaltungen: " + ", ".join(x["kurz"] for x in aktiv)
                          + (" (Folgejahr)" if jk == "j2" else ""), "Mit Gestaltungen",
                          [(jk, a, f)], rv=e.get("rv", 0.0), bav=e.get("bav", 0.0),
                          abzug_extra=sum(x["abzug"] for x in aktiv),
                          ermaessigung=sum(x["ermaessigung"] for x in aktiv),
                          hinweis="Alle ausgewählten Gestaltungen zusammen (inkl. Rente/bAV, falls eingetragen). "
                                  f"Dafür eingesetztes Geld: {_de(sum(x['einsatz'] for x in aktiv))} €."))
        v[-1]["einsatz"] = sum(x["einsatz"] for x in aktiv)
    beste = min([x for x in v if not x.get("einsatz")] or v, key=lambda x: x["steuer"]["summe"])
    basis = v[0]["steuer"]["summe"]
    for x in v:
        x["beste"] = x is beste
        x["ersparnis"] = basis - x["steuer"]["summe"]
    return v


# ===========================================================================
# Gestaltungen (Steuer sparen durch eigene Massnahmen im Auszahlungsjahr)
# ===========================================================================
AFA_ARTEN = {"2": ("2 % linear (Baujahr 1925–2022)", 0.02), "3": ("3 % linear (fertig ab 2023)", 0.03),
             "2.5": ("2,5 % linear (Baujahr vor 1925)", 0.025),
             "5": ("5 % degressiv (Neubau, Baubeginn 10/2023–9/2029)", 0.05)}
IAB_HOECHST = 200000.0           # § 7g EStG: Investitionsabzugsbetrag hoechstens 200.000 €
SPENDE_ANTEIL = 0.20             # § 10b Abs. 1: bis 20 % des Gesamtbetrags der Einkuenfte
VERMOEGENSSTOCK = 1000000.0      # § 10b Abs. 1a: Stiftung (Vermoegensstock) bis 1 Mio. € (Ehepaare 2 Mio.)
HANDWERKER_MAX = 1200.0          # § 35a Abs. 3: 20 % der Lohnkosten, max. 1.200 € Steuerermaessigung
SANIERUNG_JAHR1 = (0.07, 14000.0)  # § 35c: 7 % (max. 14.000 €) im 1. und 2. Jahr, 6 % im 3. Jahr


def gestaltungen(e):
    """Massnahmen aus e["gest"] -> {"jahr": "j1"/"j2", "massnahmen": [...]}; je Massnahme
    abzug (mindert das Einkommen), ermaessigung (mindert die Steuer direkt), einsatz (eigenes Geld),
    gegenwert, hinweis; info=True = keine Wirkung auf die Abfindungssteuer (nur Erklaerung)."""
    gs = e.get("gest") or {}
    jahr = gs.get("jahr", "j1")
    gde = (e["zve1"] if jahr == "j1" else e["zve2"]) + e["abfindung"]
    out = []

    def m(kurz, titel, abzug=0.0, ermaessigung=0.0, einsatz=0.0, gegenwert="", hinweis="", info=False):
        out.append({"kurz": kurz, "titel": titel, "abzug": float(abzug), "ermaessigung": float(ermaessigung),
                    "einsatz": float(einsatz), "gegenwert": gegenwert, "hinweis": hinweis, "info": info})

    x = gs.get("immo") or {}
    if x.get("aktiv"):
        geb = float(x.get("kaufpreis", 0)) * float(x.get("gebaeude_anteil", 80)) / 100.0
        satz = AFA_ARTEN.get(str(x.get("afa", "2")), AFA_ARTEN["2"])[1]
        erh = float(x.get("erhaltung", 0))
        warn = ""
        if erh > 0.15 * geb / 1.19 and geb > 0:   # anschaffungsnahe Herstellungskosten (§ 6 Abs. 1 Nr. 1a)
            warn = (" Achtung: Renovierung über 15 % des Gebäudewerts (netto) in den ersten 3 Jahren gilt als "
                    "Anschaffungskosten – nur über die AfA absetzbar (hier so gerechnet).")
            geb += erh
            erh = 0.0
        afa = geb * satz * max(min(int(x.get("monate", 12)), 12), 0) / 12.0
        vv = float(x.get("miete", 0)) - afa - float(x.get("zinsen", 0)) - erh - float(x.get("sonstige", 0))
        m("Immobilie", "Vermietete Immobilie kaufen (Verlust aus Vermietung)", abzug=-vv,
          einsatz=float(x.get("zinsen", 0)) + float(x.get("erhaltung", 0)) + float(x.get("sonstige", 0))
          - float(x.get("miete", 0)),
          gegenwert=f"Immobilie {_de(float(x.get('kaufpreis', 0)))} €",
          hinweis=f"AfA {_de(afa)} € ({_de(satz * 100, 1)} % vom Gebäudeanteil), Zinsen, Erhaltung und Kosten minus "
                  f"Miete = Ergebnis Vermietung {_de(vv)} €. Nur vermietete Objekte; selbst genutzt bringt der Kauf "
                  "keine Steuerersparnis. Grundstücksanteil wird nicht abgeschrieben." + warn)

    x = gs.get("firma") or {}
    if x.get("aktiv"):
        iab = min(0.5 * float(x.get("invest", 0)), IAB_HOECHST)
        anlauf = float(x.get("anlauf", 0))
        m("Selbstständigkeit", "Einzelunternehmen / Selbstständigkeit gründen (Investitionsabzugsbetrag + Anlaufverlust)",
          abzug=iab + anlauf, einsatz=anlauf,
          gegenwert=f"Betrieb; Investition {_de(float(x.get('invest', 0)))} € innerhalb von 3 Jahren",
          hinweis=f"Investitionsabzugsbetrag {_de(iab)} € (50 % der geplanten Anschaffungen, § 7g) + Anlaufkosten "
                  f"{_de(anlauf)} €. Der Abzug verschiebt Steuer in spätere Jahre (bei der Anschaffung wird er "
                  "wieder hinzugerechnet, die Abschreibung sinkt) – lohnt sich, weil die Abfindung hoch besteuert "
                  "wird. "
                  "Echte Gewinnerzielungsabsicht nötig; wird nicht investiert, wird der Abzug "
                  "rückgängig gemacht (mit Zinsen). Verluste einer GmbH lassen sich NICHT mit der Abfindung "
                  "verrechnen – nur Einzelunternehmen/Personengesellschaft.")

    x = gs.get("spende") or {}
    if x.get("aktiv"):
        sp = min(float(x.get("spende", 0)), SPENDE_ANTEIL * max(gde, 0.0))
        vs = min(float(x.get("stiftung", 0)), VERMOEGENSSTOCK * (2 if e["splitting"] else 1))
        m("Spende/Stiftung", "Spende oder Zustiftung an eine gemeinnützige Stiftung", abzug=sp + vs,
          einsatz=float(x.get("spende", 0)) + float(x.get("stiftung", 0)), gegenwert="– (gemeinnützig, Geld ist weg)",
          hinweis=f"Spenden bis 20 % der Einkünfte ({_de(SPENDE_ANTEIL * max(gde, 0))} €) abziehbar, Zustiftung in "
                  "den Vermögensstock zusätzlich bis 1 Mio. € (Ehepaare 2 Mio.), verteilbar auf 10 Jahre. "
                  "Eine eigene Familienstiftung spart dagegen keine Einkommensteuer auf die Abfindung.")

    x = gs.get("ruerup") or {}
    if x.get("aktiv"):
        frei = max(rv_spielraum(e) - min(e.get("rv", 0.0), rv_spielraum(e)), 0.0)
        ab = min(float(x.get("betrag", 0)), frei)
        m("Rürup", "Einzahlung in eine Basisrente (Rürup)", abzug=ab, einsatz=float(x.get("betrag", 0)),
          gegenwert="lebenslange Rente (später steuerpflichtig)",
          hinweis=f"Teilt sich den Höchstbetrag mit der Rentenversicherung – noch {_de(frei)} € abziehbar. Nicht "
                  "kündbar, nicht vererbbar (nur Hinterbliebenenschutz).")

    x = gs.get("fortbildung") or {}
    if x.get("aktiv"):
        m("Fortbildung", "Fortbildung, Umschulung, Bewerbungskosten, Arbeitsmittel", abzug=float(x.get("betrag", 0)),
          einsatz=float(x.get("betrag", 0)), gegenwert="Qualifikation / Arbeitsmittel",
          hinweis="Als (vorweggenommene) Werbungskosten abziehbar, wenn sie dem künftigen Beruf dienen.")

    x = gs.get("handwerker") or {}
    if x.get("aktiv"):
        er = min(0.2 * float(x.get("lohn", 0)), HANDWERKER_MAX)
        m("Handwerker", "Handwerkerleistungen im eigenen Haushalt", ermaessigung=er,
          einsatz=float(x.get("lohn", 0)), gegenwert="Renovierung/Reparatur",
          hinweis="20 % der Arbeits- und Fahrtkosten (nicht Material), höchstens 1.200 € direkt von der Steuer.")

    x = gs.get("sanierung") or {}
    if x.get("aktiv"):
        k = float(x.get("kosten", 0))
        er = min(SANIERUNG_JAHR1[0] * k, SANIERUNG_JAHR1[1])
        m("Energetische Sanierung", "Energetische Sanierung des selbst genutzten Hauses (§ 35c)", ermaessigung=er,
          einsatz=k, gegenwert="Haus: Dämmung, Fenster, Heizung …",
          hinweis=f"Im 1. Jahr 7 % ({_de(er)} €), im 2. Jahr nochmals 7 %, im 3. Jahr 6 % – zusammen 20 %, max. "
                  "40.000 €. Gebäude älter als 10 Jahre, Fachbetrieb, nicht zusätzlich gefördert.")

    x = gs.get("solar") or {}
    if x.get("aktiv"):
        kwp, kosten = float(x.get("kwp", 0)), float(x.get("kosten", 0))
        if kwp > 30:
            iab = min(0.5 * kosten, IAB_HOECHST)
            m("Solar > 30 kWp", f"Solaranlage {_de(kwp)} kWp als Gewerbe (Investitionsabzugsbetrag)", abzug=iab,
              einsatz=0.0, gegenwert=f"Anlage {_de(kosten)} €, Einspeiseerlöse",
              hinweis=f"Über 30 kWp ist die Anlage ein Gewerbebetrieb: Investitionsabzugsbetrag {_de(iab)} € (50 % "
                      "der Kosten) schon vor dem Kauf absetzbar, danach Abschreibung. Die Steuer wird in spätere "
                      "Jahre verschoben (Erträge sind steuerpflichtig) – lohnt wegen des hohen Satzes im "
                      "Abfindungsjahr. Rentabilität der Anlage selbst vorher prüfen.")
        else:
            m("Solar ≤ 30 kWp", f"Solaranlage {_de(kwp)} kWp", info=True,
              hinweis="Bis 30 kWp einkommensteuerfrei (seit 2022) – keine Abschreibung, also keine Ersparnis bei "
                      "der Abfindungssteuer. Vorteil: 0 % Umsatzsteuer beim Kauf.")

    x = gs.get("kv") or {}
    if x.get("aktiv"):
        jb = float(x.get("jahresbeitrag", 0))
        vz = 2.5 * jb
        m("KV-Vorauszahlung", "Kranken-/Pflegeversicherung für 2,5 Jahre im Voraus zahlen", abzug=vz, einsatz=0.0,
          gegenwert=f"Beiträge der nächsten Jahre bezahlt ({_de(vz)} €)",
          hinweis=f"Basisbeiträge bis zum 2,5-fachen Jahresbeitrag vorauszahlen ({_de(vz)} €) und im Abfindungsjahr "
                  "absetzen (§ 10 Abs. 1 Nr. 3 S. 4 EStG). In den Folgejahren fällt der Abzug dann weg – die Steuer "
                  "verschiebt sich in Jahre mit niedrigerem Satz. Vor allem für privat oder freiwillig "
                  "Versicherte; die Kasse muss Vorauszahlungen annehmen.")

    # Ideen ohne Wirkung auf die Abfindungssteuer - ehrlich einordnen
    if e.get("kirche"):
        m("Kirchenaustritt", "Kirchenaustritt vor der Auszahlung", info=True,
          hinweis=f"Spart die Kirchensteuer auf die Abfindung (oben im Ergebnis als „KiSt“ ausgewiesen). "
                  "Wirksam ab dem Folgemonat des Austritts – für die Abfindung zählt der Zeitpunkt der Zahlung. "
                  "Persönliche Entscheidung, hier nur als Rechenhinweis.")
    m("Eigenheim", "Immobilie selbst bewohnen", info=True,
      hinweis="Kauf, Zinsen und Abschreibung einer selbst genutzten Immobilie sind nicht absetzbar (Ausnahmen: "
              "Handwerker § 35a, energetische Sanierung § 35c, häusliches Arbeitszimmer).")
    m("Investment-GmbH", "Vermögensverwaltende GmbH gründen", info=True,
      hinweis="Die Abfindung wird vorher privat versteuert – eine GmbH senkt nur die Steuer auf künftige Erträge "
              "(rund 15–30 % statt Abgeltungsteuer, je nach Anlage), nicht die Abfindungssteuer.")
    m("Private Anschaffungen", "Auto, Möbel, Elektronik usw. privat kaufen", info=True,
      hinweis="Privat genutzte Anschaffungen sind steuerlich nicht absetzbar.")
    return {"jahr": jahr, "massnahmen": out}


def gestaltung_wirkung(e):
    """Steuerersparnis je Massnahme einzeln (gegenueber Auszahlung im gewaehlten Jahr, ohne Massnahme)."""
    g = gestaltungen(e)
    jk, a, f = g["jahr"], e["abfindung"], e["fuenftel_moeglich"]
    ohne = variante(e, "", "", [(jk, a, f)])["steuer"]["summe"]
    for x in g["massnahmen"]:
        if x["info"]:
            x["ersparnis"] = 0.0
            continue
        mit = variante(e, "", "", [(jk, a, f)], abzug_extra=x["abzug"], ermaessigung=x["ermaessigung"])
        x["ersparnis"] = ohne - mit["steuer"]["summe"]
        x["quote"] = x["ersparnis"] / x["einsatz"] if x["einsatz"] > 0 else None
    return g


# ===========================================================================
# Fuenftelregel nach Auszahlungsjahr (Jahrestabelle)
# ===========================================================================
def fuenftel_jahre(e, jahre):
    """jahre: [{"jahr": 2026, "zve": ..., "alg": ...}] -> je Jahr Steuer auf die Abfindung mit/ohne
    Fuenftelregel, falls sie in DIESEM Jahr ausgezahlt wird (wirkt nur im Auszahlungsjahr)."""
    a, sp, ki = e["abfindung"], e["splitting"], e["kirche"]
    aus = []
    for j in jahre:
        zve, pv = float(j.get("zve") or 0.0), float(j.get("alg") or 0.0)
        ohne = steuern(est(zve, sp, pv), sp, ki)
        voll = _minus(steuern(est(zve + a, sp, pv), sp, ki), ohne)
        fuenf = _minus(steuern(est_mit_abfindung(zve, a, True, sp, pv), sp, ki), ohne)
        aus.append({"jahr": int(j["jahr"]), "zve": zve, "alg": pv, "voll": voll["summe"], "fuenftel": fuenf["summe"],
                    "ersparnis": voll["summe"] - fuenf["summe"], "netto": a - fuenf["summe"],
                    "satz": fuenf["summe"] / a if a else 0.0, "erstattung_jahr": int(j["jahr"]) + 1})
    return aus


def fuenftel_einkommen(e, stufen=(0, 10000, 20000, 30000, 40000, 50000, 60000, 80000, 100000)):
    """Steuer auf die Abfindung (mit Fuenftel) je nach uebrigem Einkommen im Auszahlungsjahr."""
    return fuenftel_jahre(e, [{"jahr": 0, "zve": z, "alg": 0.0} for z in stufen])


# ===========================================================================
# Langfrist-Vergleich: Netto-Abfindung privat anlegen oder in einer Investment-GmbH
# ===========================================================================
ABGELTUNG = 0.25 * 1.055          # Abgeltungsteuer + Soli (ohne Kirchensteuer)
KST = 0.15 * 1.055                # Koerperschaftsteuer + Soli
GEWST_MESSZAHL = 0.035
ANLAGEARTEN = {
    "aktien": "Einzelaktien (Kursgewinne + Dividenden)",
    "etf": "Aktien-ETF",
    "zins": "Anleihen / Tagesgeld (Zinsen)",
}


def gmbh_saetze(hebesatz):
    """Effektive Steuersaetze in der GmbH je Ertragsart."""
    gew = GEWST_MESSZAHL * hebesatz / 100.0
    return {
        "aktien_kurs": 0.05 * (KST + gew),        # § 8b Abs. 2/3 KStG: 95 % steuerfrei
        "aktien_div": KST + gew,                  # Streubesitz < 10 %: voll steuerpflichtig
        "etf": 0.20 * KST + 0.60 * gew,           # Teilfreistellung 80 % KSt / 40 % GewSt
        "zins": KST + gew,
        "voll": KST + gew,
    }


def privat_saetze(kirche=0.0):
    abg = 0.25 * (1.055 + kirche) / (1 + 0.25 * kirche) if kirche else ABGELTUNG
    return {"aktien_kurs": abg, "aktien_div": abg, "etf": 0.70 * abg, "zins": abg, "voll": abg}


def anlage_vergleich(betrag, jahre, rendite, art="etf", ausschuettung=0.02, hebesatz=400.0,
                     kosten_gruendung=1500.0, kosten_jahr=3000.0, freibetrag=1000.0, kirche=0.0):
    """Jahr fuer Jahr: Vermoegen privat (nach Steuer bei Verkauf) gegen GmbH (in der GmbH nach Verkauf
    und nach Entnahme an dich). Ausschuettungen/Zinsen werden jaehrlich versteuert und wieder angelegt,
    Kursgewinne erst beim Verkauf. Vereinfachung: konstante Rendite, keine Vorabpauschale."""
    pr, gm = privat_saetze(kirche), gmbh_saetze(hebesatz)
    if art == "zins":
        d = rendite
    else:
        d = min(max(ausschuettung, 0.0), rendite)
    g = rendite - d
    s_div_p = pr["etf"] if art == "etf" else (pr["zins"] if art == "zins" else pr["aktien_div"])
    s_kurs_p = pr["etf"] if art == "etf" else pr["aktien_kurs"]
    s_div_g = gm["etf"] if art == "etf" else (gm["zins"] if art == "zins" else gm["aktien_div"])
    s_kurs_g = gm["etf"] if art == "etf" else gm["aktien_kurs"]
    vp, bp = float(betrag), float(betrag)                  # privat: Wert, Einstand
    vg = float(betrag) - kosten_gruendung                  # GmbH: Wert, Einstand
    bg = vg
    einlage = float(betrag)
    zeilen = []
    for j in range(1, int(jahre) + 1):
        # privat
        div = vp * d
        st_p = max(div - freibetrag, 0.0) * s_div_p
        vp = vp * (1 + g) + div - st_p
        bp += div - st_p
        # GmbH: laufende Kosten mindern den steuerpflichtigen Ertrag
        div_g = vg * d
        st_g = max(div_g - kosten_jahr, 0.0) * s_div_g
        vg = vg * (1 + g) + div_g - st_g - kosten_jahr
        bg += div_g - st_g - kosten_jahr
        privat_netto = vp - max(vp - bp - freibetrag, 0.0) * s_kurs_p
        gmbh_drin = vg - max(vg - bg, 0.0) * s_kurs_g
        gmbh_privat = gmbh_drin - max(gmbh_drin - einlage, 0.0) * pr["voll"]
        zeilen.append({"jahr": j, "privat": privat_netto, "gmbh": gmbh_drin, "gmbh_privat": gmbh_privat})
    return {"zeilen": zeilen, "saetze_privat": pr, "saetze_gmbh": gm,
            "s": {"div_p": s_div_p, "kurs_p": s_kurs_p, "div_g": s_div_g, "kurs_g": s_kurs_g}}


# ===========================================================================
# Formatierung
# ===========================================================================
def _de(x, nk=0):
    if abs(x) < 0.5 * 10 ** -nk:
        x = 0.0
    return f"{x:,.{nk}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x):
    return _de(x * 100, 1) + " %"


# ===========================================================================
# Kleiner PDF-Schreiber (Helvetica, WinAnsi) - keine Zusatzpakete noetig
# ===========================================================================
_W = {" ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191, "(": 333, ")": 333,
      "*": 389, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584,
      ">": 584, "?": 556, "@": 1015, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
      "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778,
      "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611, "[": 278,
      "\\": 278, "]": 278, "_": 556, "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
      "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556, "o": 556, "p": 556, "q": 556,
      "r": 333, "s": 500, "t": 278, "u": 556, "v": 500, "w": 722, "x": 500, "y": 500, "z": 500, "ä": 556,
      "ö": 556, "ü": 556, "Ä": 667, "Ö": 778, "Ü": 722, "ß": 611, "€": 556, "–": 556, "·": 278, "§": 556,
      "×": 584, "„": 333, "“": 333, "”": 333}
_ERSATZ = {"→": "->", "≈": "ca.", "−": "-", "✓": "", "⚠": "!", "•": "-", " ": " ", "…": "..."}


def _sauber(t):
    t = str(t)
    for a, b in _ERSATZ.items():
        t = t.replace(a, b)
    return t.encode("cp1252", "replace").decode("cp1252")


def _breite(t, groesse, fett=False):
    return sum(_W.get(c, 556) for c in _sauber(t)) * groesse / 1000.0 * (1.05 if fett else 1.0)


def _kuerzen(t, groesse, fett, max_b):
    t = _sauber(t)
    if _breite(t, groesse, fett) <= max_b:
        return t
    while t and _breite(t + "...", groesse, fett) > max_b:
        t = t[:-1]
    return t.rstrip() + "..."


class _PDF:
    B, H = 595.28, 841.89          # A4 in Punkt
    RAND = 42

    def __init__(self):
        self.seiten = []
        self.neue_seite()

    def neue_seite(self):
        self.ops = []
        self.seiten.append(self.ops)
        self.y = self.H - self.RAND

    def platz(self, hoehe):
        if self.y - hoehe < self.RAND + 20:
            self.neue_seite()

    def text(self, x, y, t, groesse=10, fett=False, farbe=(0, 0, 0), rechts=False):
        t = _sauber(t)
        if rechts:
            x -= _breite(t, groesse, fett)
        esc = t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        self.ops.append(f"{farbe[0]:.3f} {farbe[1]:.3f} {farbe[2]:.3f} rg BT /{'F2' if fett else 'F1'} {groesse} Tf "
                        f"{x:.2f} {y:.2f} Td ({esc}) Tj ET")

    def rechteck(self, x, y, b, h, farbe):
        self.ops.append(f"{farbe[0]:.3f} {farbe[1]:.3f} {farbe[2]:.3f} rg {x:.2f} {y:.2f} {b:.2f} {h:.2f} re f")

    def linie(self, x1, y1, x2, y2, farbe=(0.82, 0.82, 0.82), dicke=0.5):
        self.ops.append(f"{farbe[0]:.3f} {farbe[1]:.3f} {farbe[2]:.3f} RG {dicke} w {x1:.2f} {y1:.2f} m "
                        f"{x2:.2f} {y2:.2f} l S")

    def ueberschrift(self, t):
        self.platz(40)
        self.y -= 18
        self.text(self.RAND, self.y, t, 12, True, (0.08, 0.1, 0.16))
        self.y -= 4

    def absatz(self, t, groesse=9, fett=False, farbe=(0.25, 0.25, 0.25), einzug=0, abstand=1.35):
        breite = self.B - 2 * self.RAND - einzug
        zeilen, zeile = [], ""
        for w in _sauber(t).split(" "):
            probe = (zeile + " " + w).strip()
            if _breite(probe, groesse, fett) > breite and zeile:
                zeilen.append(zeile)
                zeile = w
            else:
                zeile = probe
        if zeile:
            zeilen.append(zeile)
        for z in zeilen:
            self.platz(groesse * abstand)
            self.y -= groesse * abstand
            self.text(self.RAND + einzug, self.y, z, groesse, fett, farbe)

    def tabelle(self, spalten, zeilen, breiten, groesse=8.5, hervor=()):
        """Erste Spalte links, uebrige rechtsbuendig; hervor = Zeilennummern mit gruener Markierung."""
        gesamt = self.B - 2 * self.RAND
        bs = [gesamt * b / sum(breiten) for b in breiten]
        zh = groesse * 2.1

        def zeichnen(werte, kopf=False, markiert=False):
            self.platz(zh)
            self.y -= zh
            if kopf:
                self.rechteck(self.RAND, self.y, gesamt, zh, (0.13, 0.16, 0.22))
            elif markiert:
                self.rechteck(self.RAND, self.y, gesamt, zh, (0.86, 0.96, 0.89))
            x = self.RAND
            fett = kopf or markiert
            farbe = (1, 1, 1) if kopf else (0.1, 0.1, 0.1)
            for i, (w, b) in enumerate(zip(werte, bs)):
                w = _kuerzen(w, groesse, fett, b - 8)
                if i == 0:
                    self.text(x + 4, self.y + zh * 0.32, w, groesse, fett, farbe)
                else:
                    self.text(x + b - 4, self.y + zh * 0.32, w, groesse, fett, farbe, rechts=True)
                x += b
            if not kopf:
                self.linie(self.RAND, self.y, self.RAND + gesamt, self.y)
        zeichnen(spalten, kopf=True)
        for i, z in enumerate(zeilen):
            zeichnen(z, markiert=i in hervor)

    def bytes(self):
        objs = []

        def obj(inhalt):
            objs.append(inhalt)
            return len(objs)
        f1 = obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        n = len(self.seiten)
        pages_id = 2 + 2 * n + 1
        seiten_ids = []
        for nr, ops in enumerate(self.seiten, 1):
            fuss = (f"0.5 0.5 0.5 rg BT /F1 7.5 Tf {self.RAND} 22 Td (Abfindungsrechner {STEUERJAHR} - "
                    f"Szenariorechnung, keine Steuerberatung - Seite {nr}/{n}) Tj ET")
            strom = "\n".join(ops + [fuss]).encode("cp1252", "replace")
            sid = obj(b"<< /Length %d >>\nstream\n" % len(strom) + strom + b"\nendstream")
            seiten_ids.append(obj(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {self.B} {self.H}] "
                                  f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {sid} 0 R >>"))
        assert obj(f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in seiten_ids)}] /Count {n} >>") == pages_id
        katalog = obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
        aus = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        pos = []
        for i, o in enumerate(objs, 1):
            pos.append(len(aus))
            inhalt = o if isinstance(o, bytes) else o.encode("cp1252", "replace")
            aus += f"{i} 0 obj\n".encode() + inhalt + b"\nendobj\n"
        xref = len(aus)
        aus += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for p in pos:
            aus += f"{p:010d} 00000 n \n".encode()
        aus += f"trailer\n<< /Size {len(objs) + 1} /Root {katalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(aus)


HINWEISE = [
    "Abfindungen sind sozialversicherungsfrei; Einkommensteuer, Soli und ggf. Kirchensteuer fallen an.",
    "Fünftelregelung nur bei Zusammenballung: Zahlung in einem Jahr und insgesamt mehr Einkünfte als ohne "
    "Kündigung. Seit 2025 nur über die Steuererklärung – bei Auszahlung wird zunächst voll Lohnsteuer einbehalten.",
    "Arbeitslosengeld ist steuerfrei, erhöht aber über den Progressionsvorbehalt den Steuersatz.",
    "Einzahlungen in die Rentenversicherung (z. B. Ausgleich von Rentenabschlägen) sind bis zum Höchstbetrag "
    f"({_de(HOECHST_ALTERSVORSORGE)} €, Ehepaare doppelt; abzüglich bereits gezahlter Beiträge) abziehbar.",
    f"bAV: steuerfrei bis 4 % der Beitragsbemessungsgrenze ({_de(BAV_JE_JAHR)} €) je Dienstjahr, höchstens "
    "10 Jahre; Beiträge des Jahres und der 6 Vorjahre werden angerechnet (hier nicht berücksichtigt).",
    "Sperrzeit/Ruhen beim Arbeitslosengeld (Aufhebungsvertrag, verkürzte Kündigungsfrist) ist nicht eingerechnet.",
    "Vereinfachte Rechnung ohne Kinderfreibeträge und Lohnsteuer-Details – für eine verbindliche Auskunft "
    "Steuerberater oder Lohnsteuerhilfeverein fragen.",
]


def pdf_bericht(e, v, erstellt=None, fj=None, fe=None, av=None, avp=None):
    """Ergebnis als PDF (bytes). fj/fe: Fuenftel-Tabellen, av/avp: Langfrist-Vergleich + Parameter."""
    erstellt = erstellt or datetime.datetime.now()
    p = _PDF()
    p.y -= 8
    p.text(p.RAND, p.y, "Abfindung – Steuerberechnung", 20, True, (0.08, 0.1, 0.16))
    p.y -= 16
    p.text(p.RAND, p.y, f"Steuerjahr {STEUERJAHR} · erstellt am {erstellt.strftime('%d.%m.%Y %H:%M')}", 9,
           farbe=(0.4, 0.4, 0.4))
    p.y -= 12

    beste = next(x for x in v if x["beste"])
    basis = v[0]
    p.rechteck(p.RAND, p.y - 64, p.B - 2 * p.RAND, 64, (0.93, 0.96, 1.0))
    p.text(p.RAND + 10, p.y - 19, f"Abfindung brutto: {_de(e['abfindung'])} €", 13, True)
    p.text(p.RAND + 10, p.y - 36, _kuerzen(f"Günstigste Variante: {beste['titel']}", 9.5, True,
                                           p.B - 2 * p.RAND - 20), 9.5, True, (0.05, 0.45, 0.2))
    p.text(p.RAND + 10, p.y - 52,
           _kuerzen(f"Steuern {_de(beste['steuer']['summe'])} € ({_pct(beste['satz'])}) · Netto {_de(beste['netto'])} €"
                    + (f" + {_de(beste['angelegt'])} € Rente/bAV" if beste["angelegt"] else "")
                    + f" · Ersparnis ggü. Lohnsteuerabzug {_de(basis['steuer']['summe'] - beste['steuer']['summe'])} €",
                    9, False, p.B - 2 * p.RAND - 20), 9, farbe=(0.15, 0.15, 0.15))
    p.y -= 70

    p.ueberschrift("Varianten im Vergleich")
    zeilen = [[x["kurz"], f"{_de(x['steuer']['est'])} €", f"{_de(x['steuer']['soli'])} €",
               f"{_de(x['steuer']['kirche'])} €", f"{_de(x['steuer']['summe'])} €", _pct(x["satz"]),
               f"{_de(x['netto'])} €", f"{_de(x['ersparnis'])} €"] for x in v]
    p.tabelle(["Variante", "ESt", "Soli", "KiSt", "Steuern", "Satz", "Netto", "Ersparnis"], zeilen,
              [2.5, 1, 0.8, 0.8, 1, 0.75, 1.05, 1], groesse=8, hervor={i for i, x in enumerate(v) if x["beste"]})
    p.absatz("Steuern = Mehrsteuer durch die Abfindung (Jahressteuer mit minus ohne Abfindung). Netto = Abfindung "
             "minus Steuern minus Einzahlungen in Rente/bAV. Ersparnis = gegenüber dem Lohnsteuerabzug bei "
             "Auszahlung ohne Fünftelregelung.", 7.5)

    g = gestaltung_wirkung(e)
    wirk = [x for x in g["massnahmen"] if not x["info"]]
    if wirk:
        p.ueberschrift("Gestaltungen – was bringt was?")
        p.tabelle(["Maßnahme", "Abzug", "Ermäßigung", "Steuer gespart", "Einsatz", "je 1 €"],
                  [[x["kurz"], f"{_de(x['abzug'])} €", f"{_de(x['ermaessigung'])} €", f"{_de(x['ersparnis'])} €",
                    f"{_de(x['einsatz'])} €", _de(x["quote"], 2) if x.get("quote") is not None else "-"]
                   for x in wirk], [2.2, 1, 1, 1.1, 1, 0.7], groesse=8)
        p.absatz("Jede Maßnahme einzeln gerechnet, Auszahlung im " + ("Folgejahr" if g["jahr"] == "j2" else
                 "laufenden Jahr") + ". Abzug = mindert das Einkommen, Ermäßigung = direkt von der Steuer. "
                 "Steuer sparen heißt Geld ausgeben – lohnend nur, wenn die Maßnahme ohnehin gewollt ist.", 7.5)
        for x in wirk:
            p.y -= 3
            p.absatz(x["titel"], 8.5, True, (0.1, 0.1, 0.1))
            p.absatz(x["hinweis"], 8, einzug=8)
    p.ueberschrift("Ideen ohne Ersparnis bei der Abfindungssteuer")
    for x in g["massnahmen"]:
        if x["info"]:
            p.absatz(f"- {x['titel']}: {x['hinweis']}", 8)

    if fj:
        p.ueberschrift("Fünftelregel – je nach Auszahlungsjahr")
        p.tabelle(["Auszahlung", "Übriges Eink.", "ALG", "ohne Fünftel", "mit Fünftel", "Ersparnis", "Netto",
                   "Erstattung"],
                  [[str(x["jahr"]), f"{_de(x['zve'])} €", f"{_de(x['alg'])} €", f"{_de(x['voll'])} €",
                    f"{_de(x['fuenftel'])} €", f"{_de(x['ersparnis'])} €", f"{_de(x['netto'])} €",
                    str(x["erstattung_jahr"])] for x in fj],
                  [0.9, 1.1, 0.9, 1.05, 1.05, 1, 1, 0.85], groesse=8,
                  hervor={min(range(len(fj)), key=lambda i: fj[i]["fuenftel"])})
        p.absatz("Die Fünftelregel wirkt nur im Jahr der Auszahlung – Folgejahre werden normal versteuert. Seit 2025 "
                 "behält der Arbeitgeber zunächst die Steuer „ohne Fünftel“ ein; die Differenz wird mit der "
                 "Steuererklärung im Folgejahr erstattet (Spalte Erstattung).", 7.5)
    if fe:
        p.ueberschrift("Steuer auf die Abfindung nach übrigem Einkommen im Auszahlungsjahr")
        p.tabelle(["Übriges Einkommen", "ohne Fünftel", "mit Fünftel", "Ersparnis", "Satz", "Netto"],
                  [[f"{_de(x['zve'])} €", f"{_de(x['voll'])} €", f"{_de(x['fuenftel'])} €",
                    f"{_de(x['ersparnis'])} €", _pct(x["satz"]), f"{_de(x['netto'])} €"] for x in fe],
                  [1.3, 1, 1, 1, 0.8, 1], groesse=8)
    if av and avp:
        p.ueberschrift("Langfrist-Vergleich: privat anlegen oder Investment-GmbH")
        p.absatz(f"Anlage {_de(avp['betrag'])} € · {ANLAGEARTEN[avp['art']]} · Rendite {_de(avp['rendite'] * 100, 1)} % p.a., "
                 f"davon {_de(avp['ausschuettung'] * 100, 1)} % Ausschüttung/Zinsen · Hebesatz {_de(avp['hebesatz'])} % · "
                 f"GmbH-Kosten {_de(avp['kosten_gruendung'])} € einmalig + {_de(avp['kosten_jahr'])} € pro Jahr. "
                 f"Steuersätze: privat {_pct(av['s']['div_p'])} auf Ausschüttungen / {_pct(av['s']['kurs_p'])} auf "
                 f"Kursgewinne, GmbH {_pct(av['s']['div_g'])} / {_pct(av['s']['kurs_g'])}, Entnahme aus der GmbH "
                 f"{_pct(av['saetze_privat']['voll'])}.", 8)
        zz = [z for z in av["zeilen"] if z["jahr"] % 5 == 0 or z["jahr"] in (1, len(av["zeilen"]))]
        p.tabelle(["Jahr", "Privat (nach Verkauf)", "GmbH (in der GmbH)", "GmbH (an dich entnommen)"],
                  [[str(z["jahr"]), f"{_de(z['privat'])} €", f"{_de(z['gmbh'])} €", f"{_de(z['gmbh_privat'])} €"]
                   for z in zz], [0.6, 1.3, 1.3, 1.5], groesse=8)
        p.absatz("Alle Werte nach Steuern bei Verkauf am Jahresende. „In der GmbH“ = Vermögen bleibt in der Firma "
                 "(z. B. zum Weiterinvestieren); „an dich entnommen“ = zusätzlich Abgeltungsteuer auf den Gewinn bei "
                 "Ausschüttung. Vereinfacht: konstante Rendite, ohne Vorabpauschale, ohne Teileinkünfteverfahren.", 7.5)

    p.ueberschrift("Eingaben")
    ein = [["Abfindung brutto", f"{_de(e['abfindung'])} €"],
           ["Zu versteuerndes Einkommen dieses Jahr (ohne Abfindung)", f"{_de(e['zve1'])} €"],
           ["Zu versteuerndes Einkommen Folgejahr (ohne Abfindung)", f"{_de(e['zve2'])} €"],
           ["Arbeitslosengeld dieses Jahr / Folgejahr", f"{_de(e['alg1'])} € / {_de(e['alg2'])} €"],
           ["Veranlagung", "Zusammen (Splitting)" if e["splitting"] else "Einzeln"],
           ["Kirchensteuer", f"{_de(e['kirche'] * 100)} %" if e["kirche"] else "keine"],
           ["Fünftelregelung anwendbar", "ja" if e["fuenftel_moeglich"] else "nein"],
           ["Werbungskosten (z. B. Anwalt)", f"{_de(e['werbungskosten'])} €"],
           ["Einzahlung Rentenversicherung (abziehbar)",
            f"{_de(e.get('rv', 0))} € ({_de(min(e.get('rv', 0), rv_spielraum(e)))} €)"],
           ["Umwandlung in bAV (steuerfrei bis)", f"{_de(e.get('bav', 0))} € ({_de(bav_frei(e))} €)"]]
    p.tabelle(["Angabe", "Wert"], ein, [3, 1.4])

    p.ueberschrift("Erläuterung der Varianten")
    for x in v:
        p.y -= 4
        p.absatz(x["titel"] + (" – günstigste" if x["beste"] else ""), 9, True, (0.1, 0.1, 0.1))
        jahre_txt = []
        for jk, lab in (("j1", "Dieses Jahr"), ("j2", "Folgejahr")):
            if jk in x["jahre"]:
                j = x["jahre"][jk]
                jahre_txt.append(f"{lab}: Steuer gesamt {_de(j['mit']['summe'])} € (ohne Abfindung "
                                 f"{_de(j['ohne']['summe'])} €)")
        p.absatz(" · ".join(jahre_txt) + (f". {x['hinweis']}" if x["hinweis"] else ""), 8.5, einzug=8)

    p.ueberschrift("Hinweise")
    for t in HINWEISE:
        p.absatz("- " + t, 8.5)
    return p.bytes()


# ===========================================================================
# Oberflaeche (Streamlit)
# ===========================================================================
def _gestaltungen_eingabe(st):
    """Eingaben fuer die Gestaltungen -> dict fuer e["gest"]."""
    g = {}
    with st.expander("💡 Steuern sparen durch Gestaltungen (Immobilie, Firma, Stiftung …)", expanded=False):
        g["jahr"] = "j2" if st.selectbox("Maßnahmen im Jahr der Auszahlung", ["Dieses Jahr", "Folgejahr"],
                                         key="abf_g_jahr") == "Folgejahr" else "j1"

        def schalter(key, label, hilfe=None):
            return st.toggle(label, key=f"abf_g_{key}", help=hilfe)

        if schalter("immo", "🏠 Vermietete Immobilie kaufen"):
            c1, c2 = st.columns(2)
            immo = {"aktiv": True,
                    "kaufpreis": c1.number_input("Kaufpreis (€)", 0.0, 1e8, 300000.0, step=10000.0, format="%.0f",
                                                 key="abf_g_kp"),
                    "gebaeude_anteil": c2.number_input("Gebäudeanteil (%)", 0.0, 100.0, 80.0, step=5.0,
                                                       key="abf_g_ga", help="Grund und Boden wird nicht abgeschrieben")}
            c3, c4 = st.columns(2)
            arten = list(AFA_ARTEN)
            immo["afa"] = c3.selectbox("Abschreibung", arten, format_func=lambda k: AFA_ARTEN[k][0], key="abf_g_afa")
            immo["monate"] = c4.number_input("Monate vermietet/besessen im Jahr", 0, 12, 6, key="abf_g_mon")
            c5, c6 = st.columns(2)
            immo["zinsen"] = c5.number_input("Kreditzinsen im Jahr (€)", 0.0, 1e7, 4000.0, step=500.0, format="%.0f",
                                             key="abf_g_zins")
            immo["erhaltung"] = c6.number_input("Renovierung / Erhaltung (€)", 0.0, 1e7, 0.0, step=1000.0,
                                                format="%.0f", key="abf_g_erh")
            c7, c8 = st.columns(2)
            immo["miete"] = c7.number_input("Mieteinnahmen im Jahr (€)", 0.0, 1e7, 5000.0, step=500.0, format="%.0f",
                                            key="abf_g_miete")
            immo["sonstige"] = c8.number_input("Sonstige Kosten (Verwaltung, Grundsteuer …, €)", 0.0, 1e7, 1000.0,
                                               step=250.0, format="%.0f", key="abf_g_sonst")
            g["immo"] = immo
        if schalter("firma", "🏢 Selbstständig machen / Einzelunternehmen gründen",
                    "Investitionsabzugsbetrag: 50 % geplanter Anschaffungen schon vorab absetzen"):
            c1, c2 = st.columns(2)
            g["firma"] = {"aktiv": True,
                          "invest": c1.number_input("Geplante Investitionen in 3 Jahren (€)", 0.0, 1e7, 40000.0,
                                                    step=1000.0, format="%.0f", key="abf_g_inv",
                                                    help="Maschinen, Fahrzeug (betrieblich > 90 %), Technik …"),
                          "anlauf": c2.number_input("Anlaufkosten / Verlust im 1. Jahr (€)", 0.0, 1e7, 5000.0,
                                                    step=500.0, format="%.0f", key="abf_g_anl")}
        if schalter("solar", "☀️ Solaranlage kaufen"):
            c1, c2 = st.columns(2)
            g["solar"] = {"aktiv": True,
                          "kwp": c1.number_input("Leistung (kWp)", 0.0, 10000.0, 50.0, step=5.0, key="abf_g_kwp",
                                                 help="Bis 30 kWp steuerfrei (keine Ersparnis), darüber Gewerbe"),
                          "kosten": c2.number_input("Kosten netto (€)", 0.0, 1e8, 50000.0, step=5000.0, format="%.0f",
                                                    key="abf_g_pvk")}
        if schalter("kv", "🏥 Kranken-/Pflegeversicherung vorauszahlen",
                    "Für privat oder freiwillig gesetzlich Versicherte"):
            g["kv"] = {"aktiv": True, "jahresbeitrag": st.number_input(
                "Jahresbeitrag Basis-Kranken- und Pflegeversicherung (€)", 0.0, 1e6, 6000.0, step=500.0,
                format="%.0f", key="abf_g_kvbeitrag")}
        if schalter("spende", "🎗️ Spende / Zustiftung an gemeinnützige Stiftung"):
            c1, c2 = st.columns(2)
            g["spende"] = {"aktiv": True,
                           "spende": c1.number_input("Spenden (€)", 0.0, 1e8, 1000.0, step=500.0, format="%.0f",
                                                     key="abf_g_sp"),
                           "stiftung": c2.number_input("Zustiftung Vermögensstock (€)", 0.0, 1e8, 0.0, step=1000.0,
                                                       format="%.0f", key="abf_g_vs")}
        if schalter("ruerup", "🧓 Basisrente (Rürup) einzahlen"):
            g["ruerup"] = {"aktiv": True, "betrag": st.number_input("Einzahlung Rürup (€)", 0.0, 1e7, 10000.0,
                                                                    step=1000.0, format="%.0f", key="abf_g_rr")}
        if schalter("fortbildung", "🎓 Fortbildung, Umschulung, Arbeitsmittel"):
            g["fortbildung"] = {"aktiv": True, "betrag": st.number_input("Kosten (€)", 0.0, 1e7, 3000.0, step=500.0,
                                                                         format="%.0f", key="abf_g_fb")}
        if schalter("handwerker", "🔧 Handwerker im eigenen Haushalt"):
            g["handwerker"] = {"aktiv": True, "lohn": st.number_input("Arbeitskosten laut Rechnung (€)", 0.0, 1e6,
                                                                      3000.0, step=500.0, format="%.0f",
                                                                      key="abf_g_hw")}
        if schalter("sanierung", "🌿 Energetische Sanierung (selbst genutztes Haus)"):
            g["sanierung"] = {"aktiv": True, "kosten": st.number_input("Sanierungskosten (€)", 0.0, 1e7, 30000.0,
                                                                       step=1000.0, format="%.0f", key="abf_g_san")}
    return g


def render():
    import streamlit as st
    import pandas as pd

    st.caption(f"Szenariorechnung für {STEUERJAHR} · keine Steuer- oder Rechtsberatung")
    abf = st.number_input("💶 Abfindungssumme brutto (€)", 0.0, 1e8, 50000.0, step=1000.0, format="%.0f",
                          key="abf_summe")

    with st.expander("📋 Einkommen & Steuer", expanded=True):
        c1, c2 = st.columns(2)
        brutto = float(c1.number_input("Jahresbrutto dieses Jahr ohne Abfindung (€)", 0.0, 1e8, 60000.0,
                                       step=1000.0, format="%.0f", key="abf_brutto",
                                       help="Grundlage für die Schätzung des zu versteuernden Einkommens und der "
                                            "bereits gezahlten Rentenbeiträge."))
        zve_auto = c2.toggle("Zu versteuerndes Einkommen schätzen (ca. 80 % vom Brutto)", value=True,
                             key="abf_zve_auto")
        zve1 = round(brutto * 0.8, -2) if zve_auto else float(c2.number_input(
            "Zu versteuerndes Einkommen dieses Jahr (€)", -1e6, 1e8, round(brutto * 0.8, -2), step=1000.0,
            format="%.0f", key="abf_zve1"))
        c3, c4 = st.columns(2)
        zve2 = float(c3.number_input("Zu versteuerndes Einkommen Folgejahr (€)", -1e6, 1e8, 0.0, step=1000.0,
                                     format="%.0f", key="abf_zve2",
                                     help="Ohne Abfindung – z. B. 0 bei Arbeitslosigkeit, sonst neues Gehalt × "
                                          "ca. 80 %."))
        veranl = c4.selectbox("Veranlagung", ["Einzeln", "Zusammen (Splitting)"], key="abf_veranl",
                              help="Bei Zusammenveranlagung das Einkommen beider Partner eintragen.")
        c5, c6 = st.columns(2)
        kirche = {"keine": 0.0, "8 % (BY, BW)": 0.08, "9 % (übrige Länder)": 0.09}[
            c5.selectbox("Kirchensteuer", ["keine", "8 % (BY, BW)", "9 % (übrige Länder)"], key="abf_kirche")]
        fuenftel = c6.toggle("Fünftelregelung anwendbar", value=True, key="abf_fuenftel",
                             help="Zahlung in einem Jahr und zusammen mit dem übrigen Einkommen mehr, als ohne "
                                  "Kündigung verdient worden wäre (Zusammenballung).")

    with st.expander("🛠️ Weitere Möglichkeiten (Steuer senken)", expanded=False):
        c7, c8 = st.columns(2)
        alg1 = float(c7.number_input("Arbeitslosengeld dieses Jahr (€)", 0.0, 1e6, 0.0, step=500.0, format="%.0f",
                                     key="abf_alg1", help="Steuerfrei, erhöht aber den Steuersatz "
                                                          "(Progressionsvorbehalt)"))
        alg2 = float(c8.number_input("Arbeitslosengeld Folgejahr (€)", 0.0, 1e6, 0.0, step=500.0, format="%.0f",
                                     key="abf_alg2"))
        c9, c10 = st.columns(2)
        wk = float(c9.number_input("Werbungskosten, z. B. Anwalt (€)", 0.0, 1e6, 0.0, step=100.0, format="%.0f",
                                   key="abf_wk", help="Zusätzlich zur Werbungskostenpauschale"))
        rv = float(c10.number_input("Einzahlung Rentenversicherung (€)", 0.0, 1e6, 0.0, step=1000.0, format="%.0f",
                                    key="abf_rv",
                                    help="Z. B. Ausgleich von Rentenabschlägen aus der Abfindung – als Sonderausgabe "
                                         "abziehbar bis zum Höchstbetrag"))
        c11, c12 = st.columns(2)
        bav = float(c11.number_input("Umwandlung in bAV (€)", 0.0, 1e6, 0.0, step=1000.0, format="%.0f",
                                     key="abf_bav", help="Teil der Abfindung in die betriebliche Altersversorgung"))
        dienst = int(c12.number_input("Dienstjahre (für bAV)", 0, 60, 10, step=1, key="abf_dienst"))

    gest = _gestaltungen_eingabe(st)

    e = {"gest": gest, "abfindung": float(abf), "zve1": float(zve1), "zve2": zve2,
         "splitting": veranl.startswith("Zusammen"),
         "kirche": kirche, "fuenftel_moeglich": bool(fuenftel), "alg1": alg1, "alg2": alg2,
         "werbungskosten": wk, "rv": rv, "rv_bisher": min(brutto, BBG_RV) * RV_SATZ, "jahresbrutto": brutto,
         "bav": bav, "dienstjahre": dienst}
    if rv:
        st.caption(f"Rentenversicherung: abziehbar sind noch {_de(rv_spielraum(e))} € (Höchstbetrag "
                   f"{_de(HOECHST_ALTERSVORSORGE * (2 if e['splitting'] else 1))} € minus bisherige Beiträge ca. "
                   f"{_de(e['rv_bisher'])} €).")
    v = varianten(e)
    beste = next(x for x in v if x["beste"])
    basis = v[0]

    st.markdown("##### Ergebnis")
    k1, k2 = st.columns(2)
    k1.metric("Steuern (günstigste Variante)", f"{_de(beste['steuer']['summe'])} €",
              f"{beste['kurz']} · {_pct(beste['satz'])}", delta_color="off")
    k2.metric("Netto", f"{_de(beste['netto'])} €",
              f"+ {_de(beste['angelegt'])} € Rente/bAV" if beste["angelegt"] else f"von {_de(abf)} € brutto",
              delta_color="off")
    k3, k4 = st.columns(2)
    k3.metric("Lohnsteuerabzug bei Auszahlung (ca.)", f"{_de(basis['steuer']['summe'])} €",
              "ohne Fünftelregelung", delta_color="off")
    k4.metric("Ersparnis ggü. Lohnsteuerabzug", f"{_de(basis['steuer']['summe'] - beste['steuer']['summe'])} €")

    st.dataframe(pd.DataFrame([{"Variante": ("✓ " if x["beste"] else "") + x["kurz"],
                                "Steuern": f"{_de(x['steuer']['summe'])} €", "Satz": _pct(x["satz"]),
                                "Netto": f"{_de(x['netto'])} €", "Ersparnis": f"{_de(x['ersparnis'])} €",
                                "ESt": f"{_de(x['steuer']['est'])} €", "Soli": f"{_de(x['steuer']['soli'])} €",
                                "KiSt": f"{_de(x['steuer']['kirche'])} €",
                                **({"Netto + Rente/bAV": f"{_de(x['netto'] + x['angelegt'])} €"}
                                   if any(y["angelegt"] for y in v) else {})} for x in v]),
                 hide_index=True, width="stretch")
    st.caption("Steuern = Mehrsteuer durch die Abfindung (Jahressteuer mit minus ohne Abfindung). Netto = Abfindung "
               "minus Steuern minus Einzahlungen in Rente/bAV.")

    if any(x["steuer"]["summe"] < 0 for x in v):
        st.caption("Negative Steuern: Die Gestaltungen sparen mehr Steuer, als die Abfindung kostet – sie senken auch "
                   "die Steuer auf das übrige Einkommen.")
    g = gestaltung_wirkung(e)
    wirk = [x for x in g["massnahmen"] if not x["info"]]
    if wirk:
        st.markdown("##### Gestaltungen – was bringt was?")
        st.dataframe(pd.DataFrame([{
            "Maßnahme": x["kurz"],
            "Abzug / Ermäßigung": (f"{_de(x['abzug'])} € Abzug" if x["abzug"] else "")
            + (f"{_de(x['ermaessigung'])} € von der Steuer" if x["ermaessigung"] else ""),
            "Steuer gespart": f"{_de(x['ersparnis'])} €",
            "Eigener Einsatz": f"{_de(x['einsatz'])} €",
            "Gespart je 1 € Einsatz": (_de(x["quote"], 2) + " €") if x.get("quote") is not None else "–",
            "Gegenwert": x["gegenwert"]} for x in wirk]), hide_index=True, width="stretch")
        st.caption("Jede Maßnahme einzeln gerechnet, Auszahlung im "
                   + ("Folgejahr" if g["jahr"] == "j2" else "laufenden Jahr")
                   + ". Mit Fünftelregelung wirken Abzüge besonders stark. Wichtig: Steuer sparen heißt Geld "
                     "ausgeben – lohnend nur, wenn du die Maßnahme ohnehin willst.")
        for x in wirk:
            st.caption(f"**{x['titel']}:** {x['hinweis']}")

    # --- Fuenftelregel nach Auszahlungsjahr ---
    st.markdown("##### 📅 Fünftelregel je nach Auszahlungsjahr")
    df_j = pd.DataFrame([{"Jahr": STEUERJAHR + i, "Übriges Einkommen €": float(z), "Arbeitslosengeld €": float(a_)}
                         for i, (z, a_) in enumerate([(zve1, alg1), (zve2, alg2), (zve2, 0.0), (zve2, 0.0)])])
    ed_j = st.data_editor(df_j, key="abf_fj_tab", hide_index=True, width="stretch", num_rows="fixed",
                          disabled=["Jahr"],
                          column_config={
                              "Jahr": st.column_config.NumberColumn("Jahr", format="%d"),
                              "Übriges Einkommen €": st.column_config.NumberColumn(
                                  "Übriges Einkommen €", step=1000.0, format="%.0f",
                                  help="Zu versteuerndes Einkommen in diesem Jahr ohne Abfindung"),
                              "Arbeitslosengeld €": st.column_config.NumberColumn("Arbeitslosengeld €", min_value=0.0,
                                                                                 step=500.0, format="%.0f")})
    fj = fuenftel_jahre(e, [{"jahr": int(z["Jahr"]), "zve": float(z["Übriges Einkommen €"] or 0),
                             "alg": float(z["Arbeitslosengeld €"] or 0)} for _, z in ed_j.iterrows()])
    bestes = min(fj, key=lambda x: x["fuenftel"])
    st.dataframe(pd.DataFrame([{"Auszahlung": ("✓ " if x is bestes else "") + str(x["jahr"]),
                                "ohne Fünftel": f"{_de(x['voll'])} €", "mit Fünftel": f"{_de(x['fuenftel'])} €",
                                "Ersparnis": f"{_de(x['ersparnis'])} €", "Satz": _pct(x["satz"]),
                                "Netto": f"{_de(x['netto'])} €", "Erstattung kommt": str(x["erstattung_jahr"])}
                               for x in fj]), hide_index=True, width="stretch")
    st.caption("Die Fünftelregel wirkt nur im Jahr der Auszahlung – die Steuer wird nicht auf mehrere Jahre "
               "verteilt, Folgejahre laufen normal. Bei Auszahlung behält der Arbeitgeber erst die Steuer „ohne "
               "Fünftel“ ein, die Differenz kommt mit der Steuererklärung im Folgejahr zurück. Einkommen und "
               "Arbeitslosengeld je Jahr oben in der Tabelle anpassen.")
    with st.expander("Steuer je nach übrigem Einkommen im Auszahlungsjahr", expanded=False):
        fe = fuenftel_einkommen(e)
        st.dataframe(pd.DataFrame([{"Übriges Einkommen": f"{_de(x['zve'])} €", "ohne Fünftel": f"{_de(x['voll'])} €",
                                    "mit Fünftel": f"{_de(x['fuenftel'])} €", "Ersparnis": f"{_de(x['ersparnis'])} €",
                                    "Satz": _pct(x["satz"]), "Netto": f"{_de(x['netto'])} €"} for x in fe]),
                     hide_index=True, width="stretch")

    # --- Langfrist: privat oder Investment-GmbH ---
    with st.expander("🏦 Langfrist: Netto-Abfindung privat anlegen oder Investment-GmbH?", expanded=False):
        c1, c2 = st.columns(2)
        av_betrag = float(c1.number_input("Anlagebetrag (€)", 0.0, 1e9, float(round(beste["netto"], -2)),
                                          step=5000.0, format="%.0f", key="abf_av_betrag",
                                          help="Vorbelegt mit dem Netto der günstigsten Variante"))
        av_jahre = int(c2.number_input("Jahre", 1, 50, 20, key="abf_av_jahre"))
        c3, c4 = st.columns(2)
        av_rendite = float(c3.number_input("Rendite p.a. (%)", -10.0, 50.0, 7.0, step=0.5, key="abf_av_r")) / 100
        av_art = c4.selectbox("Anlage", list(ANLAGEARTEN), format_func=ANLAGEARTEN.get, index=1, key="abf_av_art")
        c5, c6 = st.columns(2)
        av_aus = float(c5.number_input("davon Ausschüttung/Dividende p.a. (%)", 0.0, 50.0, 2.0, step=0.5,
                                       key="abf_av_aus", disabled=av_art == "zins")) / 100
        av_heb = float(c6.number_input("Gewerbesteuer-Hebesatz der Gemeinde (%)", 200.0, 900.0, 400.0, step=10.0,
                                       key="abf_av_heb"))
        c7, c8 = st.columns(2)
        av_kg = float(c7.number_input("GmbH-Gründung einmalig (€)", 0.0, 1e6, 1500.0, step=250.0, format="%.0f",
                                      key="abf_av_kg", help="Notar, Handelsregister, Beratung"))
        av_kj = float(c8.number_input("GmbH-Kosten pro Jahr (€)", 0.0, 1e6, 3000.0, step=250.0, format="%.0f",
                                      key="abf_av_kj", help="Bilanz, Steuererklärungen, Kammer, Konto"))
        avp = {"betrag": av_betrag, "jahre": av_jahre, "rendite": av_rendite, "art": av_art,
               "ausschuettung": av_aus, "hebesatz": av_heb, "kosten_gruendung": av_kg, "kosten_jahr": av_kj}
        av = anlage_vergleich(av_betrag, av_jahre, av_rendite, av_art, av_aus, av_heb, av_kg, av_kj,
                              freibetrag=2000.0 if e["splitting"] else 1000.0, kirche=kirche)
        letzte = av["zeilen"][-1]
        z = [r for r in av["zeilen"] if r["jahr"] % 5 == 0 or r["jahr"] in (1, av_jahre)]
        st.dataframe(pd.DataFrame([{"Jahr": r["jahr"], "Privat": f"{_de(r['privat'])} €",
                                    "GmbH (bleibt drin)": f"{_de(r['gmbh'])} €",
                                    "GmbH (an dich entnommen)": f"{_de(r['gmbh_privat'])} €"} for r in z]),
                     hide_index=True, width="stretch")
        try:
            st.line_chart(pd.DataFrame({"Privat": [r["privat"] for r in av["zeilen"]],
                                        "GmbH (bleibt drin)": [r["gmbh"] for r in av["zeilen"]],
                                        "GmbH (entnommen)": [r["gmbh_privat"] for r in av["zeilen"]]},
                                       index=[r["jahr"] for r in av["zeilen"]]), height=260)
        except Exception:
            pass
        ab = next((r["jahr"] for r in av["zeilen"] if r["gmbh"] > r["privat"]), None)
        diff_e = letzte["gmbh_privat"] - letzte["privat"]
        st.markdown(
            f"Nach {av_jahre} J.: privat **{_de(letzte['privat'])} €**, in der GmbH **{_de(letzte['gmbh'])} €**"
            + (f" (vorn ab Jahr {ab})" if ab else " (nie vorn)")
            + f", entnommen **{_de(letzte['gmbh_privat'])} €** → "
            + (f"GmbH lohnt sich auch bei Entnahme (+{_de(diff_e)} €)." if diff_e > 0 else
               f"wer das Geld privat braucht, fährt privat besser ({_de(-diff_e)} € mehr)."))
        st.caption(f"Steuersätze: privat {_pct(av['s']['div_p'])} auf Ausschüttungen/Zinsen und {_pct(av['s']['kurs_p'])} "
                   f"auf Kursgewinne (Sparerpauschbetrag eingerechnet); GmbH {_pct(av['s']['div_g'])} bzw. "
                   f"{_pct(av['s']['kurs_g'])} (Einzelaktien: Kursgewinne zu 95 % steuerfrei, Streubesitz-Dividenden "
                   "voll steuerpflichtig; Aktien-ETF: 80 % Teilfreistellung). Die Abfindung selbst wird in beiden Fällen "
                   "vorher privat versteuert. Vereinfachte Rechnung – vor einer Gründung Steuerberater fragen.")

    with st.expander("🔎 Details je Variante", expanded=False):
        for x in v:
            st.markdown(f"**{'✓ ' if x['beste'] else ''}{x['titel']}**")
            teile = []
            for jk, lab in (("j1", "Dieses Jahr"), ("j2", "Folgejahr")):
                if jk in x["jahre"]:
                    j = x["jahre"][jk]
                    teile.append(f"{lab}: Jahressteuer {_de(j['mit']['summe'])} € (ohne Abfindung "
                                 f"{_de(j['ohne']['summe'])} €) → durch die Abfindung +{_de(j['abfindung']['summe'])} €")
            st.caption(" · ".join(teile) + (f" — {x['hinweis']}" if x["hinweis"] else ""))

    with st.expander("🚫 Ideen ohne Ersparnis bei der Abfindungssteuer", expanded=False):
        for x in g["massnahmen"]:
            if x["info"]:
                st.markdown(f"- **{x['titel']}:** {x['hinweis']}")

    st.download_button("📄 Ergebnis als PDF", data=pdf_bericht(e, v, fj=fj, fe=fuenftel_einkommen(e), av=av, avp=avp),
                       file_name=f"Abfindung_{int(abf)}_EUR.pdf",
                       mime="application/pdf", width="stretch", key="abf_pdf")

    with st.expander("ℹ️ Gut zu wissen", expanded=False):
        st.markdown("\n".join("- " + t for t in HINWEISE))
