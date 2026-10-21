"""Investment-Scanner: jeder Scan legt ein NEUES Musterdepot an (Kurse aus den Top-500-Daten), vorhandene bleiben."""
import sys, br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch
S = sys.argv[1]
with sync_playwright() as p:
    b, page = frisch(p)
    page.locator(".st-key-pb_zum_scanner button").first.click(); br.warte_ruhe(page, 60)
    eck = page.locator(".st-key-pb_scan_eckdaten").first
    eck.get_by_role("spinbutton", name="Zielvermögen €").fill("20000"); page.keyboard.press("Enter")
    page.wait_for_timeout(1500); br.warte_ruhe(page)
    for profil in ("Hoch", "Niedrig"):
        page.locator(".st-key-pb_scan_profil button", has_text=profil).first.click(); page.wait_for_timeout(1500)
        br.warte_ruhe(page)
        page.locator(".st-key-pb_scan_los button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
        t = br.text(page)
        print(profil, "Meldung:", [z for z in t.splitlines() if "Musterdepot „" in z][:1])
        print(profil, "Fehler:", [z for z in t.splitlines() if "Fehler" in z or "Traceback" in z][:3])
    page.locator(".st-key-pb_scan_zum_muster button").first.click(); br.warte_ruhe(page, 120)
    t = br.text(page)
    print("Musterdepots:", [z for z in t.splitlines() if z.startswith("Investment Scanner")][:6])
    print("Fehler:", [z for z in t.splitlines() if "Fehler" in z or "Traceback" in z][:3])
    zz = t.splitlines()
    i = next((k for k, z in enumerate(zz) if z.strip().upper() == "NÖTIGE RENDITE"), None)
    print("Ziel-Anzeige:", zz[i - 3:i + 10] if i else None, [z[:120] for z in zz if "erreichbar" in z][:2])
    vorher = len([z for z in t.splitlines() if z.upper().startswith("INVESTMENT SCANNER ·")])
    page.locator(".st-key-md_loeschen_frage button").first.click(); br.warte_ruhe(page)
    page.locator(".st-key-md_loeschen button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 120)
    t = br.text(page)
    nachher = len([z for z in t.splitlines() if z.upper().startswith("INVESTMENT SCANNER ·")])
    print("Depots vorher/nachher:", vorher, nachher, "| Fehler:", [z for z in t.splitlines() if "Fehler" in z][:2])
    page.screenshot(path=f"{S}/scan_muster.png", full_page=True)
    b.close()
