"""Gleiche Kennzahl an mehreren Stellen: Depotkachel <-> Vermoegensaufbau-Tabelle <-> Prognose-Startzeile."""
import re, sys
import br
br.URL = sys.argv[1] if len(sys.argv) > 1 else br.URL
from playwright.sync_api import sync_playwright

def zahl(s):
    return float(s.replace(".", "").replace(",", ".").replace("−", "-").replace("+", ""))

def menue(page, a):
    if not page.locator(".st-key-nav_menue button", has_text=a).first.is_visible():
        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
    page.locator(".st-key-nav_menue button", has_text=a).first.click(); br.warte_ruhe(page, 180)

with sync_playwright() as p:
    b, ctx, page = br.start(p, 1440, 900, False)
    br.login(page, sys.argv[2] if len(sys.argv) > 2 else "admin", sys.argv[3] if len(sys.argv) > 3 else "Admin-Test-Passwort-1")
    menue(page, "Depot")
    t = br.text(page)
    m = re.search(r"DEPOTWERT\n([\d\.,]+)\s?€", t, re.I)
    dw = zahl(m.group(1)) if m else None
    m2 = re.search(r"Ø p\.a\. seit Kauf( \(hochgerechnet\))?\s*([−\-\+]?[\d\.,]+) %", t, re.I)
    pa = zahl(m2.group(2)) if m2 else None
    print("Kachel: Depotwert", dw, "Ø p.a.", pa, "hochgerechnet" if m2 and m2.group(1) else "")
    karten = re.findall(r"Ø p\.a\. seit Kauf[^\n%]*?\s*([−\-\+]?[\d\.,]+) %", t, re.I)
    print("Ø p.a.-Chips (alle Karten):", karten)
    menue(page, "Vermögensaufbau")
    zeilen = [z for z in page.locator("table tr").all_inner_texts() if "Hauptindizes Global" in z]
    print("Tabelle eigene Zeile:", zeilen[:1])
    kopf = [z for z in page.locator("table thead tr").all_inner_texts() if "WERT" in z.upper()]
    print("Kopf:", kopf[:1])
    if zeilen and pa is not None:
        zellen = [c.strip() for c in zeilen[0].split("\t")]
        print("  Zellen:", zellen)
    menue(page, "Zukunfts-Prognose")
    t = br.text(page)
    st_zeile = [z for z in t.splitlines() if "Start (heute)" in z][:2]
    i = t.upper().find("START (HEUTE)")
    print("Prognose Startzeile:", t[i:i + 160].replace("\n", " | ") if i >= 0 else None)
    b.close()
