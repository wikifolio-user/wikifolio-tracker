"""Portfolio Builder 2.0: Werte hinzufuegen (Katalog, Suche), Doppelschutz, Kurse aktualisieren."""
import sys
import br
from playwright.sync_api import sync_playwright

def zeilen(page):
    return page.evaluate("""() => [...document.querySelectorAll('.pb-tab tbody tr')].map(r =>
        [...r.querySelectorAll('td')].map(td => td.innerText.trim()).join(' | '))""")

def waehle(page, label_teil, text):
    sb = page.locator('[data-testid="stSelectbox"]', has_text=label_teil).first
    sb.locator("input").click(); page.wait_for_timeout(300)
    page.keyboard.type(text); page.wait_for_timeout(500)
    page.keyboard.press("Enter"); page.wait_for_timeout(1200); br.warte_ruhe(page)

def hinzufuegen(page):
    page.locator(".st-key-pb_add button", has_text="Hinzufügen").first.click()
    page.wait_for_timeout(1500); br.warte_ruhe(page); page.wait_for_timeout(500)

with sync_playwright() as p:
    w = 375 if "handy" in sys.argv else 1440
    b, ctx, page = br.start(p, w, 900, w < 600)
    br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
    if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
    page.get_by_role("button", name="↺ Standardwerte").click(); br.warte_ruhe(page); page.wait_for_timeout(600)
    # 1) Aktien-Filter, NVIDIA aus dem Katalog, Gewicht 10
    page.locator(".st-key-pb_add button", has_text="Aktien").first.click(); br.warte_ruhe(page); page.wait_for_timeout(400)
    print("Auswahl-Label:", page.locator(".st-key-pb_add [data-testid='stSelectbox'] label").first.inner_text())
    waehle(page, "Wert (", "NVIDIA")
    page.locator(".st-key-pb_add input[aria-label='Gewicht %']").fill("10"); page.keyboard.press("Enter")
    page.wait_for_timeout(800); br.warte_ruhe(page)
    hinzufuegen(page)
    print("Meldung:", [t for t in page.locator("[data-testid='stAlert']").all_inner_texts()][:2])
    print("Zeilen:", zeilen(page))
    # 2) Suche: SAP
    page.locator(".st-key-pb_add button", has_text="Alle").first.click(); br.warte_ruhe(page)
    waehle(page, "Wert (", "Nicht dabei")
    page.get_by_label("Name, WKN oder ISIN").fill("SAP"); page.keyboard.press("Enter")
    page.wait_for_timeout(1500); br.warte_ruhe(page)
    hinzufuegen(page)
    print("nach Suche:", zeilen(page)[-3:])
    # 3) Doppelt
    waehle(page, "Wert (", "NVIDIA")
    hinzufuegen(page)
    print("Doppelt:", [t for t in page.locator("[data-testid='stAlert']").all_inner_texts()][:2])
    # 4) Kurse aktualisieren
    page.get_by_role("button", name="🔄 Kurse aktualisieren").click(); page.wait_for_timeout(2500); br.warte_ruhe(page)
    print("nach Kurs-Update:", zeilen(page))
    print("Nach Art:", page.locator(".pb-hinweis", has_text="Nach Art").first.inner_text())
    page.screenshot(path=sys.argv[1], full_page=True)
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
