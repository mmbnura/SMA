# tickers.py — ~160 NSE stocks across major Nifty 500 sectors
# Format: (yfinance_ticker, display_name, sector)

NIFTY500_STOCKS = [
    # ── IT ────────────────────────────────────────────────────────────────
    ("TCS.NS",        "TCS",                    "IT"),
    ("INFY.NS",       "Infosys",                "IT"),
    ("WIPRO.NS",      "Wipro",                  "IT"),
    ("HCLTECH.NS",    "HCL Technologies",        "IT"),
    ("TECHM.NS",      "Tech Mahindra",           "IT"),
    ("LTIM.NS",       "LTIMindtree",             "IT"),
    ("MPHASIS.NS",    "Mphasis",                 "IT"),
    ("PERSISTENT.NS", "Persistent Systems",      "IT"),
    ("COFORGE.NS",    "Coforge",                 "IT"),
    ("OFSS.NS",       "Oracle Fin. Services",    "IT"),

    # ── Banking ────────────────────────────────────────────────────────────
    ("HDFCBANK.NS",   "HDFC Bank",               "Banking"),
    ("ICICIBANK.NS",  "ICICI Bank",              "Banking"),
    ("SBIN.NS",       "State Bank of India",     "Banking"),
    ("KOTAKBANK.NS",  "Kotak Mahindra Bank",     "Banking"),
    ("AXISBANK.NS",   "Axis Bank",               "Banking"),
    ("INDUSINDBK.NS", "IndusInd Bank",           "Banking"),
    ("BANDHANBNK.NS", "Bandhan Bank",            "Banking"),
    ("FEDERALBNK.NS", "Federal Bank",            "Banking"),
    ("IDFCFIRSTB.NS", "IDFC First Bank",         "Banking"),
    ("CANBK.NS",      "Canara Bank",             "Banking"),
    ("BANKBARODA.NS", "Bank of Baroda",          "Banking"),
    ("PNB.NS",        "Punjab National Bank",    "Banking"),
    ("UNIONBANK.NS",  "Union Bank of India",     "Banking"),
    ("KARURVYSYA.NS", "Karur Vysya Bank",        "Banking"),

    # ── NBFC ───────────────────────────────────────────────────────────────
    ("BAJFINANCE.NS", "Bajaj Finance",           "NBFC"),
    ("BAJAJFINSV.NS", "Bajaj Finserv",           "NBFC"),
    ("CHOLAFIN.NS",   "Cholamandalam Finance",   "NBFC"),
    ("MUTHOOTFIN.NS", "Muthoot Finance",         "NBFC"),
    ("SHRIRAMFIN.NS", "Shriram Finance",         "NBFC"),
    ("LICIHSGFIN.NS", "LIC Housing Finance",     "NBFC"),

    # ── Energy & Power ─────────────────────────────────────────────────────
    ("RELIANCE.NS",   "Reliance Industries",     "Energy"),
    ("ONGC.NS",       "ONGC",                    "Energy"),
    ("IOC.NS",        "Indian Oil Corp",         "Energy"),
    ("BPCL.NS",       "BPCL",                    "Energy"),
    ("HINDPETRO.NS",  "HPCL",                    "Energy"),
    ("GAIL.NS",       "GAIL India",              "Energy"),
    ("POWERGRID.NS",  "Power Grid Corp",         "Energy"),
    ("NTPC.NS",       "NTPC",                    "Energy"),
    ("TATAPOWER.NS",  "Tata Power",              "Energy"),
    ("ADANIGREEN.NS", "Adani Green Energy",      "Energy"),
    ("TORNTPOWER.NS", "Torrent Power",           "Energy"),
    ("COALINDIA.NS",  "Coal India",              "Energy"),
    ("ADANIPORTS.NS", "Adani Ports",             "Infrastructure"),

    # ── FMCG ───────────────────────────────────────────────────────────────
    ("HINDUNILVR.NS", "Hindustan Unilever",      "FMCG"),
    ("ITC.NS",        "ITC",                     "FMCG"),
    ("NESTLEIND.NS",  "Nestle India",            "FMCG"),
    ("BRITANNIA.NS",  "Britannia Industries",    "FMCG"),
    ("DABUR.NS",      "Dabur India",             "FMCG"),
    ("MARICO.NS",     "Marico",                  "FMCG"),
    ("GODREJCP.NS",   "Godrej Consumer Products","FMCG"),
    ("COLPAL.NS",     "Colgate-Palmolive India", "FMCG"),
    ("EMAMILTD.NS",   "Emami",                   "FMCG"),
    ("VBL.NS",        "Varun Beverages",         "FMCG"),
    ("TATACONSUM.NS", "Tata Consumer Products",  "FMCG"),
    ("UBL.NS",        "United Breweries",        "FMCG"),

    # ── Pharma ─────────────────────────────────────────────────────────────
    ("SUNPHARMA.NS",  "Sun Pharma",              "Pharma"),
    ("DRREDDY.NS",    "Dr. Reddy's",             "Pharma"),
    ("CIPLA.NS",      "Cipla",                   "Pharma"),
    ("DIVISLAB.NS",   "Divi's Labs",             "Pharma"),
    ("AUROPHARMA.NS", "Aurobindo Pharma",        "Pharma"),
    ("LUPIN.NS",      "Lupin",                   "Pharma"),
    ("ALKEM.NS",      "Alkem Labs",              "Pharma"),
    ("TORNTPHARM.NS", "Torrent Pharma",          "Pharma"),
    ("GLENMARK.NS",   "Glenmark Pharma",         "Pharma"),
    ("IPCALAB.NS",    "IPCA Labs",               "Pharma"),
    ("ABBOTINDIA.NS", "Abbott India",            "Pharma"),

    # ── Auto ───────────────────────────────────────────────────────────────
    ("MARUTI.NS",     "Maruti Suzuki",           "Auto"),
    ("TATAMOTORS.NS", "Tata Motors",             "Auto"),
    ("M&M.NS",        "Mahindra & Mahindra",     "Auto"),
    ("BAJAJ-AUTO.NS", "Bajaj Auto",              "Auto"),
    ("HEROMOTOCO.NS", "Hero MotoCorp",           "Auto"),
    ("EICHERMOT.NS",  "Eicher Motors",           "Auto"),
    ("TVSMOTOR.NS",   "TVS Motor",               "Auto"),
    ("ASHOKLEY.NS",   "Ashok Leyland",           "Auto"),
    ("BALKRISIND.NS", "Balkrishna Industries",   "Auto"),
    ("MRF.NS",        "MRF",                     "Auto"),
    ("APOLLOTYRE.NS", "Apollo Tyres",            "Auto"),
    ("BOSCHLTD.NS",   "Bosch India",             "Auto"),

    # ── Metals & Mining ────────────────────────────────────────────────────
    ("TATASTEEL.NS",  "Tata Steel",              "Metals"),
    ("HINDALCO.NS",   "Hindalco Industries",     "Metals"),
    ("JSWSTEEL.NS",   "JSW Steel",               "Metals"),
    ("VEDL.NS",       "Vedanta",                 "Metals"),
    ("NMDC.NS",       "NMDC",                    "Metals"),
    ("SAIL.NS",       "SAIL",                    "Metals"),
    ("NATIONALUM.NS", "NALCO",                   "Metals"),
    ("HINDZINC.NS",   "Hindustan Zinc",          "Metals"),
    ("APLAPOLLO.NS",  "APL Apollo Tubes",        "Metals"),

    # ── Cement ─────────────────────────────────────────────────────────────
    ("ULTRACEMCO.NS", "UltraTech Cement",        "Cement"),
    ("SHREECEM.NS",   "Shree Cement",            "Cement"),
    ("AMBUJACEM.NS",  "Ambuja Cements",          "Cement"),
    ("ACC.NS",        "ACC",                     "Cement"),
    ("RAMCOCEM.NS",   "Ramco Cements",           "Cement"),
    ("JKCEMENT.NS",   "JK Cement",              "Cement"),

    # ── Telecom ────────────────────────────────────────────────────────────
    ("BHARTIARTL.NS", "Bharti Airtel",           "Telecom"),

    # ── Real Estate ────────────────────────────────────────────────────────
    ("DLF.NS",        "DLF",                     "Real Estate"),
    ("GODREJPROP.NS", "Godrej Properties",       "Real Estate"),
    ("OBEROIRLTY.NS", "Oberoi Realty",           "Real Estate"),
    ("PRESTIGE.NS",   "Prestige Estates",        "Real Estate"),
    ("PHOENIXLTD.NS", "Phoenix Mills",           "Real Estate"),
    ("SOBHA.NS",      "Sobha",                   "Real Estate"),

    # ── Healthcare ─────────────────────────────────────────────────────────
    ("APOLLOHOSP.NS", "Apollo Hospitals",        "Healthcare"),
    ("FORTIS.NS",     "Fortis Healthcare",       "Healthcare"),
    ("MAXHEALTH.NS",  "Max Healthcare",          "Healthcare"),
    ("METROPOLIS.NS", "Metropolis Healthcare",   "Healthcare"),
    ("LALPATHLAB.NS", "Dr. Lal PathLabs",        "Healthcare"),
    ("ASTERDM.NS",    "Aster DM Healthcare",     "Healthcare"),

    # ── Consumer Durables ──────────────────────────────────────────────────
    ("TITAN.NS",      "Titan Company",           "Consumer Durables"),
    ("HAVELLS.NS",    "Havells India",           "Consumer Durables"),
    ("VOLTAS.NS",     "Voltas",                  "Consumer Durables"),
    ("BLUESTARCO.NS", "Blue Star",               "Consumer Durables"),
    ("CROMPTON.NS",   "Crompton Greaves Consumer","Consumer Durables"),
    ("POLYCAB.NS",    "Polycab India",           "Consumer Durables"),
    ("AMBER.NS",      "Amber Enterprises",       "Consumer Durables"),
    ("DIXON.NS",      "Dixon Technologies",      "Consumer Durables"),
    ("KAJARIACER.NS", "Kajaria Ceramics",        "Consumer Durables"),

    # ── Capital Goods ──────────────────────────────────────────────────────
    ("LT.NS",         "Larsen & Toubro",         "Capital Goods"),
    ("SIEMENS.NS",    "Siemens India",           "Capital Goods"),
    ("ABB.NS",        "ABB India",               "Capital Goods"),
    ("BEL.NS",        "Bharat Electronics",      "Capital Goods"),
    ("HAL.NS",        "Hindustan Aeronautics",   "Capital Goods"),
    ("BHEL.NS",       "BHEL",                    "Capital Goods"),
    ("CUMMINSIND.NS", "Cummins India",           "Capital Goods"),
    ("THERMAX.NS",    "Thermax",                 "Capital Goods"),
    ("CGPOWER.NS",    "CG Power",                "Capital Goods"),
    ("KEC.NS",        "KEC International",       "Capital Goods"),

    # ── Chemicals ──────────────────────────────────────────────────────────
    ("PIDILITIND.NS", "Pidilite Industries",     "Chemicals"),
    ("SRF.NS",        "SRF",                     "Chemicals"),
    ("DEEPAKNTR.NS",  "Deepak Nitrite",          "Chemicals"),
    ("AARTIIND.NS",   "Aarti Industries",        "Chemicals"),
    ("NAVINFLUOR.NS", "Navin Fluorine",          "Chemicals"),
    ("VINATIORGA.NS", "Vinati Organics",         "Chemicals"),
    ("TATACHEM.NS",   "Tata Chemicals",          "Chemicals"),

    # ── Paints ─────────────────────────────────────────────────────────────
    ("ASIANPAINT.NS", "Asian Paints",            "Paints"),
    ("BERGEPAINT.NS", "Berger Paints",           "Paints"),
    ("KANSAINER.NS",  "Kansai Nerolac",          "Paints"),
    ("AKZOINDIA.NS",  "Akzo Nobel India",        "Paints"),

    # ── Insurance ──────────────────────────────────────────────────────────
    ("HDFCLIFE.NS",   "HDFC Life Insurance",     "Insurance"),
    ("SBILIFE.NS",    "SBI Life Insurance",      "Insurance"),
    ("ICICIGI.NS",    "ICICI Lombard GI",        "Insurance"),
    ("ICICIPRULI.NS", "ICICI Prudential Life",   "Insurance"),
    ("LICI.NS",       "LIC India",               "Insurance"),
    ("STARHEALTH.NS", "Star Health Insurance",   "Insurance"),

    # ── Financial Services ─────────────────────────────────────────────────
    ("BSE.NS",        "BSE Ltd",                 "Financial Services"),
    ("MCX.NS",        "MCX India",               "Financial Services"),
    ("CDSL.NS",       "CDSL",                    "Financial Services"),
    ("ANGELONE.NS",   "Angel One",               "Financial Services"),

    # ── Internet / Fintech ─────────────────────────────────────────────────
    ("NAUKRI.NS",     "Info Edge (Naukri)",      "Internet"),
    ("ZOMATO.NS",     "Zomato",                  "Internet"),
    ("POLICYBZR.NS",  "PB Fintech",              "Fintech"),

    # ── Retail ─────────────────────────────────────────────────────────────
    ("DMART.NS",      "Avenue Supermarts",       "Retail"),
    ("TRENT.NS",      "Trent",                   "Retail"),
    ("PAGEIND.NS",    "Page Industries",         "Retail"),

    # ── Aviation ───────────────────────────────────────────────────────────
    ("INDIGO.NS",     "IndiGo (InterGlobe)",     "Aviation"),

    # ── Media ──────────────────────────────────────────────────────────────
    ("SUNTV.NS",      "Sun TV Network",          "Media"),
    ("PVRINOX.NS",    "PVR Inox",                "Media"),

    # ── Hotels ─────────────────────────────────────────────────────────────
    ("INDHOTEL.NS",   "Indian Hotels (Taj)",     "Hotels"),
    ("LEMONTREE.NS",  "Lemon Tree Hotels",       "Hotels"),

    # ── Agri / Fertilizers ─────────────────────────────────────────────────
    ("UPL.NS",        "UPL",                     "Agri"),
    ("COROMANDEL.NS", "Coromandel International","Agri"),
    ("PIIND.NS",      "PI Industries",           "Agri"),
    ("CHAMBLFERT.NS", "Chambal Fertilizers",     "Agri"),

    # ── Logistics ──────────────────────────────────────────────────────────
    ("DELHIVERY.NS",  "Delhivery",               "Logistics"),
    ("BLUEDART.NS",   "Blue Dart Express",       "Logistics"),

    # ── Textiles ───────────────────────────────────────────────────────────
    ("RAYMOND.NS",    "Raymond",                 "Textiles"),
    ("VARDHMAN.NS",   "Vardhman Textiles",       "Textiles"),
    ("WELSPUNIND.NS", "Welspun India",           "Textiles"),
]

# Helper: list of sectors
ALL_SECTORS = sorted(set(s for _, _, s in NIFTY500_STOCKS))

# Sectors where high D/E is structurally normal — skip D/E scoring
FINANCIAL_SECTORS = {"Banking", "NBFC", "Insurance", "Financial Services"}
