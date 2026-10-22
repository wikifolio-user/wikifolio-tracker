"""Zukunfts-Prognose: Start heute, eigene Prognose-Basis aus der Top-500-Liste hinzufuegen und entfernen."""
import sys, br
from playwright.sync_api import sync_playwright
from ux_merken import oeffne
S = sys.argv[1]
NUTZER = sys.argv[2] if len(sys.argv) > 2 else "neu"
PW = sys.argv[3] if len(sys.argv) > 3 else "Neu-Test-Pass-12"

def basis_namen(page):
    sel = page.get_by_label("Prognose Basis auswählen:", exact=True)
    if not sel.count():
        return []
    sel.first.click(); page.wait_for_timeout(600)
    n = [o.inner_text() for o in page.locator('[role="option"]').all()]
    page.keyboard.press("Escape"); page.wait_for_timeout(300)
    return n

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, NUTZER, PW); page.wait_for_timeout(1500)
    oeffne(page, "Zukunfts-Prognose"); br.warte_ruhe(page, 120)
    exp = page.get_by_text("Prognose-Basis verwalten").first
    print("Verwalten:", exp.inner_text())
    def auf():
        if not page.get_by_text("Aus der Top-500-Liste").first.is_visible():
            page.get_by_text("Prognose-Basis verwalten").first.click(); page.wait_for_timeout(800)
    auf()
    page.screenshot(path=f"{S}/prog_vorher.png", full_page=True)
    vorher = basis_namen(page); print("Basis vorher:", vorher)
    print("Label:", [z for z in br.text(page).splitlines() if "Aus der Top-500-Liste" in z][:1])
    auf()
    feld = page.get_by_label("Aus der Top-500-Liste", exact=False).first
    feld.click(); page.wait_for_timeout(1200)
    opt = page.locator('[role="option"]').first
    print("wähle:", opt.inner_text()); opt.click(); page.wait_for_timeout(800)
    page.locator(".st-key-prog_basis_add button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
    nachher = basis_namen(page); print("Basis nachher:", nachher)
    t = br.text(page)
    print("Fehlermeldung:", [z for z in t.splitlines() if "nicht hinzugefügt" in z or "Nicht gespeichert" in z][:2])
    print("Tabelle Start:", [z for z in t.splitlines() if "Start (heute)" in z][:1] or
          page.locator('[data-testid="stDataFrame"]').count())
    page.screenshot(path=f"{S}/prognose_basis.png", full_page=True)
    auf()
    weg = page.locator("[class*='st-key-prog_basis_weg_'] button")
    print("Entfernen-Knöpfe:", weg.count())
    if weg.count():
        weg.last.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
        auf()
        if weg.count():
            weg.last.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
        print("nach Entfernen:", page.get_by_text("Prognose-Basis verwalten").first.inner_text())
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
