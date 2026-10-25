"""PDF-Bericht der Depot-Analyse (A4 hoch): Kennzahlen, Empfehlungen, Hinweise, Simulation und Annahmen."""
import html
import io

# Standardschrift Helvetica (WinAnsi) kennt diese Zeichen nicht
_ERSATZ = {"−": "-", "→": "->", "≈": "ca.", "≥": ">=", "≤": "<=", "×": "x", "•": "-", "„": '"', "“": '"',
           "✓": "", "⚠": "", "️": ""}


def _t(text):
    s = str(text if text is not None else "")
    for a, b in _ERSATZ.items():
        s = s.replace(a, b)
    s = s.encode("cp1252", "ignore").decode("cp1252")
    return html.escape(s)


def bericht(titel, kopfzeile, kpis, empfehlungen, hinweise, antworten=None, plan=None, simulation=None,
            annahmen=None):
    """kpis: [(Bezeichnung, Wert)]; empfehlungen: [[Name, Klasse, Gewicht, Score, Empfehlung, Prioritaet]];
    hinweise: [Text]; antworten: [(Frage, Antwort)]; plan: [(Prio, Massnahme, Warum)];
    simulation: {"trades": [[...]], "vergleich": [[Kennzahl, Vorher, Nachher, Veraenderung, Urteil]],
    "bewertung": [(Frage, Antwort)], "fazit": str}; annahmen: [Text]. -> PDF als bytes"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    grund = ParagraphStyle("g", fontName="Helvetica", fontSize=8, leading=10)
    fett = ParagraphStyle("f", parent=grund, fontName="Helvetica-Bold")
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=18, spaceAfter=2,
                        textColor=colors.HexColor("#0B1220"))
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, spaceBefore=8, spaceAfter=4,
                        textColor=colors.HexColor("#1D4ED8"))
    klein = ParagraphStyle("k", parent=grund, fontSize=7.2, leading=9, textColor=colors.HexColor("#4B5563"))
    kopf = ParagraphStyle("kp", parent=fett, fontSize=7.4, textColor=colors.white)
    breite = A4[0] - 24 * mm

    def tabelle(zeilen, breiten, kopfzeile=True):
        daten = [[Paragraph(_t(z), kopf if (kopfzeile and i == 0) else grund) for z in zeile]
                 for i, zeile in enumerate(zeilen)]
        t = Table(daten, colWidths=breiten, repeatRows=1 if kopfzeile else 0)
        stil = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        if kopfzeile:
            stil.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4ED8")))
        t.setStyle(TableStyle(stil))
        return t

    inhalt = [Paragraph(_t(titel), h1), Paragraph(_t(kopfzeile), klein), Spacer(1, 4)]
    if kpis:
        paare = [list(kpis[i:i + 2]) for i in range(0, len(kpis), 2)]
        zeilen = [[a for kv in p for a in kv] + [""] * (4 - 2 * len(p)) for p in paare]
        inhalt += [Paragraph("Kennzahlen", h2), tabelle(zeilen, [breite * 0.22, breite * 0.28] * 2, False)]
    if antworten:
        inhalt.append(Paragraph("Analyse in sieben Fragen", h2))
        for f, a in antworten:
            inhalt += [Paragraph(_t(f), fett), Paragraph(_t(a), grund), Spacer(1, 2)]
    if plan:
        inhalt += [Paragraph("Priorisierter Aktionsplan", h2),
                   tabelle([["Priorität", "Maßnahme", "Begründung"]] + [list(p) for p in plan],
                           [breite * 0.12, breite * 0.38, breite * 0.5])]
    if empfehlungen:
        inhalt += [Paragraph("Einzelpositionen", h2),
                   tabelle([["Position", "Klasse", "Gewicht", "Score", "Empfehlung", "Priorität"]] + empfehlungen,
                           [breite * 0.34, breite * 0.11, breite * 0.1, breite * 0.09, breite * 0.22, breite * 0.14])]
    if hinweise:
        inhalt.append(Paragraph("Hinweise und Warnungen", h2))
        inhalt += [Paragraph("- " + _t(h), grund) for h in hinweise]
    if simulation:
        inhalt.append(Paragraph("Simulation (virtuell – das echte Depot wurde nicht verändert)", h2))
        if simulation.get("trades"):
            inhalt.append(tabelle([["Aktion", "Wert", "Stück", "Betrag", "Gebühr"]] + simulation["trades"],
                                  [breite * 0.12, breite * 0.4, breite * 0.12, breite * 0.18, breite * 0.18]))
            inhalt.append(Spacer(1, 4))
        if simulation.get("vergleich"):
            inhalt.append(tabelle([["Kennzahl", "Vorher", "Nachher", "Veränderung", "Urteil"]] + simulation["vergleich"],
                                  [breite * 0.32, breite * 0.18, breite * 0.18, breite * 0.18, breite * 0.14]))
        for f, a in simulation.get("bewertung") or []:
            inhalt += [Paragraph(_t(f), fett), Paragraph(_t(a), grund)]
        if simulation.get("fazit"):
            inhalt += [Spacer(1, 3), Paragraph(_t(simulation["fazit"]), fett)]
    if annahmen:
        inhalt.append(Paragraph("Datenquellen, Annahmen und Grenzen", h2))
        inhalt += [Paragraph("- " + _t(a), klein) for a in annahmen]
    inhalt += [Spacer(1, 6), Paragraph(_t("Keine Anlageberatung. Alle Scores und Empfehlungen sind regelbasierte "
                                          "Auswertungen der genannten Daten; Modellrechnungen sind keine Prognosen."),
                                       klein)]
    puffer = io.BytesIO()
    SimpleDocTemplate(puffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                      bottomMargin=12 * mm, title=_t(titel)).build(inhalt)
    return puffer.getvalue()
