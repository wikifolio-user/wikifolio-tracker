"""Portfolio Builder: Entnahmeplan - fester Betrag (Verkauf anteilig) und Entnahme ueber Stueckzahlen je Position."""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch
S = sys.argv[1]

def plan(page):
    return page.evaluate("""() => [...document.querySelectorAll('.st-key-pb_entnahmeplan .pb-tab tbody tr')].map(r =>
        [...r.querySelectorAll('td')].map(td => td.innerText.trim()).join(' | '))""")

def ergebnis(page, label):
    t = page.locator(".pb-grid").first.inner_text().split("\n")
    return t[t.index(label) + 1] if label in t else None

def verkauf(page, zeile, wert):
    grid = page.locator('.st-key-pb_entnahmeplan [data-testid="stDataFrame"]').first
    grid.scroll_into_view_if_needed(); box = grid.bounding_box()
    page.mouse.click(box["x"] + 60, box["y"] + 52 + zeile * 35); page.wait_for_timeout(400)
    page.keyboard.press("ArrowRight")          # Spalte "Verkauf Stk./Monat" direkt hinter dem Namen
    page.keyboard.press("Enter"); page.wait_for_timeout(300)
    page.keyboard.press("Control+A"); page.keyboard.type(wert); page.wait_for_timeout(300)
    page.keyboard.press("Enter"); page.wait_for_timeout(2500); br.warte_ruhe(page)

for w in [int(a) for a in sys.argv[2:]] or [1440]:
    with sync_playwright() as p:
        b, page = frisch(p)
        if w != 1440:
            page.set_viewport_size({"width": w, "height": 900}); page.wait_for_timeout(800)
        page.get_by_label("Entnahme €/Monat", exact=True).fill("200"); page.keyboard.press("Enter")
        page.wait_for_timeout(1500); br.warte_ruhe(page)
        print(w, "Betrag-Plan:"); [print("   ", z) for z in plan(page)]
        print(w, "Entnahmen + Ausgaben:", ergebnis(page, "ENTNAHMEN + AUSGABEN") or ergebnis(page, "Entnahmen + Ausgaben"))
        page.locator(".st-key-pb_entnahmeplan").get_by_text("Stückzahlen").click(); page.wait_for_timeout(1500)
        br.warte_ruhe(page)
        print(w, "Entnahme-Feld gesperrt:", page.get_by_label("Entnahme €/Monat", exact=True).is_disabled())
        print(w, "Hinweis ohne Verkauf:", page.locator(".st-key-pb_entnahmeplan").inner_text().count("Noch keine Verkäufe"))
        verkauf(page, 0, "3")
        verkauf(page, 2, "10")
        print(w, "Stück-Plan:"); [print("   ", z) for z in plan(page)]
        print(w, "Entnahmen + Ausgaben:", ergebnis(page, "ENTNAHMEN + AUSGABEN") or ergebnis(page, "Entnahmen + Ausgaben"))
        print(w, "Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
        page.locator(".st-key-pb_entnahmeplan").screenshot(path=f"{S}/entnahme_{w}.png")
        b.close()
