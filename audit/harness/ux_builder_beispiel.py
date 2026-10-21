"""Builder: Startbeispiel mit echten Produkten - Kurse live, Renditen mit Basis."""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch, zeilen
with sync_playwright() as p:
    b, page = frisch(p)
    page.wait_for_timeout(2500); br.warte_ruhe(page, 60)
    for z in zeilen(page): print("   ", z)
    grid = page.locator('[data-testid="stDataFrame"]').locator('visible=true').first
    grid.scroll_into_view_if_needed(); page.mouse.move(0, 0); page.wait_for_timeout(400)
    grid.screenshot(path=sys.argv[1])
    b.close()
