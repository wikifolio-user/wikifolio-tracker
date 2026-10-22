"""360°-Messlauf: alle Ansichten + ihre Reiter/Pillen (erste Ebene) je Breite und Rolle.
Aufruf: python x360.py <ausgabe.json> <rolle> <breite>x<hoehe>[t] [...]   (t = Touch/Mobil)"""
import json, os, sys, time
from playwright.sync_api import sync_playwright
import br
from ux_mess import MESS_JS, axe

ROLLEN = {"admin": "Admin-Test-Passwort-1", "maria": "Maria-Test-Pass-1", "neu": "Neu-Test-Pass-12",
          "leser": "Leser-Pass-123"}
FEHLER_JS = """() => { const m = document.querySelector('[data-testid=stMain]'); if (!m) return [];
  const aus = [];
  for (const e of m.querySelectorAll('[data-testid=stException], [data-testid=stAlertContentError]'))
     aus.push(e.innerText.trim().replace(/\\s+/g,' ').slice(0, 160));
  return aus; }"""
UNTER_JS = """() => { const m = document.querySelector('[data-testid=stMain]'); const aus = [];
  for (const g of m.querySelectorAll('[data-testid=stButtonGroup]')) {
     const k = [...g.querySelectorAll('button')].map(b => b.innerText.trim()).filter(Boolean);
     if (k.length > 1 && k.length <= 12) aus.push(['pill', k]); }
  for (const l of m.querySelectorAll('[role=tablist]')) {
     const k = [...l.querySelectorAll('[role=tab]')].map(b => b.innerText.trim()).filter(Boolean);
     if (k.length > 1) aus.push(['tab', k]); }
  return aus; }"""


def messen(page, touch, mit_axe):
    page.wait_for_timeout(300)
    m = page.evaluate(MESS_JS, touch)
    m["fehler"] = page.evaluate(FEHLER_JS)
    m["axe"] = axe(page) if mit_axe else None
    m.pop("winzig", None)
    m["klein"] = len(m["klein"])
    return m


def lauf(aus, rolle, geraete):
    erg = []
    with sync_playwright() as p:
        for g in geraete:
            touch = g.endswith("t")
            w, h = map(int, g.rstrip("t").split("x"))
            mit_axe = w in (375, 820, 1440)
            b, ctx, page = br.start(p, w, h, touch)
            br.login(page, rolle, ROLLEN[rolle]); page.wait_for_timeout(800)
            start = page.evaluate(MESS_JS, touch)
            erg.append({"geraet": g, "rolle": rolle, "ansicht": "START", "teil": "", "ueberlauf": start["ueberlauf"]})
            namen = page.evaluate("""() => [...document.querySelectorAll('.st-key-nav_menue button')]
                .map(b => b.innerText.trim()).filter(t => t && !t.includes('aktualisieren') && !t.includes('Abmelden') && !t.includes('logout'))""")
            for ansicht in namen:
                try:
                    if not page.locator(".st-key-nav_menue button", has_text=ansicht).first.is_visible():
                        page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page)
                    n0 = len(page.konsole); t0 = time.time()
                    page.locator(".st-key-nav_menue button", has_text=ansicht).first.click()
                    br.warte_ruhe(page, 180)
                    d = round(time.time() - t0, 2)
                    m = messen(page, touch, mit_axe)
                    page.screenshot(path=f"{os.path.dirname(aus)}/shots/{rolle}_{g}_{namen.index(ansicht):02d}.png")
                    erg.append({"geraet": g, "rolle": rolle, "ansicht": ansicht, "teil": "", "dauer": d, **m,
                                "konsole": [k for k in page.konsole[n0:] if "error" in k.lower()][:3]})
                    gesehen = set()
                    for art, knoepfe in page.evaluate(UNTER_JS)[:3]:
                        for k in knoepfe[1:]:
                            if (art, k) in gesehen:
                                continue
                            gesehen.add((art, k))
                            loc = (page.locator("[data-testid=stMain] [role=tab]", has_text=k) if art == "tab" else
                                   page.locator("[data-testid=stMain] [data-testid=stButtonGroup] button", has_text=k))
                            loc = loc.filter(visible=True).first
                            if not loc.count():
                                continue
                            n0 = len(page.konsole); t0 = time.time()
                            loc.click(); br.warte_ruhe(page, 120)
                            m2 = messen(page, touch, False)
                            erg.append({"geraet": g, "rolle": rolle, "ansicht": ansicht, "teil": f"{art}:{k}",
                                        "dauer": round(time.time() - t0, 2), **m2,
                                        "konsole": [x for x in page.konsole[n0:] if "error" in x.lower()][:3]})
                except Exception as e:
                    erg.append({"geraet": g, "rolle": rolle, "ansicht": ansicht, "teil": "HARNESS",
                                "fehler": [f"Harness: {str(e)[:200]}"]})
                    try:
                        page.goto(br.URL); br.warte_ruhe(page)
                        if page.get_by_placeholder("Benutzername eingeben").count():
                            br.login(page, rolle, ROLLEN[rolle])
                    except Exception:
                        pass
            print(rolle, g, "fertig", flush=True)
            json.dump(erg, open(aus, "w"), ensure_ascii=False, indent=0)
            b.close()
    return erg


if __name__ == "__main__":
    lauf(sys.argv[1], sys.argv[2], sys.argv[3:])
