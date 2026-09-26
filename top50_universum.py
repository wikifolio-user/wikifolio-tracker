"""
Grundgesamtheit fuer die "Watchlist Top 50".

Aus jeder Liste bildet der taegliche Agent (top50_agent.py) je Zeitraum eine
Rangliste der 50 besten Werte. Jeder Eintrag ist (ISIN, Name):

- Zuerst wird ueber die ISIN gesucht (eindeutig, genau ein Treffer).
- Ist die ISIN ungueltig oder wird nicht gefunden, sucht der Agent ueber den
  NAMEN und nimmt den ersten Treffer der passenden Kategorie ("Aktie"/"ETF").
  Ein Tippfehler in einer ISIN fuehrt also nicht zum Ausfall des Werts.
- Werte, die auf beiden Wegen nicht auffindbar sind, erscheinen in der App
  unter "Nicht gefunden" - dann hier ISIN oder Namen korrigieren.

wikifolios stehen hier NICHT: die werden automatisch ueber die Kursquelle
gesucht (alle Zertifikate mit WKN "LS9..."), siehe top50_agent.py.

Ergaenzen/Entfernen: einfach Zeilen hinzufuegen oder loeschen. Doppelte
Eintraege (z.B. eine Aktie in DAX und Euro Stoxx 50) sind unschaedlich - der
Agent entfernt Duplikate automatisch.
"""

# ---------------------------------------------------------------------------
# AKTIEN: DAX, MDAX-Auswahl, Euro Stoxx 50, Nasdaq-100, S&P-500-Schwergewichte
# ---------------------------------------------------------------------------
AKTIEN = [
    # --- DAX ---
    ("DE000A1EWWW0", "Adidas"), ("NL0000235190", "Airbus"), ("DE0008404005", "Allianz"),
    ("DE000BASF111", "BASF"), ("DE000BAY0017", "Bayer"), ("DE0005200000", "Beiersdorf"),
    ("DE0005190003", "BMW"), ("DE000A1DAHH0", "Brenntag"), ("DE000CBK1001", "Commerzbank"),
    ("DE0005439004", "Continental"), ("DE000DTR0CK8", "Daimler Truck"),
    ("DE0005140008", "Deutsche Bank"), ("DE0005810055", "Deutsche Börse"),
    ("DE0005552004", "DHL Group"), ("DE0005557508", "Deutsche Telekom"),
    ("DE000ENAG999", "E.ON"), ("DE0005785604", "Fresenius"),
    ("DE0005785802", "Fresenius Medical Care"), ("DE0008402215", "Hannover Rück"),
    ("DE0006047004", "Heidelberg Materials"), ("DE0006048432", "Henkel Vz"),
    ("DE0006231004", "Infineon"), ("DE0007100000", "Mercedes-Benz"),
    ("DE0006599905", "Merck KGaA"), ("DE000A0D9PT0", "MTU Aero Engines"),
    ("DE0008430026", "Münchener Rück"), ("DE000PAG9113", "Porsche AG"),
    ("DE000PAH0038", "Porsche SE"), ("NL0015001WM6", "Qiagen"),
    ("DE0007030009", "Rheinmetall"), ("DE0007037129", "RWE"), ("DE0007164600", "SAP"),
    ("DE0007165631", "Sartorius Vz"), ("DE0007236101", "Siemens"),
    ("DE000ENER6Y0", "Siemens Energy"), ("DE000SHL1006", "Siemens Healthineers"),
    ("DE000SYM9999", "Symrise"), ("DE0007664039", "Volkswagen Vz"),
    ("DE000A1ML7J1", "Vonovia"), ("DE000ZAL1111", "Zalando"), ("DE000A12DM80", "Scout24"),
    # --- MDAX (Auswahl) ---
    ("DE0006766504", "Aurubis"), ("DE0005158703", "Bechtle"),
    ("DE0005313704", "Carl Zeiss Meditec"), ("DE0005470306", "CTS Eventim"),
    ("DE000A2E4K43", "Delivery Hero"), ("DE000EVNK013", "Evonik"),
    ("DE0005773303", "Fraport"), ("DE000A0Z2ZZ5", "freenet"), ("DE000A3E5D64", "Fuchs Vz"),
    ("DE0006602006", "GEA Group"), ("DE000A161408", "HelloFresh"),
    ("DE000HAG0005", "Hensoldt"), ("DE0006070006", "Hochtief"), ("DE000A1PHFF7", "Hugo Boss"),
    ("DE0006219934", "Jungheinrich Vz"), ("DE000KSAG888", "K+S"), ("DE000KGX8881", "KION Group"),
    ("DE000KBX1006", "Knorr-Bremse"), ("DE0006335003", "Krones"), ("DE0005470405", "Lanxess"),
    ("DE000LEG1110", "LEG Immobilien"), ("DE0008232125", "Lufthansa"),
    ("DE0006452907", "Nemetschek"), ("DE000A0D6554", "Nordex"), ("DE0006969603", "Puma"),
    ("DE0007010803", "Rational"), ("DE000RENK730", "Renk Group"), ("DE000TLX1005", "Talanx"),
    ("DE0008303504", "TAG Immobilien"), ("DE0007500001", "thyssenkrupp"),
    ("DE000TRAT0N7", "Traton"), ("DE0005089031", "United Internet"),
    ("DE000WCH8881", "Wacker Chemie"), ("DE000A0WMPJ6", "Aixtron"), ("DE0005664809", "Evotec"),
    ("DE000A2YN900", "TeamViewer"), ("DE0007493991", "Ströer"), ("DE000A2LQ884", "Auto1 Group"),
    ("DE000STAB1L8", "Stabilus"), ("DE000A3E00M1", "Ionos Group"),
    ("NL0012044747", "Redcare Pharmacy"), ("DE0005909006", "Bilfinger"),
    ("DE000A0DJ6J9", "SMA Solar"), ("DE000DWS1007", "DWS Group"), ("DE0007231326", "Sixt"),
    ("DE0006305006", "Deutz"), ("DE0005104400", "Atoss Software"),
    # --- Euro Stoxx 50 (ohne deutsche Werte) ---
    ("NL0010273215", "ASML"), ("FR0000121014", "LVMH"), ("FR0000120271", "TotalEnergies"),
    ("FR0000120578", "Sanofi"), ("FR0000120321", "L'Oréal"),
    ("FR0000121972", "Schneider Electric"), ("FR0000120073", "Air Liquide"),
    ("FR0000052292", "Hermès"), ("FR0000131104", "BNP Paribas"), ("FR0000120628", "AXA"),
    ("ES0144580Y14", "Iberdrola"), ("ES0113900J37", "Banco Santander"), ("ES0113211835", "BBVA"),
    ("ES0148396007", "Inditex"), ("IT0003128367", "Enel"), ("IT0003132476", "Eni"),
    ("IT0000072618", "Intesa Sanpaolo"), ("IT0005239360", "UniCredit"),
    ("NL0011585146", "Ferrari"), ("NL00150001Q9", "Stellantis"), ("NL0013654783", "Prosus"),
    ("NL0011821202", "ING Groep"), ("NL0012969182", "Adyen"),
    ("NL0011794037", "Ahold Delhaize"), ("BE0974293251", "Anheuser-Busch InBev"),
    ("FI0009000681", "Nokia"), ("FI4000297767", "Nordea"), ("FR0000121485", "Kering"),
    ("FR0000120693", "Pernod Ricard"), ("FR0000073272", "Safran"), ("FR0000125486", "Vinci"),
    ("FR0000121667", "EssilorLuxottica"), ("FR0000120644", "Danone"),
    ("FR0000125007", "Saint-Gobain"), ("NL0000395903", "Wolters Kluwer"),
    ("NL0000009538", "Philips"),
    # --- Nasdaq-100 ---
    ("US0378331005", "Apple"), ("US5949181045", "Microsoft"), ("US67066G1040", "NVIDIA"),
    ("US0231351067", "Amazon"), ("US02079K3059", "Alphabet A"), ("US02079K1079", "Alphabet C"),
    ("US30303M1027", "Meta Platforms"), ("US88160R1014", "Tesla"), ("US11135F1012", "Broadcom"),
    ("US22160K1051", "Costco"), ("US64110L1061", "Netflix"), ("US0079031078", "AMD"),
    ("US7134481081", "PepsiCo"), ("US00724F1012", "Adobe"), ("US17275R1023", "Cisco"),
    ("US8725901040", "T-Mobile US"), ("US4581401001", "Intel"), ("US7475251036", "Qualcomm"),
    ("US8825081040", "Texas Instruments"), ("US4612021034", "Intuit"), ("US0311621009", "Amgen"),
    ("US0382221051", "Applied Materials"), ("US09857L1089", "Booking Holdings"),
    ("US4385161066", "Honeywell"), ("US20030N1019", "Comcast"),
    ("US46120E6023", "Intuitive Surgical"), ("US8552441094", "Starbucks"),
    ("US6092071058", "Mondelez"), ("US3755581036", "Gilead"), ("US92532F1003", "Vertex"),
    ("US0530151036", "ADP"), ("US5128073062", "Lam Research"), ("US5951121038", "Micron"),
    ("US6974351057", "Palo Alto Networks"), ("US0326541051", "Analog Devices"),
    ("US4824801009", "KLA"), ("US8716071076", "Synopsys"), ("US1273871087", "Cadence Design"),
    ("US75886F1075", "Regeneron"), ("US5738741041", "Marvell Technology"),
    ("US58733R1023", "MercadoLibre"), ("US22788C1053", "CrowdStrike"), ("US34959E1091", "Fortinet"),
    ("US70450Y1038", "PayPal"), ("US0090661010", "Airbnb"), ("US67103H1077", "O'Reilly Automotive"),
    ("US61174X1090", "Monster Beverage"), ("US1729081059", "Cintas"), ("US7043261079", "Paychex"),
    ("US7782961038", "Ross Stores"), ("US2172041061", "Copart"), ("US98138H1014", "Workday"),
    ("US0527691069", "Autodesk"), ("US5007541064", "Kraft Heinz"),
    ("US49271V1008", "Keurig Dr Pepper"), ("US7223041028", "PDD Holdings"),
    ("US23804L1035", "Datadog"), ("US98980G1022", "Zscaler"), ("US25809K1051", "DoorDash"),
    ("US69608A1088", "Palantir"), ("US0420682058", "Arm Holdings"), ("US03831W1080", "AppLovin"),
    ("US5949724083", "Strategy (MicroStrategy)"), ("US21037T1097", "Constellation Energy"),
    ("US30161N1019", "Exelon"), ("US98389B1008", "Xcel Energy"),
    ("US0255371017", "American Electric Power"), ("US1264081035", "CSX"),
    ("US6795801009", "Old Dominion Freight"), ("US3119001044", "Fastenal"), ("US6937181088", "Paccar"),
    ("US2521311074", "DexCom"), ("US45168D1046", "IDEXX"), ("US36266G1076", "GE HealthCare"),
    ("US09062X1037", "Biogen"), ("US2855121099", "Electronic Arts"),
    ("US8740541094", "Take-Two Interactive"), ("US88339J1051", "The Trade Desk"),
    ("US5950171042", "Microchip Technology"), ("NL0009538784", "NXP Semiconductors"),
    ("US6821891057", "ON Semiconductor"), ("US22160N1090", "CoStar Group"),
    ("US16119P1084", "Charter Communications"), ("US92345Y1064", "Verisk"),
    ("US5500211090", "Lululemon"), ("US25278X1090", "Diamondback Energy"),
    ("US05722G1004", "Baker Hughes"), ("US05464C1018", "Axon Enterprise"),
    ("CA82509L1076", "Shopify"), ("US0494681010", "Atlassian"), ("US7766961061", "Roper Technologies"),
    ("CA8849038085", "Thomson Reuters"),
    # --- S&P 500 (Schwergewichte ausserhalb des Nasdaq-100) ---
    ("US0846707026", "Berkshire Hathaway B"), ("US46625H1005", "JPMorgan Chase"),
    ("US5324571083", "Eli Lilly"), ("US92826C8394", "Visa"), ("US91324P1021", "UnitedHealth"),
    ("US30231G1022", "Exxon Mobil"), ("US57636Q1040", "Mastercard"),
    ("US4781601046", "Johnson & Johnson"), ("US7427181091", "Procter & Gamble"),
    ("US4370761029", "Home Depot"), ("US9311421039", "Walmart"), ("US00287Y1091", "AbbVie"),
    ("US58933Y1055", "Merck & Co"), ("US68389X1054", "Oracle"), ("US1667641005", "Chevron"),
    ("US1912161007", "Coca-Cola"), ("US0605051046", "Bank of America"),
    ("US79466L3024", "Salesforce"), ("US8835561023", "Thermo Fisher"),
    ("US5801351017", "McDonald's"), ("US0028241000", "Abbott Laboratories"),
    ("US9497461015", "Wells Fargo"), ("IE00B4BNMY34", "Accenture"), ("US2358511028", "Danaher"),
    ("IE000S9YS762", "Linde"), ("US4592001014", "IBM"), ("US3696043013", "GE Aerospace"),
    ("US1491231015", "Caterpillar"), ("US92343V1044", "Verizon"), ("US7170811035", "Pfizer"),
    ("US7181721090", "Philip Morris"), ("US2546871060", "Walt Disney"),
    ("US38141G1040", "Goldman Sachs"), ("US6174464486", "Morgan Stanley"),
    ("US0258161092", "American Express"), ("US75513E1010", "RTX"),
    ("US78409V1044", "S&P Global"), ("US9078181081", "Union Pacific"), ("US6541061031", "Nike"),
    ("US5486611073", "Lowe's"), ("US0970231058", "Boeing"), ("US90353T1007", "Uber"),
    ("US09290D1019", "BlackRock"), ("US2441991054", "Deere"), ("US5398301094", "Lockheed Martin"),
    ("US8636671013", "Stryker"), ("IE00BTN1Y115", "Medtronic"), ("US1729674242", "Citigroup"),
    ("US00206R1023", "AT&T"), ("US8085131055", "Charles Schwab"), ("US7433151039", "Progressive"),
    ("CH0044328745", "Chubb"), ("US5717481023", "Marsh McLennan"), ("US0367521038", "Elevance Health"),
    ("US1255231003", "Cigna"), ("US1011371077", "Boston Scientific"), ("US81762P1021", "ServiceNow"),
    ("US1101221083", "Bristol-Myers Squibb"), ("US9113121068", "UPS"), ("US8425871071", "Southern Co"),
    ("US26441C2044", "Duke Energy"), ("US65339F1012", "NextEra Energy"), ("US88579Y1010", "3M"),
    ("US02209S1033", "Altria"), ("US1941621039", "Colgate-Palmolive"),
    ("US94106L1098", "Waste Management"), ("US8243481061", "Sherwin-Williams"),
    ("US98978V1035", "Zoetis"), ("US1266501006", "CVS Health"), ("US6153691059", "Moody's"),
    ("US29444U7000", "Equinix"), ("US74340W1036", "Prologis"), ("US03027X1000", "American Tower"),
    ("US6668071029", "Northrop Grumman"), ("US3695501086", "General Dynamics"),
    ("US31428X1063", "FedEx"), ("US87612E1064", "Target"), ("AN8068571086", "SLB (Schlumberger)"),
    ("US20825C1045", "ConocoPhillips"), ("US26875P1012", "EOG Resources"), ("US48251W1045", "KKR"),
    ("US09260D1072", "Blackstone"), ("US0404132054", "Arista Networks"),
    ("US24703L2025", "Dell Technologies"), ("US92537N1081", "Vertiv"), ("IE00B8KQN827", "Eaton"),
    ("US7010941042", "Parker-Hannifin"), ("IE00BK9ZQ967", "Trane Technologies"),
    ("US4432011082", "Howmet Aerospace"), ("US36828A1016", "GE Vernova"),
    ("US45866F1049", "Intercontinental Exchange"), ("US12572Q1058", "CME Group"),
    ("US6934751057", "PNC Financial"), ("US9029733048", "U.S. Bancorp"),
    ("US14040H1059", "Capital One"), ("US19260Q1076", "Coinbase"), ("US7707001027", "Robinhood"),
    ("LU1778762911", "Spotify"),
]

# ---------------------------------------------------------------------------
# DIVIDENDEN-AKTIEN: bekannte Hochdividendenwerte und Dividenden-Aristokraten.
# Hinweis: die Ranglisten messen die KURS-Performance - ausgeschuettete
# Dividenden sind darin NICHT enthalten (die Kursquelle liefert keine
# Dividendendaten). Die Liste waehlt die Werte aus, die Rangfolge ergibt
# sich aus der Kursentwicklung.
# ---------------------------------------------------------------------------
DIVIDENDEN = [
    ("DE0008404005", "Allianz"), ("DE0008430026", "Münchener Rück"),
    ("DE0008402215", "Hannover Rück"), ("DE000TLX1005", "Talanx"), ("DE000BASF111", "BASF"),
    ("DE0007100000", "Mercedes-Benz"), ("DE0005190003", "BMW"),
    ("DE0005557508", "Deutsche Telekom"), ("DE0005552004", "DHL Group"),
    ("DE000ENAG999", "E.ON"), ("DE000PAH0038", "Porsche SE"), ("DE0007664039", "Volkswagen Vz"),
    ("DE000A0Z2ZZ5", "freenet"), ("DE000DWS1007", "DWS Group"),
    ("FR0000120271", "TotalEnergies"), ("GB00BP6MXD84", "Shell"), ("GB0007980591", "BP"),
    ("GB0002875804", "British American Tobacco"), ("GB0004544929", "Imperial Brands"),
    ("GB00B10RZP78", "Unilever"), ("CH0038863350", "Nestlé"), ("CH0012005267", "Novartis"),
    ("CH0012032048", "Roche Genussschein"), ("CH0011075394", "Zurich Insurance"),
    ("CH0126881561", "Swiss Re"), ("FR0000120578", "Sanofi"), ("FR0000120628", "AXA"),
    ("IT0003128367", "Enel"), ("IT0003132476", "Eni"), ("IT0000072618", "Intesa Sanpaolo"),
    ("ES0144580Y14", "Iberdrola"), ("FR0010208488", "Engie"), ("FR0000133308", "Orange"),
    ("GB0005603997", "Legal & General"), ("GB00BPQY8M80", "Aviva"),
    ("GB00BDR05C01", "National Grid"), ("GB0007188757", "Rio Tinto"),
    ("NO0010096985", "Equinor"), ("ES0178430E18", "Telefónica"),
    ("US7561091049", "Realty Income"), ("US02209S1033", "Altria"),
    ("US7181721090", "Philip Morris"), ("US92343V1044", "Verizon"), ("US00206R1023", "AT&T"),
    ("US7170811035", "Pfizer"), ("US00287Y1091", "AbbVie"), ("US4781601046", "Johnson & Johnson"),
    ("US1912161007", "Coca-Cola"), ("US7134481081", "PepsiCo"), ("US7427181091", "Procter & Gamble"),
    ("US88579Y1010", "3M"), ("US4592001014", "IBM"), ("US1667641005", "Chevron"),
    ("US30231G1022", "Exxon Mobil"), ("CA29250N1050", "Enbridge"), ("CA87807B1076", "TC Energy"),
    ("US56035L1044", "Main Street Capital"), ("US04010L1035", "Ares Capital"),
    ("US92936U1097", "W. P. Carey"), ("US4943681035", "Kimberly-Clark"),
    ("US3703341046", "General Mills"), ("US87612E1064", "Target"), ("US5801351017", "McDonald's"),
    ("US4370761029", "Home Depot"), ("US8825081040", "Texas Instruments"),
    ("US11135F1012", "Broadcom"), ("IE00BTN1Y115", "Medtronic"), ("US9113121068", "UPS"),
    ("US2605571031", "Dow"), ("NL0009434992", "LyondellBasell"),
    ("US7443201022", "Prudential Financial"), ("US59156R1086", "MetLife"),
    ("US26441C2044", "Duke Energy"), ("US8425871071", "Southern Co"),
    ("US25746U1097", "Dominion Energy"),
]

# ---------------------------------------------------------------------------
# ETFs inkl. Hebel-ETFs (Leverage)
# ---------------------------------------------------------------------------
ETFS = [
    # --- Breite Markt-ETFs ---
    ("IE00B4L5Y983", "iShares Core MSCI World"), ("IE00BK5BQT80", "Vanguard FTSE All-World"),
    ("IE00B5BMR087", "iShares Core S&P 500"), ("IE00B53SZB19", "iShares Nasdaq 100"),
    ("IE00BFZXGZ54", "Invesco EQQQ Nasdaq-100"), ("IE00BKM4GZ66", "iShares Core MSCI EM IMI"),
    ("DE0005933931", "iShares Core DAX"), ("IE00BJ0KDQ92", "Xtrackers MSCI World"),
    ("IE00B3YLTY66", "SPDR MSCI ACWI IMI"), ("IE00B4K48X80", "iShares Core MSCI Europe"),
    ("IE0008471009", "iShares Core Euro Stoxx 50"), ("IE00B945VV12", "Vanguard FTSE Dev. Europe"),
    ("IE00BZCQB185", "iShares MSCI India"), ("IE00B4L5YX21", "iShares Core MSCI Japan"),
    ("DE0006289382", "iShares Dow Jones Global Titans 50"), ("LU0274211480", "Xtrackers DAX"),
    ("IE00BP3QZ825", "iShares MSCI World Momentum"), ("IE00BP3QZ601", "iShares MSCI World Quality"),
    # --- Branchen / Themen ---
    ("IE00BM67HT60", "Xtrackers MSCI World IT"), ("IE00B3WJKG14", "iShares S&P 500 IT Sector"),
    ("IE00BMC38736", "VanEck Semiconductor"), ("LU1900066033", "Amundi MSCI Semiconductors"),
    ("IE00B1XNHC34", "iShares Global Clean Energy"), ("IE00BYZK4552", "iShares Automation & Robotics"),
    ("IE00BYZK4776", "iShares Healthcare Innovation"), ("IE000YYE6WK5", "VanEck Defense"),
    ("IE0002Y8CX98", "WisdomTree Europe Defence"), ("IE000NDWFGA5", "Global X Uranium"),
    # --- Rohstoffe / Krypto (ETC/ETP) ---
    ("DE000A0S9GB0", "Xetra-Gold"), ("DE000EWG2LD7", "EUWAX Gold II"),
    ("IE00B4ND3602", "iShares Physical Gold"), ("IE00B579F325", "Invesco Physical Gold"),
    ("CH0454664001", "21Shares Bitcoin"), ("GB00BJYDH287", "WisdomTree Physical Bitcoin"),
    # --- Hebel-ETFs (Leverage) ---
    ("FR0010342592", "Amundi Nasdaq-100 Daily 2x Leveraged"),
    ("FR0010755611", "Amundi MSCI USA Daily 2x Leveraged"),
    ("LU0252634307", "Amundi LevDAX Daily 2x"), ("LU0411075376", "Xtrackers LevDAX Daily Swap"),
    ("LU0411078552", "Xtrackers S&P 500 2x Leveraged Daily Swap"),
    ("IE00BLRPRL42", "WisdomTree Nasdaq 100 3x Daily Leveraged"),
    ("IE00B7Y34M31", "WisdomTree S&P 500 3x Daily Leveraged"),
    ("FR0010468983", "Amundi Euro Stoxx 50 Daily 2x Leveraged"),
]

# Kategorien, wie sie in der App erscheinen. "quelle" = Liste oben oder "auto"
# (automatische Suche). "kategorien_ls" = erlaubte categoryName-Werte der
# Kursquelle - schuetzt davor, bei der Namenssuche z.B. eine Anleihe
# ("APPLE 14/26") statt der Aktie zu erwischen.
KATEGORIEN = {
    "aktien":     {"titel": "Aktien",               "quelle": AKTIEN,     "kategorien_ls": {"Aktie"}},
    "dividenden": {"titel": "Dividenden-Aktien",    "quelle": DIVIDENDEN, "kategorien_ls": {"Aktie"}},
    "etf":        {"titel": "ETFs & Hebel-ETFs",    "quelle": ETFS,
                   "kategorien_ls": {"ETF", "ETC", "ETN", "ETP", "Fonds"}},
    "wikifolios": {"titel": "wikifolios",           "quelle": "auto",     "kategorien_ls": {"Wikifolio"}},
}

# Zeitraeume der Ranglisten: (Schluessel, Anzeige, Kalendertage).
# "1T" nutzt die letzten beiden Handelstage statt Kalendertagen.
ZEITRAEUME = [
    ("1T", "Tag", 1), ("1W", "Woche", 7), ("1M", "Monat", 30), ("3M", "3 Monate", 91),
    ("6M", "6 Monate", 182), ("9M", "9 Monate", 273), ("1J", "1 Jahr", 365),
    ("2J", "2 Jahre", 730), ("3J", "3 Jahre", 1095), ("5J", "5 Jahre", 1826),
    ("10J", "10 Jahre", 3652),
]

TOP_N = 50
