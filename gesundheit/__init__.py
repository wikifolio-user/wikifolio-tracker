"""Gesundheitsmodul (nur fuer den Admin): Rechenkern ohne Streamlit, Oberflaeche in gesundheit_ui.py.

  naehrstoffe.py   zentrale Naehrstoff-Tabelle (id, Anzeigename, Kategorie, Basiseinheit) + Einheiten-Umrechnung
  rechnen.py       Berechnungs-Engine: Grundumsatz, Tagesbedarf, Ziele, Mengen-Umrechnung, Tagessummen, Bilanz
  lebensmittel.py  mitgelieferte Lebensmittel (Richtwerte je 100 g/ml) + fehlertolerante Suche
  speicher.py      Datenmodell der gespeicherten Dateien (Profil, Monate mit Tagen) - reine Funktionen
  quellen.py       externe Lebensmittel-Datenbanken (Provider-Schnittstelle; Open Food Facts)
"""
