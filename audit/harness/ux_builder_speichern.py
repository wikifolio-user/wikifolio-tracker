"""Portfolio Builder 2.0: speichern und in neuer Sitzung wieder laden; eingeschraenkter Benutzer sieht die Kachel nicht."""
import br
from playwright.sync_api import sync_playwright

def oeffnen(page, wer, pw):
    br.login(page, wer, pw); page.wait_for_timeout(1500)
    if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
    page.wait_for_timeout(600)

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    oeffnen(page, "maria", "Maria-Test-Pass-1")
    f = page.get_by_label("Anfangskapital €", exact=True)
    f.fill("25000"); page.keyboard.press("Enter"); page.wait_for_timeout(1200); br.warte_ruhe(page)
    print("Status vor Speichern:", page.locator(".pb-hinweis", has_text="gespeichert").first.inner_text())
    page.get_by_role("button", name="💾 Speichern").click(); page.wait_for_timeout(1200); br.warte_ruhe(page)
    print("Status nach Speichern:", page.locator(".pb-hinweis", has_text="Gespeichert").first.inner_text())
    b.close()
    b, ctx, page = br.start(p, 1440, 900, False)
    oeffnen(page, "maria", "Maria-Test-Pass-1")
    print("Neue Sitzung, Anfangskapital:", page.get_by_label("Anfangskapital €", exact=True).input_value())
    b.close()
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "leser", "Leser-Pass-123"); page.wait_for_timeout(1500)
    if page.get_by_role("button", name="☰ Menü").count():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    print("Eingeschränkter Benutzer sieht Kachel:",
          page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").count() > 0)
    b.close()
