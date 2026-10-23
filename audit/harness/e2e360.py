"""360°-E2E: Benutzer anlegen, Login-Fehlerfaelle, Positionen anlegen/aendern/loeschen (mit Rueckfrage),
Doppelklick, ungueltige Eingaben, HTML-Einschleusung, Persistenz nach Neuladen, Sparrate, Chronik, Rechte,
Zurueck-Taste, Abmelden. Ausgabe: PASS/FAIL je Pruefpunkt. Nur Sandbox mit synthetischen Daten."""
import json
import re
import sys

import os
import br
br.URL = os.environ.get("URL", br.URL)
from playwright.sync_api import sync_playwright

ERG = []
BREITE = int(sys.argv[1]) if len(sys.argv) > 1 else 1440


def check(name, ok, info=""):
    ERG.append((name, bool(ok), info))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)


def menue(page, ansicht):
    if not page.locator(".st-key-nav_menue button", has_text=ansicht).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=ansicht).first.click(); br.warte_ruhe(page, 180)


def abmelden(page):
    if not page.locator(".st-key-logout_ecke button").first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-logout_ecke button:visible").first.click(); br.warte_ruhe(page)


def login_versuch(page, name, pw):
    page.goto(br.URL)
    page.get_by_placeholder("Benutzername eingeben").wait_for(timeout=60000)
    page.get_by_placeholder("Benutzername eingeben").fill(name)
    page.get_by_placeholder("Passwort eingeben").fill(pw)
    page.get_by_role("button", name="Anmelden").click(); br.warte_ruhe(page)
    return page.locator("body").inner_text()


def positionen_namen(page):
    t = br.text(page)
    return re.findall(r"Position \d+: (.+)", t)


with sync_playwright() as p:
    b, ctx, page = br.start(p, BREITE, 900, BREITE < 1100)
    mobil = BREITE < 1100

    # --- Login-Fehlerfaelle
    t = login_versuch(page, "admin", "falsch")
    check("Login: falsches Passwort abgewiesen", "falsch" in t.lower() and "Benutzername eingeben" in page.content())
    t = login_versuch(page, "", "")
    check("Login: leere Felder abgewiesen", page.get_by_placeholder("Benutzername eingeben").count() == 1)

    # --- Admin legt Pruefbenutzer an (inkl. Fehlerfaelle)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    menue(page, "Benutzer")
    page.locator("summary", has_text="Neuen Benutzer anlegen").first.click(); page.wait_for_timeout(500)
    form = page.locator("[data-testid=stForm]").filter(has_text="Anlegen").first

    def anlegen(n, pw):
        form.get_by_label("Benutzername").fill(n)
        form.get_by_label(re.compile("Passwort")).fill(pw)
        form.get_by_role("button", name="Anlegen").click(); br.warte_ruhe(page)
        return br.text(page)

    t = anlegen("pruefer", "kurz")
    check("Benutzer: zu kurzes Passwort abgewiesen", "pruefer" not in re.findall(r"👤 (\S+)", t) and
          any(w in t for w in ("mindestens", "Zeichen", "zu kurz")))
    t = anlegen("maria", "Irgendwas-Langes-1")
    check("Benutzer: doppelter Name abgewiesen", any(w in t.lower() for w in ("existiert", "vergeben", "bereits")))
    t = anlegen("pruefer", "Pruefer-Pass-2026")
    check("Benutzer: Anlegen erfolgreich", "pruefer" in t)
    abmelden(page)
    check("Abmelden: zurück zur Anmeldung", page.get_by_placeholder("Benutzername eingeben").count() == 1)
    page.go_back(); br.warte_ruhe(page)
    check("Zurück-Taste nach Abmelden zeigt keine Daten",
          "DEPOTWERT" not in page.locator("body").inner_text().upper() or
          page.get_by_placeholder("Benutzername eingeben").count() == 1)

    # --- Neuer Benutzer: leere Ansichten
    br.login(page, "pruefer", "Pruefer-Pass-2026")
    menue(page, "Depot verwalten")
    t = br.text(page)
    check("Neuer Benutzer: keine vorbelegten Positionen", not positionen_namen(page), str(positionen_namen(page)))

    # --- Position anlegen: Pflichtfelder
    if page.locator("summary", has_text="Positionen verwalten").count():
        page.locator("summary", has_text="Positionen verwalten").first.click(); page.wait_for_timeout(500)
    f = page.locator("[data-testid=stForm]:visible").filter(has_text="Position anlegen").first
    f.get_by_role("button", name="➕ Position anlegen").click(); br.warte_ruhe(page)
    check("Anlegen ohne Pflichtfelder: Fehlermeldung", "Bitte Name, Kaufkurs und Kapital" in br.text(page))

    # --- Position per Suche anlegen (Doppelklick auf Anlegen)
    page.get_by_label("WKN, ISIN oder Name suchen").filter(visible=True).first.fill("MSCI World"); page.keyboard.press("Enter")
    br.warte_ruhe(page)
    f = page.locator("[data-testid=stForm]:visible").filter(has_text="Position anlegen").first
    f.get_by_label("Kaufkurs (€)").fill("50"); f.get_by_label("Kaufkurs (€)").press("Tab")
    f.get_by_label("Investiertes Kapital (€)").fill("5000"); f.get_by_label("Investiertes Kapital (€)").press("Tab")
    f.get_by_role("button", name="➕ Position anlegen").dblclick(); br.warte_ruhe(page); br.warte_ruhe(page)
    namen = positionen_namen(page)
    check("Anlegen per Suche erfolgreich", any("MSCI World" in n for n in namen), str(namen))
    check("Doppelklick legt nur EINE Position an", sum("MSCI World" in n for n in namen) == 1, str(namen))
    if not page.get_by_label("WKN, ISIN oder Name suchen").filter(visible=True).count():
        page.locator("summary", has_text="Positionen verwalten").first.click(); page.wait_for_timeout(400)
    check("Suchfeld nach dem Anlegen leer",
          page.get_by_label("WKN, ISIN oder Name suchen").filter(visible=True).first.input_value() == "")

    # --- HTML-Einschleusung im Namen
    f = page.locator("[data-testid=stForm]:visible").filter(has_text="Position anlegen").first
    f.get_by_label("Name").fill('Test <img src=x onerror="document.title=\'XSS\'"> & Co')
    f.get_by_label("Kaufkurs (€)").fill("10"); f.get_by_label("Kaufkurs (€)").press("Tab")
    f.get_by_label("Investiertes Kapital (€)").fill("1000"); f.get_by_label("Investiertes Kapital (€)").press("Tab")
    f.get_by_role("button", name="➕ Position anlegen").click(); br.warte_ruhe(page)
    menue(page, "Depot")
    check("HTML im Namen wird nicht ausgeführt", page.locator("[data-testid=stMain] img[onerror]").count() == 0
          and page.title() != "XSS")
    check("HTML-Name lesbar angezeigt", "Test <img" in br.text(page) or "Test &lt;img" in page.content())

    # --- Aendern + Persistenz nach Neuladen
    menue(page, "Depot verwalten")
    page.locator("summary", has_text="Positionen verwalten").first.click(); page.wait_for_timeout(500)
    pf = page.locator("[data-testid=stForm]:visible").filter(has_text="💾 Speichern").nth(0)
    pf.get_by_label("Investiertes Kapital (€)").fill("6000"); pf.get_by_label("Investiertes Kapital (€)").press("Tab")
    pf.get_by_role("button", name="💾 Speichern").click(); br.warte_ruhe(page)
    page.reload(); br.warte_ruhe(page)
    if page.get_by_placeholder("Benutzername eingeben").count():
        check("Neuladen: Anmeldung bleibt erhalten", False, "nach F5 erneut anmelden nötig")
        br.login(page, "pruefer", "Pruefer-Pass-2026")
    else:
        check("Neuladen: Anmeldung bleibt erhalten", True)
    menue(page, "Depot verwalten")
    page.locator("summary", has_text="Positionen verwalten").first.click(); page.wait_for_timeout(500)
    pf = page.locator("[data-testid=stForm]:visible").filter(has_text="💾 Speichern").nth(0)
    wert = pf.get_by_label("Investiertes Kapital (€)").input_value()
    check("Änderung bleibt nach Neuladen erhalten", wert.replace(".", "").startswith("6000"), wert)

    # --- Loeschen mit Rueckfrage
    pf = page.locator("[data-testid=stForm]:visible").filter(has_text="💾 Speichern").nth(1)
    pf.get_by_role("button", name="🗑️ Löschen").click(); br.warte_ruhe(page)
    t = br.text(page)
    check("Löschen fragt nach", "wirklich löschen" in t)
    check("Vor Bestätigung noch vorhanden", any("Test <img" in n for n in positionen_namen(page)))
    page.get_by_role("button", name="Abbrechen").first.click(); br.warte_ruhe(page)
    check("Abbrechen behält Position", any("Test <img" in n for n in positionen_namen(page))
          and "wirklich löschen" not in br.text(page))
    if page.locator("[data-testid=stForm]:visible").filter(has_text="💾 Speichern").count() < 2:
        page.locator("summary", has_text="Positionen verwalten").first.click(); page.wait_for_timeout(300)
    pf = page.locator("[data-testid=stForm]:visible").filter(has_text="💾 Speichern").nth(1)
    pf.get_by_role("button", name="🗑️ Löschen").click(); br.warte_ruhe(page)
    page.get_by_role("button", name="🗑️ Endgültig löschen").first.click(); br.warte_ruhe(page)
    check("Endgültig löschen entfernt Position", not any("Test <img" in n for n in positionen_namen(page)),
          str(positionen_namen(page)))

    # --- Sparrate speichern
    page.locator("summary", has_text="Sparrate und Entnahme anpassen").first.click(); page.wait_for_timeout(500)
    page.get_by_role("spinbutton", name="Monatliche Sparrate (€)").first.fill("50"); page.get_by_role("spinbutton", name="Monatliche Sparrate (€)").first.press("Tab")
    br.warte_ruhe(page)
    page.get_by_role("button", name="💾 Sparrate speichern").click(); br.warte_ruhe(page)
    check("Sparrate gespeichert", any(w in br.text(page) for w in ("gespeichert", "Sparplan")))

    # --- Chronik
    menue(page, "Chronik")
    t = br.text(page)
    zeilen = [z for z in t.splitlines() if "Xtrackers" in z or "Test <img" in z or "Sparrate" in z or "Sparplan" in z]
    check("Chronik: Position angelegt", any("Xtrackers" in z for z in zeilen), " | ".join(zeilen[:6]))
    check("Chronik: Löschung protokolliert", any("Test <img" in z for z in zeilen))
    check("Hand-Position ohne WKN des vorherigen Suchtreffers",
          not any("Test <img" in z and "A1XB5U" in z for z in zeilen))

    # --- Zurueck-Taste innerhalb der App
    menue(page, "Zinseszinsrechner")
    page.go_back(); br.warte_ruhe(page)
    t = page.locator("body").inner_text()
    check("Zurück-Taste: App bleibt bedienbar (kein Absturz)", "Traceback" not in t and "Error" not in t[:500], page.url)
    abmelden(page)

    # --- Rechte: eingeschraenkter Benutzer
    br.login(page, "leser", "Leser-Pass-123")
    kacheln = page.evaluate("""() => [...document.querySelectorAll('.st-key-nav_menue button')]
        .map(b => b.innerText.trim()).filter(t => t && !t.includes('Abmelden') && !t.includes('logout')
        && !t.includes('aktualisieren'))""")
    check("Leser sieht nur freigegebene Ansichten", len(kacheln) <= 4, str(kacheln))
    page.goto(br.URL + "/?ansicht=builder"); br.warte_ruhe(page)
    t = page.locator("body").inner_text()
    check("Leser: unbekannter/gesperrter Direktlink öffnet nichts Fremdes", "Portfolio Builder" not in t[:400])
    b.close()

ok = sum(1 for _, o, _ in ERG if o)
print(f"\n{ok}/{len(ERG)} bestanden")
json.dump(ERG, open(f"{sys.argv[2] if len(sys.argv) > 2 else 'e2e360'}.json", "w"), ensure_ascii=False, indent=1)
