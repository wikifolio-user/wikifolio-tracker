"""Investoren-Checks: prueft eine Aktie nach den Kriterien bekannter Investoren und Modelle.

Registry: jeder Check meldet sich mit @registriere an und ist eine Funktion (fakten, kontext) -> Ergebnis
(Format siehe basis.ergebnis). Neue Checks: Datei in diesem Paket anlegen, Funktion mit @registriere
versehen und unten in MODULE eintragen.

fakten  = normierte Rohdaten einer Aktie (siehe daten.py)
kontext = Vergleichsdaten der Top-500-Liste (Raenge fuer Greenblatt/Dreman), Konfiguration, Schalter
"""
import importlib
import logging

REGISTRY = {}       # id -> {"fn", "investor", "kategorie", "reihenfolge"}


def registriere(cid, investor, kategorie, reihenfolge=50):
    def deko(fn):
        REGISTRY[cid] = {"fn": fn, "investor": investor, "kategorie": kategorie, "reihenfolge": reihenfolge}
        return fn
    return deko


MODULE = ["graham", "buffett", "greenblatt", "dreman", "templeton", "fisher_kuv", "terry_smith",
          "philip_fisher", "piotroski", "altman", "beneish", "red_flags", "lynch", "can_slim", "minervini", "levy",
          "dividende", "smart_money"]
for _m in MODULE:
    importlib.import_module(f"{__name__}.{_m}")


def alle_checks(fakten, kontext=None):
    """Fuehrt alle registrierten Checks aus. Ein fehlerhafter Check bricht die anderen nicht ab."""
    kontext = kontext or {}
    aus = []
    for cid, r in sorted(REGISTRY.items(), key=lambda kv: kv[1]["reihenfolge"]):
        try:
            aus.append(r["fn"](fakten, kontext))
        except Exception as e:      # robust: ein Check darf die Seite nie zerlegen
            logging.exception("Investoren-Check %s", cid)
            aus.append({"id": cid, "investor": r["investor"], "strategie": "", "kategorie": r["kategorie"],
                        "kriterien": [], "erfuellt": 0, "gesamt": 0, "anzahl": 0, "score_0_100": None,
                        "fazit": f"Nicht berechenbar ({type(e).__name__}).", "extras": [], "warnungen": [],
                        "badges": [], "ausgeblendet": [], "datenbasis": "", "sektor_typ": "", "kauf": False,
                        "info": ""})
    return aus
