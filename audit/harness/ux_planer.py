"""Planer auf dem iPhone: Hoehe und Messwerte je Ansicht/Schritt/Unterseite."""
import json, sys
import br
from ux_mess import MESS_JS
from playwright.sync_api import sync_playwright
AUS = sys.argv[1] if len(sys.argv) > 1 else "../ux_planer"
import os; os.makedirs(AUS, exist_ok=True)
erg = []
with sync_playwright() as p:
    b, ctx, page = br.start(p, 375, 667, True)
    br.login(page, "maria", "Maria-Test-Pass-1")
    page.locator(".st-key-nav_menue button", has_text="Portfolio-Planer").first.click(); br.warte_ruhe(page, 180)
    def miss(tag):
        page.wait_for_timeout(400)
        m = page.evaluate(MESS_JS, True)
        h = int(min(m["hoehe"] + 120, 12000)); page.set_viewport_size({"width": 375, "height": h}); page.wait_for_timeout(400)
        page.screenshot(path=f"{AUS}/{tag}.png"); page.set_viewport_size({"width": 375, "height": 667})
        erg.append({"tag": tag, "hoehe": m["hoehe"], "ueberlauf": m["ueberlauf"], "geschnitten": m["geschnitten"][:5],
                    "winzig": len(m["winzig"])})
        print(tag, m["hoehe"], m["ueberlauf"], flush=True)
    miss("start")
    for ans in ["Schritt für Schritt"]:
        page.locator(".st-key-pl_nav_ansicht button", has_text=ans).first.click(); br.warte_ruhe(page, 180)
        n = page.locator(".st-key-pl_nav_schritt button").count()
        for i in range(n):
            page.locator(".st-key-pl_nav_schritt button").nth(i).click(); br.warte_ruhe(page, 180)
            unter = page.locator(".st-key-pl_nav_unter button")
            k = unter.count()
            if k == 0:
                miss(f"s{i}")
            for j in range(k):
                page.locator(".st-key-pl_nav_unter button").nth(j).click(); br.warte_ruhe(page, 180)
                miss(f"s{i}_{j}")
    b.close()
json.dump(erg, open(f"{AUS}/erg.json", "w"), ensure_ascii=False, indent=1)
