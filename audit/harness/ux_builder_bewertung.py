"""Portfolio Builder: Spalte Bewertung (Score + Urteil) in der Positionen-Tabelle (Laptop + Handy)."""
import sys, br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch
S = sys.argv[1]
with sync_playwright() as p:
    b, page = frisch(p)
    # Musterdepot aus dem Scanner uebernehmen -> viele Werte aus den Watchlist-Daten
    page.locator(".st-key-pb_zum_scanner button").first.click(); br.warte_ruhe(page, 60)
    page.locator(".st-key-pb_scan_los button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
    page.locator(".st-key-pb_scan_uebernehmen button").first.click(); page.wait_for_timeout(3000); br.warte_ruhe(page, 120)
    zeilen = page.evaluate("""() => [...document.querySelectorAll('.pb-tab')].map(t => [...t.querySelectorAll('tr')]
        .slice(0, 6).map(r => r.innerText.replace(/\\s+/g, ' ')))""")
    for t in zeilen: print(t)
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    page.set_viewport_size({"width": 390, "height": 900}); page.wait_for_timeout(1000)
    print("Ueberlauf Handy:", page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 1"))
    b.close()
