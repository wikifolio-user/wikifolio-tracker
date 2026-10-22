import br
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b, ctx, page = br.start(p, 820, 1180, True)
    br.login(page, "admin", "Admin-Test-Passwort-1"); page.wait_for_timeout(800)
    page.locator(".st-key-nav_menue button", has_text="Chronik").first.click(); br.warte_ruhe(page)
    btn = page.get_by_role("button", name="☰ Menü")
    bb = btn.bounding_box(); print("Menü-Knopf:", bb)
    x, y = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
    print("Element an der Stelle:", page.evaluate(f"""() => {{ const e = document.elementFromPoint({x}, {y});
        return e ? [e.tagName, String(e.className).slice(0,60), e.getAttribute('data-testid'), (e.innerText||'').slice(0,40)] : null; }}"""))
    try:
        btn.click(timeout=5000); print("Klick ok")
    except Exception as e:
        print(str(e).split("\n")[-6:])
    b.close()
