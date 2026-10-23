import br
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "admin", "Admin-Test-Passwort-1"); page.wait_for_timeout(1000)
    page.locator(".st-key-nav_menue button", has_text="Investment-Scanner").first.click(); br.warte_ruhe(page, 120)
    page.locator(".st-key-pb_scan_los button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
    t = br.text(page)
    print("Meldung:", [z for z in t.splitlines() if "Musterdepot" in z][:3])
    print("Fehler:", [z for z in t.splitlines() if "Fehler" in z or "Traceback" in z][:3])
    if page.locator(".st-key-pb_scan_zum_muster button").count():
        page.locator(".st-key-pb_scan_zum_muster button").first.click(); br.warte_ruhe(page, 120)
        t = br.text(page)
        print("Musterdepot-Ansicht:", t[:300].replace("\n", " | "))
    b.close()
