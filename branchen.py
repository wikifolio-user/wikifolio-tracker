"""Firmen-Kategorien: Yahoo-Branche (englisch, vom Qualitaets-Agenten auf 28 Zeichen gekuerzt) ->
deutscher Sektor (11 Sektoren wie bei Yahoo/GICS) und deutsche Branchenbezeichnung."""

SEKTOREN = ["Technologie", "Gesundheit", "Finanzen", "Industrie", "Zyklischer Konsum", "Basiskonsum", "Energie",
            "Rohstoffe", "Immobilien", "Versorger", "Kommunikation"]
SEKTOR_ICON = {"Technologie": "💻", "Gesundheit": "🩺", "Finanzen": "🏦", "Industrie": "🏭",
               "Zyklischer Konsum": "🛍️", "Basiskonsum": "🛒", "Energie": "🛢️", "Rohstoffe": "⛏️",
               "Immobilien": "🏢", "Versorger": "⚡", "Kommunikation": "📡", "Sonstige": "🧩"}

# (Anfang der Yahoo-Branche, Sektor, deutsche Branche) - Anfang reicht, die Namen sind gekuerzt
_TABELLE = [
    # Technologie
    ("Software—Application", "Technologie", "Anwendungssoftware"),
    ("Software—Infrastructure", "Technologie", "Infrastruktursoftware"),
    ("Semiconductor Equipment", "Technologie", "Halbleiterausrüstung"),
    ("Semiconductors", "Technologie", "Halbleiter"),
    ("Information Technology Serv", "Technologie", "IT-Dienstleistungen"),
    ("Electronic Components", "Technologie", "Elektronische Bauteile"),
    ("Communication Equipment", "Technologie", "Kommunikationstechnik"),
    ("Computer Hardware", "Technologie", "Computer-Hardware"),
    ("Consumer Electronics", "Technologie", "Unterhaltungselektronik"),
    ("Scientific & Technical Instr", "Technologie", "Mess- und Prüftechnik"),
    ("Electronics & Computer Distr", "Technologie", "Elektronik-Großhandel"),
    ("Solar", "Technologie", "Solartechnik"),
    # Gesundheit
    ("Biotechnology", "Gesundheit", "Biotechnologie"),
    ("Drug Manufacturers—General", "Gesundheit", "Pharma (breit)"),
    ("Drug Manufacturers—Specialty", "Gesundheit", "Pharma (Spezial/Generika)"),
    ("Medical Devices", "Gesundheit", "Medizintechnik"),
    ("Medical Instruments", "Gesundheit", "Medizinische Instrumente"),
    ("Medical Care Facilities", "Gesundheit", "Kliniken und Pflege"),
    ("Medical Distribution", "Gesundheit", "Medizin-Großhandel"),
    ("Diagnostics & Research", "Gesundheit", "Diagnostik und Forschung"),
    ("Health Information Serv", "Gesundheit", "Gesundheits-IT"),
    ("Healthcare Plans", "Gesundheit", "Krankenversicherer"),
    ("Pharmaceutical Retailers", "Gesundheit", "Apotheken"),
    # Finanzen
    ("Banks", "Finanzen", "Banken"),
    ("Asset Management", "Finanzen", "Vermögensverwaltung"),
    ("Capital Markets", "Finanzen", "Kapitalmarkt/Broker"),
    ("Credit Services", "Finanzen", "Kreditdienstleister"),
    ("Financial Data & Stock Exch", "Finanzen", "Börsen und Finanzdaten"),
    ("Financial Conglomerates", "Finanzen", "Finanzkonglomerate"),
    ("Insurance Brokers", "Finanzen", "Versicherungsmakler"),
    ("Insurance", "Finanzen", "Versicherungen"),
    ("Mortgage Finance", "Finanzen", "Immobilienfinanzierung"),
    ("Shell Companies", "Finanzen", "Mantelgesellschaften"),
    # Industrie
    ("Specialty Industrial Machin", "Industrie", "Maschinenbau"),
    ("Engineering & Construction", "Industrie", "Bau und Ingenieurwesen"),
    ("Electrical Equipment", "Industrie", "Elektrotechnik"),
    ("Aerospace & Defense", "Industrie", "Luftfahrt und Rüstung"),
    ("Conglomerates", "Industrie", "Mischkonzerne"),
    ("Building Products", "Industrie", "Bauprodukte und Ausrüstung"),
    ("Integrated Freight", "Industrie", "Logistik"),
    ("Farm & Heavy Construction", "Industrie", "Land- und Baumaschinen"),
    ("Specialty Business Serv", "Industrie", "Unternehmensdienstleistungen"),
    ("Marine Shipping", "Industrie", "Schifffahrt"),
    ("Metal Fabrication", "Industrie", "Metallverarbeitung"),
    ("Tools & Accessories", "Industrie", "Werkzeuge"),
    ("Railroads", "Industrie", "Eisenbahn"),
    ("Industrial Distribution", "Industrie", "Industriehandel"),
    ("Rental & Leasing", "Industrie", "Vermietung und Leasing"),
    ("Waste Management", "Industrie", "Entsorgung"),
    ("Airlines", "Industrie", "Fluggesellschaften"),
    ("Airports & Air Services", "Industrie", "Flughäfen"),
    ("Staffing & Employment", "Industrie", "Personaldienstleister"),
    ("Consulting Services", "Industrie", "Beratung"),
    ("Infrastructure Operations", "Industrie", "Infrastrukturbetrieb"),
    ("Security & Protection", "Industrie", "Sicherheitsdienste"),
    ("Pollution & Treatment", "Industrie", "Umwelttechnik"),
    ("Business Equipment", "Industrie", "Büroausstattung"),
    ("Trucking", "Industrie", "Spedition (Lkw)"),
    # Zyklischer Konsum
    ("Auto Parts", "Zyklischer Konsum", "Autozulieferer"),
    ("Auto Manufacturers", "Zyklischer Konsum", "Autohersteller"),
    ("Auto & Truck Dealerships", "Zyklischer Konsum", "Autohandel"),
    ("Specialty Retail", "Zyklischer Konsum", "Fachhandel"),
    ("Internet Retail", "Zyklischer Konsum", "Onlinehandel"),
    ("Restaurants", "Zyklischer Konsum", "Restaurants"),
    ("Furnishings", "Zyklischer Konsum", "Möbel und Haushaltsgeräte"),
    ("Leisure", "Zyklischer Konsum", "Freizeit"),
    ("Apparel Manufacturing", "Zyklischer Konsum", "Bekleidungshersteller"),
    ("Apparel Retail", "Zyklischer Konsum", "Bekleidungshandel"),
    ("Luxury Goods", "Zyklischer Konsum", "Luxusgüter"),
    ("Department Stores", "Zyklischer Konsum", "Kaufhäuser"),
    ("Lodging", "Zyklischer Konsum", "Hotels"),
    ("Textile Manufacturing", "Zyklischer Konsum", "Textilherstellung"),
    ("Footwear", "Zyklischer Konsum", "Schuhe und Accessoires"),
    ("Residential Construction", "Zyklischer Konsum", "Wohnungsbau"),
    ("Resorts & Casinos", "Zyklischer Konsum", "Resorts und Casinos"),
    ("Travel Services", "Zyklischer Konsum", "Reisedienstleister"),
    ("Gambling", "Zyklischer Konsum", "Glücksspiel"),
    ("Recreational Vehicles", "Zyklischer Konsum", "Freizeitfahrzeuge"),
    ("Home Improvement Retail", "Zyklischer Konsum", "Baumärkte"),
    ("Personal Services", "Zyklischer Konsum", "Persönliche Dienstleistungen"),
    ("Packaging & Containers", "Zyklischer Konsum", "Verpackungen"),
    # Basiskonsum
    ("Packaged Foods", "Basiskonsum", "Nahrungsmittel"),
    ("Farm Products", "Basiskonsum", "Agrarprodukte"),
    ("Household & Personal Prod", "Basiskonsum", "Haushalts- und Körperpflege"),
    ("Grocery Stores", "Basiskonsum", "Lebensmittelhandel"),
    ("Beverages—Wineries", "Basiskonsum", "Wein und Spirituosen"),
    ("Beverages—Brewers", "Basiskonsum", "Brauereien"),
    ("Beverages—Non", "Basiskonsum", "Alkoholfreie Getränke"),
    ("Education & Training", "Basiskonsum", "Bildung"),
    ("Food Distribution", "Basiskonsum", "Lebensmittel-Großhandel"),
    ("Confectioners", "Basiskonsum", "Süßwaren"),
    ("Discount Stores", "Basiskonsum", "Discounter"),
    ("Tobacco", "Basiskonsum", "Tabak"),
    # Energie
    ("Oil & Gas E&P", "Energie", "Öl und Gas (Förderung)"),
    ("Oil & Gas Equipment", "Energie", "Öl- und Gasausrüstung"),
    ("Oil & Gas Refining", "Energie", "Raffinerien"),
    ("Oil & Gas Midstream", "Energie", "Pipelines und Speicher"),
    ("Oil & Gas Integrated", "Energie", "Integrierte Ölkonzerne"),
    ("Oil & Gas Drilling", "Energie", "Bohrdienste"),
    ("Thermal Coal", "Energie", "Kraftwerkskohle"),
    ("Uranium", "Energie", "Uran"),
    # Rohstoffe
    ("Specialty Chemicals", "Rohstoffe", "Spezialchemie"),
    ("Chemicals", "Rohstoffe", "Chemie"),
    ("Steel", "Rohstoffe", "Stahl"),
    ("Other Industrial Metals", "Rohstoffe", "Industriemetalle und Bergbau"),
    ("Building Materials", "Rohstoffe", "Baustoffe"),
    ("Gold", "Rohstoffe", "Gold"),
    ("Agricultural Inputs", "Rohstoffe", "Dünger und Agrarchemie"),
    ("Paper & Paper Products", "Rohstoffe", "Papier"),
    ("Aluminum", "Rohstoffe", "Aluminium"),
    ("Copper", "Rohstoffe", "Kupfer"),
    ("Other Precious Metals", "Rohstoffe", "Edelmetalle"),
    ("Lumber & Wood", "Rohstoffe", "Holz"),
    ("Coking Coal", "Rohstoffe", "Kokskohle"),
    ("Silver", "Rohstoffe", "Silber"),
    # Immobilien
    ("Real Estate Services", "Immobilien", "Immobiliendienstleister"),
    ("Real Estate—Development", "Immobilien", "Projektentwicklung"),
    ("Real Estate—Diversified", "Immobilien", "Immobilien (diversifiziert)"),
    ("REIT—Diversified", "Immobilien", "REIT diversifiziert"),
    ("REIT—Retail", "Immobilien", "REIT Handelsimmobilien"),
    ("REIT—Industrial", "Immobilien", "REIT Logistik/Gewerbe"),
    ("REIT—Office", "Immobilien", "REIT Büro"),
    ("REIT—Residential", "Immobilien", "REIT Wohnen"),
    ("REIT—Healthcare", "Immobilien", "REIT Gesundheit"),
    ("REIT—Specialty", "Immobilien", "REIT Spezial"),
    ("REIT—Hotel", "Immobilien", "REIT Hotel"),
    ("REIT—Mortgage", "Immobilien", "REIT Hypotheken"),
    # Versorger
    ("Utilities—Renewable", "Versorger", "Erneuerbare Energien"),
    ("Utilities—Regulated Electric", "Versorger", "Stromversorger"),
    ("Utilities—Regulated Gas", "Versorger", "Gasversorger"),
    ("Utilities—Regulated Water", "Versorger", "Wasserversorger"),
    ("Utilities—Independent Power", "Versorger", "Unabhängige Stromerzeuger"),
    ("Utilities—Diversified", "Versorger", "Versorger (diversifiziert)"),
    # Kommunikation
    ("Telecom Services", "Kommunikation", "Telekommunikation"),
    ("Internet Content", "Kommunikation", "Internet und Plattformen"),
    ("Entertainment", "Kommunikation", "Unterhaltung"),
    ("Electronic Gaming", "Kommunikation", "Videospiele"),
    ("Advertising Agencies", "Kommunikation", "Werbung"),
    ("Publishing", "Kommunikation", "Verlage"),
    ("Broadcasting", "Kommunikation", "Rundfunk"),
]
# laengster Anfang zuerst (z. B. "Insurance Brokers" vor "Insurance", "Semiconductor Equipment" vor "Semiconductors")
_TABELLE.sort(key=lambda t: -len(t[0]))


def _norm(s):
    return str(s or "").strip().replace("-", "—").lower()


def einordnen(yahoo_branche):
    """-> (Sektor, deutsche Branche). Unbekannt/leer -> ("Sonstige", Originaltext oder "unbekannt")."""
    n = _norm(yahoo_branche)
    if not n:
        return "Sonstige", "unbekannt"
    for anfang, sektor, de in _TABELLE:
        a = _norm(anfang)
        if n.startswith(a) or (len(n) >= 20 and a.startswith(n)):
            return sektor, de
    return "Sonstige", str(yahoo_branche).strip()


def sektor(yahoo_branche):
    return einordnen(yahoo_branche)[0]


def branche_de(yahoo_branche):
    return einordnen(yahoo_branche)[1]


def kategorie_text(yahoo_branche):
    """Kurzer Anzeigetext 'Sektor · Branche'."""
    s, b = einordnen(yahoo_branche)
    return s if b in ("unbekannt", s) else f"{s} · {b}"
