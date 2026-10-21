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
    print("Zielrendite:", [z[:200] for z in t.splitlines() if "Rechnerisch erreichbar" in z or "renditestärksten" in z
                           or "Zielrendite" in z][:4])
    print("Fehler:", [z for z in t.splitlines() if "Fehler" in z or "Traceback" in z][:3])
    page.locator(".st-key-pb_scan_zum_muster button").first.click(); br.warte_ruhe(page, 120)
    pills = page.locator('.st-key-md_wahl button')
    print("Pills:", [x.inner_text() for x in pills.all()][-3:])
    # zuletzt angelegtes (Zielrendite) ist vorausgewaehlt - ein Klick wuerde es abwaehlen
    t = br.text(page); zz = t.splitlines()
    i = next((k for k, z in enumerate(zz) if z.strip().upper() == "ERWARTETE RENDITE"), None)
    print("Musterdepot Zielrendite:", zz[i - 6:i + 8] if i else None)
    b.close()
