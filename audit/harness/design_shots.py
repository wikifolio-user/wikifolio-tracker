"""Ansichten fuer den Design-Vergleich: je Ansicht ein Bild (oberer Bereich), Telefon und Laptop."""
import sys, br
from playwright.sync_api import sync_playwright
S, tag = sys.argv[1], sys.argv[2]
ANS = ["START", "Depot", "Depot verwalten", "Vermögensaufbau", "Zukunfts-Prognose", "Portfolio Builder",
       "Scanner 2.0", "Watchlist", "Zinseszinsrechner", "Abfindungsrechner", "Portfolio-Planer"]
for w, h in ((390, 844), (1440, 900)):
    with sync_playwright() as p:
        b, ctx, page = br.start(p, w, h, w < 600)
        br.login(page, "admin", "Admin-Test-Passwort-1"); page.wait_for_timeout(1000)
        for a in ANS:
            if a != "START":
                if not page.locator(".st-key-nav_menue button", has_text=a).first.is_visible():
                    page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
                page.locator(".st-key-nav_menue button", has_text=a).first.click(); br.warte_ruhe(page, 120)
            page.wait_for_timeout(1800)
            page.screenshot(path=f"{S}/design/{tag}_{w}_{a.replace(' ', '_')}.png")
        b.close()
