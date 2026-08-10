import datetime
from bs4 import BeautifulSoup
import requests
import streamlit as st


@st.cache_data(ttl=300)  # Kurs für 5 Minuten cachen
def get_ls_wikifolio_price(isin="DE000LS9VFS2"):
  """Holt den Live-Kurs direkt von der Lang & Schwarz Kursseite für das Wikifolio."""
  try:
    # Direkte URL zur offiziellen Lang & Schwarz Seite des Wikifolios
    url = f"https://www.ls-tc.de/de/wikifolio/3865540"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=5)

    if response.status_code == 200:
      soup = BeautifulSoup(response.text, "html.parser")

      # Wir suchen nach dem Kurs-Container auf der Seite
      # Alternativ extrahieren wir den Text direkt über strukturierte Elemente
      price_element = soup.find(
          "span", class_="info-list-value"
      )  # Fallback-Suche
      # Sponsoren/Live-Kurs Direktfilter per Textsuche im HTML oder via CSS-Selektor
      # Bei L&S steht der Hauptkurs meist in einem prominenten Element
      text_content = soup.get_text()

      # Wir nutzen einen robusteren Weg über die bekannten Klassen von ls-tc.de:
      # Der aktuelle Kurs steht meist direkt hinter dem Namen oder im Chart-Bereich
      import re
      # Suche nach dem Kurswert im Format X.XXX,XXXX €
      match = re.search(
          r"(\d{3},\d{4})\s*€", text_content
      )   z.B. 300,7890 € oder ähnlich
      if match:
        price_str = match.group(1).replace(".", "").replace(",", ".")
        price = float(price_str)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return price, date_str

  except Exception:
    pass

  return None, None


# --- Ausführung & UI ---
isin_code = "DE000LS9VFS2"
current_price, price_date = get_ls_wikifolio_price(isin_code)

if current_price is not None:
  price_text = f"{current_price:,.3f} €"
  date_text = f"Live (L&S) vom: {price_date}"
else:
  # Fallback auf deinen festen Wert, falls die Abfrage blockiert wird
  current_price = 300.338
  price_text = f"{current_price:,.3f} €"
  date_text = "Stand (Offline-Modus / Zuletzt bekannt)"

st.markdown(
    f"""
    <div style="background: #09090B; border: 1px solid #27272A; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
        <div style="font-size: 1.25rem; font-weight: 700; color: #FFFFFF;">
            HAUPTINDIZES GLOBAL <span style="color: #00C853;">{price_text}</span>
        </div>
        <div style="font-size: 0.85rem; color: #71717A; margin-top: 4px;">
            WKN: LS9VFS • ISIN: {isin_code} • {date_text}
        </div>
    </div>
""",
    unsafe_allow_html=True,
)
