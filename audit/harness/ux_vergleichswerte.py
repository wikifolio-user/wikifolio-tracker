"""Vermoegensaufbau: eigene Vergleichswerte je Benutzer - neu leer, aus Top 500 hinzufuegen, entfernen."""
import sys, br
from playwright.sync_api import sync_playwright
S = sys.argv[1]
NUTZER, PW = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("neu", "Neu-Test-Pass-12")

def oeffne(page, name):
    if not page.locator(".st-key-nav_menue button", has_text=name).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=name).first.click(); br.warte_ruhe(page, 180)

def auf(page):
    if not page.get_by_text("Aus der Top-500-Liste").first.is_visible():
        page.get_by_text("Vergleichswerte verwalten").first.click(); page.wait_for_timeout(800)

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, NUTZER, PW); br.warte_ruhe(page, 120)
    oeffne(page, "Vermögen"); page.wait_for_timeout(1000)
    print("Start:", page.get_by_text("Vergleichswerte verwalten").first.inner_text())
    print("Info leer:", page.get_by_text("Noch keine Vergleichswerte").count())
    auf(page)
    feld = page.get_by_label("Aus der Top-500-Liste", exact=False).first
    feld.click(); page.wait_for_timeout(1000)
    o = page.locator('[role="option"]').nth(2); print("wähle:", o.inner_text()); o.click(); page.wait_for_timeout(600)
    page.locator(".st-key-vgl_add button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
    print("nach Hinzufügen:", page.get_by_text("Vergleichswerte verwalten").first.inner_text())
    t = br.text(page)
    print("Tabelle/Chart:", page.locator(".st-key-chart_vgl_eigen, .st-key-chart_wealth").count(),
          [z for z in t.splitlines() if "Symbolisch" in z][:1])
    print("Fehler:", [z for z in t.splitlines() if "Fehler" in z or "Traceback" in z][:3])
    page.screenshot(path=f"{S}/vgl_{NUTZER}.png", full_page=True)
    auf(page)
    weg = page.locator("[class*='st-key-vgl_weg_'] button")
    print("Entfernen-Knöpfe:", weg.count())
    weg.last.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 180)
    print("nach Entfernen:", page.get_by_text("Vergleichswerte verwalten").first.inner_text())
    b.close()
