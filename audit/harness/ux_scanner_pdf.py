"""Investment-Scanner: beide Musterdepots mit gleichen Spalten und Begruendung je Wert, PDF-Bericht."""
import sys, br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch
S = sys.argv[1]
with sync_playwright() as p:
    b, page = frisch(p)
    page.locator(".st-key-pb_zum_scanner button").first.click(); br.warte_ruhe(page, 60)
    eck = page.locator(".st-key-pb_scan_eckdaten").first
    for n, v in (("Startkapital €", "160000"), ("Einzahlung €/Monat", "0"), ("Laufzeit (Jahre)", "5"),
                 ("Zielvermögen €", "1000000")):
        eck.get_by_role("spinbutton", name=n).fill(v); page.keyboard.press("Enter"); page.wait_for_timeout(800)
        br.warte_ruhe(page)
    if not page.locator(".st-key-pb_scan_profil button[aria-checked='true']", has_text="Eigene").count():
        page.locator(".st-key-pb_scan_profil button", has_text="Eigene").first.click(); page.wait_for_timeout(1200)
        br.warte_ruhe(page)
    for n, v in (("ETFs %", "30"), ("Aktien %", "30"), ("wikifolios %", "30"), ("Cash %", "10"), ("Max. je Position %", "10")):
        page.get_by_role("spinbutton", name=n).fill(v); page.keyboard.press("Enter"); page.wait_for_timeout(800)
        br.warte_ruhe(page)
    page.locator(".st-key-pb_scan_los button").first.click(); page.wait_for_timeout(2000); br.warte_ruhe(page, 240)
    tabs = page.evaluate("""() => [...document.querySelectorAll('table.pb-scan.depot')].map(t => ({
        kopf: [...t.querySelectorAll('th')].map(x => x.innerText.trim()),
        breiten: [...t.querySelectorAll('th')].map(x => Math.round(x.getBoundingClientRect().width)),
        ohne: [...t.querySelectorAll('tbody tr:not(.summe)')].filter(r => !r.cells[8].innerText.trim()).length,
        zeilen: t.querySelectorAll('tbody tr').length}))""")
    for t in tabs:
        print("Tabelle:", t["zeilen"], "Zeilen, ohne Begründung:", t["ohne"], "| Breiten", t["breiten"])
    print("gleiche Spalten:", len({tuple(t["kopf"]) for t in tabs}) == 1, "| gleiche Breiten:",
          len({tuple(t["breiten"]) for t in tabs}) == 1)
    page.locator("table.pb-scan.depot").first.scroll_into_view_if_needed()
    page.screenshot(path=f"{S}/depots.png", full_page=False)
    page.locator(".st-key-pb_scan_pdf_knopf button").first.click(); page.wait_for_timeout(1500); br.warte_ruhe(page, 120)
    with page.expect_download() as d:
        page.locator(".st-key-pb_scan_pdf_download button").first.click()
    d.value.save_as(f"{S}/bericht.pdf")
    print("PDF gespeichert")
    print("Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z][:3])
    b.close()
