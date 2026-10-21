"""Investment-Scanner (eigene Ansicht): Ziel im Builder eintragen, Scanner oeffnen (Laptop: Knopf im Builder,
Handy: Menue-Kachel), scannen, alle Reiter, uebernehmen -> zurueck im Builder."""
import sys, time
import br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch, zeilen
S = sys.argv[1]
for w in ([int(a) for a in sys.argv[2:]] or [1440, 390]):
    with sync_playwright() as p:
        if w == 1440:
            b, page = frisch(p)
        else:
            b, ctx, page = br.start(p, w, 900, True)
            br.login(page, "neu", "Neu-Test-Pass-12"); page.wait_for_timeout(1500)
            if not page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.is_visible():
                page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
            page.locator(".st-key-nav_menue button", has_text="Portfolio Builder").first.click(); br.warte_ruhe(page, 60)
        page.get_by_label("Zielvermögen €", exact=True).fill("80000"); page.keyboard.press("Enter")
        page.wait_for_timeout(1200); br.warte_ruhe(page)
        print(w, "Scanner-Karte im Builder:", page.locator(".st-key-pb_scanner").count())
        if w == 1440:
            page.locator(".st-key-pb_zum_scanner button").first.click(); br.warte_ruhe(page, 60)
        else:
            page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
            page.locator(".st-key-nav_menue button", has_text="Investment-Scanner").first.click(); br.warte_ruhe(page, 60)
        eck = page.locator(".st-key-pb_scan_eckdaten").first
        print(w, "Eckdaten (vorbelegt):", [eck.get_by_role("spinbutton", name=n).input_value() for n in
                                          ("Startkapital €", "Einzahlung €/Monat", "Laufzeit (Jahre)", "Zielvermögen €")])
        if w == 1440:
            eck.get_by_role("spinbutton", name="Startkapital €").fill("25000"); page.keyboard.press("Enter")
            page.wait_for_timeout(1500); br.warte_ruhe(page)
        knopf = page.locator(".st-key-pb_scan_los button").first
        knopf.scroll_into_view_if_needed()
        t = time.time(); knopf.click(); page.wait_for_timeout(1500); br.warte_ruhe(page, 120)
        print(w, "Rechenzeit ca.", round(time.time() - t, 1), "s")
        karte = page.locator(".st-key-pb_scanner").first
        txt = karte.inner_text()
        print(w, "Fehler:", [z for z in br.text(page).splitlines() if "Fehler" in z or "Traceback" in z or "⚠️ Invest" in z][:3])
        print(w, "Depotzeilen:", karte.locator("table.pb-scan").first.locator("tbody tr").count())
        print(w, "Summe:", [z for z in txt.splitlines() if z.startswith("Summe")][:1])
        karte.screenshot(path=f"{S}/scan_{w}_depot.png")
        for reiter in ("🏆 Top-Investments", "📈 Prognose", "⚠️ Risiken", "🧭 Plan", "ℹ️ Daten"):
            karte.get_by_role("tab", name=reiter).click(); page.wait_for_timeout(1200); br.warte_ruhe(page)
            karte.screenshot(path=f"{S}/scan_{w}_{reiter.split()[1]}.png")
        k = karte.locator(".pb-scan-kpis").first.inner_text().replace("\n", " | ") if karte.locator(".pb-scan-kpis").count() else ""
        print(w, "KPIs:", k[:400])
        if w == 1440:
            karte.get_by_role("tab", name="📦 Musterdepot").click(); page.wait_for_timeout(800)
            page.locator(".st-key-pb_scan_uebernehmen button").first.click(); page.wait_for_timeout(3000); br.warte_ruhe(page, 120)
            print(w, "Builder offen:", page.locator(".pb-titel").first.inner_text(),
                  "| Builder-Anfangskapital:", page.get_by_role("spinbutton", name="Anfangskapital €").input_value())
            z = zeilen(page)
            print(w, "nach Übernahme:", len(z), "Zeilen, z. B.", z[:3], z[-1:])
        b.close()
