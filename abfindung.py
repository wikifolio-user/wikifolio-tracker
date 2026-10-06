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


def variante(e, titel, kurz, teile, rv=0.0, bav=0.0, hinweis=""):
    """teile: [(jahr_key, betrag, fuenftel)] - 'j1' = Auszahlungsjahr, 'j2' = Folgejahr.
    rv/bav: Teil der Abfindung, der in Rente/bAV fliesst (wirkt im ersten Jahr der Variante)."""
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
            abzug += rv_abzug
        a_f = sum(b for b, f in betraege if f)
        a_n = sum(b for b, f in betraege if not f)
        if jk == erstes and bav_steuerfrei:        # steuerfreier bAV-Teil mindert die steuerpflichtige Abfindung
            if a_f:
                a_f = max(a_f - bav_steuerfrei, 0.0)
            else:
                a_n = max(a_n - bav_steuerfrei, 0.0)
        rest = zve + a_n - abzug
        mit = steuern(est_mit_abfindung(rest, a_f, True, sp, pv) if a_f else est(rest, sp, pv), sp, ki)
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
    beste = min(v, key=lambda x: x["steuer"]["summe"])
    basis = v[0]["steuer"]["summe"]
    for x in v:
        x["beste"] = x is beste
        x["ersparnis"] = basis - x["steuer"]["summe"]
    return v


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


def pdf_bericht(e, v, erstellt=None):
    """Ergebnis als PDF (bytes)."""
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

    e = {"abfindung": float(abf), "zve1": float(zve1), "zve2": zve2, "splitting": veranl.startswith("Zusammen"),
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

    st.download_button("📄 Ergebnis als PDF", data=pdf_bericht(e, v), file_name=f"Abfindung_{int(abf)}_EUR.pdf",
                       mime="application/pdf", width="stretch", key="abf_pdf")

    with st.expander("ℹ️ Gut zu wissen", expanded=False):
        st.markdown("\n".join("- " + t for t in HINWEISE))
