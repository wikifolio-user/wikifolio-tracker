import br
from playwright.sync_api import sync_playwright
FOKUS = """() => { const e = document.activeElement; const s = getComputedStyle(e);
  return {name: ((e.innerText || e.getAttribute('aria-label') || e.placeholder || e.tagName) + '').trim().slice(0, 30),
          outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 1, tag: e.tagName}; }"""
with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900)
    page.goto(br.URL); page.get_by_placeholder("Benutzername eingeben").wait_for(timeout=60000); br.warte_ruhe(page)
    # Login nur per Tastatur
    for i in range(6):
        page.keyboard.press("Tab")
        if "Benutzername" in page.evaluate(FOKUS)["name"]: break
    print("Tabs bis Benutzername:", i + 1)
    page.keyboard.type("maria"); page.keyboard.press("Tab")
    page.keyboard.type("Maria-Test-Pass-1"); page.keyboard.press("Enter"); br.warte_ruhe(page)
    print("Login per Tastatur:", "Test-Depot" in br.text(page))
    weg = []
    for i in range(12):
        page.keyboard.press("Tab"); f = page.evaluate(FOKUS); weg.append(f"{f['name']}{'' if f['outline'] else ' (KEIN Fokusrahmen)'}")
    print("Tab-Reihenfolge Startseite:", weg)
    # bis "Zinseszinsrechner" tabben und Enter
    for i in range(40):
        f = page.evaluate(FOKUS)
        if "Zinseszins" in f["name"]: break
        page.keyboard.press("Tab")
    page.keyboard.press("Enter"); br.warte_ruhe(page)
    print("Ansicht per Enter geöffnet:", "Zinseszinsrechner" in br.text(page)[:200])
    # zurück zum Menü per Tastatur
    page.keyboard.press("Shift+Tab")
    for i in range(60):
        f = page.evaluate(FOKUS)
        if "Menü" in f["name"] and f["tag"] == "BUTTON": break
        page.keyboard.press("Tab")
    print("Menü-Knopf erreicht:", page.evaluate(FOKUS))
    page.keyboard.press("Enter"); br.warte_ruhe(page)
    print("Zurück im Menü:", "FINANZ" in br.text(page)[:60])
    page.screenshot(path=f"{br.SHOTS}/ux_fokus.png")
    b.close()
