# UX-Durchgang Finanz Dashboard

**Stand:** 18.10.2026 · **Basis:** `main` nach PR #1/#2 · **Umfang:** alle 14 Ansichten, 6 Geräteklassen, 4 Benutzergruppen, Tastaturbedienung

## Kurzfassung

Die App lief vorher auf keinem Gerät seitlich über und ist grundsätzlich mobil nutzbar. Der Durchgang fand aber:

- **zwei Abstürze**, die ganze Bereiche unbenutzbar machten: den Abfindungsrechner für jeden normalen Benutzer und die Benutzerverwaltung bei einem Benutzernamen „neu“;
- **abgeschnittene Zahlen und Beschriftungen auf dem Handy**, darunter die Kernwerte im Abfindungsrechner („4.00…“, „22.0…“) und in der Prognose („Wahrscheinlichkeit …“);
- **eine ungünstige Gewichtung im Depot**: Die eigene Depotsumme kam erst nach der kompletten Kurskachel. Auf Laptop und Desktop liefen alle Kacheln über die volle Bildschirmbreite;
- **Bedienelemente unter 44 px**, englische Platzhalter und Datumsformate, Fachjargon („Instrument-ID“), Kontrast- und Tastaturmängel.

Alle unten als *behoben* markierten Punkte sind umgesetzt und im abschließenden Messlauf über alle Geräte nachgeprüft.

## Vorgehen

| Baustein | Umsetzung |
|---|---|
| Geräte | iPhone SE (375×667), iPhone Pro Max (430×932), iPad hoch (768×1024), iPad quer (1024×768), Laptop (1440×900), Desktop (1920×1080); Touch-Emulation für Telefon und Tablet |
| Benutzergruppen | Admin (volles Depot, alle Ansichten), normale Benutzerin mit eigenem Depot und Sparplan, neuer Benutzer ohne Daten, eingeschränkter Benutzer (3 Ansichten) |
| Daten | Sandbox mit synthetischen Kursen und Depots; Watchlist/Qualitäts-Score mit den echten, öffentlichen Ranglisten aus dem State-Branch |
| Messung je Ansicht | seitlicher Überlauf, Elemente außerhalb des Bildschirms, abgeschnittene Texte, Touch-Ziele < 44 px, Schrift < 12 px, axe-core 4.10 (WCAG 2 A/AA), Konsolen- und App-Fehler, Ladezeit, Screenshot der ganzen Seite |
| Sichtprüfung | Screenshots aller Ansichten auf iPhone SE, iPad und Laptop gesichtet (Hierarchie, Verständlichkeit, Dichte) |
| Tastatur | Anmeldung, Menü, Ansicht öffnen und zurück nur mit Tab/Enter, Fokusrahmen geprüft |

Insgesamt 282 Ansichten je Messlauf (47 je Gerät). Skripte: `audit/harness/ux_mess.py`, `ux_tastatur.py`, `ux_spalten.py`; Start der Sandbox mit `AUDIT_SEED=seed_ux` (Marktdaten unter `../markt/state`, axe-core unter `../axe/package`). Vorher/Nachher-Bilder: `audit/belege/ux/`.

## Messergebnis vorher → nachher

| Gerät | Ansichten | Abstürze | Seitl. Überlauf | axe-Verstöße | Abgeschnittene Texte | Touch-Ziele < 44 px | Schrift < 12 px |
|---|---|---|---|---|---|---|---|
| iPhone SE | 47 | 4 → **0** | 0 → **0** | 4 → **0** | 38 → **10** | 1144 → **515** | 270 → **0** |
| iPhone Pro Max | 47 | 4 → **0** | 0 → **0** | 4 → **0** | 18 → **7** | 1149 → **515** | 270 → **0** |
| iPad hoch | 47 | 4 → **0** | 0 → **0** | 11 → **0** | 6 → **4** | 1148 → **518** | 330 → **0** |
| iPad quer | 47 | 4 → **0** | 0 → **0** | 4 → **0** | 6 → **4** | 1148 → **518** | 330 → **0** |
| Laptop | 47 | 4 → **0** | 0 → **0** | 4 → **0** | 6 → **4** | 0 → **0** | 330 → **0** |
| Desktop | 47 | 4 → **0** | 0 → **0** | 4 → **0** | 7 → **4** | 0 → **0** | 330 → **0** |

Abstürze: Ansichten mit Fehlermeldung statt Inhalt (je Gerät 1 × Benutzerverwaltung, 3 × Abfindungsrechner). Längste Ladezeit einer Ansicht im Endlauf: 2,2 s.

Verbleibende „abgeschnittene“ Texte sind gewollt: der nur als Symbol gezeigte Knopf „Abmelden“ (Text für Screenreader), lange Firmennamen in der Watchlist-Tabelle und auf dem Handy der Aufklapp-Titel „📅 Wochenveränderung“ neben dem Pfeil.

*Touch-Ziele werden nur auf Touch-Geräten gezählt. Die verbleibenden Werte stammen überwiegend aus Streamlit-internen Elementen, die die App nicht steuert (siehe „Offen“).*

## Befunde

Schweregrad: **hoch** = Bereich unbenutzbar oder Kernzahlen nicht lesbar · **mittel** = deutlich erschwerte Bedienung · **niedrig** = Komfort/Konsistenz.

| ID | Befund | Geräte / Gruppe | Schwere | Status |
|---|---|---|---|---|
| UX-01 | Abfindungsrechner stürzt für jeden normalen Benutzer ab („value 0 is less than min_value 15“ beim Alter) | alle / normale Benutzer | hoch | **behoben**: Feld leer statt 0, ungültige gemerkte Werte werden geleert |
| UX-02 | Benutzerverwaltung stürzt ab, sobald ein Benutzer „neu“ heißt (doppelter Element-Schlüssel `rechte_neu`) | alle / Admin | hoch | **behoben** + Test `test_login.EindeutigeSchluessel` |
| UX-03 | Kennzahl-Werte und -Beschriftungen abgeschnitten („4.00…“, „11 J. …“, „Mittleres Ergebnis (Me…“) | iPhone, iPad | hoch | **behoben**: Umbruch statt „…“, Wertgröße passt sich der Breite an |
| UX-04 | Schalter-/Feldbeschriftungen und Knopftexte enden mit „…“ (u. a. „Betriebsbedingte AG-Kündigung droht…“) | iPhone, iPad | mittel | **behoben** |
| UX-05 | Ansichtstitel in der Kopfleiste abgeschnitten („Performance seit 01.01.2…“) | iPhone | niedrig | **behoben**: bricht zweizeilig um |
| UX-06 | Depot: eigene Depotsumme erst nach der elfzeiligen Kurskachel; Umschalter „Hauptindizes / Nasdaq / Gold“ ohne Beschriftung | alle | mittel | **behoben**: Depot zuerst, Abschnitt „📈 Kurse“ mit „Kurs anzeigen für“ |
| UX-07 | Laptop/Desktop/iPad quer: Kacheln über die volle Breite, Beschriftung und Wert bis ~1.300 px auseinander | ≥ 1024 px | mittel | **behoben**: Depot und Kurse ab 820 px in zwei Spalten, darunter untereinander |
| UX-08 | Kopfleisten-Knöpfe (38 px), Auswahl-Pillen (34 px), Abmelden (30 px), „Kurse aktualisieren“ (32 px) unter 44 px | Touch | mittel | **behoben**: 44 px auf Touch-Geräten |
| UX-09 | Plotly-Werkzeugleiste mit 22-px-Symbolen auf dem Handy | Touch | niedrig | **behoben**: auf Touch ausgeblendet (Zoomen per Geste bleibt) |
| UX-10 | Watchlist: rund 30 Pillen (12 Kategorien, 15 Kennzahlen) vor dem ersten Inhalt – mehr als eine Bildschirmhöhe | iPhone | mittel | **behoben**: ab 7 Optionen Auswahlfeld (Kategorie, Index, Kennzahl, Feld) |
| UX-11 | Neuer Benutzer sieht zuerst die Kurskachel des Admin-Zertifikats, erst darunter „Noch kein eigenes Depot“ | neue Benutzer | mittel | **behoben** (durch UX-06) |
| UX-12 | Fachjargon „Instrument-ID (ls-tc.de)“ in Formularen und Meldungen | normale Benutzer | niedrig | **behoben**: „Kursquelle-ID (wird über die Suche gesetzt)“ |
| UX-13 | Datumsfelder im Format `2026/10/18`, englischer Platzhalter „Choose options“ | alle | niedrig | **behoben**: TT.MM.JJJJ, deutsche Platzhalter |
| UX-14 | Prozente in Tabellen mit Dezimalpunkt („+19.13%“) | alle | niedrig | **behoben**: „+19,13 %“ |
| UX-15 | Kontrast: Chronik-Kopfzeilen (#71717A) und Szenario-Jahreslabels (10,4 px) unter 4,5:1 | alle | mittel | **behoben** |
| UX-16 | Seitlich scrollbare Vergleichstabellen per Tastatur nicht erreichbar; Permanentlink im Zinsrechner nur seitlich scrollbar | Tastatur | mittel | **behoben**: Tabellen fokussierbar, Link bricht um |
| UX-17 | Schrift unter 12 px (Menügruppen 11,2 px, Tabellenköpfe 10,2 px, Planer-Hinweise 11,5 px, Diagrammachsen 11 px) | alle | niedrig | **behoben**: Untergrenze 0,8 rem (≈ 12,8 px), weil Streamlit Markdown teils auf 96 % verkleinert; Diagrammschrift 12 px |
| UX-18 | Eingabefelder 42 px hoch, Positions-Reiter 40 px, 🔄 in der Kopfleiste 37 px breit | Touch | niedrig | **behoben**: 44 px auf Touch-Geräten |
| UX-19 | Entwicklungstabelle im Zinsrechner scrollt auf dem Handy seitlich, ist aber per Tastatur nicht erreichbar (axe „scrollable-region-focusable“) | iPhone / Tastatur | mittel | **behoben**: fokussierbarer Scroll-Rahmen |
| UX-20 | Portfolio-Planer öffnet auf dem Handy in „Alle Bereiche“: Rahmenangaben und Bausteine untereinander, 9.400 px Seite | iPhone | mittel | **behoben**: auf dem Smartphone Start im geführten Ablauf „Schritt für Schritt“ (2.500 px), umschaltbar |
| UX-21 | Planer-Katalog (72 Werte) in voller Höhe, rund 3.500 px nur für die Tabelle | iPhone | mittel | **behoben**: auf dem Smartphone höchstens 15 Zeilen, der Rest scrollt in der Tabelle |
| UX-22 | Fortschrittsanzeige im geführten Planer: falsche ARIA-Rollen (axe „aria-required-children“, „aria-prohibited-attr“), Schrittnamen auf dem Handy abgeschnitten, Status nur als Farbe/Symbol | iPhone / Screenreader | mittel | **behoben**: Liste mit Status-Text für Screenreader, Fortschrittsbalken als `progressbar`; auf dem Handy nur der aktive Schritt beschriftet |
| UX-23 | Knöpfe in schmalen Spalten brachen mitten im Wort um („Gewich·te normali·sieren“), Nebenwirkung von UX-04 | iPhone | niedrig | **behoben**: Umbruch nur an Wortgrenzen, breitere Knopfspalte auf dem Handy |

## Tastaturbedienung

Anmeldung, Menü, Öffnen einer Ansicht per Enter und Rückweg über „☰ Menü“ funktionieren vollständig mit Tab und Enter. Alle angesteuerten Elemente zeigen einen sichtbaren Fokusrahmen. Der erste Tab springt auf Streamlits Link „Skip to main content“, das ist korrekt.

## Offen (bewusst nicht geändert)

| Punkt | Grund / Empfehlung |
|---|---|
| Kleine Streamlit-interne Bedienelemente: Link „Skip to main content“ (nur bei Tastaturfokus sichtbar), Kalender-Symbol (16 px), Hilfe-„?“ (13 px), Aufklapp-Pfeil der Auswahlfelder, Zahlen-Stepper (42 px), Tabellen-Werkzeugleiste (24 px) | Teil der Streamlit-Komponenten; die eigentlichen Eingabefelder sind groß genug. Nur durch tiefe CSS-Eingriffe änderbar, die bei Streamlit-Updates brechen. |
| Zahleneingaben mit Dezimalpunkt („24.27“) | Streamlit-`number_input` kennt kein deutsches Format. |
| Portfolio-Planer: einzelne Schritte bleiben lang („Auswahl“ ≈ 5.500 px, „Annahmen & Quellen“ ≈ 5.100 px auf dem iPhone), viel Erklärtext | Die Länge von „Annahmen & Quellen“ kommt in der Sandbox vor allem von „Instrument nicht gefunden“ in jeder Zeile (keine Kursquellen). Weitere Kürzung (Erklärtexte in aufklappbare Hinweise) wäre ein inhaltlicher Umbau des Planers – nur nach Rücksprache. |
| Lange Firmennamen in Watchlist-Tabellen gekürzt | Gewollt (Tabellenbreite); voller Name im Detail. |
| `st.components.v1.html` (Ladeanzeige) laut Streamlit „nach 01.06.2026 entfernt“ | Mit der fest eingestellten Version 1.66 funktioniert es. Vor einem Streamlit-Update auf `st.iframe` umstellen. |
| Nur dunkles Design, kein helles Design | Bewusste Gestaltung; bei Bedarf separat. |

## Grenzen

- **Kein echtes iOS-Gerät:** Getestet wurde mit Chromium, Touch-Emulation und Safari-Kennung (User-Agent), nicht mit Safari selbst auf iPhone/iPad. Die Safari-Kennung ist wichtig, weil der Planer über sie die Handy-Darstellung wählt; der erste Messlauf ohne sie hatte die Handy-Darstellung des Planers nicht erfasst. Safari-Eigenheiten (z. B. Zoom bei Eingabefeldern unter 16 px, Adressleiste) sind nicht geprüft. Die App setzt Eingabefelder bereits auf 16 px.
- **Systemschriftgröße:** Vergrößerte Systemschrift und Bildschirmlupe sind nicht getestet. Mit Screenreadern wurde nicht praktisch gearbeitet, nur automatisiert (axe) und per Tastatur.
- **Planer-Inhalte:** Die Planer-Bausteine zeigen in der Sandbox „kein Kurs“ (externe Kursquellen gesperrt). Die Planer-Zahlen sind deshalb nicht fachlich beurteilbar, nur Layout und Bedienung.
- **Ladezeiten:** 1–2 s je Ansicht gelten nur für die lokale Sandbox ohne echte Netzlatenz.
