"""Mitgelieferte Lebensmittel und fehlertolerante Suche.

Werte je 100 g (bzw. 100 ml bei Getraenken) sind gerundete Richtwerte aus gaengigen Naehrwerttabellen - keine
Herstellerangaben. Wer es genauer braucht, nimmt ein Produkt aus der Online-Suche (Open Food Facts) oder legt ein
eigenes Lebensmittel an. Mikronaehrstoffe folgen in Etappe 2 (bis dahin: unbekannt, nicht 0).

Ein Lebensmittel ist ein dict:
  {"id", "name", "kategorie", "basis": "g"|"ml", "pro100": {naehrstoff: wert}, "einheiten": {name: g je Einheit},
   "quelle": "Richtwert"|"Open Food Facts"|"eigen", "marke": str}
"""
import difflib
import re
import unicodedata

# (id, Name, Kategorie, Basis, kcal, Protein, KH, Zucker, Fett, Ballaststoffe, Salz, Einheiten, Suchwoerter)
_DATEN = [
    # --- Obst
    ("banane", "Banane", "Obst", "g", 93, 1.2, 20, 17, 0.2, 2.0, 0, {"Stück": 120}, ""),
    ("apfel", "Apfel", "Obst", "g", 54, 0.3, 12, 10, 0.2, 2.0, 0, {"Stück": 150}, ""),
    ("birne", "Birne", "Obst", "g", 55, 0.5, 12, 10, 0.3, 3.0, 0, {"Stück": 160}, ""),
    ("orange", "Orange", "Obst", "g", 47, 1.0, 9, 9, 0.2, 2.0, 0, {"Stück": 180}, "apfelsine"),
    ("mandarine", "Mandarine", "Obst", "g", 50, 0.7, 10, 10, 0.3, 1.8, 0, {"Stück": 70}, "clementine"),
    ("erdbeeren", "Erdbeeren", "Obst", "g", 32, 0.7, 5.5, 5, 0.4, 2.0, 0, {"Schale": 250, "Handvoll": 80}, ""),
    ("heidelbeeren", "Heidelbeeren", "Obst", "g", 42, 0.6, 7.4, 7, 0.6, 4.9, 0, {"Handvoll": 60}, "blaubeeren"),
    ("himbeeren", "Himbeeren", "Obst", "g", 36, 1.3, 4.8, 4.5, 0.3, 6.7, 0, {"Handvoll": 60}, ""),
    ("weintrauben", "Weintrauben", "Obst", "g", 70, 0.7, 15.6, 15.6, 0.3, 1.5, 0, {"Handvoll": 80}, "trauben"),
    ("kiwi", "Kiwi", "Obst", "g", 51, 1.0, 9, 9, 0.6, 3.0, 0, {"Stück": 75}, ""),
    ("ananas", "Ananas", "Obst", "g", 55, 0.5, 12, 12, 0.2, 1.2, 0, {"Scheibe": 80}, ""),
    ("mango", "Mango", "Obst", "g", 62, 0.6, 13, 13, 0.4, 1.7, 0, {"Stück": 300}, ""),
    ("wassermelone", "Wassermelone", "Obst", "g", 30, 0.6, 7, 7, 0.2, 0.4, 0, {"Scheibe": 250}, "melone"),
    ("avocado", "Avocado", "Obst", "g", 160, 2.0, 1.8, 0.7, 14.7, 6.7, 0, {"Stück": 150, "halbe": 75}, ""),
    # --- Gemuese, Huelsenfruechte
    ("tomate", "Tomate", "Gemüse", "g", 18, 0.9, 2.6, 2.6, 0.2, 1.2, 0, {"Stück": 80}, "tomaten"),
    ("gurke", "Gurke", "Gemüse", "g", 12, 0.6, 1.8, 1.7, 0.2, 0.5, 0, {"Stück": 400}, "salatgurke"),
    ("paprika", "Paprika", "Gemüse", "g", 31, 1.0, 5, 5, 0.3, 2.1, 0, {"Stück": 150}, "paprikaschote"),
    ("karotte", "Karotte", "Gemüse", "g", 36, 0.9, 6.8, 6.5, 0.2, 3.0, 0.1, {"Stück": 80}, "möhre moehre mohrrübe"),
    ("brokkoli", "Brokkoli", "Gemüse", "g", 34, 3.3, 2.7, 1.7, 0.4, 3.0, 0, {"Portion": 150}, "broccoli"),
    ("blumenkohl", "Blumenkohl", "Gemüse", "g", 25, 2.0, 2.3, 2, 0.3, 2.9, 0, {"Portion": 150}, ""),
    ("spinat", "Spinat", "Gemüse", "g", 19, 2.5, 0.6, 0.4, 0.3, 2.6, 0.1, {"Portion": 150}, "blattspinat"),
    ("zucchini", "Zucchini", "Gemüse", "g", 19, 1.6, 2, 1.7, 0.4, 1.1, 0, {"Stück": 250}, ""),
    ("salat", "Blattsalat", "Gemüse", "g", 14, 1.2, 1.1, 1, 0.2, 1.4, 0, {"Portion": 80}, "kopfsalat eisbergsalat"),
    ("zwiebel", "Zwiebel", "Gemüse", "g", 33, 1.2, 5, 4.3, 0.2, 1.8, 0, {"Stück": 80}, ""),
    ("kartoffeln", "Kartoffeln, gekocht", "Gemüse", "g", 72, 2.0, 15, 0.8, 0.1, 2.0, 0, {"Stück": 80, "Portion": 250}, "kartoffel"),
    ("suesskartoffel", "Süßkartoffel", "Gemüse", "g", 86, 1.6, 20, 4.2, 0.1, 3.0, 0.1, {"Stück": 250}, "suesskartoffel"),
    ("champignons", "Champignons", "Gemüse", "g", 22, 3.1, 0.6, 0.2, 0.3, 2.0, 0, {"Portion": 100}, "pilze"),
    ("mais", "Mais (Dose)", "Gemüse", "g", 80, 2.9, 14, 4, 1.2, 2.8, 0.5, {"EL": 20, "Dose": 140}, ""),
    ("erbsen", "Erbsen (TK)", "Gemüse", "g", 81, 5.4, 11, 5.7, 0.4, 5.1, 0, {"Portion": 150}, ""),
    ("kidneybohnen", "Kidneybohnen (Dose)", "Hülsenfrüchte", "g", 90, 6.5, 12, 0.5, 0.5, 6.0, 0.6, {"Dose": 250}, "bohnen"),
    ("kichererbsen", "Kichererbsen (Dose)", "Hülsenfrüchte", "g", 120, 7.0, 15, 0.5, 2.5, 6.0, 0.5, {"Dose": 240}, ""),
    ("linsen", "Linsen, gekocht", "Hülsenfrüchte", "g", 116, 9.0, 17, 1.8, 0.4, 8.0, 0, {"Portion": 200}, ""),
    # --- Getreide, Brot
    ("haferflocken", "Haferflocken", "Getreide", "g", 370, 13.5, 58.7, 0.7, 7.0, 10.0, 0, {"EL": 10, "Portion": 50}, "hafer porridge"),
    ("vollkornbrot", "Vollkornbrot", "Brot", "g", 220, 7.0, 38, 3, 1.5, 7.5, 1.1, {"Scheibe": 50}, "brot"),
    ("mischbrot", "Mischbrot", "Brot", "g", 240, 7.0, 45, 2.5, 1.5, 5.0, 1.2, {"Scheibe": 50}, "brot graubrot"),
    ("toast", "Toastbrot", "Brot", "g", 260, 8.0, 47, 5, 3.5, 3.5, 1.2, {"Scheibe": 25}, "toast"),
    ("broetchen", "Brötchen (Weizen)", "Brot", "g", 270, 9.0, 53, 2, 1.5, 3.0, 1.3, {"Stück": 60}, "semmel schrippe broetchen"),
    ("vollkornbroetchen", "Vollkornbrötchen", "Brot", "g", 245, 9.0, 42, 2, 3.0, 6.5, 1.1, {"Stück": 70}, "broetchen semmel"),
    ("brezel", "Laugenbrezel", "Brot", "g", 270, 8.0, 55, 1, 1.5, 2.5, 2.5, {"Stück": 85}, "breze brezn"),
    ("croissant", "Croissant", "Brot", "g", 410, 8.0, 45, 8, 21, 2.5, 1.0, {"Stück": 60}, "hörnchen"),
    ("knaeckebrot", "Knäckebrot", "Brot", "g", 340, 10.0, 65, 2, 1.5, 13.0, 1.0, {"Scheibe": 10}, "knaeckebrot"),
    ("nudeln_gekocht", "Nudeln, gekocht", "Getreide", "g", 150, 5.3, 29, 0.7, 0.9, 1.8, 0, {"Portion": 250}, "pasta spaghetti"),
    ("nudeln_roh", "Nudeln, roh", "Getreide", "g", 355, 12.5, 71, 3, 1.5, 3.0, 0, {"Portion": 125}, "pasta spaghetti"),
    ("reis_gekocht", "Reis, gekocht", "Getreide", "g", 130, 2.7, 28, 0, 0.3, 0.4, 0, {"Portion": 200}, ""),
    ("reis_roh", "Reis, roh", "Getreide", "g", 350, 7.0, 78, 0, 0.6, 1.4, 0, {"Portion": 75}, ""),
    ("muesli", "Müsli (ohne Zuckerzusatz)", "Getreide", "g", 360, 10.0, 60, 15, 6.0, 8.0, 0.1, {"Portion": 50, "EL": 10}, "muesli"),
    ("cornflakes", "Cornflakes", "Getreide", "g", 375, 7.5, 83, 8, 0.9, 3.0, 1.1, {"Portion": 30}, ""),
    ("reiswaffel", "Reiswaffel", "Snacks", "g", 385, 8.0, 80, 0.5, 3.0, 4.0, 0.1, {"Stück": 8}, ""),
    # --- Milchprodukte, Eier
    ("milch_15", "Milch 1,5 %", "Milchprodukte", "ml", 47, 3.4, 4.9, 4.9, 1.5, 0, 0.1, {"Glas": 200, "Tasse": 150}, "fettarme milch"),
    ("milch_35", "Milch 3,5 %", "Milchprodukte", "ml", 64, 3.3, 4.8, 4.8, 3.6, 0, 0.1, {"Glas": 200, "Tasse": 150}, "vollmilch"),
    ("joghurt_35", "Naturjoghurt 3,5 %", "Milchprodukte", "g", 69, 3.8, 4.6, 4.6, 3.8, 0, 0.1, {"Becher": 150, "EL": 15}, "joghurt"),
    ("joghurt_15", "Naturjoghurt 1,5 %", "Milchprodukte", "g", 48, 3.9, 4.4, 4.4, 1.5, 0, 0.1, {"Becher": 150, "EL": 15}, "joghurt"),
    ("griech_joghurt", "Griechischer Joghurt 10 %", "Milchprodukte", "g", 120, 4.0, 4, 4, 10, 0, 0.1, {"Becher": 150, "EL": 15}, "joghurt"),
    ("skyr", "Skyr", "Milchprodukte", "g", 63, 11.0, 4, 4, 0.2, 0, 0.1, {"Becher": 150}, ""),
    ("magerquark", "Magerquark", "Milchprodukte", "g", 67, 12.0, 4, 4, 0.3, 0, 0.1, {"Packung": 250, "EL": 30}, "quark"),
    ("huettenkaese", "Hüttenkäse", "Milchprodukte", "g", 98, 12.5, 2.6, 2.6, 4.3, 0, 0.8, {"Becher": 200}, "körniger frischkäse huettenkaese"),
    ("gouda", "Gouda", "Käse", "g", 356, 25.0, 0, 0, 27, 0, 2.0, {"Scheibe": 20}, "käse kaese"),
    ("emmentaler", "Emmentaler", "Käse", "g", 380, 29.0, 0, 0, 29, 0, 0.5, {"Scheibe": 20}, "käse kaese"),
    ("mozzarella", "Mozzarella", "Käse", "g", 250, 18.0, 1, 1, 19, 0, 0.5, {"Kugel": 125}, "käse kaese"),
    ("feta", "Feta", "Käse", "g", 264, 14.2, 4, 4, 21, 0, 2.7, {"Portion": 50}, "schafskäse käse"),
    ("frischkaese", "Frischkäse natur", "Käse", "g", 250, 5.5, 3.5, 3, 24, 0, 0.8, {"EL": 15}, "frischkaese"),
    ("butter", "Butter", "Fette", "g", 741, 0.7, 0.6, 0.6, 83, 0, 0, {"TL": 5, "EL": 12}, ""),
    ("sahne", "Sahne 30 %", "Milchprodukte", "g", 290, 2.4, 3.2, 3.2, 30, 0, 0.1, {"EL": 15}, "schlagsahne"),
    ("ei", "Ei", "Eier", "g", 137, 12.9, 0.7, 0.7, 9.3, 0, 0.3, {"Stück": 58}, "eier hühnerei spiegelei rührei"),
    # --- Fleisch, Fisch, Alternativen
    ("haehnchen_roh", "Hähnchenbrust, roh", "Fleisch", "g", 105, 23.5, 0, 0, 1.2, 0, 0.15, {"Portion": 150}, "huhn hähnchen haehnchen chicken"),
    ("haehnchen_gebraten", "Hähnchenbrust, gebraten", "Fleisch", "g", 165, 31.0, 0, 0, 3.6, 0, 0.2, {"Portion": 120}, "huhn hähnchen haehnchen chicken"),
    ("pute", "Putenbrust", "Fleisch", "g", 105, 24.0, 0, 0, 1.0, 0, 0.15, {"Portion": 150}, "truthahn"),
    ("rinderhack", "Rinderhackfleisch", "Fleisch", "g", 254, 17.0, 0, 0, 20, 0, 0.2, {"Portion": 125}, "hack hackfleisch"),
    ("hack_gemischt", "Hackfleisch, gemischt", "Fleisch", "g", 260, 17.0, 0, 0, 21, 0, 0.2, {"Portion": 125}, "hack hackfleisch"),
    ("rindersteak", "Rindersteak", "Fleisch", "g", 120, 22.0, 0, 0, 3.5, 0, 0.15, {"Portion": 200}, "steak rind"),
    ("schweinefilet", "Schweinefilet", "Fleisch", "g", 106, 21.0, 0, 0, 2.5, 0, 0.15, {"Portion": 150}, "schwein"),
    ("kochschinken", "Kochschinken", "Wurst", "g", 118, 20.0, 1, 1, 4.0, 0, 2.5, {"Scheibe": 20}, "schinken"),
    ("salami", "Salami", "Wurst", "g", 390, 22.0, 0.5, 0.5, 33, 0, 4.5, {"Scheibe": 10}, "wurst"),
    ("wiener", "Wiener Würstchen", "Wurst", "g", 270, 13.0, 1, 0.5, 24, 0, 2.0, {"Stück": 50}, "würstchen wuerstchen wurst"),
    ("lachs", "Lachs", "Fisch", "g", 208, 20.0, 0, 0, 13, 0, 0.1, {"Portion": 125}, "fisch"),
    ("thunfisch", "Thunfisch (Dose, Saft)", "Fisch", "g", 110, 25.0, 0, 0, 1.0, 0, 1.0, {"Dose": 150}, "fisch"),
    ("garnelen", "Garnelen", "Fisch", "g", 85, 19.0, 0, 0, 1.0, 0, 0.6, {"Portion": 100}, "shrimps krabben"),
    ("tofu", "Tofu natur", "Alternativen", "g", 120, 13.0, 1.5, 0.5, 7.0, 1.5, 0, {"Packung": 200, "Portion": 100}, ""),
    # --- Fette, Nuesse, Samen
    ("olivenoel", "Olivenöl", "Fette", "g", 884, 0, 0, 0, 100, 0, 0, {"EL": 10, "TL": 4}, "öl oel"),
    ("rapsoel", "Rapsöl", "Fette", "g", 884, 0, 0, 0, 100, 0, 0, {"EL": 10, "TL": 4}, "öl oel"),
    ("erdnussbutter", "Erdnussbutter", "Fette", "g", 600, 25.0, 13, 6, 49, 6.0, 0.4, {"EL": 16, "TL": 7}, "erdnussmus"),
    ("mandeln", "Mandeln", "Nüsse", "g", 595, 21.0, 9.1, 4.4, 50, 12.5, 0, {"Handvoll": 30}, "nüsse nuesse"),
    ("walnuesse", "Walnüsse", "Nüsse", "g", 680, 15.0, 7, 2.6, 65, 6.7, 0, {"Handvoll": 30}, "nüsse nuesse walnuss"),
    ("cashews", "Cashewkerne", "Nüsse", "g", 580, 18.0, 27, 6, 44, 3.0, 0, {"Handvoll": 30}, "nüsse nuesse cashew"),
    ("erdnuesse", "Erdnüsse, geröstet", "Nüsse", "g", 600, 25.0, 12, 4, 49, 8.0, 0.8, {"Handvoll": 30}, "nüsse nuesse"),
    ("chiasamen", "Chiasamen", "Samen", "g", 450, 17.0, 8, 0.5, 31, 34.0, 0, {"EL": 12}, "chia"),
    ("leinsamen", "Leinsamen", "Samen", "g", 510, 18.0, 1.6, 1.5, 42, 27.0, 0, {"EL": 10}, "lein"),
    # --- Suesses, Snacks, Aufstriche, Saucen
    ("zucker", "Zucker", "Süßes", "g", 400, 0, 100, 100, 0, 0, 0, {"TL": 4, "EL": 12}, ""),
    ("honig", "Honig", "Süßes", "g", 305, 0.4, 76, 75, 0, 0, 0, {"TL": 8}, ""),
    ("marmelade", "Konfitüre", "Süßes", "g", 250, 0.4, 60, 58, 0.1, 1.0, 0, {"TL": 10, "EL": 20}, "marmelade"),
    ("nussnugat", "Nuss-Nougat-Creme", "Süßes", "g", 540, 6.0, 57, 56, 31, 3.0, 0.1, {"TL": 10, "EL": 15}, "nutella"),
    ("vollmilchschoko", "Vollmilchschokolade", "Süßes", "g", 535, 7.0, 57, 55, 30, 2.0, 0.2, {"Riegel": 6, "Tafel": 100}, "schokolade"),
    ("zartbitter", "Zartbitterschokolade 70 %", "Süßes", "g", 570, 8.0, 33, 28, 42, 11.0, 0, {"Riegel": 6, "Tafel": 100}, "schokolade"),
    ("gummibaerchen", "Fruchtgummi", "Süßes", "g", 343, 7.0, 77, 46, 0.1, 0, 0.1, {"Handvoll": 25}, "gummibärchen gummibaerchen"),
    ("chips", "Kartoffelchips", "Snacks", "g", 535, 6.0, 50, 1, 34, 4.5, 1.5, {"Handvoll": 25, "Tüte": 175}, "chips"),
    ("butterkeks", "Butterkeks", "Süßes", "g", 440, 8.0, 72, 22, 12, 2.5, 0.7, {"Stück": 5}, "keks kekse"),
    ("ruehrkuchen", "Rührkuchen", "Süßes", "g", 390, 5.0, 50, 30, 19, 1.0, 0.4, {"Stück": 80}, "kuchen"),
    ("eis", "Speiseeis (Vanille)", "Süßes", "g", 200, 3.5, 24, 21, 10, 0, 0.1, {"Kugel": 55}, "eiscreme"),
    ("proteinriegel", "Proteinriegel", "Snacks", "g", 380, 30.0, 32, 4, 13, 10.0, 0.4, {"Stück": 45}, "eiweißriegel"),
    ("muesliriegel", "Müsliriegel", "Snacks", "g", 400, 6.0, 64, 28, 13, 4.0, 0.2, {"Stück": 25}, "muesliriegel"),
    ("hummus", "Hummus", "Aufstriche", "g", 250, 7.0, 12, 1, 19, 5.0, 1.0, {"EL": 15}, ""),
    ("ketchup", "Ketchup", "Saucen", "g", 110, 1.2, 25, 22, 0.2, 0.8, 1.8, {"EL": 15}, ""),
    ("mayonnaise", "Mayonnaise", "Saucen", "g", 680, 1.0, 2, 1, 75, 0, 1.2, {"EL": 15}, "mayo"),
    # --- Getraenke (je 100 ml)
    ("wasser", "Wasser", "Getränke", "ml", 0, 0, 0, 0, 0, 0, 0, {"Glas": 250, "Flasche": 500}, "mineralwasser"),
    ("kaffee", "Kaffee, schwarz", "Getränke", "ml", 2, 0.1, 0, 0, 0, 0, 0, {"Tasse": 150}, "espresso"),
    ("cappuccino", "Cappuccino", "Getränke", "ml", 33, 1.7, 2.5, 2.5, 1.8, 0, 0.05, {"Tasse": 200}, "kaffee latte"),
    ("tee", "Tee, ungesüßt", "Getränke", "ml", 1, 0, 0, 0, 0, 0, 0, {"Tasse": 200}, ""),
    ("orangensaft", "Orangensaft", "Getränke", "ml", 45, 0.7, 9, 9, 0.2, 0.2, 0, {"Glas": 200}, "saft"),
    ("apfelsaft", "Apfelsaft", "Getränke", "ml", 46, 0.1, 11, 10, 0.1, 0, 0, {"Glas": 200}, "saft"),
    ("apfelschorle", "Apfelschorle", "Getränke", "ml", 24, 0, 5.5, 5, 0, 0, 0, {"Glas": 300, "Flasche": 500}, "schorle"),
    ("cola", "Cola", "Getränke", "ml", 42, 0, 10.6, 10.6, 0, 0, 0, {"Glas": 250, "Dose": 330}, "softdrink limo"),
    ("cola_zero", "Cola Zero", "Getränke", "ml", 0.3, 0, 0, 0, 0, 0, 0.02, {"Glas": 250, "Dose": 330}, "light softdrink"),
    ("bier", "Bier (Pils)", "Getränke", "ml", 42, 0.5, 3, 0, 0, 0, 0, {"Flasche": 500, "Glas": 300}, "pils"),
    ("rotwein", "Wein", "Getränke", "ml", 85, 0.1, 2.6, 0.6, 0, 0, 0, {"Glas": 200}, "rotwein weißwein"),
    ("hafermilch", "Haferdrink", "Getränke", "ml", 46, 1.0, 6.6, 4, 1.5, 0.8, 0.1, {"Glas": 200}, "hafermilch"),
    ("sojadrink", "Sojadrink", "Getränke", "ml", 39, 3.3, 2.5, 2.5, 1.8, 0.5, 0.1, {"Glas": 200}, "sojamilch"),
    ("proteinpulver", "Proteinpulver (Whey)", "Snacks", "g", 380, 78.0, 6, 4, 6, 0, 0.5, {"Portion": 30}, "eiweißpulver whey shake"),
    # --- Gerichte
    ("pizza", "Pizza Margherita", "Gerichte", "g", 250, 11.0, 30, 3, 9, 2.0, 1.2, {"Stück": 350, "Stück (Achtel)": 45}, ""),
    ("doener", "Döner Kebab", "Gerichte", "g", 230, 13.0, 20, 2, 11, 2.0, 1.2, {"Stück": 350}, "döner doener kebab"),
    ("pommes", "Pommes frites", "Gerichte", "g", 300, 3.5, 36, 0.5, 15, 3.5, 0.6, {"Portion": 150}, "fritten"),
    ("burger", "Hamburger", "Gerichte", "g", 250, 13.0, 25, 5, 11, 1.5, 1.2, {"Stück": 220}, "burger"),
    ("lasagne", "Lasagne", "Gerichte", "g", 140, 7.5, 12, 2, 7, 1.0, 0.6, {"Portion": 350}, ""),
    ("bolognese", "Spaghetti Bolognese", "Gerichte", "g", 130, 6.0, 16, 2, 4.5, 1.5, 0.5, {"Portion": 400}, "nudeln"),
    ("currywurst", "Currywurst mit Sauce", "Gerichte", "g", 250, 10.0, 9, 7, 19, 0.5, 2.0, {"Portion": 200}, "wurst"),
    ("gemuesesuppe", "Gemüsesuppe", "Gerichte", "g", 35, 1.3, 4, 2, 1.2, 1.5, 0.7, {"Teller": 300}, "suppe"),
    ("kartoffelsalat", "Kartoffelsalat (mit Mayo)", "Gerichte", "g", 145, 2.0, 13, 2, 9, 1.5, 0.9, {"Portion": 200}, ""),
]

SCHLUESSEL = ("kcal", "protein", "kh", "zucker", "fett", "ballast", "salz")


def _lm(z):
    lid, name, kat, basis, *werte, einheiten, such = z
    return {"id": lid, "name": name, "kategorie": kat, "basis": basis, "pro100": dict(zip(SCHLUESSEL, werte)),
            "einheiten": dict(einheiten), "quelle": "Richtwert", "marke": "", "such": such}


MITGELIEFERT = [_lm(z) for z in _DATEN]
NACH_ID = {lm["id"]: lm for lm in MITGELIEFERT}


def einheiten(lm):
    """Waehlbare Einheiten eines Lebensmittels: zuerst die eigenen (Stück, Scheibe …), dann g bzw. ml."""
    return list((lm.get("einheiten") or {}).keys()) + [lm.get("basis") or "g"]


def standard_menge(lm):
    """Sinnvoller Startwert ohne Vorgeschichte: 1 Stück/Portion, sonst 100 g/ml."""
    e = lm.get("einheiten") or {}
    return (1.0, next(iter(e))) if e else (100.0, lm.get("basis") or "g")


def _norm(text):
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("ß", "ss")
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def suchen(begriff, alle, nutzung=None, favoriten=(), limit=12):
    """Fehlertolerante Suche. Ranking: Favoriten, dann haeufig/zuletzt genutzt, dann Treffergenauigkeit.
    Ohne Suchbegriff: Favoriten und zuletzt genutzte. alle: Liste von Lebensmitteln; nutzung: {id: {"n", "zuletzt"}}."""
    nutzung = nutzung or {}
    fav = set(favoriten or ())
    q = _norm(begriff)

    def bonus(lm):
        u = nutzung.get(lm["id"]) or {}
        return (lm["id"] in fav) * 3 + min(int(u.get("n") or 0), 20) / 10

    if not q:
        kandidaten = [lm for lm in alle if lm["id"] in fav or lm["id"] in nutzung]
        kandidaten.sort(key=lambda lm: (-(lm["id"] in fav), -int((nutzung.get(lm["id"]) or {}).get("n") or 0),
                                        str((nutzung.get(lm["id"]) or {}).get("zuletzt") or "")), reverse=False)
        return kandidaten[:limit]
    treffer = []
    for lm in alle:
        name = _norm(lm["name"])
        woerter = (name + " " + _norm(lm.get("such", "")) + " " + _norm(lm.get("marke", ""))).split()
        if name.startswith(q):
            g = 3.0
        elif any(w.startswith(q) for w in woerter):
            g = 2.5
        elif q in name:
            g = 2.0
        else:
            g = max((difflib.SequenceMatcher(None, q, w[:len(q) + 2]).ratio() for w in woerter), default=0)
            if g < 0.75:             # Tippfehler-Toleranz: "bananne" -> Banane, aber kein Raten
                continue
        treffer.append((g + bonus(lm), lm))
    treffer.sort(key=lambda t: (-t[0], t[1]["name"]))
    return [lm for _, lm in treffer[:limit]]
