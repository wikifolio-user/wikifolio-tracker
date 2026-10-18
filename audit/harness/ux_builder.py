"""Portfolio Builder 2.0: ganze Seite je Geraet, Messwerte (Ueberlauf, abgeschnitten, axe), Fehlertexte."""
import json, sys
import br
from ux_mess import MESS_JS, axe
from playwright.sync_api import sync_playwright
AUS = sys.argv[1]
GER = {"iphone-se": (375, 667, True), "ipad-hoch": (768, 1024, True), "laptop": (1440, 900, False)}
with sync_playwright() as p:
    for g in (sys.argv[2:] or list(GER)):
        w, hgt, t = GER[g]
        b, ctx, page = br.start(p, w, hgt, t)
        br.login(page, "maria", "Maria-Test-Pass-1"); page.wait_for_timeout(1500)
        if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
            page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
        page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
        page.wait_for_timeout(800)
        m = page.evaluate(MESS_JS, t)
        a = axe(page)
        txt = br.text(page)
        print(g, "hoehe", m["hoehe"], "ueberlauf", m["ueberlauf"], "geschnitten", m["geschnitten"][:5],
              "winzig", len(m["winzig"]), "axe", [(x["id"], x["n"], x["bsp"]) for x in a],
              "fehler", [z for z in txt.splitlines() if "Fehler" in z][:3], flush=True)
        page.set_viewport_size({"width": w, "height": int(min(m["hoehe"] + 150, 9000))}); page.wait_for_timeout(600)
        page.screenshot(path=f"{AUS}/{g}.png")
        b.close()
