"""Investment Scanner Pro (eigenes Board): Menue-Kachel, berechnen, Kaufplan, Sofortentnahme, Szenarien (Laptop + Handy)."""
import sys
import br
from playwright.sync_api import sync_playwright
S = sys.argv[1]
for w in [int(a) for a in sys.argv[2:]] or [1440, 390]:
    with sync_playwright() as p:
        b, ctx, page = br.start(p, w, 900, w < 800)
        br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
        if not page.locator(".st-key-nav_menue button", has_text="Scanner Pro").first.is_visible():
            page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
        page.locator(".st-key-nav_menue button", has_text="Scanner Pro").first.click(); br.warte_ruhe(page, 60)
        page.get_by_role("spinbutton", name="Sofortentnahme (€)").fill("3000")
        page.get_by_role("button", name="🔍 Investment Scanner berechnen").click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 120)
        txt = br.text(page)
        print(w, "Fehler:", [z for z in txt.splitlines() if "Fehler" in z or "Traceback" in z or "nicht berechnet" in z][:3])
        for k in ("Gesamtdepot (Planungsstand)", "Geplante Neukäufe", "Sofort auszahlbar (Modell)", "Median-Endvermögen", "Zielchance (Modell)"):
            i = txt.find(k); print(w, k, "->", txt[i:i + len(k) + 20].replace("\n", " ") if i >= 0 else None)
        print(w, "Tabellen:", page.locator('[data-testid="stDataFrame"]').count())
        page.get_by_role("button", name="🔄 Jetzt echte Börsenkurse abrufen").click(); page.wait_for_timeout(3000); br.warte_ruhe(page, 120)
        print(w, "Kursabruf:", [z for z in br.text(page).splitlines() if "exakt zugeordnet" in z or "Nicht verfügbar" in z][:2])
        page.get_by_text("Für Neukäufe nur frisch abgerufene EUR-Kurse verwenden").click(); page.wait_for_timeout(2000); br.warte_ruhe(page)
        t2 = br.text(page); i = t2.find("Geplante Neukäufe")
        print(w, "ohne Echtkurs-Pflicht:", t2[i:i + 40].replace("\n", " "))
        ueber = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 1")
        print(w, "horizontaler Ueberlauf:", ueber)
        page.screenshot(path=f"{S}/pro_{w}.png", full_page=True)
        b.close()
