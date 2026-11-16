import login
def seed(f):
    f.seed("state/benutzer.json", {"benutzer": {
        "anna.b": {"hash": login.passwort_hash("Anna-Punkt-Pass-1"), "aktiv": True, "ansichten": None},
        "anna-b": {"hash": login.passwort_hash("Anna-Strich-Pass-1"), "aktiv": True, "ansichten": None},
        "leser":  {"hash": login.passwort_hash("Leser-Pass-123"), "aktiv": True, "ansichten": ["🧮 Zinseszinsrechner"]},
    }})
    # Startseite: Ueberblick-Kacheln (Alarm, Chronik, EKS)
    f.seed("state/trades_db.json", [
        {"id": 2, "datum": "2026-11-16", "zeit": "09:25", "kategorie": "alarm", "typ": "Alarme & Hochs",
         "titel": "🚨 Schwelle unterschritten Test AG (A1B2C3)", "inhalt": "", "quelle": "auto"},
        {"id": 1, "datum": "2026-11-15", "zeit": "18:02", "kategorie": "depot", "typ": "Depot",
         "titel": "➕ Position angelegt: Test AG (A1B2C3)", "inhalt": "", "quelle": "auto"}])
    from eks_rechner import modell as M
    eks = M.leer()
    eks["ideen"].append(M.neue_idee("Testidee", eks["einstellungen"]))
    f.seed("state/eks_ideen.json", eks)
