"""Browser-Helfer fuer die Audit-Durchlaeufe (Playwright, lokale Sandbox)."""
import os
import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8601"
EXE = "/opt/pw-browsers/chromium"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shots")
os.makedirs(SHOTS, exist_ok=True)


def warte_ruhe(page, timeout=90):
    """Bis Streamlit fertig gerechnet hat (kein running-State, kein Lade-Overlay)."""
    t0 = time.time()
    page.wait_for_timeout(600)
    while time.time() - t0 < timeout:
        state = page.evaluate("() => document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state')")
        overlay = page.locator(".loading-overlay").count()
        if state not in ("running", "rerunRequested") and not overlay:
            page.wait_for_timeout(400)
            state2 = page.evaluate("() => document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state')")
            if state2 not in ("running", "rerunRequested"):
                return time.time() - t0
        page.wait_for_timeout(250)
    return None


def start(p, breite=1400, hoehe=900, mobil=False):
    b = p.chromium.launch(executable_path=EXE)
    ctx = b.new_context(viewport={"width": breite, "height": hoehe}, is_mobile=mobil,
                        has_touch=mobil, device_scale_factor=1, locale="de-DE", timezone_id="Europe/Berlin")
    page = ctx.new_page()
    page.konsole = []
    page.on("console", lambda m: page.konsole.append(f"{m.type}: {m.text[:200]}"))
    page.on("pageerror", lambda e: page.konsole.append(f"pageerror: {str(e)[:200]}"))
    return b, ctx, page


def login(page, name, pw):
    page.goto(URL)
    page.get_by_placeholder("Benutzername eingeben").wait_for(timeout=60000)
    page.get_by_placeholder("Benutzername eingeben").fill(name)
    page.get_by_placeholder("Passwort eingeben").fill(pw)
    t0 = time.time()
    page.get_by_role("button", name="Anmelden").click()
    warte_ruhe(page)
    return time.time() - t0


def ansicht(page, name_teil):
    t0 = time.time()
    page.locator("button", has_text=name_teil).first.click()
    warte_ruhe(page, 180)
    return time.time() - t0


def shot(page, name, voll=True):
    pfad = os.path.join(SHOTS, f"{name}.png")
    page.screenshot(path=pfad, full_page=voll)
    return pfad


def text(page):
    return page.locator("[data-testid=stMain]").inner_text()
