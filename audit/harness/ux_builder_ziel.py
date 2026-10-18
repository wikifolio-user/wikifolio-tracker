"""Portfolio Builder 2.0: Zielvermoegen + automatische Gewichte."""
import sys
import br
from playwright.sync_api import sync_playwright

def zeilen(page):
    return page.evaluate("""() => [...document.querySelectorAll('.pb-tab tbody tr')].map(r =>
        [...r.querySelectorAll('td')].map(td => td.innerText.trim()).join(' | '))""")

def feld(page, label, wert):
    page.get_by_label(label, exact=True).fill(str(wert)); page.keyboard.press("Enter")
    page.wait_for_timeout(1200); br.warte_ruhe(page)

with sync_playwright() as p:
    w = 375 if "handy" in sys.argv else 1440
    b, ctx, page = br.start(p, w, 900, w < 600)
    br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
    if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
    page.get_by_role("button", name="↺ Standardwerte").click(); br.warte_ruhe(page); page.wait_for_timeout(600)
    feld(page, "Zielvermögen €", 80000)
    print("Ziel-Hinweis:", page.locator(".pb-hinweis", has_text="Nötig").first.inner_text().replace("\n", " "))
    # NVIDIA aus dem Katalog (bringt seine 5-J.-Rendite mit)
    sb = page.locator('.st-key-pb_add [data-testid="stSelectbox"]').first
    sb.locator("input").click(); page.wait_for_timeout(300); page.keyboard.type("NVIDIA"); page.wait_for_timeout(400)
    page.keyboard.press("Enter"); page.wait_for_timeout(1200); br.warte_ruhe(page)
    page.locator(".st-key-pb_add button", has_text="Hinzufügen").first.click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
    page.locator(".st-key-pb_reihe3 [data-testid='stCheckbox'], .st-key-pb_reihe3 label", has_text="Automatisch aufs Ziel").first.click()
    page.wait_for_timeout(1500); br.warte_ruhe(page); page.wait_for_timeout(500)
    print("Ziel-Hinweis:", page.locator(".pb-hinweis", has_text="Nötig").first.inner_text().replace("\n", " "))
    print("Positionen:", zeilen(page))
    print("KPI Endwert:", page.locator(".pb-kpi").nth(3).inner_text().replace("\n", " | "))
    print("Meldungen:", page.locator("[data-testid='stAlert']").all_inner_texts()[:2])
    k = page.locator(".st-key-pb_reihe1").first; k.scroll_into_view_if_needed()
    bx = page.locator(".st-key-pb_reihe1").first.bounding_box()
    page.screenshot(path=sys.argv[1], clip={"x": 0, "y": max(bx["y"] - 60, 0), "width": w, "height": 900 if w > 600 else 1100}, full_page=True)
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
