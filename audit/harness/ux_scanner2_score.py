"""Scanner 2.0: ETFs/wikifolios mit eigenem Score in der Score-Tabelle und in den Teilbewertungen."""
import sys, br
from playwright.sync_api import sync_playwright
from ux_scanner2 import oeffne
S = sys.argv[1]
with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "admin", "Admin-Test-Passwort-1"); br.warte_ruhe(page, 120)
    oeffne(page, "Scanner 2.0"); page.wait_for_timeout(1500)
    t = br.text(page)
    print("Caption:", [z[:220] for z in t.splitlines() if "Werten bewertbar" in z][:1])
    karte = page.locator("text=Investment-Score · transparente Auswahl").first
    karte.scroll_into_view_if_needed()
    tab = page.locator("table").filter(has_text="Daten").last
    print("Score-Tabelle:", tab.inner_text().replace("\n", " | ")[:700])
    sel = page.get_by_label("Teilbewertungen")
    sel.click(); page.wait_for_timeout(500)
    opts = page.locator("[role=option]").all_inner_texts()
    ziel = next((o for o in opts if "ETF" in o or "Wikifolio" in o or "wikifolio" in o), None)
    print("Optionen:", opts[:12], "->", ziel)
    if ziel:
        page.locator("[role=option]", has_text=ziel).first.click(); page.wait_for_timeout(1200); br.warte_ruhe(page)
        print("Teilbewertung:", page.locator("table").filter(has_text="Faktor").last.inner_text().replace("\n", " | ")[:400])
    page.locator("text=Investment-Score · transparente Auswahl").first.scroll_into_view_if_needed()
    page.screenshot(path=f"{S}/scanner2_score.png")
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
