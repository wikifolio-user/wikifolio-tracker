import br, json, re, time
from playwright.sync_api import sync_playwright
def dw(page):
    m = re.search(r"DEPOTWERT\n([\d\.,]+)€", br.text(page)); return m.group(1) if m else None
def menu(page):
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    br.ansicht(page, "Depot"); t = br.text(page)
    print("1) Höchststand-Zeile:", [l for l in t.splitlines() if "Höchststand vom" in l][:1])
    print("1) Depotwert vorher:", dw(page))
    # 2) Hauptposition bearbeiten -> muss wirken
    menu(page); br.ansicht(page, "Einstellungen")
    page.locator("summary:visible", has_text="Positionen verwalten").first.click(); page.wait_for_timeout(800)
    f = page.locator("[data-testid=stForm]:visible").filter(has_text="Kaufkurs (€)").first
    print("2) WKN-Feld gesperrt:", f.get_by_label("WKN / ISIN").is_disabled())
    f.get_by_label("Investiertes Kapital (€)").fill("26000"); f.get_by_label("Investiertes Kapital (€)").press("Tab")
    f.get_by_role("button", name="💾 Speichern").click(); br.warte_ruhe(page)
    menu(page); br.ansicht(page, "Depot"); print("2) Depotwert nach Kapital 26.000:", dw(page))
    page.reload(); br.login(page, "admin", "Admin-Test-Passwort-1"); br.ansicht(page, "Depot")
    print("2) nach Reload:", dw(page))
    # 3) Aktualisieren-Drossel
    page.get_by_role("button", name="🔄").click(); br.warte_ruhe(page)
    print("3) Drossel-Toast:", page.locator("[data-testid=stToast]").all_inner_texts()[:1])
    # 4) Benutzerverwaltung: Kollision + Namensregel
    menu(page); br.ansicht(page, "Benutzer"); t = br.text(page)
    print("4) Kollisionswarnung:", [l for l in t.splitlines() if "teilen sich" in l][:1])
    page.locator("summary:visible", has_text="Neuen Benutzer anlegen").first.click(); page.wait_for_timeout(600)
    f = page.locator("[data-testid=stForm]:visible").filter(has_text="Anlegen").first
    f.get_by_label("Benutzername").fill("max.m"); f.get_by_label(re.compile("Passwort")).fill("Sicheres-Pass-42")
    f.get_by_role("button", name="Anlegen").click(); br.warte_ruhe(page)
    print("4) Anlegen 'max.m':", [l for l in br.text(page).splitlines() if "Benutzername:" in l or "angelegt" in l][:2])
    print("Konsole:", [k for k in page.konsole if "error" in k.lower()][:3])
    b.close()
