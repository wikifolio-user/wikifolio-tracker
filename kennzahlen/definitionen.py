"""Zentrale Kennzahl-Definitionen mit Metadaten.

Jede Kennzahl: Titel, Einheit, Bewertungsbereich, Herkunft, Quelle, Zeitraum, Richtung (hoeher besser?) und
fuer welche Geschaeftsmodelle sie NICHT gilt. Herkunft unterscheidet konsequent:
  gemessen    Marktdaten (Kurs, Volumen)
  primaer     aus dem Jahresabschluss uebernommen
  berechnet   aus Abschlusswerten berechnet (z. B. ROIC, Wachstum p. a.)
  schaetzung  Analystenschaetzung (z. B. erwartetes KGV, Kursziel, Revisionen)
  annahme     Modellannahme (z. B. Diskontsatz, fairer Wert aus DCF)
"""
from dataclasses import dataclass, field

HERKUNFT = ("gemessen", "primaer", "berechnet", "schaetzung", "annahme")
SEKTOR_TYPEN = ("bank", "reit", "versorger", "zyklisch", "standard")


@dataclass(frozen=True)
class Kennzahl:
    titel: str
    einheit: str                    # "%", "x", "Jahre", "EUR", "Punkte", ""
    bereich: str                    # Qualitaet, Wachstum, Cashflow, Bilanz, Management, Burggraben, Bewertung, Risiko ...
    herkunft: str
    quelle: str                     # "yfinance", "ls-tc", "SEC", "Modell"
    zeitraum: str                   # "letztes GJ", "Ø Historie", "p. a. Historie", "aktuell", "12 Monate" ...
    hoeher_besser: bool = True
    nicht_fuer: tuple = field(default_factory=tuple)   # Sektor-Typen, fuer die die Kennzahl nicht aussagekraeftig ist
    hinweis: str = ""


K = Kennzahl
REGISTER = {
    # --- Qualitaets-Agent (state/qualitaet/alle_N.json) ---
    "g_ums": K("Umsatzwachstum p. a.", "%", "Wachstum", "berechnet", "yfinance", "p. a. Historie"),
    "g_eps": K("Gewinnwachstum je Aktie p. a.", "%", "Wachstum", "berechnet", "yfinance", "p. a. Historie"),
    "g_fcf": K("FCF-Wachstum p. a.", "%", "Cashflow", "berechnet", "yfinance", "p. a. Historie", nicht_fuer=("bank",)),
    "g_fcfps": K("FCF je Aktie Wachstum p. a.", "%", "Cashflow", "berechnet", "yfinance", "p. a. Historie",
                 nicht_fuer=("bank",)),
    "roic": K("Rendite auf das investierte Kapital (Ø)", "%", "Qualitaet", "berechnet", "yfinance", "Ø Historie",
              nicht_fuer=("bank",), hinweis="Steuersatz pauschal, wenn keine Steuerquote vorliegt"),
    "om": K("Operative Marge (Ø)", "%", "Qualitaet", "berechnet", "yfinance", "Ø Historie", nicht_fuer=("bank",)),
    "fm": K("FCF-Marge (Ø)", "%", "Cashflow", "berechnet", "yfinance", "Ø Historie", nicht_fuer=("bank",)),
    "nde": K("Nettoverschuldung / EBITDA", "x", "Bilanz", "berechnet", "yfinance", "letztes GJ", hoeher_besser=False,
             nicht_fuer=("bank", "reit")),
    "akt": K("Veraenderung der Aktienanzahl p. a.", "%", "Management", "berechnet", "yfinance", "p. a. Historie",
             hoeher_besser=False),
    "fkgv": K("Erwartetes KGV", "x", "Bewertung", "schaetzung", "yfinance", "12 Monate voraus", hoeher_besser=False,
              nicht_fuer=("reit",)),
    "ev_ebit": K("EV / EBIT", "x", "Bewertung", "berechnet", "yfinance", "letztes GJ", hoeher_besser=False,
                 nicht_fuer=("bank",)),
    "fcfy": K("FCF-Rendite", "%", "Bewertung", "berechnet", "yfinance", "letztes GJ", nicht_fuer=("bank",)),
    "mos": K("Sicherheitsmarge zum fairen Wert (DCF)", "%", "Bewertung", "annahme", "Modell", "aktuell",
             hinweis="Basisszenario-DCF des Qualitaets-Agenten"),
    "div": K("Dividendenrendite", "%", "Dividende", "berechnet", "yfinance", "12 Monate"),
    "div_q": K("Ausschuettungsquote", "%", "Dividende", "berechnet", "yfinance", "letztes GJ", hoeher_besser=False),
    "mcap": K("Boersenwert", "Mrd. EUR", "Groesse", "gemessen", "yfinance", "aktuell"),
    "kurs": K("Kurs", "", "Markt", "gemessen", "yfinance", "aktuell"),
    "p6": K("Kursentwicklung 6 Monate", "%", "Momentum", "gemessen", "yfinance", "6 Monate"),
    "p12": K("Kursentwicklung 12 Monate", "%", "Momentum", "gemessen", "yfinance", "12 Monate"),
    "rev90": K("Gewinnrevisionen 90 Tage", "%", "Wachstum", "schaetzung", "yfinance", "90 Tage"),
    "gesamt": K("Qualitaets-Score", "Punkte", "Gesamt", "berechnet", "Modell", "aktuell"),
    # --- Investoren-Checks (state/investoren/ergebnis_NN.json) ---
    "inv_score": K("Legenden-Konsens", "Punkte", "Investoren", "berechnet", "Modell", "aktuell"),
    "fv": K("Fairer Wert gegenueber Kurs (Median der Modelle)", "%", "Bewertung", "annahme", "Modell", "aktuell",
            hinweis="enthaelt das Analysten-Kursziel (Schaetzung) als eines der Modelle"),
    # --- ETF (Katalog / klassen_score) ---
    "etf_rendite": K("Rendite p. a. (laengster Zeitraum)", "%", "Rendite", "gemessen", "ls-tc", "bis 10 Jahre"),
    "etf_vola": K("Schwankung p. a.", "%", "Risiko", "gemessen", "ls-tc", "1 Jahr", hoeher_besser=False),
    "etf_dd": K("Groesster Rueckgang", "%", "Risiko", "gemessen", "ls-tc", "Historie"),
    "etf_jahre": K("Kurshistorie", "Jahre", "Historie", "gemessen", "ls-tc", "Historie"),
}


def meta(schluessel):
    """Kennzahl-Definition oder None."""
    return REGISTER.get(schluessel)


def anwendbar(schluessel, sektor_typ):
    """Gilt die Kennzahl fuer diesen Sektor-Typ? Unbekannte Kennzahlen gelten (keine stille Sperre)."""
    m = REGISTER.get(schluessel)
    return m is None or sektor_typ not in m.nicht_fuer


def mit_meta(schluessel, wert, stand=None, sektor_typ="standard", warnungen=()):
    """Wert mit allen Metadaten - fuer Erklaerungen und das Datenvertrauen."""
    m = REGISTER.get(schluessel)
    return {"schluessel": schluessel, "wert": wert, "fehlt": wert is None,
            "titel": m.titel if m else schluessel, "einheit": m.einheit if m else "",
            "bereich": m.bereich if m else "", "herkunft": m.herkunft if m else "berechnet",
            "quelle": m.quelle if m else "", "zeitraum": m.zeitraum if m else "", "stand": stand,
            "anwendbar": anwendbar(schluessel, sektor_typ), "warnungen": list(warnungen),
            "hinweis": m.hinweis if m else ""}
