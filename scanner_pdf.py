"""PDF-Bericht des Investment-Scanners (A4 quer): Eckdaten, Ergebnis und beide Musterdepots mit Begruendung."""
import html
import io

import scanner as S

KLASSE = {"etf": "ETF", "aktie": "Aktie", "wikifolio": "wikifolio", "cash": "Cash", "": ""}
KOPF = ["Wertpapier", "Gewicht", "Betrag", "Rendite p. a.", "Grundlage", "Beitrag", "Kategorie",
        "ISIN / WKN / Ticker", "Begründung"]


def _de(x, dez=0):
    return f"{x:,.{dez}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(x, dez=0):
    # Standardschrift Helvetica kennt kein Unicode-Minus - normales Minus
    return ("-" if x < -1e-9 else "") + _de(abs(x), dez) + " €"


def _pct(x, dez=1, vz=False):
    if x is None:
        return "–"
    return ("+" if vz and x > 0 else "-" if x < 0 else "") + _de(abs(x), dez) + " %"


def _text(t):
    """Fuer Helvetica (WinAnsi): Zeichen ohne Glyphe ersetzen, dann fuer Paragraph maskieren."""
    t = str(t).replace("−", "-").replace("≈", "ca.").replace("≥", ">=").replace("≤", "<=").replace("×", "x")
    return html.escape(t)


def kennzahlen(erg):
    """[(Bezeichnung, Wert)] fuer Eckdaten und Ergebnis."""
    e, a = erg["eingaben"], erg["auswertung"]
    auft = erg["aufteilung"]
    eck = [("Startkapital", _eur(erg["start"])), ("Einzahlung je Monat", _eur(e["einzahlung"])),
           ("Entnahme je Monat", _eur(e["entnahme"])), ("Laufzeit", f"{_de(erg['monate'] / 12, 0)} Jahre"),
           ("Zielvermögen", _eur(e["zielvermoegen"]) if e["zielvermoegen"] > 0 else "kein Ziel"),
           ("Aufteilung", " / ".join(f"{KLASSE[k]} {_de(auft[k])} %" for k in ("etf", "aktie", "wikifolio", "cash"))),
           ("Max. Verlust / je Position", f"{_de(e['scan_max_dd'])} % / {_de(e['scan_max_gewicht'], 1)} %"),
           ("Kosten / Inflation p. a.", f"{_de(e['scan_kosten'], 1)} % / {_de(e['scan_inflation'], 1)} %")]
    w = a.get("wahrscheinlichkeit")
    ben = (erg.get("benoetigt") or {}).get("rendite")
    ergebnis = [("Nötige Rendite p. a.", _pct(ben, 1) if ben is not None else "–"),
                ("Erwartete Rendite p. a. (nach Kosten)", _pct(erg["mu"] - e["scan_kosten"], 1, True)),
                ("Wahrscheinlichkeit Ziel", _pct(w * 100, 0) if w is not None else "–"),
                ("Endwert Median", _eur(a["end"][50])),
                ("Endwert schlecht / gut (10 % / 90 %)", f"{_eur(a['end'][10])} / {_eur(a['end'][90])}"),
                ("Max. Rückgang (95 %)", _pct(-a["dd95"], 0))]
    zd = erg.get("ziel_depot")
    if zd and zd["positionen"]:
        ergebnis.append(("Zielrendite-Depot: bisherige Rendite p. a.", _pct(zd["hist_rendite"], 1, True)
                         + (" – Ziel rechnerisch erreicht" if zd["erreicht"] else " – reicht nicht")))
    return eck, ergebnis


def bericht(erg, kapital, profil_titel=""):
    """-> PDF als bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    grund = ParagraphStyle("g", fontName="Helvetica", fontSize=7.4, leading=9)
    fett = ParagraphStyle("f", parent=grund, fontName="Helvetica-Bold")
    rechts = ParagraphStyle("r", parent=grund, alignment=2)
    rechts_fett = ParagraphStyle("rf", parent=rechts, fontName="Helvetica-Bold")
    kopf = ParagraphStyle("k", parent=grund, fontName="Helvetica-Bold", fontSize=6.8, textColor=colors.white)
    kopf_r = ParagraphStyle("kr", parent=kopf, alignment=2)
    titel = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=15, leading=18, spaceAfter=2)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=3)
    klein = ParagraphStyle("kl", fontName="Helvetica", fontSize=7.6, leading=9.6,
                           textColor=colors.HexColor("#4B5563"), spaceAfter=4)
    breite = landscape(A4)[0] - 20 * mm
    anteile = (0.15, 0.055, 0.07, 0.07, 0.07, 0.06, 0.06, 0.105, 0.36)   # wie die Spalten in der App
    spalten = [breite * a for a in anteile]

    def depot_tabelle(zeilen):
        daten = [[Paragraph(_text(k), kopf_r if 1 <= i <= 5 else kopf) for i, k in enumerate(KOPF)]]
        for z in zeilen:
            s = z["typ"] == "summe"
            daten.append([
                Paragraph(_text(z["name"]), fett),
                Paragraph(_pct(z["gewicht"]), rechts_fett if s else rechts),
                Paragraph(_eur(z["betrag"]), rechts_fett if s else rechts),
                Paragraph("" if z["rendite"] is None else _pct(z["rendite"], 1, True), rechts),
                Paragraph(_text(z["grundlage"]), rechts),
                Paragraph(_pct(z["beitrag"], 2, True), rechts_fett if s else rechts),
                Paragraph("" if s else KLASSE.get(z["art"], z["art"]), grund),
                Paragraph(_text(z["kennung"]), grund),
                Paragraph(_text(z["grund"]), grund)])
        t = Table(daten, colWidths=spalten, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F3F4F6")]),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#111827")),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
        return t

    def kv_tabelle(paare):
        t = Table([[Paragraph(_text(k), grund), Paragraph(_text(v), fett)] for k, v in paare],
                  colWidths=[breite * 0.2, breite * 0.28])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                               ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
        return t

    eck, ergebnis = kennzahlen(erg)
    teile = [Paragraph("Investment-Scanner – Ergebnis", titel),
             Paragraph(_text(f"Berechnet am {erg['zeit']} · Profil {profil_titel} · simulierte Verläufe: 10.000"),
                       klein)]
    zwei = Table([[Paragraph("Eckdaten und Regeln", h2), Paragraph("Ergebnis (Simulation)", h2)],
                  [kv_tabelle(eck), kv_tabelle(ergebnis)]], colWidths=[breite / 2, breite / 2])
    zwei.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    teile.append(zwei)

    zd = erg.get("ziel_depot")
    ben = (erg.get("benoetigt") or {}).get("rendite")
    nr = 1
    if zd and zd["positionen"]:
        teile.append(KeepTogether([
            Paragraph("1 · Zielrendite-Musterdepot", h2),
            Paragraph(_text("Ausgewählt nach der bisherigen Rendite, damit das Ziel rechnerisch erreicht wird. "
                            "„Rendite p. a.“ ist hier die bisherige Rendite, keine Prognose – sehr riskant, große "
                            "Verluste möglich."), klein),
            depot_tabelle(S.depot_zeilen(zd, kapital, "historisch", ben))]))
        nr = 2
    d = erg["depot"]
    teile.append(KeepTogether([
        Paragraph(f"{nr} · Musterdepot mit deiner Aufteilung" if nr == 2 else "Musterdepot mit deiner Aufteilung", h2),
        Paragraph(_text("Ausgewählt nach Score; „Rendite p. a.“ = vorsichtige Prognose vor Kosten, „Beitrag“ = "
                        "Gewicht × Rendite."), klein),
        depot_tabelle(S.depot_zeilen(d, kapital))]))     # Ueberschrift nicht allein am Seitenende
    for hw in d.get("hinweise") or []:
        teile.append(Paragraph(_text("Hinweis: " + hw), klein))
    teile += [Spacer(1, 4 * mm), Paragraph(_text(
        "Modellrechnung auf Basis der Top-500-/Watchlist-Daten und vereinfachter Annahmen – keine Anlageberatung "
        "und keine Garantie. Vergangene Renditen sind kein verlässlicher Hinweis auf künftige Ergebnisse."), klein)]

    def fuss(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawRightString(landscape(A4)[0] - 10 * mm, 7 * mm, f"Seite {doc.page}")
        canvas.drawString(10 * mm, 7 * mm, f"Investment-Scanner · {erg['zeit']}")
        canvas.restoreState()

    puffer = io.BytesIO()
    SimpleDocTemplate(puffer, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm,
                      bottomMargin=12 * mm, title="Investment-Scanner – Ergebnis").build(
        teile, onFirstPage=fuss, onLaterPages=fuss)
    return puffer.getvalue()
