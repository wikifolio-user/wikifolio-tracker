"""Portfolio Builder: neue Werte mit 0 % in ein schon zu 100 % verteiltes Portfolio -> automatisch Anteil + Stueck."""
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

def frisch(p):
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
    if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
    page.get_by_role("button", name="↺ Standardwerte").click(); br.warte_ruhe(page)
    page.get_by_role("button", name="Ja, zurücksetzen").click(); br.warte_ruhe(page); page.wait_for_timeout(800)
    print("nach Reset:", [z.split(" | ")[:2] for z in zeilen(page)])
    return b, page

def tippe_neu(page, zeile, wert):
    """Neue Zeile: Zelle anklicken und direkt tippen (Tippen startet die Bearbeitung)."""
    grid = page.locator('[data-testid="stDataFrame"]').locator('visible=true').first
    grid.scroll_into_view_if_needed(); box = grid.bounding_box()
    page.mouse.click(box["x"] + 60, box["y"] + 52 + zeile * 35); page.wait_for_timeout(400)
    page.keyboard.type(wert, delay=60); page.wait_for_timeout(300)
    page.keyboard.press("Enter"); page.wait_for_timeout(2500); br.warte_ruhe(page)

def zelle(page, zeile, spalte, wert):
    grid = page.locator('[data-testid="stDataFrame"]').locator('visible=true').first
    grid.scroll_into_view_if_needed(); box = grid.bounding_box()
    page.mouse.click(box["x"] + 60, box["y"] + 52 + zeile * 35); page.wait_for_timeout(400)
    for _ in range(spalte):
        page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter"); page.wait_for_timeout(300)
    page.keyboard.press("Control+A"); page.keyboard.type(wert); page.wait_for_timeout(300)
    page.keyboard.press("Enter"); page.wait_for_timeout(2500); br.warte_ruhe(page)

with sync_playwright() as p:
    # A) ueber "Hinzufuegen" mit Gewicht 0
    b, page = frisch(p)
    waehle(page, "Wert (", "NVIDIA")
    print("Vorschlag Gewicht:", page.locator(".st-key-pb_add input[aria-label='Gewicht %']").input_value())
    page.locator(".st-key-pb_add input[aria-label='Gewicht %']").fill("0"); page.keyboard.press("Enter")
    page.wait_for_timeout(800); br.warte_ruhe(page)
    hinzufuegen(page)
    print("A Meldung:", [t for t in page.locator("[data-testid='stAlert']").all_inner_texts()][:1])
    for z in zeilen(page): print("   ", z)
    b.close()
    # B) neue Tabellenzeile: nur Name + Kurs
    b, page = frisch(p)
    tippe_neu(page, 4, "Gold")
    print("B nach Name:", zeilen(page)[4])
    zelle(page, 4, 3, "50")
    print("B Tabelle:")
    for z in zeilen(page): print("   ", z)
    print("Rendite zeigt None:", page.evaluate("""() => [...document.querySelectorAll('[data-testid="stDataFrame"]')]
          .filter(e => e.offsetParent).map(e => e.innerText.includes('None'))"""))
    b.close()
    # C) Automatisch aufs Ziel + neuer Wert mit 0 %
    b, page = frisch(p)
    page.get_by_label("Zielvermögen €", exact=True).fill("25000"); page.keyboard.press("Enter")
    page.wait_for_timeout(1000); br.warte_ruhe(page)
    page.get_by_text("Automatisch aufs Ziel").click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
    waehle(page, "Wert (", "NVIDIA")
    page.locator(".st-key-pb_add input[aria-label='Gewicht %']").fill("0"); page.keyboard.press("Enter")
    page.wait_for_timeout(800); br.warte_ruhe(page)
    hinzufuegen(page)
    print("C Tabelle (auto):")
    for z in zeilen(page): print("   ", z)
    page.screenshot(path=sys.argv[1] if len(sys.argv) > 1 else "/dev/null", full_page=True)
    b.close()
