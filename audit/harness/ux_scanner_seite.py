"""Investment-Scanner: Menue-Kachel unter Planung & Analyse, Einstellung wird gespeichert (neue Sitzung)."""
import sys
import br
from playwright.sync_api import sync_playwright
S = sys.argv[1]
with sync_playwright() as p:
    for runde in (1, 2):
        b, ctx, page = br.start(p, 390, 900, True)
        br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
        if runde == 1:
            page.screenshot(path=f"{S}/scan_menue.png", full_page=True)
        page.locator(".st-key-nav_menue button", has_text="Investment-Scanner").first.click(); br.warte_ruhe(page, 60)
        knopf = page.locator(".st-key-pb_scan_profil button", has_text="Hoch").first
        print(runde, "Hoch gewählt:", knopf.get_attribute("aria-checked") or knopf.get_attribute("kind"),
              "Max-Verlust:", page.get_by_role("spinbutton", name="Max. Verlust %").input_value())
        if runde == 1:
            knopf.click(); page.wait_for_timeout(2500); br.warte_ruhe(page)
            print(1, "nach Klick Max-Verlust:", page.get_by_role("spinbutton", name="Max. Verlust %").input_value())
            page.screenshot(path=f"{S}/scan_seite.png")
        b.close()
