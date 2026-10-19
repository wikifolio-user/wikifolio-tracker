"""Portfolio Builder: Renditen fuer Wikifolios aus Katalog, Ranglisten (Top 500) bzw. Kurshistorie."""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch, zeilen, tippe_neu

def rendite_zellen(page):
    # Rendite steht in der Tabelle (Canvas) - ueber die Kennzahlen-Zeile "Portfolio: x % p. a." pruefen
    return [t for t in page.locator(".pb-hinweis").all_inner_texts() if "Renditedaten" in t or "Nötig" in t]

with sync_playwright() as p:
    b, page = frisch(p)
    tippe_neu(page, 4, "FF Inlinetrading")
    tippe_neu(page, 5, "Hauptindizes Global")
    page.wait_for_timeout(2000); br.warte_ruhe(page)
    page.get_by_label("Zielvermögen €", exact=True).fill("150000"); page.keyboard.press("Enter")
    page.wait_for_timeout(1000); br.warte_ruhe(page)
    page.locator(".st-key-pb_reihe3 [data-testid='stCheckbox'], .st-key-pb_reihe3 label", has_text="Automatisch aufs Ziel").first.click()
    page.wait_for_timeout(2500); br.warte_ruhe(page)
    for z in zeilen(page): print("   ", z)
    for t in rendite_zellen(page): print("Hinweis:", t[:300])
    page.screenshot(path=sys.argv[1] if len(sys.argv) > 1 else "/dev/null", full_page=True)
    b.close()
