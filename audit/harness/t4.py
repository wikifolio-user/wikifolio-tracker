import br
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "leser", "Leser-Pass-123")
    t = br.text(page); print("Menue leser:", [l for l in t.splitlines() if l.strip() and l[0] in "🏠⚙📝📈🔍🔎🕯🔮📊💼🏆💶🧮👥"])
    print("Depot-Daten sichtbar:", "DEPOTWERT" in t, "150,000" in t)
    # Permanentlink auf nicht erlaubte Ansicht
    page.goto(br.URL + "/?ansicht=abfindung"); br.warte_ruhe(page)
    t = br.text(page); print("nach ?ansicht=abfindung (neue Sitzung -> Login?):", "Anmelden" in page.content(), "Abfindung" in t[:300])
    br.login(page, "leser", "Leser-Pass-123")
    page.goto(br.URL + "/?ansicht=abfindung"); br.warte_ruhe(page)
    print("Titelzeile:", br.text(page)[:120].replace("\n"," | "))
    b.close()
