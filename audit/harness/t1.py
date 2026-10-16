import time, br
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    t0=time.time(); page.goto(br.URL); page.get_by_placeholder("Benutzername eingeben").wait_for(timeout=60000)
    print("Login-Maske nach %.1fs" % (time.time()-t0)); br.shot(page,"01_login")
    # falsches Passwort
    page.get_by_placeholder("Benutzername eingeben").fill("admin"); page.get_by_placeholder("Passwort eingeben").fill("falsch")
    t0=time.time(); page.get_by_role("button", name="Anmelden").click(); br.warte_ruhe(page)
    print("Fehllogin-Antwort %.1fs:" % (time.time()-t0), [t for t in br.text(page).splitlines() if "falsch" in t or "Fehlver" in t][:2])
    dt = br.login(page, "admin", "Admin-Test-Passwort-1")
    print("Login+Startseite %.1fs" % dt); br.shot(page,"02_start")
    print(br.text(page)[:1500])
    dt = br.ansicht(page, "Depot"); print("Depot-Ansicht %.1fs" % dt)
    br.shot(page,"03_depot")
    print("=====DEPOT=====\n"+br.text(page)[:5000])
    print("KONSOLE:", [k for k in page.konsole if 'error' in k.lower()][:10])
    b.close()
