"""Investment-Scanner: Profil "Favoriten" - Werte aus der Top-500-Liste auswaehlen, nur mit ihnen rechnen."""
import sys, br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch
S = sys.argv[1]
with sync_playwright() as p:
    b, page = frisch(p)
    page.locator(".st-key-pb_zum_scanner button").first.click(); br.warte_ruhe(page, 60)
    if not page.locator(".st-key-pb_scan_favoriten").count():
        page.locator(".st-key-pb_scan_profil button", has_text="Favoriten").first.click(); page.wait_for_timeout(1500)
    br.warte_ruhe(page, 60)
    page.locator(".st-key-pb_scan_favoriten [aria-label='Clear all']").first.click() if page.locator(".st-key-pb_scan_favoriten [aria-label='Clear all']").count() else None
    page.wait_for_timeout(1500); br.warte_ruhe(page)
    print("Knopf gesperrt ohne Favoriten:", page.locator(".st-key-pb_scan_los button").first.is_disabled())
    ms = page.locator(".st-key-pb_scan_favoriten input").first
    for such in ("iShares Core MSCI World", "Apple", "NVIDIA"):
        ms.click(); ms.fill(such); page.wait_for_timeout(1500)
        opt = page.locator('[role="option"]').filter(has_not_text="matches").first
        print("wähle:", opt.inner_text()[:80]); opt.click(); page.wait_for_timeout(1500); br.warte_ruhe(page, 60)
    page.keyboard.press("Escape")
    t = br.text(page)
    print("Info:", [z for z in t.splitlines() if z.startswith("Favoriten:") or "Keine Favoriten" in z or "nicht genutzt" in z][:3])
    for n, v in (("ETFs %", "40"), ("Aktien %", "60"), ("wikifolios %", "0"), ("Cash %", "0"), ("Max. je Position %", "50")):
        page.get_by_role("spinbutton", name=n).fill(v); page.keyboard.press("Enter"); page.wait_for_timeout(800)
        br.warte_ruhe(page)
    t = br.text(page)
    print("Info nach Aufteilung:", [z for z in t.splitlines() if z.startswith("Favoriten:") or "Keine Favoriten" in z or "nicht genutzt" in z][:3])
    page.locator(".st-key-pb_scanner").screenshot(path=f"{S}/favoriten_einst.png")
    print("Tag-Schrift:", page.evaluate("() => getComputedStyle(document.querySelector('.st-key-pb_scan_favoriten [data-tag] span')).color"))
    page.locator(".st-key-pb_scan_los button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
    t = br.text(page)
    i = t.find("Musterdepot angelegt")
    print("Meldung:", [z[:300] for z in t.splitlines() if "Musterdepot" in z and "angelegt" in z][:2])
    print("Favoriten im Ergebnis:", [n for n in ("MSCI World", "Apple", "NVIDIA") if n in t[i:]])
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    page.locator(".st-key-pb_scanner").screenshot(path=f"{S}/favoriten_erg.png")
    b.close()
