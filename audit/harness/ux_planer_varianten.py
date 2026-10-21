"""Planer: Variante speichern, Arbeitsstand aendern, Variante bleibt unveraendert, Laden, Ueberschreiben nur mit Bestaetigung."""
import sys, br
from playwright.sync_api import sync_playwright
S = sys.argv[1]
import time
NAME = f"Test {int(time.time()) % 100000}"

def modelle(page):
    page.locator(".st-key-pl_nav_bereich button", has_text="Daten").first.click(); br.warte_ruhe(page, 180)
    page.locator(".st-key-pl_nav_bereich button", has_text="Gespeicherte Modelle").first.click(); br.warte_ruhe(page, 180)

def tabelle(page):
    return page.evaluate("""() => [...document.querySelectorAll('table tr')].map(r => r.innerText.replace(/\\s+/g,' '))
        .filter(t => t.startsWith('Test ') || t.startsWith('Aktuelles Modell'))""")

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 1000, False)
    br.login(page, "maria", "Maria-Test-Pass-1")
    page.locator(".st-key-nav_menue button", has_text="Portfolio-Planer").first.click(); br.warte_ruhe(page, 180)
    page.locator(".st-key-pl_nav_ansicht button", has_text="Alle Bereiche").first.click(); br.warte_ruhe(page, 180)
    modelle(page)
    page.get_by_role("textbox", name="Name der Variante").fill(NAME); page.keyboard.press("Enter"); page.wait_for_timeout(1000)
    page.get_by_role("button", name="💾 Speichern").click(); page.wait_for_timeout(2500); br.warte_ruhe(page, 180)
    print("nach Speichern:", [z for z in br.text(page).splitlines() if "Variante" in z and "gespeichert" in z][:2])
    print("Tabelle:", tabelle(page))
    # Arbeitsstand aendern: Ziel & Rahmen ist im Bereich Portfolio? -> Zielvermoegen-Feld suchen
    page.locator(".st-key-pl_nav_ansicht button", has_text="Schritt für Schritt").first.click(); br.warte_ruhe(page, 180)
    page.get_by_role("spinbutton", name="Startkapital (€)").first.fill("20000"); page.keyboard.press("Enter")
    page.wait_for_timeout(2500); br.warte_ruhe(page, 300)
    page.locator(".st-key-pl_nav_ansicht button", has_text="Alle Bereiche").first.click(); br.warte_ruhe(page, 180)
    modelle(page)
    print("Tabelle nach Aenderung:", tabelle(page))
    # gleichen Namen waehlen -> Bestaetigung noetig
    page.locator('[data-testid="stSelectbox"]', has_text="Speichern als").locator("input").click(); page.wait_for_timeout(300)
    page.keyboard.type(NAME); page.keyboard.press("Enter"); page.wait_for_timeout(1500); br.warte_ruhe(page)
    print("Speichern gesperrt ohne Bestaetigung:", page.get_by_role("button", name="💾 Speichern").is_disabled(),
          "| Checkbox:", page.get_by_text(f"Gespeicherte Variante „{NAME}“ mit dem aktuellen Stand überschreiben").count())
    print("Fehler:", [z for z in br.text(page).splitlines() if "Traceback" in z or "Fehler:" in z][:3])
    page.screenshot(path=f"{S}/planer_varianten.png", full_page=True)
    b.close()
