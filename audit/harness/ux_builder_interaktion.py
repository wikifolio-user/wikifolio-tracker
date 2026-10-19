"""Portfolio Builder 2.0 im Browser bedienen: Tabelle (Stueck/Betrag), Auf 100 %, Kredit + Rate uebernehmen."""
import re, sys
import br
from playwright.sync_api import sync_playwright

def positionen(page):
    rows = page.evaluate("""() => [...document.querySelectorAll('.pb-tab tbody tr')].map(r =>
        [...r.querySelectorAll('td')].map(td => td.innerText.trim()))""")
    return rows

def ergebnis(page):
    return page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.pb-grid > div')].map(d =>
        [d.querySelector('.l').innerText, d.querySelector('.w').innerText]))""")

def zelle(page, zeile, spalte, wert):
    grid = page.locator('[data-testid="stDataFrame"]').locator('visible=true').first
    grid.scroll_into_view_if_needed()
    box = grid.bounding_box()
    page.mouse.click(box["x"] + 60, box["y"] + 35 + 17 + zeile * 35)     # Name-Zelle der Zeile
    page.wait_for_timeout(300)
    for _ in range(spalte):
        page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")                    # Editor oeffnen
    page.wait_for_timeout(300)
    page.keyboard.press("Control+A")
    page.keyboard.type(str(wert))
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)              # Streamlit startet den Neuaufbau verzoegert
    br.warte_ruhe(page)
    page.wait_for_timeout(600)

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
    if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
    page.wait_for_timeout(800)
    print("Start:", positionen(page)[0])
    g = page.locator('[data-testid="stDataFrame"]').locator('visible=true').first; g.scroll_into_view_if_needed()
    bx = g.bounding_box(); page.mouse.click(bx["x"] + 60, bx["y"] + 52); page.wait_for_timeout(500)   # Fokus
    zelle(page, 0, 4, "30")                                   # Stueck MSCI World = 30
    print("Stück 30 ->", positionen(page)[0])
    zelle(page, 1, 3, "3000")                                 # Betrag EM = 3000
    print("Betrag 3000 ->", positionen(page)[1])
    zelle(page, 2, 4, "40")                                   # Stueck Bitcoin = 40 (Kurs 50)
    print("Stück 40 ->", positionen(page)[2])
    print("Summe-Badge:", page.locator(".pb-status").first.inner_text())
    page.get_by_role("button", name="⚖️ Rebalancing").click(); br.warte_ruhe(page); page.wait_for_timeout(500)
    print("nach Auf 100 %:", [r[:2] for r in positionen(page)], page.locator(".pb-status").first.inner_text())
    # Kredit
    page.get_by_label("Kredit €", exact=True).fill("20000"); page.keyboard.press("Enter"); br.warte_ruhe(page)
    page.get_by_label("Kreditzins % p. a.", exact=True).fill("5"); page.keyboard.press("Enter"); br.warte_ruhe(page)
    page.get_by_role("button", name="Rate übernehmen").click(); br.warte_ruhe(page); page.wait_for_timeout(500)
    print("Rate:", page.get_by_label("Kreditrate €/Monat", exact=True).input_value())
    e = ergebnis(page)
    print("Ergebnis:", {k: e[k] for k in ("Verfügbares Anlagekapital", "Monatlicher Netto-Cashflow",
                                          "Verbleibende Kreditschulden", "Nettoendvermögen", "Kreditzinsen gesamt")})
    print("KPIs:", page.evaluate("() => [...document.querySelectorAll('.pb-kpi')].map(k => k.innerText.replace(/\\n/g,' | '))"))
    # Laufzeit in Monaten
    page.locator('[data-testid="stButtonGroup"] button', has_text="Monate").first.click(); br.warte_ruhe(page)
    print("Laufzeit (Monate):", page.get_by_label("Laufzeit (Monate)", exact=True).input_value())
    page.screenshot(path=sys.argv[1], full_page=True)
    txt = br.text(page)
    print("Fehler:", [z for z in txt.splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
