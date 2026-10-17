# Auditbericht Finanz Dashboard (wikifolio-tracker)

**Stand:** 17.10.2026 · **Geprüfter Code:** `main` @ `898b3a9` · **Vertraulich:** enthält Schwachstellenbeschreibungen, nicht in das öffentliche Repository pushen, solange es öffentlich ist.

Zugangsdaten, Tokens und personenbezogene Inhalte sind in diesem Bericht maskiert bzw. nicht wiedergegeben. Inhalte des produktiven State-Branches wurden **nicht gelesen** (nur Dateinamen und HTTP-Status).

---

## Umsetzungsstand (17.10.2026)

Nach dem Audit wurden die Befunde auf demselben Branch behoben (fachliche Vorgaben des Betreibers: **Kaufkurs 128,80 €**, **Entnahmen sind echte Verkäufe**). Verifiziert mit 440 Unit-Tests, den Audit-Reproduktionstests (18/18 grün) und erneuten Browser-Durchläufen in der Sandbox.

| ID | Status | Umsetzung | Nachweis |
|---|---|---|---|
| A-01 | **Code erledigt, Betreiber-Aktion offen** | `.streamlit/secrets.toml` entfernt, `.gitignore` ergänzt | Webhook in Discord löschen/neu anlegen (nur Betreiber) |
| A-02 | **Betreiber-Aktion offen** | – (Repo-Einstellung) | Repo privat stellen bzw. State in privates Repo, `ICON_BASE_URL` setzen |
| A-03 | erledigt | `nutzerdaten.name_pruefen` (nur a–z, 0–9, `-`, `_`, kein belegter Ordner), Kollisionswarnung in der Benutzerverwaltung | Tests `test_nutzerdaten`, Browser: `max.m` abgelehnt, Warnung für `anna.b`/`anna-b` |
| A-04 | erledigt | Hauptposition aus `positionen.json[0]` (`hauptposition_werte`), Sitzungsfelder entfernt, Papier gesperrt | Browser: Kapital 26.000 € → 28.927,80 € (auch nach Reload) |
| A-05 | erledigt | keine Kursautomatik mehr; `config.ANFANGSKURS = 128.80` | Stückzahl unabhängig von der Datenlage |
| A-06 | erledigt | kein Festkurs, keine Zufallsreihe; Kaskade Live → Schlusskurs → Workflow-Kurs (`state/price_history`) → keine Depotwerte | Browser: Fehlermeldung bzw. „letzter gespeicherter Kurs vom …“ |
| A-07 | erledigt | gecachte Abrufe werfen bei Fehlern (`_live_abruf`, `_benchmark_roh`) | Browser: nach Wiederherstellung sofort Live-Daten |
| A-08 | erledigt | Kachel „Ø p.a. seit Kauf“ = Tabelle (`rendite_pa_seit_kauf`) | Browser: 10,9 % / 10,95 % |
| A-09 | erledigt | Sparplan-Käufe mit Kauftag (`sparplan_einzelkaeufe`, `sparplan_verlauf`) in allen Reihen | Browser: Kachel = Chart = 14.288,05 € |
| A-10 | erledigt | Hinweis bei Speicher-Lesefehlern, ehrliche Login-Meldung | Browser + `test_login.SpeicherAusfall` |
| A-11 | erledigt | „Live“ nur frisch und in Handelszeit, sonst „Stand …“; Kurszeit statt Abrufzeit; Live-Punkt am Kurstag | Browser: „Stand 16.10. 14:00“ am Samstag |
| A-12 | erledigt | Hauptzahl = Depotwert nach echten Verkäufen; Gewinn inkl. Ausgezahltem; Gesamt, Meilenstein, Prognose mit echter Entnahmelogik | Browser: 13.788,05 € / +1.838,05 € wie unabhängig gerechnet |
| A-13 | erledigt | Sitzung endet bei Passwortwechsel und nach 12 h | `test_login.Sitzung` |
| A-14 | teilweise | Versionen in `requirements.txt` und Workflows fest | Branch-Schutz für `main` nur in den GitHub-Einstellungen möglich (Betreiber) |
| A-15 | erledigt | Standardszenarien −10/0/5/10/15/20/30 % p.a. | Browser-Screenshot |
| A-16 | erledigt | Kontraste, Abmelde-Button mit Namen, sichtbarer Tastatur-Fokus | axe-core: 0 Verstöße |
| A-17 | teilweise | Prozente/Stückzahlen in Kacheln mit Dezimalkomma | `fmt()` (Betrag ohne Leerzeichen vor €) bewusst unverändert |
| A-18 | zurückgenommen | kein Fehler: ein sichtbarer Knopf, das zweite Element ist Streamlits unsichtbarer Tooltip-Anker | Browser: 1 Container, 1 sichtbarer Knopf |
| A-19 | erledigt | Division durch null abgesichert | Audit-Test |
| A-20 | erledigt | „Aktualisieren“ höchstens 1×/Minute global | Browser-Toast |
| A-21 | erledigt | doppelte Testdatei entfernt | – |
| A-22, A-23 | akzeptiert | rechtliche Frage bzw. Streamlit-Sitzungsmodell | – |
| A-24 | erledigt | Sicherungs-Tag `state-backup-JJJJ-MM` vor jedem Squash (letzte 3) | lokal mit Test-Repo geprüft |
| A-25 | **Betreiber-Aktion offen** | – | Pinger (cron-job.org) auf Mo–Fr 7:30–23:00 begrenzen |
| A-26 | erledigt | `github_store.lese_text` lädt große Dateien über die Rohdatei | `test_github_store` |
| A-27 | erledigt | Sparplan-Kauf am ersten Handelstag ab Termin (max. 7 Tage), Ersatzkurs nur für noch offene Käufe | `test_app_rechner` |

Bekannte Grenze der Korrektur A-06: Ist gar kein echter Kurs verfügbar, zeigen die kursabhängigen Ansichten (Depot, Einstellungen, Charts, Prognosen) nur die Fehlermeldung. Chronik, Rechner, Planer, Watchlist und Benutzerverwaltung bleiben erreichbar (die Chronik läuft seit 17.10. als eigenständige Ansicht ohne Kursabruf).

---

## A. Gesamturteil

Der Code ist für ein Einzelprojekt ungewöhnlich sorgfältig: konsequentes HTML-Escaping, fail-closed-Login mit PBKDF2 und Sperrlogik, optimistische Sperre (sha) beim Schreiben, kein Schreiben nach Lesefehlern, 441 grüne Unit-Tests und eine korrekt implementierte Steuerlogik (§ 32a, § 34 EStG, SolZG). Die geprüften Kernformeln stimmen mit unabhängig gerechneten Referenzwerten überein.

**Ein sicherer produktiver Einsatz ist trotzdem aktuell nicht gegeben.** Verhindert wird er durch zwei Betriebs- und Sicherheitsbefunde, die nichts mit der Code-Qualität zu tun haben (laut Betreiber enthält der State bisher nur Testdaten – A-02 ist damit aktuell strukturell statt akut, der Webhook in A-01 ist dagegen echt):

1. **Das Repository ist öffentlich.** Damit sind (a) ein Discord-Webhook im Klartext und (b) der komplette State-Branch mit Passwort-Hashes, Depotpositionen, Rechner-Eingaben (u. a. Abfindung/Einkommen) und Chronik für jeden ohne Anmeldung abrufbar. Der Code selbst schreibt in `app.py:33-38` vor, dass das Repo in diesem Fall privat sein muss.
2. **Die Mandantentrennung ist lückenhaft:** verschiedene Benutzernamen (z. B. `anna.b` / `anna-b`) teilen sich denselben Datenordner – im Browser nachgewiesen.

Dazu kommen **hohe** Befunde zur Finanzanzeige: Der angezeigte Depotwert hängt von einer standardmäßig aktiven Kaufkurs-Automatik ab (Stückzahl springt im Test zwischen 130 und 80,9 Anteilen), bei Ausfall der Kursquelle wird ein fest kodierter Kurs (302,98 €) als Depotwert-Grundlage angezeigt, Änderungen an der Hauptposition werden gespeichert, wirken aber nicht, und Fehlabrufe werden bis zu ~10 Stunden zwischengespeichert.

Kurzfristig (Repo privat, Webhook rotieren, Passwörter zurücksetzen, Slug-Kollision verhindern) ist das Risiko mit überschaubarem Aufwand deutlich senkbar.

---

## B. Prüfabdeckung

| Bereich | Status | Prüfmethode | Ergebnis | Verbleibende Lücken |
|---|---|---|---|---|
| Bestandsaufnahme (Stack, Struktur, Datenflüsse) | geprüft | Codeanalyse aller Module, Workflows, Konfiguration | Streamlit-Monolith (`app.py` 7.600 Z.), State in GitHub-Branch `app-state`, Kurse von ls-tc.de, Agenten via GitHub Actions | keine README/Anforderungsdoku vorhanden |
| Sicherheit: Secrets/Repo-Sichtbarkeit | geprüft | Code, GitHub-API, HEAD-Request ohne Anmeldung | **kritisch** (A-01, A-02) | Inhalte des State-Branches bewusst nicht gelesen; Branches `app-state-v2`, `bot-state` nicht inspiziert |
| Sicherheit: Authentifizierung/Autorisierung | geprüft | Code, Unit-Tests, Browser (Fehllogin, Rechte, Permanentlink) | Login, Sperren, Ansichtsrechte funktionieren; Sitzungen überleben Passwortwechsel (A-13) | kein MFA vorhanden; Idle-Timeout nur per Code geprüft |
| Sicherheit: Mandantentrennung | geprüft | Unit-Test + Browser mit zwei Testnutzern | **Datenvermischung bestätigt** (A-03) | – |
| Sicherheit: XSS/Injection | teilweise geprüft | Grep aller `unsafe_allow_html`-Stellen (133), Browser-Test mit präpariertem Namen | kein XSS nachweisbar, Escaping konsequent | nicht jede der 133 Stellen einzeln verifiziert; SQL nicht relevant (keine DB) |
| Sicherheit: CSRF/CORS/Header/HTTPS | nicht geprüft | – | – | Produktions-URL bewusst nicht angegriffen; Header werden von Streamlit Cloud gesetzt |
| Abhängigkeiten | geprüft | `pip-audit` | keine bekannten CVEs in aktuellen Versionen; **keine Versions-Pins** (A-14) | – |
| Finanzlogik Depot | geprüft | unabhängige Nachrechnung + Browser mit synthetischen Kursen | Formeln korrekt; Anzeige-/Datenfluss-Fehler (A-04 bis A-09, A-12) | echte Kurse nicht abrufbar (Netzsperre) |
| Finanzlogik Steuer (Abfindung) | geprüft | eigene § 32a-Implementierung, Handrechnung | korrekt für Tarif 2026 | Tarif 2027 (Regierungsentwurf) nicht verifizierbar; arbeitsrechtliche Modelle (`abfindung_modelle.py`) nur über vorhandene Tests |
| Finanzlogik Zinseszins / Planer | geprüft (Stichprobe) | eigene Referenzformeln | korrekt | Optimizer (Simplex), Sensitivität nur über vorhandene Tests |
| Datenqualität/Speicherung | geprüft | Code, Fehlerinjektion (GitHub 500, ls-tc down) | keine Überschreibungen nach Lesefehlern; fehlende Hinweise (A-10), negatives Caching (A-07) | Langzeitverhalten nicht beobachtet |
| Funktionen/Abläufe | teilweise geprüft | Browser-Rundgang aller 14 Ansichten (Desktop+Mobil), gezielte Abläufe | alle Ansichten laden fehlerfrei | nicht jeder Button einzeln (insb. Planer, Abfindungs-PDF, Top-50-Filter) |
| Design/UX | teilweise geprüft | Screenshots Desktop/Mobil, Textauswertung | konsistentes Dark-Theme, kein Überlauf; Format-/Label-Inkonsistenzen | Tablet-Breite nicht geprüft; Light-Mode nicht vorhanden |
| Barrierefreiheit | teilweise geprüft | axe-core 4.10 (WCAG 2 A/AA) auf 4 Seiten, Tab-Reihenfolge | 3 Verstöße (A-16) | Screenreader nicht real getestet |
| Diagramme | teilweise geprüft | Plotly-Daten ausgelesen und gegen Kennzahlen verglichen | Inkonsistenz Sparplan (A-09), Szenarien (A-15) | Candlestick: OHLC wird künstlich aus Close erzeugt (siehe D) |
| Performance | teilweise geprüft | Zeitmessung im Browser (lokal) | 1–2 s je Ansicht **ohne echte Netzlatenz** | reale Ladezeiten mit ls-tc/GitHub nicht messbar |
| Tests/Build/CI | geprüft | Suite lokal + in CI-identischer Umgebung, GitHub-Actions-Historie | 441/441 grün, CI grün | Testabdeckung nicht gemessen (kein coverage-Tool) |
| Betrieb/Backup | teilweise geprüft | Workflows, Laufhistorie | kein Backup vor monatlichem Force-Push-Squash (A-25) | Wiederherstellung nicht praktisch getestet |
| Datenschutz | teilweise geprüft | Code (Datensparsamkeit, Löschung) | technische Umsetzung gut, aber durch A-02 ausgehebelt | rechtliche Bewertung (DSGVO, Meldepflicht) nicht Gegenstand |

---

## C. Priorisierte Befunde

Legende Nachweis: **bestätigt** = reproduziert (Test/Browser/API); **vermutet** = aus Code begründet, nicht praktisch reproduziert.

### A-01 · Discord-Webhook im öffentlichen Repository
- **Kategorie:** Sicherheit / Secrets · **Schweregrad:** kritisch · **Nachweis:** bestätigt
- **Betroffen:** `.streamlit/secrets.toml` (getrackt trotz `.gitignore`-Eintrag `.streamlit/`), Commit `9f45584`
- **Beschreibung/Auswirkung:** Die Datei enthält eine vollständige Webhook-URL (`https://discord.com/api/webhooks/<ID>/<TOKEN>` – maskiert). Da das Repo öffentlich ist, kann jeder Nachrichten in den Alarm-Kanal posten, z. B. gefälschte „Kurs-Alarme“ oder „Allzeithoch“-Meldungen, die zu falschen Kauf-/Verkaufsentscheidungen verleiten. Zusätzlich ist die Datei kein gültiges TOML (`TOMLDecodeError` Zeile 1) – würde Streamlit sie laden, scheitert der Start.
- **Reproduktion:** `git ls-files .streamlit` → Datei ist getrackt; `python -c "import tomllib; tomllib.load(open('.streamlit/secrets.toml','rb'))"` → Fehler.
- **Erwartet:** keine Secrets im Repo. **Tatsächlich:** Webhook öffentlich.
- **Lösung:** (1) Webhook in Discord sofort löschen und neu anlegen, neue URL nur in Streamlit-Cloud-Secrets und GitHub-Actions-Secrets. (2) `git rm --cached .streamlit/secrets.toml`. (3) GitHub Secret Scanning + Push Protection aktivieren. History-Bereinigung ist nach Rotation optional.
- **Aufwand:** 30 Min. · **Test:** `audit/test_audit_reproduktion.py::BefundSEC01_Secrets` wird grün.

### A-02 · State-Branch mit Passwort-Hashes und Finanzdaten öffentlich abrufbar
- **Kategorie:** Sicherheit / Datenschutz · **Schweregrad:** hoch (strukturell; kritisch, sobald echte Daten eingetragen werden) · **Nachweis:** bestätigt
- **Nachtrag des Betreibers (17.10.2026):** Der State enthält bisher ausschließlich Testdaten. Aktuell werden daher keine echten personenbezogenen oder Finanzdaten offengelegt; Restrisiko nur bei wiederverwendeten Testpasswörtern. Die Maßnahme bleibt Voraussetzung für den ersten echten Nutzer.
- **Betroffen:** Repository-Sichtbarkeit (`visibility: public`), Branch `app-state` (`state/benutzer.json`, `positionen.json`, `eingaben.json`, `trades_db.json`, `musterdepot.json`, `state/benutzer/*`, `state/planer/*`)
- **Beschreibung/Auswirkung:** `HEAD https://raw.githubusercontent.com/.../app-state/state/benutzer.json` → **HTTP 200 ohne Anmeldung** (ebenso `positionen.json`). Laut Code liegen dort PBKDF2-Hashes (200.000 Iterationen) aller Benutzer – Offline-Brute-Force ist ohne jede Rate-Limitierung möglich – sowie Depotdaten, Rechner-Eingaben (Einkommen, Abfindung) und Anmeldedaten in der Chronik. Auch die Git-Historie des Branches und weitere Branches (`app-state-v2`, `bot-state`) sind betroffen. Die App-Login-Hürde ist damit für Lesezugriffe wirkungslos.
- **Reproduktion:** GitHub-API `GET /repos/wikifolio-user/wikifolio-tracker` → `"private": false`; HEAD-Request wie oben.
- **Erwartet:** State nur für die App lesbar (Code-Kommentar SEC-01, `app.py:33-38`). **Tatsächlich:** weltweit lesbar.
- **Lösung:** Repo auf privat stellen **oder** State in ein separates privates Repo verlagern (`GITHUB_REPO`-Secret) und dieses Repo öffentlich lassen; Icons über `ICON_BASE_URL` ausliefern. Danach alle Benutzerpasswörter zurücksetzen, Admin-Passwort-Hash neu erzeugen, GitHub-Token rotieren. Ob eine meldepflichtige Datenpanne vorliegt, ist rechtlich zu klären (nicht Teil dieses Audits).
- **Aufwand:** 1–2 h (+ ggf. Datenmigration). **Abhängigkeit:** nach Privatstellung kosten Actions-Minuten Geld (A-26). · **Test:** unauthentifizierter HEAD liefert 404.

### A-03 · Benutzer teilen sich Datenordner (Slug-Kollision)
- **Kategorie:** Sicherheit / Autorisierung · **Schweregrad:** hoch · **Nachweis:** bestätigt (Unit-Test + Browser)
- **Betroffen:** `nutzerdaten.py:26-39` (`slug`, `ordner`), `login.py:662-689` (Anlegen ohne Kollisionsprüfung)
- **Beschreibung/Auswirkung:** `slug()` normalisiert Namen verlustbehaftet: `anna.b`→`anna-b`, `jörg`→`jorg`, `a b`→`a-b`, rein nicht-lateinische Namen → `benutzer`. Zwei Konten sehen und ändern dann dieselben Depot-, Planer-, Rechner- und Chronikdaten. Löscht der Admin eines der Konten, werden auch die Daten des anderen gelöscht.
- **Reproduktion:** Benutzer `anna.b` und `anna-b` anlegen; als `anna.b` eine Position anlegen; als `anna-b` anmelden → Position sichtbar (Beleg `belege/06_anna-b_sieht_fremde_daten.png`; Speicherpfad `state/benutzer/anna-b/positionen.json`).
- **Erwartet:** getrennte Daten. **Tatsächlich:** gemeinsame Daten.
- **Lösung:** Benutzernamen beim Anlegen auf `^[a-z0-9_-]{2,40}$` beschränken **und** prüfen, dass `slug(neu)` keinem bestehenden Slug entspricht; alternativ Ordnername = stabile, zufällige Benutzer-ID, die in `benutzer.json` gespeichert wird. Bestehende Konten auf Kollisionen prüfen.
- **Aufwand:** 2–4 h · **Test:** `BefundSEC03_Mandantentrennung` grün; Browser-Szenario `harness/t3.py`.

### A-04 · Bearbeitung der Hauptposition wird gespeichert, wirkt aber nicht
- **Kategorie:** Funktion / Finanzlogik · **Schweregrad:** hoch · **Nachweis:** bestätigt (Browser)
- **Betroffen:** `app.py:6141-6200` (Formular „Hauptposition“), `app.py:4650-4677` (Berechnung nutzt `config.py`/Sitzungswerte), `app.py:1672-1682` (`depot_aufteilung` übernimmt nur den Namen)
- **Beschreibung/Auswirkung:** Unter Einstellungen → „Positionen verwalten“ lassen sich Kaufdatum, Kaufkurs, Kapital und sogar das Wertpapier der Hauptposition ändern; `positionen.json` wird aktualisiert. Depotwert, Charts und Prognosen rechnen aber weiter mit `config.STARTKAPITAL`/Sitzungswerten und `config.LS_INSTRUMENT_ID`. Die Eingaben unter „Kauf, Kapital, Sparrate …“ (`haupt_kaufdatum_input`, `haupt_startkapital_input`, `haupt_kaufkurs_input`) gelten nur für die Sitzung und gehen beim Neuladen verloren.
- **Reproduktion:** Kaufkurs 160,68 / Kapital 26.000 speichern → `positionen.json` enthält die Werte, Depotwert bleibt 19.500 € (130 Anteile, Einstand 13.000 €), auch nach Reload (`belege/04_…`, `05_…`).
- **Erwartet:** 26.000/160,68 = 161,81 Anteile → 24.271,84 €. **Tatsächlich:** 19.500 €.
- **Lösung:** Eine einzige Quelle: Hauptposition-Werte aus `positionen.json[0]` lesen (Fallback `config.py`), Sitzungsfelder entfernen oder beim Speichern in die Position schreiben; Instrument-Wechsel der Hauptposition entweder unterstützen oder sperren.
- **Aufwand:** 0,5–1 Tag · **Test:** Browser-Szenario `harness/t2.py` erwartet 24.271,84 €.

### A-05 · Kaufkurs-Automatik überschreibt den tatsächlichen Kaufkurs; Stückzahl hängt von Datenverfügbarkeit ab
- **Kategorie:** Finanzlogik · **Schweregrad:** hoch · **Nachweis:** Mechanismus bestätigt; Wirkung in Produktion vermutet
- **Betroffen:** `app.py:4661-4677`, `config.py:13`
- **Beschreibung/Auswirkung:** Standardmäßig (`haupt_kaufkurs_auto=True`) wird der Kaufkurs aus der Historie am Kaufdatum genommen, nicht `config.ANFANGSKURS`. Laut Code-Kommentaren (`app.py:78`, `2155`) beginnt die ls-tc-Historie am 09.07.2025 bei **128,80 €**, `config.ANFANGSKURS` ist **160,68 €**. Falls 160,68 € der tatsächlich gezahlte Kurs ist, rechnet die App mit 100,93 statt 80,91 Anteilen – der Depotwert wäre um **24,75 % zu hoch**. Zudem fällt die App bei fehlender Historie still auf den Config-Kurs zurück: im Test sprang die Stückzahl zwischen 130,0000 und 80,9061.
- **Fachliche Unklarheit:** Welcher Kurs (128,80 € oder 160,68 €) tatsächlich gezahlt wurde, ist aus dem Code nicht ableitbar – bitte klären.
- **Reproduktion:** Sandbox, Kurs am 09.07.2025 = 100 → 130 Anteile; ls-tc-Ausfall → 80,9061 Anteile (`harness/t1.py`, `t6.py`).
- **Lösung:** Gespeicherter Kaufkurs hat Vorrang; Automatik nur als einmaliger Vorschlag beim Anlegen; nie stilles Umschalten.
- **Aufwand:** 2–4 h (zusammen mit A-04) · **Test:** Depotwert identisch bei verfügbarer und fehlender Historie.

### A-06 · Fest kodierter Ersatzkurs wird als Kurs und Depotwert angezeigt
- **Kategorie:** Finanzlogik / Datenqualität · **Schweregrad:** hoch · **Nachweis:** bestätigt (Browser)
- **Betroffen:** `app.py:4641-4642` (`302.980` / `302.100`), `app.py:1538-1556` (synthetische Historie mit Zufallsrauschen)
- **Beschreibung/Auswirkung:** Fallen Live-Kurs und Historie aus, zeigt die Startkachel „302,980 €“ und den Depotwert „24.512,94 €“ als große Hauptzahlen. Ein rotes Banner warnt zwar, die Zahlen selbst sind aber erfunden (im Test 26 % über dem tatsächlichen Wert). Die Vergleichsansichten zeigen eine Zufallsreihe.
- **Reproduktion:** Fehlerinjektion `{"lstc":"down"}`, „Kurse aktualisieren“ → `belege/07_lstc_ausfall.png`.
- **Erwartet:** „Kein aktueller Kurs“ bzw. letzter bekannter echter Kurs mit Datum (z. B. aus `state/price_history/*.csv`). **Tatsächlich:** Fantasiewert.
- **Lösung:** Festwert und synthetische Reihe entfernen; letzten Kurs aus der eigenen Preis-Historie mit Zeitstempel anzeigen, sonst Kennzahlen ausblenden.
- **Aufwand:** 2–4 h · **Test:** `BefundFIN01_FesterErsatzkurs` grün; Browser-Szenario `t6.py` zeigt keinen Depotwert ohne Kurs.

### A-07 · Fehlgeschlagene Kursabrufe werden zwischengespeichert
- **Kategorie:** Datenqualität / Zuverlässigkeit · **Schweregrad:** hoch · **Nachweis:** bestätigt (Browser)
- **Betroffen:** `app.py:1412` `get_live_market_data`, `1872` `get_live_kurs`, `1561` `get_benchmark_history` (je `@st.cache_data(ttl=26h)`, geben bei Fehlern Werte zurück statt zu werfen)
- **Beschreibung/Auswirkung:** Ein einzelner Fehlabruf bleibt für alle Nutzer bis zum nächsten Aktualisierungstermin im Cache – tagsüber bis 2 h, nachts (23→9 Uhr) bis ~10 h. Benchmarks fehlen dann still im Vergleich.
- **Reproduktion:** Quelle ausfallen lassen, aktualisieren, Quelle wiederherstellen, neue Sitzung öffnen → weiterhin „keine echten Live-Daten“, bis manuell aktualisiert wird (`harness/t6.py`).
- **Lösung:** Wie bei `lade_rohhistorie`: im gecachten Teil bei Fehlern eine Ausnahme werfen, Fallback außerhalb des Caches.
- **Aufwand:** 1 h · **Test:** `BefundDATA_FehlerNichtCachen` grün; `t6.py` zeigt nach Wiederherstellung Live-Daten.

### A-08 · „Ø p.a.“ auf der Depotkachel ist die Prognoserate, nicht die eigene Rendite
- **Kategorie:** Finanzlogik / UX · **Schweregrad:** mittel · **Nachweis:** bestätigt
- **Betroffen:** `app.py:5547-5554` (verwendet `prognose_rendite_pa`); Widerspruch zum Docstring `app.py:2197-2200`
- **Beschreibung/Auswirkung:** Testdaten: Kachel „Ø p.a. 24,3 %“, Vergleichstabelle für dieselbe Position „Ø/Jahr +37,50 %“ (korrekt realisiert). Nutzer lesen die Kachel als eigene Jahresrendite.
- **Lösung:** Kachel zeigt realisierte Rendite p. a. (ab 1 Jahr), Prognoserate nur in Prognoseansichten mit Label „Prognosebasis“.
- **Aufwand:** 30 Min. · **Test:** Kachel- und Tabellenwert identisch.

### A-09 · Sparplan-Anteile fehlen in Vermögensaufbau-Chart und Vergleichstabelle
- **Kategorie:** Finanzlogik / Visualisierung · **Schweregrad:** mittel · **Nachweis:** bestätigt (Plotly-Daten ausgelesen)
- **Betroffen:** `app.py:4826` (`Depotwert_Brutto = Close × stueckzahl_aktiv`), `_render_wealth` ab `6315`
- **Beschreibung/Auswirkung:** Mit 500 € Sparplan: Kachel 20.000,00 € (133,3333 Anteile), Chartlinie endet bei 19.500,00 €. Tabelle zeigt +50 % statt der Kachel-Rendite. Für normale Benutzer (Startkapital 0) ist die Chartlinie dauerhaft 0.
- **Lösung:** Sparplan-Kaufverlauf als zeitabhängige Stückzahl in die Reihe einrechnen; Rendite gegen kumulierte Einzahlungen (bzw. zeitgewichtet) ausweisen.
- **Aufwand:** 0,5 Tag · **Test:** letzter Chartwert = Kachelwert (`harness/t11.py`).

### A-10 · Keine Rückmeldung bei Speicher-Ausfall
- **Kategorie:** Datenqualität / UX · **Schweregrad:** mittel · **Nachweis:** bestätigt (Fehlerinjektion GitHub HTTP 500)
- **Beschreibung/Auswirkung:** Chronik zeigt „Noch keine Einträge“ (wirkt wie Datenverlust), Depot zeigt still Startwerte, normale Benutzer erhalten „Benutzername oder Passwort falsch“. Schreibvorgänge werden korrekt verhindert.
- **Lösung:** `gh_read_cached_status` an allen Lesestellen auswerten und ein Banner „Speicher nicht erreichbar – Anzeige unvollständig“ zeigen; Login-Fehlertext „Anmeldung vorübergehend nicht möglich“.
- **Aufwand:** 2–3 h · **Test:** `harness/t7.py` erwartet Banner.

### A-11 · „Live“ und „Stand“ zeigen Abrufzeit statt Kurszeit
- **Kategorie:** Datenqualität / UX · **Schweregrad:** mittel · **Nachweis:** bestätigt (Browser, Samstag 00:39)
- **Beschreibung/Auswirkung:** Badge „Live“ und „Stand: 17.10.2026 00:39:51 Uhr“ außerhalb der Handelszeit; Kurse sind laut Zeitplan bis zu 2 h alt. Der Zeitstempel des letzten Intraday-Punkts wird nicht verwendet.
- **Lösung:** Zeitstempel aus `intraday[-1][0]` anzeigen; „Live“ nur innerhalb der Handelszeit (`config.ist_handelszeit`) und bei Kursalter < 15 Min.
- **Aufwand:** 1–2 h.

### A-12 · „Depot gesamt“ und 100k-Meilenstein ignorieren bereits entnommenes Geld
- **Kategorie:** Finanzlogik · **Schweregrad:** mittel · **Nachweis:** bestätigt (Code + Browser)
- **Beschreibung/Auswirkung:** Gesamtsumme und Meilenstein starten beim Brutto-Depotwert (19.500 €), obwohl laut Konfiguration monatlich 70 € entnommen werden (Netto real 18.148,30 €). Meilensteindatum dadurch zu optimistisch. Netto-Werte sind in einem eingeklappten Bereich versteckt.
- **Fachliche Unklarheit:** Werden die 70 € tatsächlich durch Anteilsverkauf entnommen? Davon hängt ab, welcher Wert der „echte“ Depotwert ist.
- **Lösung:** Abhängig von der Klärung den realen Wert als Hauptzahl verwenden.

### A-13 · Passwortänderung beendet bestehende Sitzungen nicht; kein Inaktivitäts-Timeout
- **Kategorie:** Sicherheit / Sessions · **Schweregrad:** mittel · **Nachweis:** vermutet (Code)
- **Betroffen:** `login.py:459-466`, `516-541` (Sitzung speichert nur `login_name`)
- **Lösung:** Passwort-Version (z. B. Hash-Präfix) in der Sitzung speichern und bei jedem `pruefen()` vergleichen; Inaktivitäts-Timeout.
- **Aufwand:** 1–2 h.

### A-14 · Änderungsprozess und Lieferkette
- **Kategorie:** Betrieb · **Schweregrad:** mittel · **Nachweis:** bestätigt
- **Beschreibung:** Alle Änderungen direkt per Web-Commit auf ungeschützten `main` (sofortiges Deployment, kein Review, CI läuft erst danach). `requirements.txt` ohne Versionen (getestet mit pandas 3.0.5, Streamlit 1.66 – neue Hauptversionen können ungeprüft live gehen). Actions per Tag statt SHA gepinnt.
- **Lösung:** Branch-Schutz mit Pflicht-CI; `requirements.txt` pinnen (z. B. `pip freeze`); Dependabot.

### A-15 · Szenario-Simulator: Standardszenarien 12,7–213,8 % p. a.
- **Kategorie:** Finanzlogik / Visualisierung · **Schweregrad:** mittel · **Nachweis:** bestätigt (`belege/chart_Szenario-Simulator_0.png`)
- **Beschreibung:** 19 Linien von 1 % bis 10 % pro Monat, keine Null-/Verlustszenarien, Farben wiederholen sich (Linien nicht unterscheidbar), Endwerte bis 3 Mio. €. Legt unrealistische Erwartungen nahe.
- **Lösung:** Standard z. B. −5/0/5/10/15/historisch % p. a.; max. 6–7 Linien mit eindeutigen Farben.

### A-16 · Barrierefreiheit
- **Schweregrad:** niedrig · **Nachweis:** bestätigt (axe-core)
- Login-Button: Kontrast 3,63:1 (weiß auf #3987e5, Soll 4,5:1). Abmelde-Button: kein zugänglicher Name (Text per CSS entfernt). Label „Ø p.a.“: 4,43:1. Fokus-Outline global entfernt; ob der Schatten als Fokusanzeige reicht, ist visuell zu prüfen (vermutet).

### A-17 · Uneinheitliche Zahlenformate
- **Schweregrad:** niedrig · **Nachweis:** bestätigt
- „19.500,00€“ (ohne Leerzeichen) neben „+2.184,00 €“; „24.3 %“, „0.15 %“, „0.95 % p.a.“ und „130.0000 Anteile“ mit Dezimalpunkt; Kurse mit 3 Nachkommastellen. Lösung: ein zentraler Formatierer für Betrag/Prozent/Stück.

### A-18 bis A-27 · Weitere Befunde (niedrig)
| ID | Befund | Nachweis | Beleg / Ort |
|---|---|---|---|
| A-18 | Abmelde-Button doppelt im DOM (Playwright: 2 Elemente) | bestätigt | `app.py:3043` |
| A-19 | `berechne_performance_kennzahlen` teilt durch Startwert ohne Prüfung (in der UI durch Aufrufer abgesichert, latent) | bestätigt (Unit-Test) | `app.py:1338` |
| A-20 | Jeder Benutzer (auch mit nur einer Ansicht) leert per „Kurse aktualisieren“ den globalen Kurs-Cache aller Nutzer → Lastverstärkung gegen ls-tc | vermutet | `app.py:2794`, `2941` |
| A-21 | `test_app_rechner.py` und `test_app_rechnung.py` sind identisch | bestätigt (`cmp`) | – |
| A-22 | Abrufe mit vorgetäuschtem Browser-User-Agent/Referer (ls-tc, wikifolio, Yahoo); Nutzungsbedingungen rechtlich nicht bewertet | bestätigt (Code) | `config.py:145-149` |
| A-23 | Neuladen der Seite erfordert neue Anmeldung (keine persistente Sitzung) – störend als Homescreen-App | bestätigt | Streamlit-Sitzungsmodell |
| A-24 | Kein Backup vor dem monatlichen Force-Push-Squash; Wiederherstellung undokumentiert | bestätigt (Code) | `squash-state-history.yml` |
| A-25 | Externer Pinger startet den Alarm-Workflow alle 5 Min. rund um die Uhr (>13.000 Läufe); nach Privatstellung kostenpflichtig | bestätigt (Laufliste) | cron-job.org-Einstellung |
| A-26 | `append_csv_line`: bei Dateien > 1 MB liefert die Contents-API keinen Inhalt → Datei würde mit nur einer Zeile überschrieben (aktuell max. 111 KB/Monat) | vermutet | `github_store.py:487-505` |
| A-27 | Sparplan-Kauf am Wochenende zum Kurs des Vortags, ohne Spread (Verkauf mit Spread) – leichte Asymmetrie | bestätigt (Code) | `app.py:1224` |

---

## D. Finanzielle Validierung

**Testdatensatz (synthetisch):** LS9VFS-Kurs 100,00 € am 09.07.2025, je Handelstag +0,10 € (letzter Schluss 133,20 € am 16.10.2026), Live 150,00 €; Konfiguration 13.000 € Startkapital, 70 €/Monat Entnahme, Spread 0,15 %. Referenzwerte unabhängig gerechnet (Hand bzw. eigene Formeln in `audit/test_audit_reproduktion.py`).

| Kennzahl | Erwartet (eigene Rechnung) | App (Browser) | Ergebnis |
|---|---|---|---|
| Stückzahl (Auto-Kaufkurs 100 €) | 13.000/100 = 130,0000 | 130,0000 | ✅ (fachlich siehe A-05) |
| Depotwert brutto | 130 × 150 = 19.500,00 € | 19.500,00 € | ✅ |
| Gewinn / Rendite seit Kauf | 6.500,00 € / 50,00 % | +6.500,00 € / +50,00 % | ✅ |
| Tagesveränderung Depot | 16,80 × 130 = 2.184,00 € | +2.184,00 € | ✅ |
| Anzahl Entnahmen 09.08.25–09.10.26 | 15 | 15 | ✅ |
| Netto (Simulation) | 19.500 − 15 × 70 = 18.450,00 € | 18.450,00 € | ✅ |
| Netto (real verkauft) | 120,9886 Anteile → 18.148,30 € | 120,9886 / 18.148,30 € | ✅ |
| Rendite p. a. realisiert (465 Tage) | 1,5^(365,25/465) − 1 = 37,50 % | Tabelle 37,50 %, **Kachel 24,3 %** | ⚠️ A-08 |
| Mit Sparplan 500 € (Kauf zu 150 €) | 133,3333 Anteile / 20.000,00 € | Kachel 20.000,00 €, **Chart 19.500,00 €** | ❌ A-09 |
| Hauptposition 160,68 € / 26.000 € | 24.271,84 € | 19.500,00 € | ❌ A-04 |
| ESt 2026, zvE 50.000 € (Grundtarif) | 10.548 € (Handrechnung) | 10.548 € | ✅ |
| ESt-Tarif 13 Stützstellen inkl. Zonengrenzen | eigene § 32a-Implementierung | identisch | ✅ |
| Splitting zvE 100.000 € | 2 × ESt(50.000) | identisch | ✅ |
| Fünftelregelung (Rest 40.000 €, Abfindung 60.000 €) | ESt(40k) + 5 × [ESt(52k) − ESt(40k)] | identisch | ✅ |
| Fünftel bei negativem Resteinkommen (−5.000 €) | min(5 × ESt(11.000), ESt(55.000)) | identisch | ✅ |
| Soli bei ESt 25.000 € (Milderungszone) | 11,9 % × 4.650 = 553,35 € | 553,35 € | ✅ |
| Zinseszins 10.000 €, 5 %, 10 J., jährl. Gutschrift | 16.288,95 € (Cent-gerundet je Jahr) | identisch | ✅ |
| Sparplan 100 €/Monat nachschüssig, 3 %, 1 J. | 1.216,50 € | 1.216,50 € | ✅ |
| Planer `future_value` 10.000 €, 7 %, 10 J., 200 €/Mon. | 53.881,86 € | 53.881,86 € | ✅ |
| Planer erforderliche Rendite (Umkehrung) | 7,00 % | 7,00 % | ✅ |
| Monatsende-Kappung 31.01. + n Monate | 29.02./31.03./30.04. | identisch | ✅ |
| Kursausfall | kein Depotwert bzw. letzter echter Kurs | **302,980 € / 24.512,94 €** | ❌ A-06 |

**Weitere fachliche Feststellungen ohne Fehlercharakter:**
- „Netto (Simulation)“ zieht Entnahmen ab, lässt die Stückzahl aber konstant – entnommenes Geld rendiert also in der Simulation weiter. Die reale Variante ist die belastbarere Zahl.
- Die Euro-Beträge je Zeitraum (Woche/Monat …) rechnen die *heutige* Stückzahl rückwirkend (im Code dokumentierte Näherung); bei Sparplan-Käufen im Zeitraum wird Einzahlung als Gewinn gezählt.
- Candlestick: High/Low werden als Close ± 0,3 % erzeugt, keine echten OHLC-Daten. Die Ansicht weist darauf bereits in einer Bildunterschrift hin („Open/High/Low approximiert“).
- Gebühren (0,95 % p. a., 10 % Performance Fee) sind laut Code im Kurs eingepreist und werden korrekt nicht erneut abgezogen. Steuern auf Kursgewinne werden im Depot nicht berücksichtigt (Werte sind vor Steuern).

---

## E. Maßnahmenplan

**1. Sofort beheben (heute)**
- A-01 Discord-Webhook löschen/neu erzeugen, Datei aus dem Repo entfernen, Secret Scanning aktivieren.
- A-02 Repository privat stellen (oder State in privates Repo verlagern) – spätestens vor dem ersten echten Nutzer bzw. echten Eintrag; Testpasswörter nirgends sonst verwenden. Da bisher nur Testdaten betroffen sind, ist keine rechtliche Bewertung der bisherigen Offenlegung nötig.
- A-03 Bis zur Korrektur keine Benutzer mit Sonderzeichen/Umlauten anlegen; bestehende Namen auf Slug-Kollisionen prüfen.

**2. Vor dem nächsten produktiven Einsatz**
- A-03 Slug-Kollision im Code verhindern.
- A-04/A-05 Eine Datenquelle für die Hauptposition, gespeicherter Kaufkurs hat Vorrang; tatsächlichen Kaufkurs (128,80 € vs. 160,68 €) klären.
- A-06 Fest kodierten Kurs und synthetische Reihen entfernen.
- A-07 Fehlerergebnisse nicht cachen.
- A-08/A-09 Kennzahlen zwischen Kachel, Tabelle und Chart vereinheitlichen.
- A-14 Branch-Schutz + gepinnte Abhängigkeiten.

**3. Anschließend verbessern**
- A-10 Speicher-Ausfall sichtbar machen; A-11 Kurszeitstempel/„Live“-Logik; A-12 Netto als Hauptzahl (nach fachlicher Klärung); A-13 Session-Invalidierung; A-24 Backup vor Squash; A-25 Pinger auf Handelszeiten begrenzen; A-15 realistische Szenarien.
- Aufteilung von `app.py` (7.600 Zeilen) in Daten-, Berechnungs- und Darstellungsmodule – Nutzen: Render-Logik wird testbar, die Ursache von A-04/A-09 (mehrere Berechnungswege für dieselbe Kennzahl) entfällt. Aufwand mehrere Tage, Risiko von Regressionen → schrittweise, abgesichert durch die vorhandenen Tests und die Browser-Szenarien aus `audit/harness`.

**4. Optional optimieren**
- A-16 Kontraste, Button-Namen, sichtbarer Fokus; A-17 zentrale Formatierung; A-18, A-20, A-21, A-23, A-26, A-27.
- Browser-Szenarien (`audit/harness`) in die CI übernehmen.

---

## F. Grenzen des Audits

- **Netzwerk:** ls-tc.de, Yahoo und onvista waren aus der Prüfumgebung gesperrt. Alle Laufzeit- und Browsertests nutzen synthetische Kurse und einen In-Memory-Ersatz der GitHub-Contents-API (`audit/harness/fake_net.py`). Reale Ladezeiten, API-Formatänderungen und das Verhalten bei echten Kursdaten sind **nicht geprüft**.
- **Produktion:** Die produktive Streamlit-App (`*.streamlit.app`) wurde nicht aufgerufen oder angegriffen; Sicherheitsheader, HTTPS-Konfiguration und Cloud-Secrets sind **nicht geprüft**.
- **Produktivdaten:** Inhalte des State-Branches wurden bewusst nicht gelesen; die Aussage, dass dort Hashes und Finanzdaten liegen, stützt sich auf den Code und Dateinamen/-größen.
- **Historie:** Das Repo lag als Shallow Clone (50 Commits) vor; ältere Commits und die Branches `app-state-v2`, `bot-state`, `refactor/v2` wurden nicht untersucht.
- **Umfang:** Nicht jede der 133 HTML-Ausgabestellen und nicht jeder Button wurde einzeln verifiziert; Portfolio-Planer (Optimizer, Sensitivität), Top-50-/Qualitäts-Agenten und arbeitsrechtliche Abfindungsmodelle sind nur über die vorhandenen Tests und Stichproben abgedeckt.
- **Fachliche Annahmen:** Steuer-Tarif 2026 nach meinem Kenntnisstand von § 32a EStG verifiziert; der Tarif 2027 (Regierungsentwurf) ist nicht verifizierbar. Keine Steuer- oder Rechtsberatung, keine Aussage zur DSGVO-Konformität.
- **Nicht geprüfte Bereiche gelten nicht als fehlerfrei.**

---

## Ausgeführte Prüfungen (Protokoll)

| Prüfung | Ergebnis |
|---|---|
| `python -m unittest discover -p "test_*.py"` (Python 3.13, alle Pakete) | 441 Tests, OK (23 s) |
| Dieselbe Suite in CI-identischer Umgebung (nur requests/pandas/numpy/tzdata) | 441 Tests, OK, 0 übersprungen |
| `python -m unittest audit/test_audit_reproduktion.py` | 18 Tests: 13 Nachrechnungen grün, 5 Befund-Tests erwartungsgemäß rot |
| `pip-audit -r requirements.txt` | keine bekannten Schwachstellen |
| TOML-Prüfung `.streamlit/secrets.toml` | ungültig |
| GitHub-API Repository/Branches/Actions | öffentlich; CI grün auf `898b3a9`; Alarm-Workflow alle 5 Min. |
| HEAD auf `state/benutzer.json`, `state/positionen.json` ohne Anmeldung | HTTP 200 |
| Browser (Chromium 141, Playwright): Login/Fehllogin, alle 14 Ansichten Desktop 1400 px und Mobil 390 px | keine Fehler, kein horizontaler Überlauf |
| Browser: Hauptposition bearbeiten (`t2.py`) | A-04 bestätigt |
| Browser: Mandantentrennung + XSS-Probe (`t3.py`) | A-03 bestätigt, kein XSS |
| Browser: Rechte, Permanentlink, verstecktes DOM (`t4.py`, `t5.py`) | korrekt, keine Datenlecks |
| Browser: Kursquelle-Ausfall + Wiederherstellung (`t6.py`) | A-06, A-07 bestätigt |
| Browser: GitHub-Speicher HTTP 500 (`t7.py`) | A-10 bestätigt, keine Schreibvorgänge |
| Browser: Diagrammdaten (`t9.py`, `t11.py`) | A-09, A-15 bestätigt |
| axe-core 4.10.2 (WCAG 2 A/AA) auf Login, Start, Depot, Zinsrechner | 3 Verstöße (A-16) |
| Nicht ausführbar | echte Kursabrufe (Netzsperre), Produktions-App (bewusst nicht angegriffen), Screenreader-Test |
