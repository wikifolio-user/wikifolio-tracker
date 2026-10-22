"""Frischer Benutzer: was ist in jeder Ansicht vorbelegt?"""
import sys, json, br
from playwright.sync_api import sync_playwright

def oeffne(page, name):
    if not page.locator(".st-key-nav_menue button", has_text=name).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=name).first.click(); br.warte_ruhe(page, 60); page.wait_for_timeout(500)
S = sys.argv[1]
ANS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["Depot", "Depot verwalten", "Chronik", "Musterdepot", "Vermögen", "Seit 2026", "Seit 2021", "Candles",
       "Prognose", "Szenarien", "Portfolio Builder", "Investment-Scanner", "Investment Scanner Pro", "Planer",
       "Watchlist", "Abfindung", "Zinseszins"]
with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
    for a in ANS:
        try:
            oeffne(page, a); br.warte_ruhe(page, 120); page.wait_for_timeout(800)
        except Exception as e:
            print("##", a, "nicht geöffnet", str(e)[:80]); continue
        d = page.evaluate("""() => {
          const lab = el => { const w = el.closest('[data-testid]'); const c = el.closest('.stNumberInput, .stTextInput, .stTextArea, .stDateInput, .stSelectbox');
             const l = c ? c.querySelector('label') : null; return l ? l.innerText.trim() : (el.getAttribute('aria-label')||''); };
          const vis = el => el.offsetParent !== null;
          const inp = [...document.querySelectorAll('input')].filter(vis).filter(i => !['checkbox','radio'].includes(i.type))
             .map(i => lab(i) + ' = ' + i.value).filter(x => !x.endsWith('= '));
          const dfs = [...document.querySelectorAll('[data-testid="stDataFrame"], table')].filter(vis).length;
          const sel = [...document.querySelectorAll('[data-testid="stSelectbox"]')].filter(vis).map(s => s.innerText.replace(/\\n/g,' | ').slice(0,90));
          return {inp, dfs, sel};
        }""")
        print("##", a, "| Tabellen:", d["dfs"])
        for x in d["inp"][:40]: print("   IN", x)
        for x in d["sel"][:10]: print("   SEL", x)
        page.screenshot(path=f"{S}/neu_{a.replace(' ','_')}.png", full_page=True)
    b.close()
