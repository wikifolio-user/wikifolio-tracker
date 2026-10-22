"""wikifolio-Rangliste: seitlich wischen am iPhone, Rang+Name fix, PDF-Knopf."""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_wikifolios import oeffne
S = sys.argv[1]
for w in (390, 1440):
    with sync_playwright() as p:
        b, ctx, page = br.start(p, w, 900, w < 600)
        br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
        oeffne(page, "Watchlist")
        page.locator("[data-testid=stButtonGroup] button", has_text="Wikifolios").first.click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
        wrap = page.locator(".ue-wrap").first
        print(w, "scrollWidth/clientWidth:", wrap.evaluate("e => [e.scrollWidth, e.clientWidth]"))
        wrap.scroll_into_view_if_needed(); page.wait_for_timeout(300)
        page.screenshot(path=f"{S}/wk_scroll_{w}_a.png")
        wrap.evaluate("e => e.scrollLeft = 2000"); page.wait_for_timeout(400)
        print(w, "scrollLeft:", wrap.evaluate("e => e.scrollLeft"))
        print(w, "Name-Spalte x:", page.locator("table.wk tbody tr td.wk-name").first.bounding_box()["x"],
              "Rang x:", page.locator("table.wk tbody tr td.wk-rang").first.bounding_box()["x"])
        page.screenshot(path=f"{S}/wk_scroll_{w}_b.png")
        page.locator("button", has_text="PDF der ganzen Liste").click(); br.warte_ruhe(page, 60)
        with page.expect_download() as dl:
            page.locator("button", has_text="PDF herunterladen").click()
        dl.value.save_as(f"{S}/wk_{w}.pdf")
        print(w, "PDF ok", open(f"{S}/wk_{w}.pdf", "rb").read(4))
        print(w, "Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
        b.close()
