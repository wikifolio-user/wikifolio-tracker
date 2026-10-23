import json
import br
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "maria", "Maria-Test-Pass-1")
    page.locator(".st-key-nav_menue button", has_text="Depot verwalten").first.click(); br.warte_ruhe(page)
    page.locator("summary", has_text="Sparrate und Entnahme anpassen").first.click(); page.wait_for_timeout(400)
    f = page.get_by_role("spinbutton", name="Monatliche Sparrate (€)").first
    print("vorher:", f.input_value())
    f.fill("77"); f.press("Enter"); br.warte_ruhe(page)
    btn = page.get_by_role("button", name="💾 Sparrate speichern")
    print("Knopf:", btn.count(), btn.first.is_enabled() if btn.count() else None)
    json.dump({"github_write": "500"}, open("fault.json", "w"))
    btn.first.click(); br.warte_ruhe(page)
    t = br.text(page)
    print([z for z in t.splitlines() if "Sparrate" in z or "fehl" in z.lower()][:6])
    json.dump({}, open("fault.json", "w"))
    page.reload(); br.login(page, "maria", "Maria-Test-Pass-1")
    page.locator(".st-key-nav_menue button", has_text="Depot verwalten").first.click(); br.warte_ruhe(page)
    page.locator("summary", has_text="Sparrate und Entnahme anpassen").first.click(); page.wait_for_timeout(400)
    print("nach Neuanmeldung gespeichert:", page.get_by_role("spinbutton", name="Monatliche Sparrate (€)").first.input_value())
    b.close()
