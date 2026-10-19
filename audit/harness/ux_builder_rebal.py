"""Portfolio Builder: Werte mit 0 % und ohne Kurs (wie alte gespeicherte Staende) -> Rebalancing rechnet alles neu."""
import sys
import br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch, zeilen, zelle, tippe_neu

with sync_playwright() as p:
    b, page = frisch(p)
    zelle(page, 1, 4, "0")            # Emerging Markets -> 0 %
    zelle(page, 2, 4, "0")            # Bitcoin -> 0 %
    tippe_neu(page, 4, "SAP")         # neue Zeile ohne Kurs
    zelle(page, 4, 4, "0")
    print("vorher:")
    for z in zeilen(page): print("   ", z)
    print("Hinweis:", [t for t in page.locator(".pb-hinweis", has_text="Noch nicht eingerechnet").all_inner_texts()][:1])
    page.get_by_role("button", name="⚖️ Rebalancing").click(); page.wait_for_timeout(2500); br.warte_ruhe(page)
    print("nach Rebalancing (anteilig):")
    for z in zeilen(page): print("   ", z)
    print("Hinweis weg:", page.locator(".pb-hinweis", has_text="Noch nicht eingerechnet").count() == 0)
    sb = page.locator(".st-key-pb_reihe_rebal [data-testid='stSelectbox']").first
    sb.locator("input").click(); page.wait_for_timeout(300); page.keyboard.type("gleich"); page.keyboard.press("Enter")
    page.wait_for_timeout(800); br.warte_ruhe(page)
    page.get_by_role("button", name="⚖️ Rebalancing").click(); page.wait_for_timeout(2500); br.warte_ruhe(page)
    print("nach Rebalancing (gleich):")
    for z in zeilen(page): print("   ", z)
    page.locator(".st-key-pb_reihe_rebal").screenshot(path=sys.argv[1] if len(sys.argv) > 1 else "/dev/null")
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
