import br, json
from playwright.sync_api import sync_playwright
AXE = open("../axe/package/axe.min.js").read()
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    page.goto(br.URL); page.get_by_placeholder("Benutzername eingeben").wait_for(timeout=60000); br.warte_ruhe(page)
    ziele = [("Login", None)]
    def pruefen(name):
        page.add_script_tag(content=AXE)
        r = page.evaluate("async () => (await axe.run(document, {runOnly: ['wcag2a','wcag2aa']})).violations.map(v => [v.id, v.impact, v.nodes.length, v.nodes.slice(0,2).map(n=>n.target.join(' ')+' :: '+(n.failureSummary||'').split('\\n')[1])])")
        print(f"== {name}: {len(r)} Regelverstoesse")
        for v in r: print("  ", v[0], v[1], "Knoten:", v[2], v[3][:1])
    pruefen("Login")
    br.login(page, "admin", "Admin-Test-Passwort-1"); pruefen("Startseite")
    br.ansicht(page, "Test-Depot"); pruefen("Depot")
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    br.ansicht(page, "Zinseszins"); pruefen("Zinsrechner")
    # Tastaturbedienung: Tab-Reihenfolge auf der Startseite
    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    fokus = []
    for _ in range(8):
        page.keyboard.press("Tab")
        fokus.append(page.evaluate("() => { const e=document.activeElement; const s=getComputedStyle(e); return (e.innerText||e.getAttribute('aria-label')||e.tagName).slice(0,25)+' | outline='+s.outlineStyle+' '+s.outlineWidth+' boxShadow='+(s.boxShadow!='none') }"))
    print("Tab-Fokus:", *fokus, sep="\n  ")
    b.close()
