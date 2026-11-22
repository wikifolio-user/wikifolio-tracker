"""PDF-Auswertung eines Einzelwerts aus der Ansicht "Bewertung" (A4 hoch).

Inhalt: Kopf mit Kennungen und Datenstand, Ergebnis auf einen Blick, Teilscores mit Netzdiagramm, Staerken und
Schwaechen, alle Kennzahlen mit Vergleich, Einschaetzung des Qualitaets-Agenten und - nur bei Aktien - eine
Zusammenfassung der Investoren-Checks (je Investor eine Zeile), Fairer Wert und IBD-aehnliches Rating.
Es wird nichts neu berechnet: Der Bericht nimmt genau die Ergebnisse, die die Ansicht anzeigt."""
import datetime
import html
import io

# Standardschrift Helvetica (WinAnsi) kennt diese Zeichen nicht
_ERSATZ = {"−": "-", "→": "->", "≈": "ca.", "≥": ">=", "≤": "<=", "×": "x", "•": "-", "↑": "", "↓": "",
           "✓": "", "⚠": "", "️": "", "–": "-", "„": '"', "“": '"', "”": '"', "…": "...", "‘": "'", "’": "'"}

TINTE = "#0B1220"
AKZENT = "#1D4ED8"
GRAU = "#4B5563"
LINIE = "#CBD5E1"
FLAECHE = "#F1F5F9"
AMPEL = {"gruen": "#059669", "gelb": "#B45309", "rot": "#DC2626", "grau": "#6B7280"}
AMPEL_TEXT = {"gruen": "stark", "gelb": "mittel", "rot": "schwach", "grau": "n/a"}
EINORDNUNG = {"gut": "gruen", "neutral": "gelb", "schlecht": "rot", "n/a": "grau"}
NOTE_FARBE = {"A": "gruen", "B": "gruen", "C": "gelb", "D": "gelb", "E": "rot", "F": "rot"}


def _roh(text):
    """Text fuer die Standardschrift (WinAnsi) - ohne HTML-Maskierung (Seitenrand, Metadaten)."""
    s = str(text if text is not None else "")
    for a, b in _ERSATZ.items():
        s = s.replace(a, b)
    return s.encode("cp1252", "ignore").decode("cp1252")


def _t(text):
    return html.escape(_roh(text))


def _de(x, n=1):
    if x is None:
        return "n/a"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ampel(score):
    import scoring as SC
    return "grau" if score is None else SC.ampel(score)


def dateiname(e, heute=None):
    kennung = e.get("ticker") or e.get("wkn") or e.get("isin") or e.get("name") or "Wert"
    sauber = "".join(c if c.isalnum() or c in "-." else "_" for c in str(kennung))[:40]
    return f"Bewertung_{sauber}_{(heute or datetime.date.today()).isoformat()}.pdf"


def _fair_zeilen(fair, waehrung):
    """Fairer Wert: [(Methode, Wert, Abstand zum Kurs)] nur fuer Methoden mit Wert."""
    import investoren_ui as IU
    kurs = (fair or {}).get("kurs")
    zeilen = []
    for m in (fair or {}).get("modelle") or []:
        if not m.get("wert"):
            continue
        abst = f"{'+' if m['wert'] >= kurs else '-'}{_de(abs(m['wert'] / kurs - 1) * 100, 0)} %" if kurs else "n/a"
        zeilen.append([m["methode"], IU.wert_text(m["wert"], "kurs", waehrung), abst])
    return zeilen


def _netz(kategorien, groesse):
    """Netzdiagramm der Teilscores (reportlab-Grafik, kein Bild)."""
    from reportlab.graphics.charts.spider import SpiderChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    import bewertung_ui as BU
    mit = [c for c in kategorien if c["score"] is not None]
    if len(mit) < 3:
        return None
    d = Drawing(groesse, groesse)
    sp = SpiderChart()
    sp.x, sp.y = 34, 22
    sp.width = sp.height = groesse - 68
    # zweite, unsichtbare Linie bei 100 haelt die Skala fest (sonst skaliert das Netz auf den groessten Wert)
    sp.data = [[round(c["score"]) for c in mit], [100] * len(mit)]
    sp.labels = [_t(BU.KURZ.get(c["key"], c["titel"])) for c in mit]
    sp.strands[0].fillColor = colors.Color(0.11, 0.31, 0.85, alpha=0.22)
    sp.strands[0].strokeColor = colors.HexColor(AKZENT)
    sp.strands[0].strokeWidth = 1.4
    sp.spokes.strokeColor = colors.HexColor(LINIE)
    sp.strandLabels.fontSize = 0
    sp.spokeLabels.fontName = "Helvetica"
    sp.spokeLabels.fontSize = 7.5
    sp.spokeLabels.fillColor = colors.HexColor(TINTE)
    sp.strands[1].fillColor = None
    sp.strands[1].strokeColor = None
    sp.strands[1].strokeWidth = 0
    d.add(sp)
    return d


def bericht(e, b, stand, investoren=None, erstellt=None):
    """e: Eintrag aus scoring.universum, b: scoring.bewerten(e, ...), stand: Datenstand-Text,
    investoren: Rueckgabe von investoren_ui.bereich (nur Aktien) oder None. -> PDF als bytes"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    import bewertung_ui as BU
    import scoring as SC

    erstellt = erstellt or datetime.datetime.now()
    farbe = colors.HexColor
    grund = ParagraphStyle("g", fontName="Helvetica", fontSize=8.2, leading=10.4, textColor=farbe(TINTE))
    fett = ParagraphStyle("f", parent=grund, fontName="Helvetica-Bold")
    rechts = ParagraphStyle("r", parent=grund, alignment=2)
    klein = ParagraphStyle("k", parent=grund, fontSize=7.2, leading=9, textColor=farbe(GRAU))
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=farbe(TINTE))
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=10, spaceAfter=5,
                        textColor=farbe(AKZENT))
    kopf = ParagraphStyle("kp", parent=fett, fontSize=7.4, textColor=colors.white)
    kopfr = ParagraphStyle("kpr", parent=kopf, alignment=2)
    gross = ParagraphStyle("gr", fontName="Helvetica-Bold", fontSize=24, leading=27, alignment=1)
    breite = A4[0] - 30 * mm

    def p(text, stil=grund):
        return Paragraph(_t(text), stil)

    def farbig(text, ampel, stil=fett):
        return Paragraph(f'<font color="{AMPEL[ampel]}">{_t(text)}</font>', stil)

    def gitter(daten, breiten, kopfzeile=True, zebra=True, extra=()):
        t = Table(daten, colWidths=breiten, repeatRows=1 if kopfzeile else 0, hAlign="LEFT")
        stil = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, farbe(LINIE)),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if kopfzeile:
            stil.append(("BACKGROUND", (0, 0), (-1, 0), farbe(AKZENT)))
        if zebra:
            stil += [("BACKGROUND", (0, i), (-1, i), farbe(FLAECHE))
                     for i in range(1 if kopfzeile else 0, len(daten)) if i % 2 == 0]
        t.setStyle(TableStyle(stil + list(extra)))
        return t

    art = BU.ART_TEXT[e["art"]]
    inhalt = []

    # ---------------------------------------------------------------- Kopf
    kennungen = [f"{n} {e[k]}" for n, k in (("Ticker", "ticker"), ("WKN", "wkn"), ("ISIN", "isin")) if e.get(k)]
    kurs = f"{_de(e['kurs'], 2)} {e.get('waehrung') or ''}".strip() if e.get("kurs") else "n/a"
    tag = "" if e.get("tag") is None else f" ({'+' if e['tag'] > 0 else ''}{_de(e['tag'], 2)} % am Tag)"
    inhalt += [p(f"Bewertung {art}", ParagraphStyle("ue", parent=fett, textColor=farbe(AKZENT), fontSize=9)),
               p(e["name"], h1), Spacer(1, 2),
               p(" · ".join(kennungen + ([f"Sektor: {e.get('sektor') or 'n/a'}"] if e["art"] == "aktie" or e.get("sektor")
                                   else [])), klein), Spacer(1, 6)]
    info = [[p("Kurs", klein), p("Datenstand", klein), p("Erstellt", klein), p("Vergleichsbasis", klein)],
            [p(kurs + tag, fett), p(stand, fett), p(erstellt.strftime("%d.%m.%Y %H:%M"), fett),
             p(f"alle {SC.KLASSEN_TEXT[e['art']]} der Top-500-Liste", fett)]]
    inhalt.append(gitter(info, [breite * 0.25] * 4, kopfzeile=False, zebra=False,
                         extra=[("BACKGROUND", (0, 0), (-1, -1), farbe(FLAECHE)),
                                ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white)]))

    # ---------------------------------------------------------------- Ergebnis auf einen Blick
    g = b["gesamt"]
    n, von = b["abdeckung"]
    links = [Paragraph(f'<font color="{AMPEL[b["ampel"]]}">{"n/a" if g is None else f"{g:.0f}"}</font>', gross),
             p("Gesamtscore von 100", ParagraphStyle("gs", parent=klein, alignment=1)), Spacer(1, 3),
             Paragraph(f'<font color="{AMPEL[b["ampel"]]}">Ampel: {AMPEL_TEXT[b["ampel"]]}</font>',
                       ParagraphStyle("am", parent=fett, alignment=1))]
    if b.get("fazit"):
        links.append(Paragraph(f'<font color="{AMPEL[{"unterbewertet": "gruen", "fair bewertet": "gelb", "teuer": "rot"}[b["fazit"]]]}">'
                               f'{_t(b["fazit"])}</font>', ParagraphStyle("fz", parent=fett, alignment=1)))
    punkte = [p(SC.kurzfazit(e, b), fett), Spacer(1, 3),
              p(f"{n} von {von} Kennzahlen vorhanden - fehlende zählen nicht mit.", klein)]
    if investoren:
        k = investoren["konsens"]
        punkte += [Spacer(1, 5), Paragraph(
            f'<b>Investoren-Checks:</b> Note <font color="{AMPEL[NOTE_FARBE.get(k["note"], "grau")]}"><b>'
            f'{_t(k["note"])}</b></font> - {k["kaufen"]} von {k["investoren"]} Investoren würden kaufen', grund)]
        fair = investoren.get("fair") or {}
        if fair.get("median") and fair.get("kurs"):
            abst = (fair["median"] / fair["kurs"] - 1) * 100
            import investoren_ui as IU
            punkte.append(Paragraph(f"<b>Fairer Wert (Median):</b> {_t(IU.wert_text(fair['median'], 'kurs', fair.get('waehrung') or ''))}"
                                    f" - {'über' if abst >= 0 else 'unter'} dem Kurs um {_de(abs(abst), 0)} %", grund))
        r = investoren.get("ibd")
        if r:
            punkte.append(Paragraph(f"<b>IBD-ähnliches Rating:</b> EPS {r['eps']} / 99 · Composite "
                                    f"{r['composite']} / 99", grund))
        if k["warnungen"]:
            punkte.append(Paragraph(f'<font color="{AMPEL["rot"]}"><b>{len(set(k["warnungen"]))} Warnsignal(e)</b>'
                                    "</font> - Details unten", grund))
    blick = Table([[links, punkte]], colWidths=[breite * 0.3, breite * 0.7])
    blick.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 0.6, farbe(LINIE)),
                               ("LINEAFTER", (0, 0), (0, 0), 0.6, farbe(LINIE)),
                               ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    inhalt += [p("Ergebnis auf einen Blick", h2), blick]

    # ---------------------------------------------------------------- Teilscores + Netz
    zeilen = [[p("Bereich", kopf), p("Teilscore", kopfr), p("Kennzahlen", kopfr), p("Gewicht", kopfr)]]
    for c in b["kategorien"]:
        s = c["score"]
        zeilen.append([p(c["titel"]), farbig("n/a" if s is None else f"{s:.0f} / 100", _ampel(s),
                                              ParagraphStyle("sr", parent=fett, alignment=2)),
                       p(f"{c['anzahl']} von {c['von']}", rechts), p(f"{c['gewicht']} %", rechts)])
    tab = gitter(zeilen, [breite * 0.26, breite * 0.14, breite * 0.12, breite * 0.1])
    netz = _netz(b["kategorien"], breite * 0.32)
    teil = Table([[tab, netz or p("Für das Netzdiagramm braucht es mindestens drei Teilscores.", klein)]],
                 colWidths=[breite * 0.63, breite * 0.37])
    teil.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    inhalt += [p("Teilscores", h2), teil]

    # ---------------------------------------------------------------- Staerken / Schwaechen
    def liste(eintraege, leer):
        if not eintraege:
            return [p(leer, klein)]
        return [p(f"- {z['titel']}: {BU.wert_text(z, e['info'])} - besser als {z['perzentil']:.0f} % "
                  f"({BU._vergleich_text(e, z)})") for z in eintraege]
    sw = Table([[farbig("Stärken", "gruen"), farbig("Schwächen", "rot")],
                [liste(b["staerken"], "Keine Kennzahl im oberen Viertel."),
                 liste(b["schwaechen"], "Keine Kennzahl im unteren Viertel.")]],
               colWidths=[breite * 0.5, breite * 0.5])
    sw.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    inhalt += [KeepTogether([p("Stärken und Schwächen", h2), sw])]

    # ---------------------------------------------------------------- Kennzahlen
    zeilen = [[p("Kennzahl", kopf), p("Wert", kopfr), p("Einordnung", kopf), p("Vergleich (Median)", kopfr),
               p("Besser als", kopfr)]]
    extra = []
    for c in b["kategorien"]:
        score = "Teilscore n/a" if c["score"] is None else f"Teilscore {c['score']:.0f}"
        extra += [("SPAN", (0, len(zeilen)), (-1, len(zeilen))),
                  ("BACKGROUND", (0, len(zeilen)), (-1, len(zeilen)), farbe("#DBEAFE"))]
        zeilen.append([p(f"{c['titel']} · {score}", fett), "", "", "", ""])
        for z in (z for z in b["kennzahlen"] if z["kategorie"] == c["key"]):
            richtung = "höher besser" if z["richtung"] > 0 else "niedriger besser"
            basis = "Sektor" if z["basis"] == "sektor" else "Top 500"
            pz = z["perzentil"]
            zeilen.append([Paragraph(f"{_t(z['titel'])} <font size=6.5 color='{GRAU}'>{richtung}</font>", grund),
                           p(BU.wert_text(z, e["info"]), rechts),
                           farbig(z["einordnung"], EINORDNUNG[z["einordnung"]]),
                           Paragraph(f"{_t(BU.median_text(z))} <font size=6.5 color='{GRAU}'>{basis}</font>", rechts),
                           farbig("n/a" if pz is None else f"{pz:.0f} %", _ampel(pz),
                                  ParagraphStyle("pz", parent=fett, alignment=2))])
    inhalt += [CondPageBreak(60 * mm), p("Alle Kennzahlen", h2),
               gitter(zeilen, [breite * 0.36, breite * 0.17, breite * 0.13, breite * 0.2, breite * 0.14],
                      zebra=False, extra=extra)]
    teile = BU.einschaetzung_teile(e) if e["art"] == "aktie" else []
    if teile:
        inhalt += [Spacer(1, 4), p("Einschätzung des Qualitäts-Agenten (zur Info, nicht im Score): "
                                   + " · ".join(teile), klein)]

    # ---------------------------------------------------------------- Investoren (Zusammenfassung)
    if investoren:
        import investoren_ui as IU
        k = investoren["konsens"]
        zeilen = [[p("Investor / Check", kopf), p("Strategie", kopf), p("Score", kopfr), p("Erfüllt", kopfr),
                   p("Fazit", kopf)]]
        for r in investoren["ergebnisse"]:
            s = r["score_0_100"]
            erf = f"{r['erfuellt']} von {r['gesamt']}" if r["gesamt"] else "n/a"
            zeilen.append([p(r["investor"], fett), p(r["strategie"], klein),
                           farbig("n/a" if s is None else f"{s:.0f}", _ampel(s),
                                  ParagraphStyle("is", parent=fett, alignment=2)),
                           p(erf, rechts), p(r["fazit"], klein)])
        block = [CondPageBreak(70 * mm), p("Investoren-Checks (Zusammenfassung)", h2),
                 Paragraph(f'Gesamtnote <font color="{AMPEL[NOTE_FARBE.get(k["note"], "grau")]}"><b>{_t(k["note"])}'
                           f'</b></font> · {k["kaufen"]} von {k["investoren"]} Investoren würden kaufen · '
                           f"{_t(k['satz'])}", grund), Spacer(1, 4),
                 gitter(zeilen, [breite * 0.2, breite * 0.33, breite * 0.08, breite * 0.11, breite * 0.28])]
        if k["warnungen"]:
            block += [Spacer(1, 4), farbig("Warnsignale", "rot")]
            block += [p(f"- {w}") for w in dict.fromkeys(k["warnungen"])]
        inhalt += block

        fair = investoren.get("fair") or {}
        fz = _fair_zeilen(fair, fair.get("waehrung") or investoren.get("waehrung") or "")
        if fz:
            kurs_txt = IU.wert_text(fair.get("kurs"), "kurs", fair.get("waehrung") or "") if fair.get("kurs") else "n/a"
            tab = gitter([[p("Methode", kopf), p("Fairer Wert je Aktie", kopfr), p("Abstand zum Kurs", kopfr)]]
                         + [[p(a), p(w, rechts), p(x, rechts)] for a, w, x in fz],
                         [breite * 0.5, breite * 0.25, breite * 0.25])
            teil = [p("Fairer Wert - alle Methoden", h2),
                    p(f"Kurs in Berichtswährung: {kurs_txt}"
                      + (f" · Median aller Methoden: {IU.wert_text(fair['median'], 'kurs', fair.get('waehrung') or '')}"
                         if fair.get("median") else ""), grund), Spacer(1, 3), tab]
            if (fair.get("reverse") or {}).get("text"):
                teil += [Spacer(1, 3), p(f"Reverse-DCF: {fair['reverse']['text']}", grund)]
            teil.append(p("Modelle sind Näherungen - die Spanne zeigt die Unsicherheit. DCF mit den in der App "
                          "eingestellten Annahmen.", klein))
            inhalt.append(KeepTogether(teil))

        r = investoren.get("ibd")
        if r:
            import ibd_rating as IBD
            zeilen = [[p("Baustein", kopf), p("Rang (1-100)", kopfr)]]
            zeilen += [[p(titel), p("n/a" if r["teile"].get(key) is None else str(r["teile"][key]), rechts)]
                       for key, titel in IBD.TEILE.items()]
            inhalt.append(KeepTogether([
                p("IBD-ähnliches Rating (zusätzliche Bewertung)", h2),
                Paragraph(f"EPS-Rating <b>{r['eps']}</b> / 99 · Composite-Rating <b>{r['composite']}</b> / 99", grund),
                Spacer(1, 3), gitter(zeilen, [breite * 0.6, breite * 0.2]),
                p("Rang im Vergleich mit allen vom Agenten bewerteten Aktien (99 = besser als 99 %). Nachgebildet "
                  "nach den veröffentlichten Bausteinen von William O'Neil - nicht das offizielle IBD-Rating.",
                  klein)]))

    # ---------------------------------------------------------------- Methodik
    block = [p("So wird gerechnet", h2)]
    block += [Paragraph(f"<b>{_t(t)}:</b> {_t(x)}", klein) for t, x in BU.methodik(e)]
    block.append(Paragraph("<b>Datenquellen:</b> Tägliche Agenten-Dateien der App (Katalog, Qualitäts- und "
                           "Performance-Daten)" + (", für die Investoren-Checks Fundamentaldaten von Yahoo Finance"
                                                   if investoren else "") + ". Daten können verzögert oder "
                           "unvollständig sein.", klein))
    inhalt += [KeepTogether(block), Spacer(1, 6),
               p("Keine Anlageberatung. Der Score ist eine regelbasierte Auswertung der vorhandenen Kennzahlen im "
                 "Vergleich zur Top-500-Liste; Investoren-Checks sind vereinfachte Annäherungen an die Methoden der "
                 "genannten Personen. Modellrechnungen sind keine Prognosen.", klein)]

    titel = f"Bewertung {e['name']}"

    def rand(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(farbe(AKZENT))
        canvas.setLineWidth(2)
        canvas.line(15 * mm, A4[1] - 9 * mm, A4[0] - 15 * mm, A4[1] - 9 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(farbe(GRAU))
        canvas.drawString(15 * mm, 9 * mm, _roh(f"{titel} · Datenstand {stand}")[:110])
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    puffer = io.BytesIO()
    SimpleDocTemplate(puffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                      bottomMargin=15 * mm, title=_roh(titel), author="wikifolio-tracker",
                      subject="Bewertung").build(inhalt, onFirstPage=rand, onLaterPages=rand)
    return puffer.getvalue()
