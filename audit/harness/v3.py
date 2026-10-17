import br, json, re, time, sys
sys.path.insert(0, ".")
from playwright.sync_api import sync_playwright
def dw(page):
    m = re.search(r"DEPOTWERT\n([\d\.,]+)€", br.text(page)); return m.group(1) if m else None
def kopf(page):
    t = br.text(page); i = t.find("LS9VFS"); return t[i:i+45].replace("\n", " | ") if i >= 0 else None
def fehler(page):
    return [l for l in br.text(page).splitlines() if "kein echter Kurs" in l or "keine Live" in l.lower() or "Datenspeicher" in l][:2]
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    time.sleep(61)                                         # Drossel des Aktualisieren-Knopfs abwarten
    # A) ls-tc komplett weg, keine gespeicherten Kurse
    json.dump({"lstc": "down"}, open("fault.json", "w"))
    page.get_by_role("button", name="🔄 Kurse aktualisieren").click(); br.warte_ruhe(page)
    br.ansicht(page, "Depot"); br.shot(page, "v3_ausfall_ohne_kurs")
    print("A) Depotwert:", dw(page), "| Meldung:", fehler(page))
    # B) Workflow-Preis-Historie vorhanden -> echter gespeicherter Kurs mit Zeitstempel
    import fake_net
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    b.close()
