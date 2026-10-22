import br
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p, 390, 844, True)
    br.login(page, "admin", "Admin-Test-Passwort-1"); page.wait_for_timeout(800)
    page.locator(".st-key-nav_menue button", has_text="Zukunfts-Prognose").first.click(); br.warte_ruhe(page)
    print(page.evaluate("""() => [...document.querySelectorAll('[data-testid=stTooltipIcon]')].slice(0,4).map(e => [e.parentElement.getAttribute('data-testid'), e.parentElement.tagName, e.outerHTML.slice(0,300)])"""))
    b.close()
