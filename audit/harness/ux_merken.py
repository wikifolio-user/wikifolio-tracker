"""Bleiben Eingaben erhalten? Builder: Werte aendern -> andere Ansicht -> zurueck; neue Sitzung."""
import sys
import br
from playwright.sync_api import sync_playwright

def oeffne(page, name):
    if not page.locator(".st-key-nav_menue button", has_text=name).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=name).first.click(); br.warte_ruhe(page, 60); page.wait_for_timeout(500)

def lies(page):
    return {l: page.get_by_label(l, exact=True).input_value() for l in ("Anfangskapital €", "Einzahlung €/Monat", "Zielvermögen €")}

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
    oeffne(page, "Portfolio Builder")
    for l, v in (("Anfangskapital €", 55555), ("Einzahlung €/Monat", 777), ("Zielvermögen €", 222222)):
        page.get_by_label(l, exact=True).fill(str(v)); page.keyboard.press("Enter"); page.wait_for_timeout(1000); br.warte_ruhe(page)
    print("nach Eingabe:", lies(page))
    oeffne(page, "Zinseszinsrechner")
    oeffne(page, "Portfolio Builder")
    print("nach Ansichtswechsel:", lies(page))
    b.close()
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
    oeffne(page, "Portfolio Builder")
    print("neue Sitzung:", lies(page))
    b.close()
