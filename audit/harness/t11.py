import br, re, json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    print("sparplan_state:", json.load(open("store_dump.json")).get("state/sparplan_state.json"))
    br.ansicht(page, "Test-Depot"); t = br.text(page); i = t.find("DEPOTWERT"); print(t[i:i+30].replace("\n"," "), "|", re.findall(r"[\d\.]+ Anteile[^\n]*", t)[:1])
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    br.ansicht(page, "Vermögensaufbau")
    info = page.evaluate("""() => { const el=[...document.querySelectorAll('.js-plotly-plot')].filter(e=>e.offsetParent)[0];
        return el.data.filter(t=>t.name && t.name.startsWith('Brutto')).map(t=>({name:t.name, y: t.y})) }""")
    import base64, struct
for t in info:
    y = t["y"]; raw = base64.b64decode(y["bdata"]) if isinstance(y, dict) else None
    werte = struct.unpack("<%dd" % (len(raw)//8), raw) if raw else y
    print("Chart", t["name"], "letzter Wert:", werte[-1], "Punkte:", len(werte))
    # aufraeumen: Sparplan beenden nicht noetig (Sandbox)
    b.close()
