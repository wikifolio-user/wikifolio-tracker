import json, time
import br
br.URL = "http://127.0.0.1:8602"
from playwright.sync_api import sync_playwright
json.dump({"lstc": "down"}, open("fault.json", "w"))
time.sleep(130)
with sync_playwright() as p:
    b, ctx, page = br.start(p, 390, 844, True)
    br.login(page, "maria", "Maria-Test-Pass-1")
    page.locator(".st-key-nav_menue button", has_text="Depot").first.click(); br.warte_ruhe(page)
    t = br.text(page)
    print(t[:900].replace("\n", " | "))
    print("Absturz:", page.locator("[data-testid=stException]").count())
    page.screenshot(path="fault_k.png", full_page=True)
    b.close()
json.dump({}, open("fault.json", "w"))
