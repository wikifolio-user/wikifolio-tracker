"""Bleiben Eingaben in allen Ansichten nach einem Ansichtswechsel erhalten? (synthetische Testnutzer)"""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_merken import oeffne

def zahlfelder(page):
    return page.locator("[data-testid='stNumberInput'] input:visible")

def probe(page, ansicht, wert):
    oeffne(page, ansicht)
    f = zahlfelder(page)
    n = f.count()
    if not n:
        print(f"{ansicht:22} keine Zahlfelder"); return
    lab = f.first.get_attribute("aria-label")
    f.first.fill(str(wert)); page.keyboard.press("Enter"); page.wait_for_timeout(1200); br.warte_ruhe(page)
    feld = lambda: page.get_by_label(lab, exact=True).locator("visible=true").first
    vorher = feld().input_value()
    oeffne(page, "Depot")
    oeffne(page, ansicht)
    nachher = feld().input_value() if feld().count() else "fehlt"
    print(f"{ansicht:22} {lab[:28]:28} Felder {n:2}  eingegeben {vorher:>10}  nach Wechsel {nachher:>10}  {'OK' if vorher == nachher else 'VERLOREN'}")

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, sys.argv[1] if len(sys.argv) > 1 else "admin", sys.argv[2] if len(sys.argv) > 2 else "Admin-Test-Passwort-1")
    page.wait_for_timeout(1500)
    for a, w in (("Zukunfts-Prognose", 12345), ("Szenario-Simulator", 23456), ("Portfolio-Planer", 4321), ("Zinseszinsrechner", 7777),
                 ("Abfindungsrechner", 52), ("Portfolio Builder", 9999)):
        try:
            probe(page, a, w)
        except Exception as e:
            print(a, "Fehler", type(e).__name__, str(e)[:150])
    b.close()
