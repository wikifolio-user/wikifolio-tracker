import br, json, time
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    time.sleep(61)   # 60-s-Lesecache ablaufen lassen
    json.dump({"github_read": "500"}, open("fault.json", "w"))
    br.login(page, "anna-b", "Anna-Strich-Pass-1")
    print("anna-b bei GitHub-500:", [l for l in br.text(page).splitlines() if "falsch" in l or "Fehler" in l or "Speicher" in l][:3])
    br.login(page, "admin", "Admin-Test-Passwort-1")
    br.ansicht(page, "Depot"); t = br.text(page)
    print("Admin Depot bei 500 - Warnhinweise:", [l for l in t.splitlines() if "nicht lesbar" in l or "Speicher" in l or "⚠" in l][:5])
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    br.ansicht(page, "Chronik"); t = br.text(page)
    print("Chronik bei 500:", t[:400].replace("\n", " | "))
    br.shot(page, "08_chronik_github500")
    json.dump({}, open("fault.json", "w"))
    b.close()
