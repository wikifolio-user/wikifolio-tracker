import br, json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p)
    br.login(page, "admin", "Admin-Test-Passwort-1")
    page.wait_for_timeout(3000)
    print("Start: Abmelde-Knöpfe:", page.locator(".st-key-logout_ecke button").count(),
          "| Container:", page.locator(".st-key-logout_ecke").count())
    br.ansicht(page, "Depot"); page.get_by_role("button", name="☰ Menü").click(); br.warte_ruhe(page); page.wait_for_timeout(3000)
    print("Nach Ansicht+Menü:", page.locator(".st-key-logout_ecke button").count(), "| sichtbar:", page.locator(".st-key-logout_ecke button:visible").count())
    html = page.evaluate("() => [...document.querySelectorAll('.st-key-logout_ecke')].map(e => (e.closest('[data-stale]')?'stale':'') + '|' + e.parentElement.className.slice(0,40))")
    print(html)
    # Chronik bei Kursausfall
    json.dump({"lstc": "down"}, open("fault.json", "w"))
    br.ansicht(page, "Chronik"); t = br.text(page)
    print("Chronik bei Kursausfall erreichbar:", "Eigene Notiz hinzufügen" in t, "| Fehlermeldung Kurs:", "kein echter Kurs" in t)
    json.dump({}, open("fault.json", "w"))
    b.close()
