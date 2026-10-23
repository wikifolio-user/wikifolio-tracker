"""Zwei Sitzungen desselben Benutzers legen gleichzeitig je eine Position an - keine darf verloren gehen."""
import threading, re, json
import br
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright

def vorbereiten(p, name):
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, "maria", "Maria-Test-Pass-1")
    page.locator(".st-key-nav_menue button", has_text="Depot verwalten").first.click(); br.warte_ruhe(page)
    page.locator("summary", has_text="Positionen verwalten").first.click(); page.wait_for_timeout(400)
    f = page.locator("[data-testid=stForm]:visible").filter(has_text="Position anlegen").first
    f.get_by_label("Name").fill(name)
    f.get_by_label("Kaufkurs (€)").fill("10"); f.get_by_label("Kaufkurs (€)").press("Tab")
    f.get_by_label("Investiertes Kapital (€)").fill("100"); f.get_by_label("Investiertes Kapital (€)").press("Tab")
    return b, page, f

with sync_playwright() as p:
    b1, p1, f1 = vorbereiten(p, "Parallel-A")
    b2, p2, f2 = vorbereiten(p, "Parallel-B")
    f1.get_by_role("button", name="➕ Position anlegen").click(no_wait_after=True)
    f2.get_by_role("button", name="➕ Position anlegen").click(no_wait_after=True)
    br.warte_ruhe(p1); br.warte_ruhe(p2)
    p1.reload(); br.login(p1, "maria", "Maria-Test-Pass-1")
    p1.locator(".st-key-nav_menue button", has_text="Depot verwalten").first.click(); br.warte_ruhe(p1)
    p1.locator("summary", has_text="Positionen verwalten").first.click(); p1.wait_for_timeout(500)
    t = br.text(p1)
    namen = re.findall(r"Position \d+: (.+)", t)
    print("Positionen nach parallelem Anlegen:", namen)
    print("PASS" if "Parallel-A" in namen and "Parallel-B" in namen else "FAIL", "beide vorhanden")
    b1.close(); b2.close()
