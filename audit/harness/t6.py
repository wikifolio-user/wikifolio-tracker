import br, json, re
from playwright.sync_api import sync_playwright
def kern(page):
    t = br.text(page)
    m = re.search(r"DEPOTWERT\n([\d\.,]+)€", t)
    return {"kurs": (re.search(r"LS9VFS\n([\d\.,]+ €)", t) or [None, None])[1] if re.search(r"LS9VFS\n([\d\.,]+ €)", t) else None,
            "depotwert": m.group(1) if m else None,
            "warnung": [l for l in t.splitlines() if "keine echten" in l.lower() or "SYNTHETISCH" in l or "FALLBACK" in l.upper()][:3]}
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    json.dump({"lstc": "down"}, open("fault.json", "w"))
    page.get_by_role("button", name="🔄 Kurse aktualisieren").click(); br.warte_ruhe(page)
    br.ansicht(page, "Depot"); br.shot(page, "07_lstc_ausfall")
    print("AUSFALL:", kern(page))
    json.dump({}, open("fault.json", "w"))
    page.reload(); br.warte_ruhe(page); br.login(page, "admin", "Admin-Test-Passwort-1"); br.ansicht(page, "Depot")
    print("QUELLE WIEDER DA, neue Sitzung ohne Klick:", kern(page))
    page.get_by_role("button", name="🔄").click(); br.warte_ruhe(page)
    print("nach Klick auf Aktualisieren:", kern(page))
    b.close()
