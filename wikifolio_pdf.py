"""PDF-Ranglisten (A4 quer): wikifolio-Rangliste nach Zeitraum und ETF-/wikifolio-Score."""
import html
import io


def _de(x, dez=1):
    return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v):
    # Standardschrift Helvetica kennt kein Unicode-Minus - normales Minus
    if v is None:
        return "-"
    return ("+" if v >= 0 else "-") + _de(abs(v)) + " %"


def bericht(liste, spalten, titel, zeitraum, kopfzeile):
    """liste: Eintraege aus wikifolio_rangliste ({rang, name, wkn, perf}); spalten: Zeitraum-Schluessel
    in Anzeigereihenfolge (sortierter zuerst); titel: {schluessel: Bezeichnung}. -> PDF als bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    grund = ParagraphStyle("g", fontName="Helvetica", fontSize=7.6, leading=9.2)
    name_stil = ParagraphStyle("n", parent=grund, fontName="Helvetica-Bold")
    kopf_l = ParagraphStyle("k", parent=grund, fontName="Helvetica-Bold", fontSize=7, textColor=colors.white)
    kopf_r = ParagraphStyle("kr", parent=kopf_l, alignment=2)
    klein = ParagraphStyle("kl", fontName="Helvetica", fontSize=7.6, leading=9.6,
                           textColor=colors.HexColor("#4B5563"), spaceAfter=4)
    breite = landscape(A4)[0] - 20 * mm
    rest = breite - 12 * mm - 70 * mm - 20 * mm
    breiten = [12 * mm, 70 * mm, 20 * mm] + [rest / len(spalten)] * len(spalten)

    kopf = ([Paragraph("#", kopf_r), Paragraph("wikifolio", kopf_l), Paragraph("WKN", kopf_l)]
            + [Paragraph(html.escape(titel[k]), kopf_r)
               for k in spalten])
    daten = [kopf]
    for w in liste:
        daten.append([str(w["rang"]), Paragraph(html.escape(w["name"]), name_stil), w["wkn"]]
                     + [_pct(w["perf"].get(k)) for k in spalten])
    t = Table(daten, colWidths=breiten, repeatRows=1)
    stil = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 7.6),
            ("ALIGN", (0, 1), (0, -1), "RIGHT"), ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    sortiert = 3 + spalten.index(zeitraum) if zeitraum in spalten else None
    if sortiert is not None:
        stil.append(("FONT", (sortiert, 1), (sortiert, -1), "Helvetica-Bold", 7.6))
    for r, w in enumerate(liste, 1):
        if r % 2 == 0:
            stil.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F3F4F6")))
        for i, k in enumerate(spalten):
            v = w["perf"].get(k)
            if v is not None:
                stil.append(("TEXTCOLOR", (3 + i, r), (3 + i, r),
                             colors.HexColor("#047857" if v >= 0 else "#B91C1C")))
    t.setStyle(TableStyle(stil))

    inhalt = [Paragraph("wikifolio-Rangliste", ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15,
                                                                leading=18, spaceAfter=2)),
              Paragraph(html.escape(kopfzeile), klein), Spacer(1, 2 * mm), t, Spacer(1, 4 * mm),
              Paragraph("- = in diesem Zeitraum nicht unter den Top 500 (oder noch keine so lange Historie). "
                        "Vergangene Entwicklung ist keine Prognose und keine Kaufempfehlung.", klein)]

    def fuss(c, doc):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#6B7280"))
        c.drawString(10 * mm, 7 * mm, "wikifolio-Rangliste")
        c.drawRightString(landscape(A4)[0] - 10 * mm, 7 * mm, f"Seite {doc.page}")
        c.restoreState()

    puffer = io.BytesIO()
    SimpleDocTemplate(puffer, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm,
                      bottomMargin=12 * mm, title="wikifolio-Rangliste").build(inhalt, onFirstPage=fuss,
                                                                                 onLaterPages=fuss)
    return puffer.getvalue()


def score_bericht(liste, art, kopfzeile):
    """PDF der ETF-/wikifolio-Score-Rangliste (klassen_score.rangliste). -> bytes"""
    import klassen_score as KS
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    grund = ParagraphStyle("g", fontName="Helvetica", fontSize=7.2, leading=8.8)
    name_stil = ParagraphStyle("n", parent=grund, fontName="Helvetica-Bold")
    kopf_l = ParagraphStyle("k", parent=grund, fontName="Helvetica-Bold", fontSize=6.8, textColor=colors.white)
    kopf_r = ParagraphStyle("kr", parent=kopf_l, alignment=2)
    klein = ParagraphStyle("kl", fontName="Helvetica", fontSize=7.6, leading=9.6,
                           textColor=colors.HexColor("#4B5563"), spaceAfter=4)
    farbe = {"prio": "#047857", "beobachten": "#B45309", "nicht": "#6B7280"}
    risiko = ("rr", "Rendite je Risiko") if art == "etf" else ("rdd", "Rendite je Rückgang")
    titel = "ETF-Score" if art == "etf" else "wikifolio-Score"
    breite = landscape(A4)[0] - 20 * mm
    feste = [10 * mm, 58 * mm, 22 * mm, 13 * mm, 18 * mm, 18 * mm, 16 * mm, 16 * mm, 14 * mm]
    breiten = feste + [breite - sum(feste)]

    def zahl(v, dez=1, einheit="", vz=False):
        if v is None:
            return "-"
        return ("+" if vz and v >= 0 else "-" if v < 0 else "") + _de(abs(v), dez) + einheit

    kopf = [Paragraph(t, kopf_r if r else kopf_l) for t, r in (
        ("#", True), ("Name", False), ("WKN / ISIN", False), ("Score", True), ("Rendite p. a.", True),
        (risiko[1], True), ("Max. Rückgang", True), ("Schwankung", True), ("Historie", True),
        ("Begründung", False))]
    daten, stil = [kopf], []
    for r, e in enumerate(liste, 1):
        b, k = e["bewertung"], e["bewertung"]["kennzahlen"]
        st_, sw = KS.staerken_schwaechen(b, art)
        begr = "; ".join(["+ " + x for x in st_] + ["- " + x for x in sw]).replace("–", "-")
        daten.append([str(e["rang"]), Paragraph(html.escape(e["name"]), name_stil), e["kennung"] or e["isin"],
                      _de(b["score"], 0), zahl(k["rendite"], 1, " %", vz=True), zahl(k[risiko[0]], 2),
                      zahl(-k["dd"], 0, " %") if k["dd"] is not None else "-", zahl(k["vola"], 0, " %"),
                      zahl(k["jahre"], 1, " J."), Paragraph(html.escape(begr), grund)])
        stil.append(("TEXTCOLOR", (3, r), (3, r), colors.HexColor(farbe[b["einordnung"]])))
        if r % 2 == 0:
            stil.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F3F4F6")))
    t = Table(daten, colWidths=breiten, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
                           ("FONT", (0, 1), (-1, -1), "Helvetica", 7.4),
                           ("FONT", (3, 1), (3, -1), "Helvetica-Bold", 8),
                           ("ALIGN", (0, 1), (0, -1), "RIGHT"), ("ALIGN", (3, 1), (8, -1), "RIGHT"),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)] + stil))
    kriterien = ", ".join(f"{t_.split(' (')[0]} {g} %" for _, t_, g, _, _ in KS.KRITERIEN[art])
    inhalt = [Paragraph(titel, ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15, leading=18,
                                              spaceAfter=2)),
              Paragraph(html.escape(kopfzeile), klein),
              Paragraph(html.escape(f"Eigene Bewertung, unabhängig vom Aktien-Score. Kriterien: {kriterien}. "
                                    "Score-Farbe: grün = Hohe Analysepriorität, orange = Beobachtungsliste, "
                                    "grau = Nicht weiterverfolgen."), klein),
              Spacer(1, 2 * mm), t, Spacer(1, 4 * mm),
              Paragraph("Modellbewertung aus vergangenen Kursen - keine Prognose und keine Kaufempfehlung.", klein)]

    def fuss(c, doc):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#6B7280"))
        c.drawString(10 * mm, 7 * mm, titel)
        c.drawRightString(landscape(A4)[0] - 10 * mm, 7 * mm, f"Seite {doc.page}")
        c.restoreState()

    puffer = io.BytesIO()
    SimpleDocTemplate(puffer, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm,
                      bottomMargin=12 * mm, title=titel).build(inhalt, onFirstPage=fuss, onLaterPages=fuss)
    return puffer.getvalue()
