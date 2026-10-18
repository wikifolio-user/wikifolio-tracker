"""Was sieht man waehrend eines Klicks? Screenshots alle 150 ms nach einem Schrittwechsel im Planer."""
import sys, br
from playwright.sync_api import sync_playwright
AUS = sys.argv[1]
with sync_playwright() as p:
    b, ctx, page = br.start(p, 375, 667, True)
    br.login(page, "admin", "Admin-Test-Passwort-1"); page.wait_for_timeout(1500)
    if not page.locator(".st-key-nav_menue button", has_text="Portfolio-Planer").first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text="Portfolio-Planer").first.click(); br.warte_ruhe(page, 120)
    for nr, i in enumerate([1, 2, 3]):
        page.locator(".st-key-pl_nav_schritt button").nth(i).click()
        for t in range(10):
            page.screenshot(path=f"{AUS}/k{nr}_{t:02d}.png"); page.wait_for_timeout(150)
        br.warte_ruhe(page)
    b.close()
