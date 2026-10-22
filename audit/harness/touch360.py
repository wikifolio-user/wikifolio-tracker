import br, sys, collections
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright
from ux_mess import MESS_JS
c = collections.Counter()
with sync_playwright() as p:
    b, ctx, page = br.start(p, 375, 667, True)
    br.login(page, "admin", "Admin-Test-Passwort-1"); page.wait_for_timeout(800)
    namen = page.evaluate("""() => [...document.querySelectorAll('.st-key-nav_menue button')].map(b => b.innerText.trim())
        .filter(t => t && !t.includes('aktualisieren') && !t.includes('Abmelden') && !t.includes('logout'))""")
    for a in namen:
        if not page.locator(".st-key-nav_menue button", has_text=a).first.is_visible():
            page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
        page.locator(".st-key-nav_menue button", has_text=a).first.click(); br.warte_ruhe(page, 120)
        m = page.evaluate(MESS_JS, True)
        for k in m["klein"]:
            c[k.split(" (")[0][:28] + " (" + k.split(" (")[-1]] += 1
for k, n in c.most_common(40): print(n, k)
