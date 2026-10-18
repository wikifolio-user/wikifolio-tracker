import br
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    for name, w, h, t in [("iphone-se", 375, 667, True), ("ipad-hoch", 768, 1024, True), ("ipad-quer", 1024, 768, True), ("laptop", 1440, 900, False)]:
        b, ctx, page = br.start(p, w, h, t)
        br.login(page, "admin", "Admin-Test-Passwort-1"); br.ansicht(page, "Depot")
        r = page.evaluate("""() => [...document.querySelectorAll('.st-key-depot_spalten [data-testid=stColumn]')].slice(0,2)
              .map(c => { const b = c.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width)]; })""")
        modebar = page.evaluate("() => [...document.querySelectorAll('.modebar-container')].filter(e => e.offsetParent).length")
        print(f"{name:10} Spalten [links,oben,breite]: {r}")
        page.screenshot(path=f"{br.SHOTS}/spalten_{name}.png")
        b.close()
