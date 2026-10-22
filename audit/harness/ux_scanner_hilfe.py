"""Investment-Scanner: Erklaerungen zu den Einstellungen lassen sich aufklappen (auch ohne Hover)."""
import sys, br
from playwright.sync_api import sync_playwright
from ux_builder_null import frisch
S = sys.argv[1]
with sync_playwright() as p:
    b, page = frisch(p)
    page.locator(".st-key-pb_zum_scanner button").first.click(); br.warte_ruhe(page, 60)
    page.get_by_text("Was bedeuten die Einstellungen?").first.click(); page.wait_for_timeout(800)
    t = br.text(page)
    print("Optimieren erklärt:", "30 %, 40 % … 100 %" in t)
    print("Fehler:", [z for z in t.splitlines() if "Fehler" in z or "Traceback" in z][:3])
    page.get_by_text("Auf Zielwahrscheinlichkeit optimieren – der Scanner").first.scroll_into_view_if_needed()
    page.screenshot(path=f"{S}/hilfe.png")
