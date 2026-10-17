import br, json, re, time
from playwright.sync_api import sync_playwright
def dw(page):
    m = re.search(r"DEPOTWERT\n([\d\.,]+)€", br.text(page)); return m.group(1) if m else None
def kopf(page):
    t = br.text(page); i = t.find("LS9VFS"); return t[i:i+40].replace("\n", " | ") if i >= 0 else None
def hinweise(page):
    return [l for l in br.text(page).splitlines() if "gespeicherter Kurs" in l or "Schlusskurs" in l or "Datenspeicher" in l or "kein echter Kurs" in l][:2]
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    # B) ls-tc weg, aber Workflow-Kurs gespeichert
    json.dump({"state/price_history/2026-10.csv": "timestamp,price\n2026-10-16T22:55:00+02:00,140.5000\n"}, open("extra_store.json", "w"))
    json.dump({"lstc": "down"}, open("fault.json", "w"))
    br.login(page, "admin", "Admin-Test-Passwort-1")
    br.ansicht(page, "Depot")
    print("B) Kurskopf:", kopf(page), "| Depotwert:", dw(page), "| Hinweise:", hinweise(page))
    # C) Quelle wieder da: neue Sitzung OHNE Aktualisieren-Klick zeigt Live-Daten (A-07)
    json.dump({}, open("fault.json", "w"))
    page.reload(); br.login(page, "admin", "Admin-Test-Passwort-1"); br.ansicht(page, "Depot")
    print("C) nach Wiederherstellung:", kopf(page), "| Depotwert:", dw(page))
    # D) GitHub-Speicher 500
    time.sleep(61)
    json.dump({"github_read": "500"}, open("fault.json", "w"))
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    br.ansicht(page, "Chronik"); print("D) Admin-Hinweis:", hinweise(page)); br.shot(page, "v4_speicher_500")
    page.reload(); br.login(page, "anna-b", "Anna-Strich-Pass-1")
    print("D) Login normaler Benutzer:", [l for l in br.text(page).splitlines() if "Anmeldung" in l or "falsch" in l][:2])
    json.dump({}, open("fault.json", "w"))
    b.close()
