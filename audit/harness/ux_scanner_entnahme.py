"""Investment-Scanner: Entnahme als Betrag und als Stueckzahlen je Musterdepot-Position, Uebernahme in den Builder."""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch
S = sys.argv[1]

def plan(page, wo):
    return page.evaluate("""(wo) => [...document.querySelectorAll(wo + ' .pb-tab tbody tr')].filter(r => r.offsetParent)
        .map(r => [...r.querySelectorAll('td')].map(td => td.innerText.trim()).join(' | '))""", wo)

def kpi(page, label):
    t = page.locator(".st-key-pb_scanner .pb-scan-kpis").first.inner_text().split("\n")
    return t[t.index(label) + 1] if label in t else None

def scannen(page):
    page.locator(".st-key-pb_scan_los button").first.click(); page.wait_for_timeout(1500); br.warte_ruhe(page, 120)

def reiter(page, name):
    page.locator(".st-key-pb_scanner").get_by_role("tab", name=name).click(); page.wait_for_timeout(1200); br.warte_ruhe(page)

with sync_playwright() as p:
    b, page = frisch(p)
    page.get_by_label("Zielvermögen €", exact=True).fill("80000"); page.keyboard.press("Enter")
    page.wait_for_timeout(1200); br.warte_ruhe(page)
    page.locator(".st-key-pb_zum_scanner button").first.click(); br.warte_ruhe(page, 60)
    page.locator(".st-key-pb_scan_entnahme_karte").get_by_role("spinbutton", name="Entnahme €/Monat").fill("200"); page.keyboard.press("Enter")
    page.wait_for_timeout(1200); br.warte_ruhe(page)
    scannen(page)
    reiter(page, "📈 Prognose"); print("Betrag: Wahrscheinlichkeit", kpi(page, "ZIELWAHRSCHEINLICHKEIT") or kpi(page, "Zielwahrscheinlichkeit"))
    reiter(page, "💸 Entnahme"); z = plan(page, ".st-key-pb_scanner"); print("Betrag-Plan:", len(z), "Zeilen,", z[-1:])
    page.locator(".st-key-pb_scan_entnahme_karte").get_by_text("Stückzahlen").click(); page.wait_for_timeout(1500); br.warte_ruhe(page)
    print("veraltet-Hinweis:", page.get_by_text("Eingaben geändert").count())
    reiter(page, "💸 Entnahme")
    grid = page.locator('.st-key-pb_scanner [data-testid="stDataFrame"]').locator("visible=true").first
    grid.scroll_into_view_if_needed(); box = grid.bounding_box()
    for zeile, wert in ((0, "5"), (1, "3")):
        page.mouse.click(box["x"] + 60, box["y"] + 52 + zeile * 35); page.wait_for_timeout(400)
        page.keyboard.press("ArrowRight"); page.keyboard.press("Enter"); page.wait_for_timeout(300)
        page.keyboard.press("Control+A"); page.keyboard.type(wert); page.keyboard.press("Enter")
        page.wait_for_timeout(2500); br.warte_ruhe(page)
    z = plan(page, ".st-key-pb_scanner"); print("Stück-Plan:"); [print("   ", x) for x in z]
    scannen(page)
    reiter(page, "📈 Prognose"); print("Stück: Wahrscheinlichkeit", kpi(page, "ZIELWAHRSCHEINLICHKEIT") or kpi(page, "Zielwahrscheinlichkeit"))
    reiter(page, "💸 Entnahme"); print("nach Neuberechnung Plan:", plan(page, ".st-key-pb_scanner")[:2])
    page.locator(".st-key-pb_scanner").screenshot(path=f"{S}/scan_entnahme.png")
    reiter(page, "📦 Musterdepot")
    page.locator(".st-key-pb_scan_uebernehmen button").first.click(); page.wait_for_timeout(3000); br.warte_ruhe(page, 120)
    print("Builder:", page.locator(".pb-titel").first.inner_text())
    print("Builder-Entnahmeplan:", plan(page, ".st-key-pb_entnahmeplan"))
    print("Fehler:", [x for x in br.text(page).splitlines() if "Fehler" in x or "Traceback" in x][:3])
    b.close()
