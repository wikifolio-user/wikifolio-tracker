"""Portfolio Builder 2.0: jede Bearbeitungsart der Tabelle einzeln (frische Seite je Fall)."""
import br
from playwright.sync_api import sync_playwright
FAELLE = [("Stück MSCI = 30", 0, 4, "30"), ("Betrag EM = 3000", 1, 3, "3000"),
          ("Gewicht Bitcoin = 25", 2, 2, "25"), ("Kurs MSCI = 200", 0, 1, "200")]
with sync_playwright() as p:
    for name, zeile, spalte, wert in FAELLE:
        b, ctx, page = br.start(p, 1440, 900, False)
        br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
        if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
            page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
        page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
        page.get_by_role("button", name="↺ Standardwerte").click(); br.warte_ruhe(page); page.wait_for_timeout(800)
        grid = page.locator('[data-testid="stDataFrame"]').first
        grid.scroll_into_view_if_needed(); box = grid.bounding_box()
        page.mouse.click(box["x"] + 60, box["y"] + 52 + zeile * 35); page.wait_for_timeout(300)
        for _ in range(spalte):
            page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter"); page.wait_for_timeout(300)
        page.keyboard.press("Control+A"); page.keyboard.type(wert); page.wait_for_timeout(300)
        page.keyboard.press("Enter"); page.wait_for_timeout(2500); br.warte_ruhe(page)
        z = page.evaluate("""(i) => [...document.querySelectorAll('.pb-tab tbody tr')[i].querySelectorAll('td')]
                              .map(td => td.innerText.trim())""", zeile)
        print(f"{name:24s} -> Anteil {z[1]:8s} Stück {z[2]:8s} Kurs {z[3]:10s} Wert {z[4]}", flush=True)
        b.close()
