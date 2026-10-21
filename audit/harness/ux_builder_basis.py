"""Portfolio Builder: Wikifolio-Renditen auf 1-Jahres-Basis, junge Werte hochgerechnet, Spalte Basis."""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch, zeilen, tippe_neu

with sync_playwright() as p:
    b, page = frisch(p)
    for i, name in enumerate(("FF Inlinetrading", "Hauptindizes Global", "Global Wealth Concentrated")):
        tippe_neu(page, 4 + i, name)
        page.wait_for_timeout(3000); br.warte_ruhe(page, 60)
    page.wait_for_timeout(2500); br.warte_ruhe(page)
    for z in zeilen(page): print("   ", z)
    grid = page.locator('[data-testid="stDataFrame"]').locator('visible=true').first
    grid.scroll_into_view_if_needed(); page.mouse.move(0, 0); page.wait_for_timeout(400)
    grid.screenshot(path=f"{sys.argv[1]}_1j.png")
    sb = page.locator(".st-key-pb_reihe_basis input").first
    sb.click(); page.wait_for_timeout(300); page.keyboard.type("Längster"); page.keyboard.press("Enter")
    page.wait_for_timeout(2500); br.warte_ruhe(page)
    grid = page.locator('[data-testid="stDataFrame"]').locator('visible=true').first
    grid.scroll_into_view_if_needed(); page.mouse.move(0, 0); page.wait_for_timeout(400)
    grid.screenshot(path=f"{sys.argv[1]}_lang.png")
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
