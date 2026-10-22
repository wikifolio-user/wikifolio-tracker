"""Stoerungen: Kursquelle aus, GitHub-Schreiben 500, GitHub-Lesen 500 - kein Absturz, verstaendliche Meldung,
kein stiller Datenverlust. Nur Sandbox (fake_net)."""
import json, time
import br
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright

def fault(d):
    json.dump(d, open("fault.json", "w"))

def menue(page, a):
    if not page.locator(".st-key-nav_menue button", has_text=a).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=a).first.click(); br.warte_ruhe(page, 180)

def fehler(page):
    return page.evaluate("""() => [...document.querySelectorAll('[data-testid=stException]')].map(e => e.innerText.slice(0,120))""")

with sync_playwright() as p:
    b, ctx, page = br.start(p, 390, 844, True)
    # 1) Kursquelle faellt aus
    fault({"lstc": "down"})
    br.login(page, "maria", "Maria-Test-Pass-1")
    for a in ("Depot", "Vermögensaufbau", "Zukunfts-Prognose", "Candlestick", "Szenario", "Performance > 2026"):
        menue(page, a)
        t = br.text(page)
        print("lstc down |", a, "| Absturz:", fehler(page), "| Hinweis:", [z[:90] for z in t.splitlines() if "⚠" in z or "keine" in z.lower() and "kurs" in z.lower()][:1])
    fault({})
    # 2) GitHub-Schreiben schlaegt fehl
    menue(page, "Depot verwalten")
    page.locator("summary", has_text="Sparrate und Entnahme anpassen").first.click(); page.wait_for_timeout(400)
    fault({"github_write": "500"})
    page.get_by_role("spinbutton", name="Monatliche Sparrate (€)").first.fill("77"); page.keyboard.press("Tab"); br.warte_ruhe(page)
    page.get_by_role("button", name="💾 Sparrate speichern").click(); br.warte_ruhe(page)
    t = br.text(page)
    print("github_write 500 | Meldung:", [z[:120] for z in t.splitlines() if "fehl" in z.lower() or "nicht gespeichert" in z.lower() or "speicher" in z.lower()][:2], "| Absturz:", fehler(page))
    fault({})
    b.close()
    # 3) GitHub-Lesen 500 (Lesecache 60 s ablaufen lassen)
    time.sleep(62)
    fault({"github_read": "500"})
    b, ctx, page = br.start(p, 390, 844, True)
    page.goto(br.URL); page.get_by_placeholder("Benutzername eingeben").wait_for()
    page.get_by_placeholder("Benutzername eingeben").fill("maria"); page.get_by_placeholder("Passwort eingeben").fill("Maria-Test-Pass-1")
    page.get_by_role("button", name="Anmelden").click(); br.warte_ruhe(page)
    t = page.locator("body").inner_text()
    print("github_read 500 | Login-Meldung:", [z[:120] for z in t.splitlines() if "nicht möglich" in z or "falsch" in z or "vorübergehend" in z][:2])
    fault({})
    b.close()
