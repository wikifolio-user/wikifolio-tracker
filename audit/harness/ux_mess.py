"""UX-Messlauf: alle Ansichten je Geraet und Rolle.

Misst je Ansicht: Ladezeit, horizontalen Ueberlauf, Elemente ausserhalb des Bildschirms,
abgeschnittene Texte, zu kleine Touch-Ziele (< 44 px, nur Touch-Geraete), sehr kleine
Schrift (< 12 px), axe-core-Verstoesse (WCAG 2 A/AA), Konsolenfehler; dazu Screenshot der
ganzen Seite. Aufruf: python3 ux_mess.py [geraet ...]
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

import br

GERAETE = {
    "iphone-se": (375, 667, True),
    "iphone-pro-max": (430, 932, True),
    "ipad-hoch": (768, 1024, True),
    "ipad-quer": (1024, 768, True),
    "laptop": (1440, 900, False),
    "desktop": (1920, 1080, False),
}
ROLLEN = [("admin", "Admin-Test-Passwort-1"), ("maria", "Maria-Test-Pass-1"),
          ("neu", "Neu-Test-Pass-12"), ("leser", "Leser-Pass-123")]
AXE = open(os.path.join(os.path.dirname(__file__), "..", "axe", "package", "axe.min.js")).read()
AUS = os.path.join(os.path.dirname(__file__), "..", "ux")

MESS_JS = r"""
(touch) => {
  const vw = window.innerWidth;
  const sichtbar = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && e.offsetParent !== null; };
  const scrollVorfahr = e => { for (let p = e.parentElement; p; p = p.parentElement) {
      const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') return true; } return false; };
  const name = e => ((e.innerText || e.getAttribute('aria-label') || e.value || e.tagName) + '').trim().replace(/\s+/g, ' ').slice(0, 40);
  const haupt = document.querySelector('[data-testid=stMain]');
  const ueberlauf = Math.max(document.documentElement.scrollWidth, haupt ? haupt.scrollWidth : 0) - vw;
  const raus = [];
  for (const e of document.querySelectorAll('[data-testid=stMain] *')) {
    if (!sichtbar(e) || e.children.length) continue;
    const r = e.getBoundingClientRect();
    if (r.right > vw + 2 && !scrollVorfahr(e)) raus.push(name(e));
  }
  const geschnitten = [];
  for (const e of document.querySelectorAll('[data-testid=stMain] p, [data-testid=stMain] span, [data-testid=stMain] div, [data-testid=stMain] td, [data-testid=stMain] th, [data-testid=stMain] label, button')) {
    if (!sichtbar(e) || !e.innerText || e.children.length > 1) continue;
    if (e.getBoundingClientRect().width <= 2) continue;  // nur fuer Screenreader (visuell versteckt)
    const s = getComputedStyle(e);
    if ((s.overflow === 'hidden' || s.overflowX === 'hidden' || s.textOverflow === 'ellipsis') && e.scrollWidth > e.clientWidth + 2)
      geschnitten.push(name(e));
  }
  const klein = [];
  if (touch) for (const e of document.querySelectorAll('button, a[href], input, select, textarea, summary, [role=tab], [role=button], [role=checkbox], [role=switch], [role=option], [role=radio]')) {
    if (!sichtbar(e)) continue;
    const r = e.getBoundingClientRect();
    if ((r.height < 44 || r.width < 44) && r.height > 0) klein.push(name(e) + ` (${Math.round(r.width)}x${Math.round(r.height)})`);
  }
  const winzig = new Set();
  for (const e of document.querySelectorAll('[data-testid=stMain] *')) {
    if (!sichtbar(e) || !e.childNodes.length) continue;
    const hatText = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (hatText && parseFloat(getComputedStyle(e).fontSize) < 12) winzig.add(name(e) + ' ' + getComputedStyle(e).fontSize);
  }
  const hoehe = haupt ? haupt.scrollHeight : document.body.scrollHeight;
  return {ueberlauf, raus: [...new Set(raus)], geschnitten: [...new Set(geschnitten)], klein: [...new Set(klein)],
          winzig: [...winzig], hoehe};
}
"""


def ansichten_der_startseite(page):
    namen = page.evaluate("""() => [...document.querySelectorAll('.st-key-nav_menue button')]
        .map(b => b.innerText.trim()).filter(t => t && !t.includes('aktualisieren') && !t.includes('logout'))""")
    return [n for n in namen if n and n[0] not in "🔄"]


def axe(page):
    try:
        page.add_script_tag(content=AXE)
        return page.evaluate("""async () => (await axe.run(document, {runOnly: ['wcag2a','wcag2aa']}))
            .violations.map(v => ({id: v.id, impact: v.impact, n: v.nodes.length,
              bsp: v.nodes.slice(0, 2).map(n => n.target.join(' ').slice(-80))}))""")
    except Exception as e:
        return [{"id": "axe-fehler", "impact": str(e)[:80], "n": 0, "bsp": []}]


def voll_screenshot(page, pfad, breite, hoehe, mess):
    h = int(min(max(mess["hoehe"] + 120, hoehe), 9000))
    page.set_viewport_size({"width": breite, "height": h})
    page.wait_for_timeout(500)
    page.screenshot(path=pfad, full_page=False)
    page.set_viewport_size({"width": breite, "height": hoehe})


def lauf(geraet):
    breite, hoehe, touch = GERAETE[geraet]
    erg = []
    with sync_playwright() as p:
        for rolle, pw in ROLLEN:
            b, ctx, page = br.start(p, breite, hoehe, touch)
            os.makedirs(os.path.join(AUS, geraet, rolle), exist_ok=True)
            br.login(page, rolle, pw)
            page.wait_for_timeout(800)
            ansichten = ansichten_der_startseite(page)
            for i, ansicht in enumerate(["START"] + ansichten):
                n0 = len(page.konsole)
                t0 = time.time()
                if ansicht != "START":
                    page.locator(".st-key-nav_menue button", has_text=ansicht).first.click()
                    br.warte_ruhe(page, 180)
                dauer = time.time() - t0
                page.wait_for_timeout(400)
                mess = page.evaluate(MESS_JS, touch)
                verstoesse = axe(page)
                datei = os.path.join(AUS, geraet, rolle, f"{i:02d}.png")
                voll_screenshot(page, datei, breite, hoehe, mess)
                fehlertexte = [l for l in br.text(page).splitlines()
                               if "Fehler" in l or "Traceback" in l or "konnte nicht" in l][:3]
                erg.append({"geraet": geraet, "rolle": rolle, "ansicht": ansicht, "datei": os.path.relpath(datei, AUS),
                            "dauer": round(dauer, 2), **mess, "axe": verstoesse, "fehlertexte": fehlertexte,
                            "konsole": [k for k in page.konsole[n0:] if "error" in k.lower()][:3]})
                if ansicht != "START":
                    page.get_by_role("button", name="☰ Menü").click()
                    br.warte_ruhe(page)
            b.close()
    with open(os.path.join(AUS, f"{geraet}.json"), "w") as f:
        json.dump(erg, f, ensure_ascii=False, indent=1)
    return erg


if __name__ == "__main__":
    for g in (sys.argv[1:] or list(GERAETE)):
        e = lauf(g)
        print(g, len(e), "Ansichten gemessen", flush=True)
