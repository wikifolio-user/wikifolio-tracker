"""Planer/App durchklicken: je Klick Wartezeit im Browser, Serverlaeufe und Netzzugriffe.

Serverlaeufe: PROFIL_DIR gesetzt und render_dashboard so umhuellt, dass jeder Lauf eine Datei
"NNNN_<sek>s_frag.prof" schreibt; Netzzugriffe: NETZ_LOG (fake_net protokolliert GET/PUT)."""
import collections, json, os, sys, time
import br
from playwright.sync_api import sync_playwright
PROF, NETZ = sys.argv[1], sys.argv[2]
rolle, pw = (sys.argv[3], sys.argv[4]) if len(sys.argv) > 4 else ("admin", "Admin-Test-Passwort-1")
erg = []
def zeilen():
    try:
        return open(NETZ).read().splitlines()
    except FileNotFoundError:
        return []
def schritt(page, name, fn):
    vor, n0 = set(os.listdir(PROF)), len(zeilen())
    t0 = time.time(); fn(); br.warte_ruhe(page, 240); dt = time.time() - t0
    laeufe = [f.split("_")[1] for f in sorted(set(os.listdir(PROF)) - vor)]
    netz = collections.Counter(" ".join(z.split()[1:2]) + " " + z.split()[2].split("/contents/")[-1][:60] for z in zeilen()[n0:])
    gets = sum(v for k, v in netz.items() if k.startswith("GET")); puts = sum(v for k, v in netz.items() if k.startswith("PUT"))
    erg.append({"aktion": name, "sek": round(dt, 2), "laeufe": laeufe, "get": gets, "put": puts, "netz": dict(netz)})
    print(f"{name:32s} {dt:5.2f}s  Server: {' '.join(laeufe):24s} GET {gets:3d}  PUT {puts}", flush=True)
with sync_playwright() as p:
    b, ctx, page = br.start(p, 375, 667, True)
    schritt(page, "Login", lambda: br.login(page, rolle, pw))
    page.wait_for_timeout(1500)
    if not page.locator(".st-key-nav_menue button", has_text="Portfolio-Planer").first.is_visible():
        schritt(page, "Menü (gemerkte Ansicht)", lambda: page.get_by_role("button", name="☰ Menü").click())
    if len(sys.argv) > 5 and sys.argv[5] == "app":
        for runde in (1, 2):
            for ansicht in ["Test-Depot", "Einstellungen", "Chronik", "Vermögensaufbau", "Performance > 2026",
                            "Candlestick", "Zukunfts-Prognose", "Szenario-Simulator", "Watchlist", "Abfindungsrechner",
                            "Zinseszinsrechner"]:
                schritt(page, f"R{runde} {ansicht}", lambda a=ansicht: page.locator(".st-key-nav_menue button", has_text=a).first.click())
                schritt(page, f"R{runde}   Menü", lambda: page.get_by_role("button", name="☰ Menü").click())
        b.close()
        json.dump(erg, open(os.path.join(PROF, "..", "klicks.json"), "w"), ensure_ascii=False, indent=1)
        sys.exit(0)
    schritt(page, "Planer öffnen", lambda: page.locator(".st-key-nav_menue button", has_text="Portfolio-Planer").first.click())
    if page.locator(".st-key-pl_nav_schritt button").count() == 0:
        schritt(page, "Ansicht: Schritt für Schritt", lambda: page.locator(".st-key-pl_nav_ansicht button", has_text="Schritt für Schritt").first.click())
    for i in range(5):
        schritt(page, f"Schritt {i+1}", lambda i=i: page.locator(".st-key-pl_nav_schritt button").nth(i).click())
        k = page.locator(".st-key-pl_nav_unter button").count()
        for j in range(1, k):
            schritt(page, f"  Unterseite {j+1}/{k}", lambda j=j: page.locator(".st-key-pl_nav_unter button").nth(j).click())
    schritt(page, "Menü", lambda: page.get_by_role("button", name="☰ Menü").click())
    schritt(page, "Depot öffnen", lambda: page.locator(".st-key-nav_menue button", has_text="Depot").first.click())
    b.close()
json.dump(erg, open(os.path.join(PROF, "..", "klicks.json"), "w"), ensure_ascii=False, indent=1)
