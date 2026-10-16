import br, time
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "leser", "Leser-Pass-123")
    dt = br.ansicht(page, "Zinseszins")
    html = page.content()
    for s in ["Depotwert", "DEPOTWERT", "Hauptindizes Global", "Positionen verwalten", "150,000", "Sparrate"]:
        print(f"{s!r} im DOM: {s in html}")
    print("Zinsrechner geladen in %.1fs" % dt)
    b.close()
