"""Watchlist: Reiter 🧩 Wikifolios (Top 500, alle Zeitraeume, Seiten, Suche) + Builder-Startbeispiel mit echten Produkten."""
import sys
import br
from playwright.sync_api import sync_playwright
S = sys.argv[1] if len(sys.argv) > 1 else "."

def oeffne(page, name):
    if not page.locator(".st-key-nav_menue button", has_text=name).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=name).first.click(); br.warte_ruhe(page, 60)

if __name__ == '__main__':
 for w in (1440, 390):
     with sync_playwright() as p:
         b, ctx, page = br.start(p, w, 900, w < 600)
         br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
         oeffne(page, "Watchlist")
         page.locator("[data-testid=stButtonGroup] button", has_text="Wikifolios").first.click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
         t = br.text(page)
         print(w, [z for z in t.splitlines() if z.startswith("Stand ")][:1])
         kopf = page.locator("table.pt thead").first.inner_text().replace("\n", " ")
         print(w, "Kopf:", kopf)
         print(w, "Zeilen:", page.locator("table.pt tbody tr").count())
         page.locator("table.pt").first.screenshot(path=f"{S}/wk_{w}.png")
         page.locator("button", has_text="▶").locator("visible=true").last.click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
         print(w, "Seite 2 erster Rang:", page.locator("table.pt tbody tr td").first.inner_text())
         page.locator("[data-testid=stButtonGroup] button", has_text="3 Jahre").first.click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
         print(w, "3 Jahre, Rang 1:", page.locator("table.pt tbody tr").first.inner_text().replace("\n", " | ")[:120])
         page.get_by_label("In der Liste suchen").fill("Hauptindizes"); page.keyboard.press("Enter")
         page.wait_for_timeout(1500); br.warte_ruhe(page)
         page.locator("[data-testid=stButtonGroup] button").filter(has_text="1 Jahr").first.click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
         print(w, "Suche:", page.locator("table.pt tbody tr").first.inner_text().replace("\n", " | ")[:140])
         print(w, "Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
         b.close()
