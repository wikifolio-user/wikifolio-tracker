import login
def seed(f):
    f.seed("state/benutzer.json", {"benutzer": {
        "anna.b": {"hash": login.passwort_hash("Anna-Punkt-Pass-1"), "aktiv": True, "ansichten": None},
        "anna-b": {"hash": login.passwort_hash("Anna-Strich-Pass-1"), "aktiv": True, "ansichten": None},
        "leser":  {"hash": login.passwort_hash("Leser-Pass-123"), "aktiv": True, "ansichten": ["🧮 Zinseszinsrechner"]},
    }})
