"""Planer: Hoechstgewicht je Baustein, automatisch ergaenzte Werte, Varianten speichern ohne Ueberschreiben."""
import sys, re
import br
from playwright.sync_api import sync_playwright
S = sys.argv[1]

def fehler(page):
    return [z for z in br.text(page).splitlines() if "Traceback" in z or "Error" in z or "Fehler im" in z][:3]

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 1000, False)
    br.login(page, "maria", "Maria-Test-Pass-1")
    page.locator(".st-key-nav_menue button", has_text="Portfolio-Planer").first.click(); br.warte_ruhe(page, 180)
    page.locator(".st-key-pl_nav_ansicht button", has_text="Schritt für Schritt").first.click(); br.warte_ruhe(page, 180)
    for name, wert in (("Startkapital (€)", "50000"), ("Monatliche Sparrate (€)", "500"), ("Dauer Aufbau (Jahre)", "15")):
        page.get_by_role("spinbutton", name=name).first.fill(wert); page.keyboard.press("Enter")
        page.wait_for_timeout(1200); br.warte_ruhe(page, 180)
    page.get_by_role("spinbutton", name="Zielvermögen am Ende (€)").fill("1000000"); page.keyboard.press("Enter")
    page.wait_for_timeout(1500); br.warte_ruhe(page, 180)
    feld = page.get_by_role("spinbutton", name="Max. je Baustein (% vom Gesamtbetrag)")
    print("Feld Max je Baustein:", feld.count())
    feld.fill("10"); page.keyboard.press("Enter"); page.wait_for_timeout(1500); br.warte_ruhe(page, 180)
    sw = page.locator("label", has_text="Passende Werte automatisch ergänzen").locator("input")
    print("Schalter:", sw.count(), [x.get_attribute("disabled") for x in sw.all()])
    print(page.locator("label", has_text="Passende Werte automatisch ergänzen").first.evaluate("e => e.closest('[data-testid]').outerHTML.slice(0,600)"))
    sw.first.click(force=True, timeout=5000); page.wait_for_timeout(3000); br.warte_ruhe(page, 300)
    print("Schalter an:", sw.first.is_checked())
    t = br.text(page)
    print("Meldung:", [z for z in t.splitlines() if "Automatisch ergänzt" in z][:2])
    print("Fehler:", fehler(page))
    page.screenshot(path=f"{S}/planer_auto.png", full_page=True)
    page.locator(".st-key-pl_nav_schritt button").nth(1).click(); br.warte_ruhe(page, 180)
    t = br.text(page)
    gew = [float(x.replace(",", ".")) for x in re.findall(r"\n(\d+[.,]\d)\n", t)]
    print("Bausteine-Seite Fehler:", fehler(page), "Gewichte gefunden:", gew[:20])
    page.screenshot(path=f"{S}/planer_bausteine.png", full_page=True)
    b.close()
