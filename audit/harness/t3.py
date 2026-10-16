import br, json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "anna.b", "Anna-Punkt-Pass-1")
    br.ansicht(page, "Einstellungen")
    page.locator("summary:visible", has_text="Positionen verwalten").first.click(); page.wait_for_timeout(800)
    f = page.locator("[data-testid=stForm]:visible").filter(has_text="Position anlegen").first
    f.get_by_label("Name").fill("Geheimes Depot von anna.b <img src=x onerror=\"document.title='XSS'\">")
    f.get_by_label("Kaufkurs (€)").fill("10"); f.get_by_label("Kaufkurs (€)").press("Tab")
    f.get_by_label("Investiertes Kapital (€)").fill("5000"); f.get_by_label("Investiertes Kapital (€)").press("Tab")
    f.get_by_role("button", name="➕ Position anlegen").click(); br.warte_ruhe(page)
    st = json.load(open("store_dump.json")); print("Pfade im Speicher:", sorted(k for k in st if "benutzer/" in k))
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-logout_ecke button:visible").first.click(); br.warte_ruhe(page)
    # zweiter, ANDERER Benutzer
    br.login(page, "anna-b", "Anna-Strich-Pass-1")
    br.ansicht(page, "Depot")
    t = br.text(page)
    print("anna-b sieht fremde Position:", "Geheimes Depot von anna.b" in t)
    br.shot(page, "06_anna-b_sieht_fremde_daten")
    print("Seitentitel:", page.title())
    print("img-Tags im Inhalt mit onerror:", page.locator("[data-testid=stMain] img[onerror]").count())
    b.close()
