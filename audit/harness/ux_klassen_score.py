"""Watchlist -> 🏅 ETF- & wikifolio-Score: ETFs/wikifolios, Teilpunkte, Wischen, PDF; Scanner 2.0 Score."""
import re
import sys
import br
from playwright.sync_api import sync_playwright
from ux_wikifolios import oeffne
S = sys.argv[1]
BREITEN = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [390, 820, 1440]
for w in BREITEN:
    with sync_playwright() as p:
        b, ctx, page = br.start(p, w, 1180 if w < 1100 else 900, w < 1100)
        br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
        oeffne(page, "Watchlist")
        page.locator("[data-testid=stButtonGroup] button", has_text="ETF- & wikifolio-Score").first.click()
        page.wait_for_timeout(1500); br.warte_ruhe(page)
        for art in ("ETFs", "wikifolios"):
            page.locator("[data-testid=stButtonGroup] button").filter(has_text=re.compile(rf"^\s*{art}\s*$")).first.click(); page.wait_for_timeout(1200); br.warte_ruhe(page)
            t = br.text(page)
            print(w, art, [z for z in t.splitlines() if z.startswith("Stand ")][:1])
            print(w, art, "Zeilen:", page.locator("table.ks tbody tr").count(), "| 1.:",
                  page.locator("table.ks tbody tr").first.inner_text().replace("\n", " | ")[:200])
            wrap = page.locator(".ue-wrap:has(table.ks)").first
            print(w, art, "scroll", wrap.evaluate("e => [e.scrollWidth, e.clientWidth]"))
            wrap.scroll_into_view_if_needed(); page.wait_for_timeout(300)
            page.screenshot(path=f"{S}/ks_{w}_{art}.png")
        page.locator("summary", has_text="Wie wird bewertet").first.click(); page.wait_for_timeout(600)
        page.locator("summary", has_text="Wie wird bewertet").first.scroll_into_view_if_needed()
        page.screenshot(path=f"{S}/ks_{w}_info.png")
        page.locator("button", has_text="PDF der ganzen Liste").click(); br.warte_ruhe(page, 60)
        with page.expect_download() as dl:
            page.locator("button", has_text="PDF herunterladen").click()
        dl.value.save_as(f"{S}/ks_{w}.pdf")
        print(w, "PDF", open(f"{S}/ks_{w}.pdf", "rb").read(4))
        print(w, "Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3],
              [k for k in page.konsole if "error" in k.lower()][:3])
        b.close()
