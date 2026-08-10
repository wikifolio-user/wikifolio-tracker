import datetime
import json
import os
from bs4 import BeautifulSoup
import requests

DB_FILE = "trades_db.json"
WIKIFOLIO_URL = (
    "https://www.wikifolio.com/de/de/w/wfindizglo"  # Deine Wikifolio-URL
)


def fetch_trades_with_session():
  # Session-Klasse nutzen, um Anfragen gebündelt zu senden
  session = requests.Session()

  # Cookie aus den GitHub Secrets auslesen
  cookie_val = os.getenv("WIKIFOLIO_COOKIE")
  if not cookie_val:
    print("Kein Cookie gefunden!")
    return []

  # Cookie in die Session injizieren
  session.cookies.set("wikifolio_session", cookie_val, domain=".wikifolio.com")

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }

  try:
    response = session.get(WIKIFOLIO_URL, headers=headers, timeout=10)
    if response.status_code != 200:
      print(f"Fehler beim Abrufen: Statuscode {response.status_code}")
      return []

    soup = BeautifulSoup(response.text, "html.parser")
    new_events = []

    # BEISPIEL-SELEKTOREN (Müssen an die echten Klassen von Wikifolio angepasst werden)
    for item in soup.select(".wikifolio-activity-item"):
      titel = item.find("h4").get_text(strip=True)
      datum = item.find(".date-class").get_text(strip=True)
      inhalt = item.find("p").get_text(strip=True)

      new_events.append({
          "typ": "Wikifolio-Auto",
          "datum": datum,
          "titel": titel,
          "inhalt": inhalt,
      })

    return new_events
  except Exception as e:
    print(f"Exception aufgetreten: {e}")
    return []


def update_database():
  if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f:
      db_events = json.load(f)
  else:
    db_events = []

  fetched_events = fetch_trades_with_session()

  existing_keys = {
      (e["datum"], e["titel"]) for e in db_events if e.get("typ") == "Wikifolio-Auto"
  }

  added_count = 0
  for ev in fetched_events:
    key = (ev["datum"], ev["titel"])
    if key not in existing_keys:
      db_events.insert(0, ev)
      added_count += 1

  if added_count > 0:
    with open(DB_FILE, "w", encoding="utf-8") as f:
      json.dump(db_events, f, ensure_ascii=False, indent=4)
    print(f"{added_count} neue Events erfolgreich gespeichert.")
  else:
    print("Keine neuen Events gefunden.")


if __name__ == "__main__":
  update_database()
