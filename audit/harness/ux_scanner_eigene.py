"""Investment-Scanner: eigene Aufteilung 30/30/30/10 bleibt erhalten (kein Cash-Berg bei unerreichbarem Ziel)."""
import sys, br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch
S = sys.argv[1]
with sync_playwright() as p:
    b, page = frisch(p)
    page.locator(".st-key-pb_zum_scanner button").first.click(); br.warte_ruhe(page, 60)
    eck = page.locator(".st-key-pb_scan_eckdaten").first
    for n, v in (("Startkapital €", "160000"), ("Einzahlung €/Monat", "0"), ("Laufzeit (Jahre)", "5"),
                 ("Zielvermögen €", "1000000")):
        eck.get_by_role("spinbutton", name=n).fill(v); page.keyboard.press("Enter"); page.wait_for_timeout(800)
        br.warte_ruhe(page)
    page.locator(".st-key-pb_scan_profil button", has_text="Eigene").first.click(); page.wait_for_timeout(1200)
    br.warte_ruhe(page)
    for n, v in (("ETFs %", "30"), ("Aktien %", "30"), ("wikifolios %", "30"), ("Cash %", "10"), ("Max. Verlust %", "50")):
        page.get_by_role("spinbutton", name=n).fill(v); page.keyboard.press("Enter"); page.wait_for_timeout(800)
        br.warte_ruhe(page)
    page.locator(".st-key-pb_scan_los button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
    t = br.text(page)
    print("Ziel:", [z[:220] for z in t.splitlines() if "nötig" in z][:1])
    zeile = [z for z in t.splitlines() if z.startswith("Cash / Tagesgeld")]
    print("Cash-Zeile:", zeile[:1])
    print("Fehler:", [z for z in t.splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
