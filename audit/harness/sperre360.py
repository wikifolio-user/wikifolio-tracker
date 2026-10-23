import br
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    for i in range(7):
        page.goto(br.URL); page.get_by_placeholder("Benutzername eingeben").wait_for()
        page.get_by_placeholder("Benutzername eingeben").fill("neu"); page.get_by_placeholder("Passwort eingeben").fill(f"falsch{i}")
        page.get_by_role("button", name="Anmelden").click(); br.warte_ruhe(page)
        t = page.locator("body").inner_text()
        print(i + 1, [z for z in t.splitlines() if "falsch" in z.lower() or "gesperrt" in z.lower() or "warte" in z.lower() or "versuch" in z.lower()][:2])
    page.goto(br.URL); page.get_by_placeholder("Benutzername eingeben").wait_for()
    page.get_by_placeholder("Benutzername eingeben").fill("neu"); page.get_by_placeholder("Passwort eingeben").fill("Neu-Test-Pass-12")
    page.get_by_role("button", name="Anmelden").click(); br.warte_ruhe(page)
    t = page.locator("body").inner_text()
    print("richtiges Passwort während Sperre angemeldet:", "Menü" in t and "Benutzername eingeben" not in page.content())
    b.close()
