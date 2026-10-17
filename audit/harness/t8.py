import br, sys, time
from playwright.sync_api import sync_playwright
ANS = ["Test-Depot","Einstellungen","Chronik","Vermögensaufbau","Performance > 2026","Performance > 2021","Candlestick","Zukunfts-Prognose","Szenario-Simulator","Portfolio-Planer","Watchlist","Abfindungsrechner","Zinseszinsrechner","Benutzer"]
mobil = sys.argv[1] == "mobil"
with sync_playwright() as p:
    b, ctx, page = br.start(p, 390 if mobil else 1400, 844 if mobil else 900, mobil)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    br.shot(page, f"m_{'mobil' if mobil else 'desk'}_00_start")
    for i, a in enumerate(ANS, 1):
        n0 = len(page.konsole)
        dt = br.ansicht(page, a)
        t = br.text(page)
        fehler = [l for l in t.splitlines() if l.startswith("⚠️") or "Fehler" in l or "Traceback" in l or "konnte nicht" in l][:3]
        breite = page.evaluate("() => document.documentElement.scrollWidth")
        print(f"{a:22s} {dt:6.1f}s  scrollWidth={breite}  Fehlertexte={fehler}  Konsole={[k for k in page.konsole[n0:] if 'error' in k][:2]}")
        br.shot(page, f"m_{'mobil' if mobil else 'desk'}_{i:02d}_{a.split()[0].replace('>','')}")
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    b.close()
