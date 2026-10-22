"""PDF der wikifolio-Rangliste (A4 quer): alle Plaetze der gewaehlten Liste mit allen Zeitraeumen."""
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
