"""Portfolio Builder: Top-Listen - Wikifolios Top 500, Zeitraum, Seiten, Suche, Hinzufuegen (Laptop + Handy)."""
import sys
import br
from playwright.sync_api import sync_playwright

def waehle(page, schluessel, text):
    sb = page.locator(f".st-key-{schluessel} input").first
    sb.click(); page.wait_for_timeout(300); page.keyboard.type(text); page.wait_for_timeout(400)
    page.keyboard.press("Enter"); page.wait_for_timeout(1200); br.warte_ruhe(page)

def hinweis(page):
    br.warte_ruhe(page)
    t = page.locator(".st-key-pb_add").first.inner_text().splitlines()
    return next((z for z in t if z.startswith("Top ") or "nicht unter den Top" in z), "?")

def bereich(page):
    el = page.locator(".st-key-pb_top_nav [data-baseweb='select']").first
    return el.text_content() if el.count() else "(keine Seiten)"

if __name__ == "__main__":
  for w in (1440, 390):
      with sync_playwright() as p:
          b, ctx, page = br.start(p, w, 900, w < 600)
          br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
          if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
              page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
          page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
          page.locator(".st-key-pb_add button", has_text="Wikifolios").first.click(); br.warte_ruhe(page)
          page.get_by_role("tab", name="🏆 Top-Listen").click(); page.wait_for_timeout(800); br.warte_ruhe(page)
          waehle(page, "pb_top_krit", "1 Jahr")
          waehle(page, "pb_top_n", "Top 500")
          print(w, "Hinweis:", hinweis(page)[:80])
          print(w, "Seite:", bereich(page))
          grid = page.locator(".st-key-pb_add [data-testid='stDataFrame']").locator("visible=true").first
          print(w, "Tabellenhoehe:", round(grid.bounding_box()["height"]))
          br.warte_ruhe(page); page.locator(".st-key-pb_top_vor button").locator("visible=true").last.click(); page.wait_for_timeout(1200); br.warte_ruhe(page)
          print(w, "nach ▶:", bereich(page))
          waehle(page, "pb_top_nav", "Rang 481")
          print(w, "Sprung:", bereich(page))
          page.locator(".st-key-pb_top_reihe input[aria-label='In der Liste suchen']").fill("Bergsteiger")
          page.keyboard.press("Enter"); page.wait_for_timeout(1500); br.warte_ruhe(page)
          print(w, "Suche:", hinweis(page)[:90], "|", bereich(page))
          page.locator(".st-key-pb_add").screenshot(path=f"{sys.argv[1]}_{w}.png")
          # erste Zeile anhaken und hinzufuegen
          grid = page.locator(".st-key-pb_add [data-testid='stDataFrame']").locator("visible=true").first
          box = grid.bounding_box()
          page.mouse.click(box["x"] + 14, box["y"] + 38 + 17); page.wait_for_timeout(1200); br.warte_ruhe(page)
          page.locator(".st-key-pb_top_btn button").locator("visible=true").last.click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
          print(w, "Meldung:", [t for t in page.locator("[data-testid='stAlert']").all_inner_texts()][:1])
          print(w, "Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
          b.close()
