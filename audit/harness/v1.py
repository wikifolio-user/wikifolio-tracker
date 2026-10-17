import br, json, re, base64, struct
from playwright.sync_api import sync_playwright
def depot(page):
    t = br.text(page); i = t.find("DEPOTWERT"); return t[i:i+900]
def chart_letzter(page, name):
    info = page.evaluate("""(n) => { const el=[...document.querySelectorAll('.js-plotly-plot')].filter(e=>e.offsetParent)[0];
        return el ? el.data.filter(t=>t.name===n).map(t=>t.y) : [] }""", name)
    if not info: return None
    y = info[0]; raw = base64.b64decode(y["bdata"]) if isinstance(y, dict) else None
    return (struct.unpack("<%dd" % (len(raw)//8), raw) if raw else y)[-1]
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    br.ansicht(page, "Depot"); br.shot(page, "v1_depot")
    t = br.text(page); print("KURSKOPF:", t[t.find("LS9VFS"):t.find("LS9VFS")+40].replace("\n"," | "))
    print("Fussnote Kurs:", [l for l in t.splitlines() if "Kurs vom" in l][:1])
    print("=== DEPOT ===\n" + depot(page).replace("\n", " | "))
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    br.ansicht(page, "Vermögensaufbau")
    t = br.text(page); i = t.find("Hauptindizes Global"); print("TABELLE:", t[i:i+120].replace("\n", " | "))
    print("Chart Depotwert letzter Wert:", chart_letzter(page, "Depotwert"), "| Eingezahlt:", chart_letzter(page, "Eingezahlt"))
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    br.ansicht(page, "Zukunfts-Prognose"); t = br.text(page); i = t.find("Heute"); print("PROGNOSE:", t[i:i+200].replace("\n"," | "))
    print("Konsole:", [k for k in page.konsole if "error" in k.lower()][:5])
    b.close()
