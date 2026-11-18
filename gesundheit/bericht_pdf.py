"""PDF-Bericht Gesundheit (A4 hoch, druckfreundlich): Kurzbericht oder Detailbericht fuer einen Zeitraum.

Gleiche Technik wie depot_analyse_pdf.py (reportlab, Standardschrift). Diagramme als Vektorgrafik (reportlab
graphics), damit nichts weiter installiert werden muss. Nur dokumentierte Werte und rechnerische Vergleiche.
"""
import html

from . import mikro as MI
from . import naehrstoffe as N
from . import referenz as F
from . import statistik as ST

_ERSATZ = {"−": "-", "→": "->", "≈": "ca.", "≥": ">=", "≤": "<=", "×": "x", "•": "-", "„": '"', "“": '"',
           "✓": "", "⚠": "", "️": "", "≙": "=", "Ø": "Durchschnitt"}
HINWEIS = ("Alle Werte sind rechnerische Schätzungen auf Basis der dokumentierten Einträge. Sie ersetzen keine "
           "medizinische oder ernährungsmedizinische Beratung.")


def _t(text):
    s = str(text if text is not None else "")
    for a, b in _ERSATZ.items():
        s = s.replace(a, b)
    return html.escape(s.encode("cp1252", "ignore").decode("cp1252"))


def _z(x, stellen=0, leer="–"):
    return leer if x is None else ST._z(x, stellen)


def _linie(punkte, breite, hoehe, farbe="#1D4ED8", ziel=None):
    """Einfaches Liniendiagramm [(x_index, wert)] -> Drawing."""
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    d = Drawing(breite, hoehe)
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 30, 18, breite - 40, hoehe - 28
    daten = [punkte]
    if ziel:
        daten.append([(punkte[0][0], ziel), (punkte[-1][0], ziel)])
    lp.data = daten
    lp.lines[0].strokeColor = colors.HexColor(farbe)
    lp.lines[0].strokeWidth = 1.6
    if ziel:
        lp.lines[1].strokeColor = colors.HexColor("#0F766E")
        lp.lines[1].strokeDashArray = [3, 2]
    werte = [w for _, w in punkte] + ([ziel] if ziel else [])
    spanne = (max(werte) - min(werte)) or 1
    lp.yValueAxis.valueMin = min(werte) - spanne * 0.1
    lp.yValueAxis.valueMax = max(werte) + spanne * 0.1
    lp.yValueAxis.labels.fontSize = 6
    lp.xValueAxis.labels.fontSize = 6
    lp.xValueAxis.visible = False
    d.add(lp)
    return d


def bericht(r, doc, ziele, titel, von, bis, detail=False, alter=40):
    """r: Tageswerte (statistik.reihe); ziele: rechnen.ziele(). -> PDF als bytes"""
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    grund = ParagraphStyle("g", fontName="Helvetica", fontSize=8.5, leading=11)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=18, spaceAfter=2,
                        textColor=colors.HexColor("#0B1220"))
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, spaceBefore=8, spaceAfter=4,
                        textColor=colors.HexColor("#1D4ED8"))
    klein = ParagraphStyle("k", parent=grund, fontSize=7.2, leading=9, textColor=colors.HexColor("#4B5563"))
    kopf = ParagraphStyle("kp", parent=grund, fontName="Helvetica-Bold", fontSize=7.6, textColor=colors.white)
    breite = A4[0] - 24 * mm

    def tabelle(zeilen, breiten):
        daten = [[Paragraph(_t(c), kopf if i == 0 else grund) for c in z] for i, z in enumerate(zeilen)]
        t = Table(daten, colWidths=breiten, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                               ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return t

    z = ST.zusammenfassung(r)
    teile = [Paragraph(_t(titel), h1),
             Paragraph(_t(f"Zeitraum {von.strftime('%d.%m.%Y')} – {bis.strftime('%d.%m.%Y')} · "
                          f"{'Detailbericht' if detail else 'Kurzbericht'}"), klein), Spacer(1, 6),
             Paragraph("Zusammenfassung", h2)]
    teile += [Paragraph(_t("- " + s), grund) for s in ST.aussagen(z, "im Zeitraum")]
    teile.append(Paragraph("Durchschnitt je dokumentiertem Tag", h2))
    zeilen = [["Wert", "Durchschnitt", "Ziel", "Anteil"]]
    for k, name, einheit, stellen in (("kcal", "Kalorien", "kcal", 0), ("protein", "Protein", "g", 0),
                                      ("kh", "Kohlenhydrate", "g", 0), ("fett", "Fett", "g", 0)):
        anteil = z[k] / ziele[k] * 100 if z[k] is not None and ziele.get(k) else None
        zeilen.append([name, f"{_z(z[k], stellen)} {einheit}", f"{_z(ziele.get(k))} {einheit}", f"{_z(anteil)} %"])
    wasser = z["fluessigkeit_ml"]
    zeilen.append(["Getrunken", f"{_z(None if wasser is None else wasser / 1000, 1)} L",
                   f"{_z((ziele.get('wasser_ml') or 0) / 1000, 1)} L",
                   f"{_z(wasser / ziele['wasser_ml'] * 100 if wasser and ziele.get('wasser_ml') else None)} %"])
    zeilen.append(["Sport", f"{_z(z['sport_min'])} min an {z['sport_tage']} Tagen", "", f"{_z(z['sport_kcal'])} kcal"])
    if z["gewicht_start"] is not None:
        zeilen.append(["Gewicht", f"{_z(z['gewicht_start'], 1)} -> {_z(z['gewicht_ende'], 1)} kg", "",
                       f"{_z(z['gewicht_diff'], 1, '0')} kg"])
    if z["supp_treue"] is not None:
        zeilen.append(["Supplements", "eingenommen laut Plan", "", f"{_z(z['supp_treue'])} %"])
    if z["fasten_anzahl"]:
        zeilen.append(["Fasten", f"{z['fasten_anzahl']} Fastenzeiten", "",
                       f"Durchschnitt {_z(z['fasten_schnitt'], 1)} h"])
    teile.append(tabelle(zeilen, [breite * 0.25, breite * 0.35, breite * 0.2, breite * 0.2]))

    if detail:
        gew = [(i, x["gewicht"]) for i, x in enumerate(r) if x["gewicht"]]
        if len(gew) >= 2:
            teile += [Paragraph("Gewicht", h2), _linie(gew, breite, 120, ziel=(doc.get("profil") or {}).get("zielgewicht_kg"))]
        kcal = [(i, x["kcal"]) for i, x in enumerate(r) if x["erfasst"]]
        if len(kcal) >= 2:
            teile += [Paragraph("Kalorien je Tag", h2), _linie(kcal, breite, 120, "#7C3AED", ziel=ziele.get("kcal"))]
        tage = [x["_tag"] for x in r if x["erfasst"]]
        if tage:
            teile.append(Paragraph("Vitamine und Mineralstoffe (Durchschnitt je dokumentiertem Tag)", h2))
            zeilen = [["Nährstoff", "Durchschnitt", "Referenz", "Anteil"]]
            for n in N.MIKRO:
                mw, _ = MI.durchschnitt(tage, n)
                ref = F.suchen(n, (doc.get("profil") or {}).get("geschlecht", "x"), alter)
                if not mw and not ref:
                    continue
                e = N.NAEHRSTOFFE[n].einheit
                zeilen.append([N.NAEHRSTOFFE[n].name, f"{_z(mw, 1)} {e}", f"{_z(ref.ziel, 1)} {e}" if ref else "–",
                               f"{_z(MI.abdeckung(mw or 0, ref.ziel))} %" if ref else "–"])
            teile.append(tabelle(zeilen, [breite * 0.4, breite * 0.22, breite * 0.22, breite * 0.16]))
            teile.append(Paragraph(_t(f"Referenzwerte: {F.QUELLE_ZIEL} (Stand {F.VERSION}). Fehlende Nährstoffwerte "
                                      "einzelner Lebensmittel zählen nicht als 0 – die Summen sind dann eher zu niedrig."),
                                   klein))
        teile.append(Paragraph("Tageswerte", h2))
        zeilen = [["Datum", "kcal", "Protein", "Getrunken", "Sport", "Gewicht", "Suppl.", "Fasten"]]
        for x in r:
            if not (x["erfasst"] or x["gewicht"] or x["sport_min"] or x["supp_ein"] or x["fasten_h"]):
                continue
            zeilen.append([x["datum"].strftime("%d.%m.%Y"), _z(x["kcal"]) if x["erfasst"] else "–",
                           f"{_z(x['protein'])} g" if x["erfasst"] else "–", f"{_z(x['fluessigkeit_ml'])} ml",
                           f"{_z(x['sport_min'])} min" if x["sport_min"] else "", f"{_z(x['gewicht'], 1)} kg" if x["gewicht"] else "",
                           f"{x['supp_ein']}/{x['supp_geplant']}" if x["supp_geplant"] or x["supp_ein"] else "",
                           f"{_z(x['fasten_h'], 1)} h" if x["fasten_h"] is not None else ""])
        teile.append(tabelle(zeilen, [breite * w for w in (0.15, 0.1, 0.12, 0.14, 0.12, 0.13, 0.1, 0.14)]))
    teile += [Spacer(1, 8), Paragraph(_t(HINWEIS), klein)]
    puffer = io.BytesIO()
    SimpleDocTemplate(puffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                      bottomMargin=12 * mm, title=_t(titel)).build(teile)
    return puffer.getvalue()
