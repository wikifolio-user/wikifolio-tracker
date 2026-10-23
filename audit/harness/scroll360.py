import br
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright
JS = """() => { const m = document.querySelector('[data-testid=stMain]'); const h = document.querySelector('.st-key-kopf, [class*=st-key-kopf]');
  const k = [...document.querySelectorAll('button')].find(b => b.innerText.trim() === '☰ Menü');
  return {win: scrollY, main: m ? m.scrollTop : null, menuTop: k ? Math.round(k.getBoundingClientRect().top) : null}; }"""
with sync_playwright() as p:
    b, ctx, page = br.start(p, 375, 667, True)
    br.login(page, "admin", "Admin-Test-Passwort-1"); page.wait_for_timeout(800)
    for a in ("Investment Scanner Pro", "Abfindungsrechner", "Watchlist", "Zinseszinsrechner", "Depot verwalten"):
        if not page.locator(".st-key-nav_menue button", has_text=a).first.is_visible():
            page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
            print("  Menü:", page.evaluate(JS))
        page.locator(".st-key-nav_menue button", has_text=a).first.click(); br.warte_ruhe(page, 120); page.wait_for_timeout(1500)
        print(a, page.evaluate(JS))
        page.evaluate("() => { const m = document.querySelector('[data-testid=stMain]'); m && m.scrollBy(0, 900); scrollBy(0, 900); }")
        page.wait_for_timeout(300)
    b.close()
