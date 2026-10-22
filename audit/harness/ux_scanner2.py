"""Investment Scanner 2.0: Seite laedt, Strategien/Kaufplan/Entnahmen, Depot-CSV, aktuelle Kurse - keine Fehler."""
import sys, br
from playwright.sync_api import sync_playwright
S = sys.argv[1]
NUTZER, PW = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("admin", "Admin-Test-Passwort-1")
BREITE = int(sys.argv[4]) if len(sys.argv) > 4 else 1440

def oeffne(page, name):
    if not page.locator(".st-key-nav_menue button", has_text=name).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=name).first.click(); br.warte_ruhe(page, 180)

with sync_playwright() as p:
    b, ctx, page = br.start(p, BREITE, 900, BREITE < 500)
    br.login(page, NUTZER, PW); br.warte_ruhe(page, 120)
    oeffne(page, "Scanner 2.0"); page.wait_for_timeout(1500)
    t = br.text(page)
    print("Felder:", {l: page.get_by_label(l, exact=True).first.input_value() for l in
                      ("Neues Anfangskapital €", "Zielwert des gesamten Depots €", "Nachkaufreserve %")})
    if NUTZER != "admin":
        for l, v in (("Neues Anfangskapital €", "20000"), ("Zielwert des gesamten Depots €", "30000")):
            page.get_by_label(l, exact=True).fill(v); page.keyboard.press("Enter"); page.wait_for_timeout(900); br.warte_ruhe(page)
        t = br.text(page)
    print("Ziel:", [z[:160] for z in t.splitlines() if "Zielwert wird" in z][:1])
    print("Kaufpositionen:", [z for z in t.splitlines() if "Kaufpositionen" in z][:1])
    page.locator(".st-key-is2_wahl_defensiv button").first.click(); page.wait_for_timeout(1200); br.warte_ruhe(page)
    print("nach Defensiv:", [z[:120] for z in br.text(page).splitlines() if "Kaufplan Defensiv" in z][:1])
    page.get_by_label("Einmalige Auszahlung · sofort €", exact=True).fill("1000"); page.keyboard.press("Enter")
    page.wait_for_timeout(1000); br.warte_ruhe(page)
    page.get_by_label("Regelmäßige Auszahlung pro Monat €", exact=True).fill("100"); page.keyboard.press("Enter")
    page.wait_for_timeout(1000); br.warte_ruhe(page)
    print("Entnahmen:", [z for z in br.text(page).splitlines() if "Strategievergleich nach Entnahmen" in z or "Sofort ausgezahlt" in z][:2])
    page.locator('[data-testid="stFileUploader"]').nth(1).locator("input[type=file]").set_input_files(
        files=[{"name": "depot.csv", "mimeType": "text/csv",
                "buffer": "id;name;type;shares;price\nTEST-1;Test ETF (fiktiv);ETF;10;100\n".encode()}])
    page.wait_for_timeout(2000); br.warte_ruhe(page)
    print("Depot:", [z for z in br.text(page).splitlines() if "Vorhandenes Depot" in z][:1])
    page.locator(".st-key-is2_live_btn button").first.click(); page.wait_for_timeout(2500); br.warte_ruhe(page, 180)
    print("Kurse:", [z[:140] for z in br.text(page).splitlines() if "aktuelle Kurse geladen" in z][:1])
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    page.evaluate("() => { const m = document.querySelector('[data-testid=stMain]') || document.scrollingElement; m.scrollTo(0, 0); }")
    for i in range(12):
        page.wait_for_timeout(500)
        page.screenshot(path=f"{S}/scanner2_{NUTZER}_{BREITE}_{i}.png")
        weiter = page.evaluate("""() => { const m = document.querySelector('[data-testid=stMain]');
            const vor = m.scrollTop; m.scrollBy(0, 820); return m.scrollTop > vor; }""")
        if not weiter:
            break
    b.close()
