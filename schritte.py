"""Schritt-fuer-Schritt-Fuehrung: Schrittleiste oben in einer Ansicht und nummerierte Abschnittstitel.

Jede Ansicht beschreibt ihre Schritte einmal (FUEHRUNG[schluessel]); oben steht die Leiste mit allen
Schritten (Klick springt zum Abschnitt), an den Abschnitten selbst die passende Nummer mit kurzem Hinweis,
was dort zu tun ist. Reines HTML/CSS - keine Logik, keine Daten. Aussehen: ui_stil (CSS_NAV, "SCHRITTE").
"""
import html

# schluessel -> [(kurztitel, was ist zu tun), ...] - Reihenfolge = Bedienreihenfolge
FUEHRUNG = {
    "depot": [
        ("Überblick", "Gesamtwert, Gewinn seit Kauf und die Zeiträume oben prüfen"),
        ("Positionen", "Einen Wert aufklappen, um Kurs, Stückzahl und Ergebnis zu sehen"),
        ("Kurse", "Einen Wert in der Auswahl wählen und seine Entwicklung ansehen"),
        ("Weitere Infos", "Meilenstein, Anfangskapital, Entnahmen und Kosten nachlesen"),
    ],
    "verwalten": [
        ("Sparrate & Entnahme", "Monatliche Sparrate und Entnahme eintragen"),
        ("Beobachtungsliste", "Werte für die Kurs-Ansicht hinzufügen oder entfernen"),
        ("Positionen", "Käufe erfassen, ändern oder löschen"),
        ("System", "Status und Diagnose bei Problemen prüfen"),
    ],
    "vergleich": [
        ("Vergleichswerte", "Indizes oder Werte auswählen, mit denen verglichen wird"),
        ("Vergleichsart", "Kennzahl wählen (Ø/Jahr, Gesamt, Monate oder €) und die Tabelle vergleichen"),
        ("Chart lesen", "Verlauf des Depots und der Vergleichswerte ansehen"),
    ],
    "candle": [
        ("Kerzen lesen", "Grün = Tag im Plus, Rot = im Minus; die Striche zeigen Tageshoch und -tief"),
        ("Zoomen", "Im Chart einen Bereich aufziehen; Doppelklick zeigt wieder alles"),
    ],
    "prognose": [
        ("Prognose-Basis", "Wert oder Index wählen, dessen Rendite als Grundlage dient"),
        ("Rendite", "Angenommene Rendite p. a. prüfen oder anpassen"),
        ("Tabelle", "Erwarteten Depotwert je Jahr ablesen"),
        ("Bandbreite", "Zeitraum wählen und mögliche gute/schlechte Verläufe ansehen"),
    ],
    "szenario": [
        ("Wert wählen", "Standard-Szenarien oder einen eigenen Wert als Grundlage wählen"),
        ("Beträge", "Startkapital, Entnahme und Sparrate eintragen; bei einem Wert auch die Rendite"),
        ("Ergebnis", "Endwerte je Szenario und den Verlauf über 5 Jahre ablesen"),
    ],
    "builder": [
        ("Kapital", "Anfangskapital, Einzahlung, Entnahme, Rendite und Laufzeit eingeben"),
        ("Werte", "Aktien, ETFs oder wikifolios suchen und hinzufügen"),
        ("Aufteilung", "Gewichte anpassen, bis die Summe 100 % ergibt"),
        ("Ergebnis", "Verteilung, Vermögensentwicklung und Bewertung prüfen"),
    ],
    "bewertung": [
        ("Suchen", "Name, Ticker, WKN oder ISIN eingeben und den Wert aus der Trefferliste wählen"),
        ("Gesamtscore", "Kopfdaten, Gesamtscore mit Ampel und das Kurzfazit lesen"),
        ("Teilscores", "Teilbereiche, Netzdiagramm sowie Stärken und Schwächen ansehen"),
        ("Kennzahlen", "Jede Kennzahl mit Einordnung, Median-Vergleich und Perzentil-Rang prüfen"),
        ("Investoren-Checks", "Prüfen, welche Investoren-Legenden die Aktie kaufen würden – und warum"),
    ],
    "scanner": [
        ("Eckdaten", "Startkapital, Einzahlung, Entnahme, Laufzeit und Zielvermögen eingeben"),
        ("Risiko & Regeln", "Risikobereitschaft, Aufteilung je Anlageklasse und Grenzen festlegen"),
        ("Scannen", "„Scannen & Musterdepot berechnen“ drücken"),
        ("Ergebnis", "Musterdepot, Prognose und Risiken in den Reitern prüfen und übernehmen"),
    ],
    "scanner_pro": [
        ("Bestand", "Optional ein vorhandenes Depot als CSV importieren"),
        ("Eingaben", "Kapital, Ziel, Ein- und Auszahlungen sowie Regeln eintragen, dann berechnen"),
        ("Kaufplan", "Echte Kurse abrufen und den Kaufplan in Stück prüfen oder herunterladen"),
        ("Entnahmen & Ziel", "Entnahmen, alternative Anlagevermögen und Zielerreichung ansehen"),
    ],
    "scanner2": [
        ("Kapital & Ziel", "Anfangskapital, Zielwert, Anlagezeit und Sparrate eingeben"),
        ("Anlageklassen", "Anlageklassen für neue Käufe, Scan-Limit und Sortierung wählen"),
        ("Daten & Depot", "Optional eigene Wertpapiere oder ein Depot als CSV importieren"),
        ("Entnahmen", "Sofort- und Monatsauszahlungen festlegen"),
        ("Ergebnis & Strategie", "Ergebnis prüfen und eine der drei Strategien mit „Wählen“ übernehmen"),
        ("Kaufplan", "Kurse laden und den Kaufplan prüfen oder als CSV herunterladen"),
    ],
    "watchlist": [
        ("Liste wählen", "Gesamtübersicht, Qualitäts-Score, Performance oder eine andere Rangliste wählen"),
        ("Rangliste lesen", "Filter und Umfang bei Bedarf anpassen, dann die Werte vergleichen"),
    ],
    "analyse": [
        ("Depot wählen", "Mein Depot oder das selbst erfasste Analyse-Depot wählen"),
        ("Bereich wählen", "Übersicht, Positionen, Simulator, Szenarien, Assistent oder Daten & Profil"),
        ("Auswerten", "Ergebnisse, Hinweise und Empfehlungen im gewählten Bereich prüfen"),
    ],
    "analyse_depot": [
        ("Wert hinzufügen", "Wert per Name, WKN oder ISIN suchen und mit Stückzahl übernehmen"),
        ("Positionen prüfen", "Stückzahlen und Kaufkurse in der Tabelle kontrollieren oder ändern"),
        ("Mehrere auf einmal", "Optional per Schnelleingabe oder CSV-/Excel-Import erfassen"),
        ("Sparplan & Entnahme", "Monatliche Sparrate und Entnahme eintragen; danach in der Depot-Analyse auswerten"),
    ],
    "chronik": [
        ("Filter", "Alle Einträge oder nur eine Kategorie (z. B. Alarme, Depot) anzeigen"),
        ("Einträge lesen", "Die neuesten Ereignisse stehen oben, nach Tagen gruppiert"),
        ("Notiz", "Eine eigene Notiz mit Datum, Titel und Details speichern"),
    ],
    "abfindung": [
        ("Person", "Alter, Kinder, Schwerbehinderung und Rentennähe angeben"),
        ("Beschäftigung", "Beginn, Ende, Kündigungsfrist und Monatsverdienst eintragen"),
        ("Beendigung", "Art der Beendigung und Begleitumstände wählen"),
        ("Angebot", "Optional angebotene Abfindung eintragen; das Ergebnis steht oben"),
    ],
    "abfindung_netto": [
        ("Abfindung", "Bruttobetrag und Auszahlungsjahr eintragen"),
        ("Einkommen", "Jahresbrutto und zu versteuerndes Einkommen ohne Abfindung"),
        ("Steuer", "Veranlagung, Kirchensteuer und Fünftelregelung"),
        ("Optional", "Nur bei Bedarf: Arbeitslosengeld, Kosten, Rente, bAV, Gestaltungen"),
        ("Ergebnis", "Netto, Steuer und Vergleich der Auszahlungsjahre ablesen"),
    ],
    "zins": [
        ("Was berechnen?", "Wählen, welche Größe ermittelt wird (z. B. Endkapital oder Zinssatz)"),
        ("Kapital & Sparrate", "Startbetrag, Sparrate, Intervall und Dynamik eingeben"),
        ("Verzinsung", "Zinssatz, Gutschrift und optional Steuer festlegen"),
        ("Laufzeit", "Startdatum, Ansparzeit und Ruhezeit festlegen"),
        ("Pläne (optional)", "Sparrate oder Entnahme je Zeitraum unterschiedlich planen"),
        ("Ergebnis", "Endkapital, Entwicklung und Tabelle ablesen"),
    ],
    "benutzer": [
        ("Anlegen", "Neuen Benutzer mit Passwort anlegen"),
        ("Rechte", "Benutzer aufklappen, Ansichten freigeben und „💾 Rechte speichern“ tippen"),
    ],
}


def _anker(schluessel, nr):
    return f"sf-{schluessel}-{nr}"


def leiste_html(schluessel, aktiv=None, spaeter=()):
    """Schrittleiste: alle Schritte der Ansicht als nummerierte Kapseln (Klick springt zum Abschnitt).
    aktiv = Schrittnummern, die auf der Seite gerade vorkommen (Rest ausgeblendet, Anzeige fortlaufend);
    spaeter = Schritte, die erst nach einer Aktion erscheinen (z. B. Ergebnis nach "Berechnen") - gedimmt, ohne Sprung."""
    schritte = FUEHRUNG.get(schluessel)
    if not schritte:
        return ""
    teile = []
    for nr, (kurz, was) in enumerate(schritte, 1):
        if aktiv is not None and nr not in aktiv:
            continue
        zeige = len(teile) + 1
        if nr in spaeter:
            teile.append(f'<span class="sf-s sf-spaeter" title="{html.escape(was)} – erscheint nach dem Berechnen">'
                         f'<b>{zeige}</b><span>{html.escape(kurz)}</span></span>')
            continue
        teile.append(f'<a class="sf-s" href="#{_anker(schluessel, nr)}" target="_self" title="{html.escape(was)}">'
                     f'<b>{zeige}</b><span>{html.escape(kurz)}</span></a>')
    return (f'<nav class="sf-leiste" aria-label="Schritte">'
            f'<span class="sf-kopf">So gehst du vor</span>{"".join(teile)}</nav>')


def titel_html(schluessel, nr, titel=None):
    """Nummerierter Abschnittstitel mit Hinweis, was in diesem Schritt zu tun ist."""
    schritte = FUEHRUNG.get(schluessel) or []
    if not 1 <= nr <= len(schritte):
        return ""
    kurz, was = schritte[nr - 1]
    return (f'<div class="sf-titel" id="{_anker(schluessel, nr)}"><b class="sf-nr">{nr}</b>'
            f'<div><div class="sf-name">{html.escape(titel or kurz)}</div>'
            f'<div class="sf-was">{html.escape(was)}</div></div></div>')


def leiste(st, schluessel, aktiv=None, spaeter=()):
    h = leiste_html(schluessel, aktiv, spaeter)
    if h:
        st.markdown(h, unsafe_allow_html=True)


def titel(st, schluessel, nr, titel=None):
    h = titel_html(schluessel, nr, titel)
    if h:
        st.markdown(h, unsafe_allow_html=True)


def nummer_html(schluessel, nr, sichtbar=None):
    """Kleine leuchtende Nummer fuer vorhandene Abschnittsueberschriften (Sprungziel der Leiste);
    sichtbar = angezeigte Nummer, wenn Schritte ausgeblendet sind (siehe leiste_html(..., aktiv))."""
    schritte = FUEHRUNG.get(schluessel) or []
    if not 1 <= nr <= len(schritte):
        return ""
    return (f'<b class="sf-nr sf-klein" id="{_anker(schluessel, nr)}" '
            f'title="{html.escape(schritte[nr - 1][1])}">{sichtbar or nr}</b>')
