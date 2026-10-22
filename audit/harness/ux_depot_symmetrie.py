"""Depot-Ansicht: Depot- und Kursspalte gleich aufgebaut (Kopfzeilen und Kacheln auf gleicher Hoehe)."""
import sys, br
from playwright.sync_api import sync_playwright
S = sys.argv[1]

def oeffne(page, name):
    if not page.locator(".st-key-nav_menue button", has_text=name).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=name).first.click(); br.warte_ruhe(page, 120)
with sync_playwright() as p:
    for breite, mobil in ((1440, False), (1024, False), (390, True)):
        b, ctx, page = br.start(p, breite, 900, mobil)
        br.login(page, "admin", "Admin-Test-Passwort-1"); br.warte_ruhe(page, 180); page.wait_for_timeout(1500)
        oeffne(page, "Depot"); page.wait_for_timeout(1500)
        m = page.evaluate("""() => { const r = s => { const e = document.querySelector(s); if (!e) return null;
            const b = e.getBoundingClientRect(); return [Math.round(b.top), Math.round(b.height), Math.round(b.width)]; };
          const heros = [...document.querySelectorAll('.st-key-depot_spalten [data-testid="stColumn"]')].slice(0, 2).map(c => {
            const k = [...c.querySelectorAll('.hero, .quote')].filter(e => e.offsetParent && e.getBoundingClientRect().height > 50);
            const l = k[k.length - 1]; if (!l) return null; const b = l.getBoundingClientRect();
            return [l.className, Math.round(b.top), Math.round(b.bottom)]; });
          return {links: r('.st-key-depot_kopf_links'), rechts: r('.st-key-depot_kopf_rechts'), heros}; }""")
        print(breite, m)
        page.screenshot(path=f"{S}/depot_sym_{breite}.png")
        if mobil:
            page.locator(".st-key-depot_kopf_rechts").scroll_into_view_if_needed(); page.wait_for_timeout(500)
            page.screenshot(path=f"{S}/depot_sym_{breite}_kurse.png")
        b.close()
