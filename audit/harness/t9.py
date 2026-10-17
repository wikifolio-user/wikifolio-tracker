import br
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    for a in ["Vermögensaufbau", "Performance > 2021", "Candlestick", "Zukunfts-Prognose", "Szenario-Simulator"]:
        br.ansicht(page, a)
        charts = page.locator("[data-testid=stPlotlyChart]:visible")
        n = charts.count(); print(a, "Diagramme:", n)
        for i in range(min(n, 3)):
            charts.nth(i).scroll_into_view_if_needed(); page.wait_for_timeout(700)
            charts.nth(i).screenshot(path=f"{br.SHOTS}/chart_{a.split()[0].replace('>','')}_{i}.png")
            # Achsen/Legende auslesen
            info = page.evaluate("""(i) => { const el=[...document.querySelectorAll('[data-testid=stPlotlyChart] .js-plotly-plot')].filter(e=>e.offsetParent)[i];
               if(!el||!el.data) return null; return {traces: el.data.map(t=>[t.name, t.type, (t.y||[]).length]), ytitle: el.layout.yaxis?.title?.text, xtitle: el.layout.xaxis?.title?.text, yrange: el.layout.yaxis?.range, rangemode: el.layout.yaxis?.rangemode}; }""", i)
            print("   ", info)
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    b.close()
