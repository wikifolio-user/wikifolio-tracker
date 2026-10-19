"""Portfolio Builder 2.0: Top-100-Rangliste anzeigen, Zeilen anhaken, uebernehmen."""
import sys
import br
from playwright.sync_api import sync_playwright

def zeilen(page):
    return page.evaluate("""() => [...document.querySelectorAll('.pb-tab tbody tr')].map(r =>
        [...r.querySelectorAll('td')].map(td => td.innerText.trim()).join(' | '))""")

with sync_playwright() as p:
    w = 375 if "handy" in sys.argv else 1440
    b, ctx, page = br.start(p, w, 900, w < 600)
    br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
    if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
    page.get_by_role("button", name="↺ Standardwerte").click(); br.warte_ruhe(page); page.get_by_role("button", name="Ja, zurücksetzen").click(); br.warte_ruhe(page); page.wait_for_timeout(600)
    # Gewichte frei machen: Bitcoin + Tagesgeld auf 0 -> 20 % Rest
    page.get_by_role("tab", name="🏆 Top-Listen").click(); page.wait_for_timeout(800)
    print("Label:", page.locator(".st-key-pb_add label", has_text="sortiert nach").first.inner_text())
    grid = page.locator(".st-key-pb_add [data-testid='stDataFrame']").first
    grid.scroll_into_view_if_needed(); page.wait_for_timeout(400)
    box = grid.bounding_box()
    page.screenshot(path=sys.argv[1], clip={"x": 0, "y": max(box["y"] - 220, 0), "width": w, "height": box["height"] + 320})
    for i in (0, 1, 2):                                     # Kaestchen der ersten drei Zeilen
        page.mouse.click(box["x"] + 14, box["y"] + 35 + 17 + i * 35); page.wait_for_timeout(1200); br.warte_ruhe(page)
        grid = page.locator(".st-key-pb_add [data-testid='stDataFrame']").first; box = grid.bounding_box()
    knopf = page.locator(".st-key-pb_add button", has_text="ausgewählte hinzufügen").first
    print("Knopf:", knopf.inner_text())
    knopf.click(); page.wait_for_timeout(1500); br.warte_ruhe(page); page.wait_for_timeout(500)
    print("Meldung:", page.locator("[data-testid='stAlert']").all_inner_texts()[:1])
    print("Positionen:", zeilen(page)[-5:])
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
