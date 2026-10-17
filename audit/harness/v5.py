import br, json, re, base64, struct
from playwright.sync_api import sync_playwright
def dw(page):
    m = re.search(r"DEPOTWERT\n([\d\.,]+)€", br.text(page)); return m.group(1) if m else None
def menu(page):
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    # B erneut
    json.dump({"state/price_history/2026-10.csv": "timestamp,price\n2026-10-16T22:55:00+02:00,140.5000\n"}, open("extra_store.json", "w"))
    json.dump({"lstc": "down"}, open("fault.json", "w"))
    br.login(page, "admin", "Admin-Test-Passwort-1"); br.ansicht(page, "Depot")
    t = br.text(page); i = t.find("LS9VFS")
    print("B) Kopf:", t[i:i+40].replace("\n"," | "), "| Allzeithoch erwähnt:", "Allzeithoch" in t or "Höchststand" in t)
    print("B) Fussnote:", [l for l in t.splitlines() if "Anteile ·" in l][:1])
    json.dump({}, open("fault.json", "w"))
    # Sparplan 500 -> Kachel = Chart
    page.reload(); br.login(page, "admin", "Admin-Test-Passwort-1")
    br.ansicht(page, "Einstellungen")
    page.locator("summary:visible").filter(has_text="Sparrate").first.click(); page.wait_for_timeout(800)
    page.locator("input[aria-label='Monatliche Sparrate (€)']:visible").fill("500"); page.keyboard.press("Tab"); br.warte_ruhe(page)
    page.get_by_role("button", name="💾 Sparrate speichern").click(); br.warte_ruhe(page)
    menu(page); br.ansicht(page, "Depot"); print("S) Kachel Depotwert:", dw(page))
    menu(page); br.ansicht(page, "Vermögensaufbau")
    info = page.evaluate("""() => { const el=[...document.querySelectorAll('.js-plotly-plot')].filter(e=>e.offsetParent)[0];
        return el.data.filter(t=>t.name==='Depotwert' || t.name==='Eingezahlt').map(t=>[t.name, t.y]) }""")
    for name, y in info:
        raw = base64.b64decode(y["bdata"]) if isinstance(y, dict) else None
        w = struct.unpack("<%dd" % (len(raw)//8), raw) if raw else y
        print(f"S) Chart {name} letzter Wert: {w[-1]:.2f}")
    b.close()
