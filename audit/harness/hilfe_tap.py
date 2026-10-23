import br
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p, 390, 844, True)
    br.login(page, "admin", "Admin-Test-Passwort-1"); page.wait_for_timeout(800)
    page.locator(".st-key-nav_menue button", has_text="Zukunfts-Prognose").first.click(); br.warte_ruhe(page)
    icon = page.locator("[data-testid=stTooltipIcon]").filter(visible=True).first
    print("Hilfe-Icons sichtbar:", page.locator("[data-testid=stTooltipIcon]").filter(visible=True).count())
    bb = icon.bounding_box(); print("Größe:", bb)
    icon.tap(); page.wait_for_timeout(800)
    tip = page.locator("[data-testid=stTooltipContent], [role=tooltip]").filter(visible=True)
    print("Tooltip nach Antippen sichtbar:", tip.count(), tip.first.inner_text()[:80] if tip.count() else "")
    page.screenshot(path="hilfe_tap.png")
    b.close()
