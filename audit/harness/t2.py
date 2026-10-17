import br, json, re
from playwright.sync_api import sync_playwright
def depotwert(page):
    t = br.text(page); m = re.search(r"DEPOTWERT\n([\d\.,]+)€", t); return m.group(1) if m else None
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    br.ansicht(page, "Depot")
    for ex in ["Meilenstein", "Netto-Werte"]:
        page.get_by_text(ex).first.click(); page.wait_for_timeout(800)
    t = br.text(page); i = t.find("100k"); print("--- Expander ---\n", t[i:i+900])
    print("Depotwert vorher:", depotwert(page))
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    br.ansicht(page, "Einstellungen")
    page.get_by_text("Positionen verwalten").first.click(); page.wait_for_timeout(1000)
    form = page.locator("[data-testid=stForm]").filter(has_text="Kaufkurs (€)").first
    form.get_by_label("Kaufkurs (€)").fill("160.68"); form.get_by_label("Kaufkurs (€)").press("Tab")
    form.get_by_label("Investiertes Kapital (€)").fill("26000"); form.get_by_label("Investiertes Kapital (€)").press("Tab")
    form.get_by_role("button", name="💾 Speichern").click(); br.warte_ruhe(page)
    br.shot(page, "04_hauptposition_gespeichert")
    print("Meldungen:", [l for l in br.text(page).splitlines() if "Gespeichert" in l or "fehlgeschlagen" in l][:3])
    st = json.load(open("store_dump.json")); print("positionen.json:", st.get("state/positionen.json"))
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    br.ansicht(page, "Depot")
    print("Depotwert nachher:", depotwert(page)); br.shot(page, "05_depot_nach_edit")
    t = br.text(page); i = t.find("DEPOTWERT"); print(t[i:i+120]); j=t.find("Anteile ·"); print(t[j-20:j+60])
    page.reload(); br.warte_ruhe(page); br.login(page, "admin", "Admin-Test-Passwort-1"); br.ansicht(page, "Depot")
    print("Depotwert nach Reload:", depotwert(page))
    b.close()
