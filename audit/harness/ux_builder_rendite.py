"""Portfolio Builder: junges Wikifolio (nur 1-J.-Daten) ohne Rendite -> Rendite aus dem Katalog, Zielverteilung nutzt sie."""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch, zeilen, tippe_neu

def renditen(page):
    return page.evaluate("""() => [...document.querySelectorAll('.pb-tab tbody tr')].map(r =>
        [...r.querySelectorAll('td')].map(td => td.innerText.trim()))""")

with sync_playwright() as p:
    b, page = frisch(p)
    tippe_neu(page, 4, "Hauptindizes Global")      # neue Zeile ohne Rendite und ohne Kurs
    page.get_by_role("button", name="⚖️ Rebalancing").click(); page.wait_for_timeout(2500); br.warte_ruhe(page)
    for z in zeilen(page): print("   ", z)
    print("Hinweis:", [t for t in page.locator(".pb-hinweis", has_text="Summe").all_inner_texts()][:1])
    page.get_by_label("Zielvermögen €", exact=True).fill("150000"); page.keyboard.press("Enter")
    page.wait_for_timeout(1000); br.warte_ruhe(page)
    page.locator(".st-key-pb_reihe3 [data-testid='stCheckbox'], .st-key-pb_reihe3 label", has_text="Automatisch aufs Ziel").first.click()
    page.wait_for_timeout(2000); br.warte_ruhe(page)
    print("Ziel 150.000 automatisch:")
    for z in zeilen(page): print("   ", z)
    print("Ziel-Status:", page.locator(".pb-status").first.inner_text(), "|",
          [t for t in page.locator(".pb-hinweis", has_text="Nötig").all_inner_texts()][:1])
    page.screenshot(path=sys.argv[1] if len(sys.argv) > 1 else "/dev/null", full_page=True)
    b.close()
